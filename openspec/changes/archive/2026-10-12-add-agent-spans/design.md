# Design

## Context

- The tracing pipeline exists (`app-tracing`, `add-langfuse-trace-export`). `core/telemetry.py` registers a global SDK `TracerProvider` when `TELEMETRY__ENABLED=true`. FastAPI emits the SERVER span, `HTTPX2ClientInstrumentor` emits the CLIENT span for each LLM HTTP call, and the Collector forwards everything to Langfuse 4.53. With tracing off, the global provider stays the no-op default.
- The graph (`agents/attendant/graph.py`) is `START → call_model → (tools → call_model)* → END`. `call_model` is our own node (`nodes.py`). `tools` is LangGraph's prebuilt `ToolNode`, which runs the calls of one model answer concurrently. In `langgraph` 1.2.14 / `langgraph-prebuilt` 1.1.0, `ToolNode(..., awrap_tool_call=...)` accepts an async wrapper that receives a `ToolCallRequest` (`tool_call`, `tool`, `state`, `runtime`) and a handler that returns the `ToolMessage`.
- Every tool sets `handle_tool_error = True`, so a `ToolException` (domain errors and our generic internal error) becomes a `ToolMessage` with `status="error"` inside the tool. Invalid arguments from the LLM become an error `ToolMessage` through `ToolNode`'s default handler. In both cases no exception reaches the wrapper.
- `GraphAttendant.reply(conversation_id, text)` is the turn boundary. The conversation id is the LangGraph `thread_id` in the run config. `escalate_to_human` already reads it from `runtime.config`.
- The prompt version comes from `SystemPrompt.version`. `call_model` stores it on each answer and in the turn output (`prompt-versioning`).
- GenAI semconv moved to `open-telemetry/semantic-conventions-genai` (read at commit `6fd0d76`, 2026-10-09; every attribute still has development status):
  - `invoke_agent`: for an in-process agent, the "internal" variant applies (kind INTERNAL). The name is `invoke_agent {gen_ai.agent.name}`. Unlike the CLIENT variant (remote agents), its attribute table has no `gen_ai.provider.name`, and `gen_ai.request.model` is only recommended "if applicable".
  - Inference: name `{operation} {request.model}`, kind CLIENT.
  - `execute_tool`: name `execute_tool {tool.name}`, kind INTERNAL.
  - `gen_ai.conversation.id` is conditionally required when the app has one.
  - Usage, response and finish-reason attributes are recommended.
  - Span status follows the general "Recording Errors" rules, with `error.type` set to a low-cardinality value.
- Langfuse OTel mapping:
  - `session.id` or `langfuse.session.id` on any span sets the trace's `sessionId`. `gen_ai.conversation.id` is not mapped to a session.
  - The model comes from `gen_ai.request.model` or `gen_ai.response.model`, usage from `gen_ai.usage.*`.
  - Langfuse computes cost only for `generation` observations. Usage buckets must be mutually exclusive.
  - The observation type is inferred from conventions, then from a model attribute.
  - Unmapped attributes land in `metadata.attributes`.
- Existing unit tests (`tests/unit/test_tracing.py`) register one in-memory exporter on the process-wide provider, once per session, because the global provider can be set only once.

## Goals / Non-Goals

**Goals:**
- Spans by hand, with exactly the attributes in the `agent-tracing` spec, written against the current GenAI registry.
- Langfuse shows each turn as agent → generations and tools, with cost per generation and all turns of a conversation in one session.
- Telemetry code stays out of the agent's control flow. Removing tracing must not change replies or side effects.

**Non-Goals:**
- Content capture (`gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `gen_ai.tool.call.arguments`/`result`, `gen_ai.tool.definitions`). It needs redaction first: the Collector in step B, Presidio in phase 6. Phase 3 will want to read message content in Langfuse; that is a separate, explicit change.
- Metrics (`gen_ai.client.token.usage`, `gen_ai.client.operation.duration`) and logs correlation: step B.
- `langfuse.*` attributes (observation type, `langfuse.version`, metadata promotion) in app code. If Langfuse misreads a type, step B's Collector can rewrite it with a `transform` processor.
- Tracing in `apps/chat` or the simulator.
- Changing the graph shape, the prompt or the tools' behavior.

## Decisions

### 1. Spans by hand, not a LangChain instrumentation library

The tracer API (`opentelemetry.trace`) is used directly in the agent package.

- *Traceloop `opentelemetry-instrumentation-langchain` 0.62.4* (the PyPI name looks official but is OpenLLMetry's). It already names spans `invoke_agent`/`execute_tool` and uses many current `gen_ai.*` attributes. Rejected:
  - It builds its own span tree through LangChain callbacks and LangGraph patches, with a span per node, chain and middleware hook, plus `goto` and `execute_task` spans. The waterfall would show LangChain's runnables, not our graph.
  - It adds `traceloop.*` attributes.
  - It records prompts and completions by default (`TRACELOOP_TRACE_CONTENT` defaults to `true`), so customer text would reach Langfuse unredacted.
  - Our prompt version and session id would still need custom code on top.
- *OpenInference `openinference-instrumentation-langchain` 0.1.79.* Rejected: it emits `llm.*`/`openinference.*`, not `gen_ai.*`, and the project standardizes on the OTel GenAI conventions.
- *The official OTel contrib.* It ships GenAI instrumentations for OpenAI, OpenAI Agents and Vertex AI only, and none for LangChain or Anthropic. `opentelemetry-util-genai` 1.2b0 is a beta helper for building instrumentations, and it would hide the attribute choices this phase is meant to teach.
- *Hybrid (library for `chat`/`execute_tool`, hand-made `invoke_agent`).* Rejected: two sources of truth for `gen_ai.*`, and it keeps the extra spans and content defaults.
- Cost of this choice: we maintain the attribute names ourselves as the conventions change. They live in one constants module with the semconv commit they were read from, so a later bump is one diff.

### 2. Where each span is created

| Span | Where | Why there |
|---|---|---|
| `invoke_agent fornada-attendant` | `GraphAttendant.reply`, around `graph.ainvoke` | It is the turn boundary and knows the conversation id. It runs inside the FastAPI SERVER span's context, so the parent is automatic. |
| `chat {model}` | `call_model` node, around `model_with_tools.ainvoke` | We own the node. The httpx2 CLIENT span starts inside it and nests under it. The node already has the prompt version. |
| `execute_tool {name}` | `awrap_tool_call` on `ToolNode`, around `handler(request)` | One call per tool call, with the call id and the `ToolMessage` result, without replacing the prebuilt node. Each concurrent call runs in its own task, so sibling spans overlap as they really did. |

- *Alternative: a LangChain callback handler* (`on_chat_model_start`/`on_tool_start` and similar). Rejected: it keeps a run-id → span map, and callbacks start no context, so the httpx2 span would not nest under `chat`. The node and the wrapper give real context nesting for free.
- *Alternative: one span per graph node (`call_model`, `tools`).* Rejected: the semconv tree is agent → inference/tool. A `tools` span would add a level that the spec's waterfall does not have.
- The conversation id inside the graph comes from the run config's `thread_id`, as in `escalate_to_human`. `call_model` gains a `config` parameter, and the wrapper reads `request.runtime.config`. It never comes from state or from the model.

### 3. Tracer from the global provider

The module gets `trace.get_tracer(...)` from the global provider. Before `setup_tracing` runs, that is a proxy that resolves to the real provider once one is registered, and with tracing off it stays no-op. No tracer is threaded through `build_graph`, and the "tracing disabled" requirement holds by construction. Tests reuse the session-wide in-memory exporter, moved from `tests/unit/test_tracing.py` to `tests/unit/conftest.py`.

- *Alternative: inject a `Tracer` into `build_graph`/`GraphAttendant`.* Easier to isolate in tests, but every caller and test fixture would have to pass it, and FastAPI and httpx2 already use the global provider.

### 4. Provider and model come from the chat model, and only on `chat` spans

`call_model` already holds the chat model. `BaseChatModel._get_ls_params()` returns `ls_provider` and `ls_model_name`, the same values LangChain uses for its own tracing. `ChatAnthropic` and `ChatOpenAI` override it with fixed values (`anthropic`/`self.model`, `openai`/`self.model_name`), which match the semconv `gen_ai.provider.name` values. They are read once, when the node is built.

- The method has a leading underscore. The risk is low: it is the contract LangChain's own tracing relies on, and both providers override it. A unit test over the real `ChatAnthropic` and `ChatOpenAI` classes fails if it changes. `ScriptedChatModel` overrides it in tests.
- `invoke_agent` carries neither provider nor model. The internal variant does not list the provider, and the `chat` children already show the model. So `GraphAttendant` needs nothing new.
- *Alternative (rejected after implementing it in 1.3): a `ModelInfo(provider, model)` value built from `LLM__*` settings in `main.py` and threaded through `build_graph`, `make_call_model` and `GraphAttendant`.* It duplicated what the model object already knows and changed three signatures and their test callers.

### 5. Attribute constants in one module

`fornada_api/agents/attendant/tracing.py` holds:
- the attribute and operation names as string constants;
- the semconv commit they follow;
- the `fornada.*` names (`fornada.prompt.version`, `fornada.capacity.free_kg`);
- the tracer.

`opentelemetry-semantic-conventions` 0.66b1 (`opentelemetry.semconv._incubating.attributes.gen_ai_attributes`) is not used: it is an incubating, private-path module that lags the GenAI repo, and depending on it gives no guarantee. Strings plus a commit reference are explicit. `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` does not apply: it switches instrumentation libraries, and we have none for GenAI.

### 6. Tokens only on `chat` spans; cost computed by Langfuse

- `gen_ai.usage.input_tokens` and `output_tokens` come from the answer's `usage_metadata`.
- `response.model`, `response.id` and finish reasons come from `response_metadata` and the message id. The exact keys differ per provider and are checked during implementation.
- Cost is left to Langfuse: model name plus usage gives a `generation` with a price. We do not compute it in the app. That would duplicate the price table, and `gen_ai.usage.cost` is not a semconv attribute.
- No usage on `invoke_agent`. Langfuse can count tokens on parent spans twice, and summing is Langfuse's job (the session and trace totals).
- Cache token attributes are left out for now. LangChain's `input_tokens` already includes cache reads and writes, which matches semconv. Sending `cache_read` next to it would break Langfuse's exclusive-bucket pricing. The prompt uses no `cache_control` today, so these counts are 0.

### 7. Status rules

| Situation | Span | Status | `error.type` |
|---|---|---|---|
| Model call raises (provider, timeout, parsing) | `chat` and `invoke_agent` | ERROR, exception recorded | exception class name |
| Graph raises (e.g. `GraphRecursionError`) | `invoke_agent` | ERROR, exception recorded | exception class name |
| Tool returns `ToolMessage(status="error")` (domain error, internal error, invalid args) | `execute_tool` | ERROR | TODO(human), see below |
| `check_capacity` returns a report with `free_kg = 0` | `execute_tool check_capacity` | UNSET | — |
| Successful call | any | UNSET | — |

- **Full day (maintainer's decision, 2026-10-11): UNSET plus `fornada.capacity.free_kg`.** A full day is the right answer to the question the model asked, not a broken tool. Marking it ERROR would put "the oven is full" in the same bucket as "the database is down", and the final dashboard's tool error rate would mean nothing. What went wrong when a full day leads to a confirmed order is the *agent's* decision, and phase 3 finds that by reading the trace (`free_kg = 0` followed by `create_order`), not from a status. `check_capacity(date)` takes no weight, so "full for this order" depends on the order. The span records the number and the model decides.
- Where `free_kg` is set: inside the `check_capacity` tool, on the current span (`trace.get_current_span()`), which is the `execute_tool` span started by the wrapper. The tool has the typed `CapacityReport`. *Alternative:* parse the JSON `ToolMessage.content` in the wrapper with per-tool logic. Rejected: it parses a string the tool just serialized, and it moves domain knowledge into generic telemetry code.
- A failed tool call does not mark `invoke_agent`: the model gets the error and continues (`attendant-agent`, "Tool errors go back to the model"). The turn only fails if it raises.
- Status descriptions never include exception messages or `ToolMessage` text: they can carry customer data (the spec forbids conversation content on spans). `record_exception` stores the message and stack trace in a span event. That is acceptable for provider and driver errors, whose messages tools already keep away from the LLM. TODO(human) to confirm or turn it off with `record_exception=False`.

### 8. Core decisions left as `TODO(human)` in the code

Phase 2's core is "which spans and attributes exist" (AGENTS.md). The spec fixes the contract. The agent writes the constants, plumbing and failing tests, and leaves these for the maintainer:

1. **`invoke_agent` span** in `GraphAttendant.reply`: which attributes go at creation time (semconv lists `gen_ai.operation.name` and `gen_ai.agent.name` as sampling-relevant; this span carries no provider or model, see decision 4), setting the prompt version from the turn output, and exception handling. Weigh: `start_as_current_span` already records exceptions and sets ERROR by default, but does it set `error.type`?
2. **`chat` span** in `call_model`: provider and request model from `_get_ls_params()` at creation time, and reading usage, response model, response id and finish reasons from the `AIMessage`. Weigh: what to do when `usage_metadata` is `None`, and why finish reasons are an array.
3. **`execute_tool` wrapper**: the status rule for `ToolMessage.status == "error"` and the `error.type` value. Options: the constant `tool_error`; `_OTHER` (semconv's fallback); or a split such as `invalid_arguments` / `domain_error` / `internal_error`, which needs a signal the wrapper can see without reading message text. Weigh: phase 4 has a deterministic eval for "valid tool args".
4. **`fornada.capacity.free_kg`** in `check_capacity`: set it as a double, and decide whether `meets_regular_lead_time` and `meets_custom_lead_time` also deserve attributes. The spec requires only `free_kg`.

### 9. Measuring the cost of tracing

This is not a guardrail, but the "guardrails have a price" rule applies in spirit. Span creation is in-process and export is batched off the request path. The end-to-end check compares turn latency with tracing on and off over the same scripted turn, and records the difference in the task summary. The token cost is zero, because no LLM call is added.

## Risks / Trade-offs

- [Langfuse does not infer the observation types from `gen_ai.operation.name` (agent/generation/tool) and shows plain spans, or computes no cost] → The end-to-end task checks it in the UI. A `chat` span with `gen_ai.request.model` and usage falls back to `generation` anyway, which is enough for cost. A wrong type for agent or tool spans is cosmetic and can be fixed in step B with a Collector `transform` processor, not in app code.
- [No built-in Langfuse price for `claude-haiku-4-5` (or the `-20251001` response model), so cost shows as 0] → The end-to-end task checks it. Fallback: a custom model definition in the dev Langfuse project (UI or API), recorded in `apps/api/README.md`. No app change.
- [`session.id` only on agent spans; the SERVER root span lacks it] → Langfuse reads trace-level attributes from any span, so the session still forms. If the end-to-end check shows the trace outside the session, `GraphAttendant.reply` also sets `session.id` on the current SERVER span. That is a small, local change; the spec can be extended then.
- [The OTel context is not propagated into LangGraph's node tasks or `ToolNode`'s concurrent calls, so spans become roots or siblings of the wrong parent] → The unit tests assert parentage (`chat`/`execute_tool` under `invoke_agent`, the httpx2 span under `chat` in the end-to-end check). LangGraph runs nodes in tasks that copy `contextvars`, which is where OTel keeps its context.
- [Semconv attribute names change (they are development status)] → One constants module with the commit it follows. Tests assert the names, so a bump is a deliberate diff.
- [`record_exception` puts exception messages in span events, which Langfuse stores] → Provider and driver exceptions carry no customer text. Tool exceptions never reach the wrapper (they become `ToolMessage`s). See decision 7, TODO(human).
- [`gen_ai.conversation.id` and `session.id` repeat the same UUID on every span] → A few bytes per span. It is not personal data (a client-generated UUID), but it links all of one customer's turns. That is the point, and it goes into the LGPD map in phase 7.

## Migration Plan

1. Deploy with the existing `TELEMETRY__ENABLED` switch. No new setting, dependency or Collector change.
2. Old traces (before this change) have no session and stay ungrouped in Langfuse. That is expected.
3. Rollback: revert the commit. The agent's behavior is unchanged either way.

## Open Questions

- Should the prompt version also map to Langfuse's `version` field (via `langfuse.version`) so it is filterable in the UI? That conflicts with the "no `langfuse.*` in app code" non-goal. It can be done in step B in the Collector by copying `fornada.prompt.version` to `langfuse.version`. Decide when the step B pipeline is written.
