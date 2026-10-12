# Tasks

Tasks marked `TODO(human)` are core (AGENTS.md, phase 2: "which spans and attributes exist"). The agent leaves the marker, a short "Learn by Doing" note and failing tests, then stops and waits for the maintainer. Everything else, including graph wiring, is periphery the agent does. Run `uv run task check` from `apps/api` at the end of each group.

## 1. Test fixtures and attribute constants

- [x] 1.1 Move the session-wide in-memory exporter fixtures (`session_exporter`, `spans`) from `tests/unit/test_tracing.py` to `tests/unit/conftest.py`, unchanged (design.md, decision 3). Verify `uv run task test:unit` passes with the same test count as before.
- [x] 1.2 Create `fornada_api/agents/attendant/tracing.py` with the module tracer (`trace.get_tracer(__name__)`), the agent name `fornada-attendant`, and the `gen_ai.*`, `session.id`, `error.type` and `fornada.*` attribute names and operation values the `agent-tracing` spec uses. The module docstring cites `open-telemetry/semantic-conventions-genai` commit `6fd0d76` (2026-10-09) (design.md, decision 5). Verify `uv run task lint typecheck` passes.
- [x] 1.3 ~~Add a `ModelInfo` value from the settings~~. Dropped after implementing it: provider and model come from the chat model's `_get_ls_params()` (design.md, decision 4). The code was reverted, and `uv run task check` passes with no signature change.

## 2. Turn span (`invoke_agent`)

- [ ] 2.1 Write failing unit tests in `tests/unit/agents/test_agent_tracing.py` (scripted model, `spans` fixture, graph compiled with an in-memory checkpointer). Cover the `agent-tracing` scenarios:
  - one `invoke_agent fornada-attendant` span per turn, kind INTERNAL, with operation and agent name, and no provider or model attribute;
  - `gen_ai.conversation.id` and `session.id` equal to the conversation id;
  - `fornada.prompt.version` from the turn output;
  - no `gen_ai.usage.*` on the turn span;
  - a model that raises gives an ERROR span with `error.type` set to the exception class name;
  - the same replies and stored messages with the no-op provider.

  Verify they fail.
- [ ] 2.2 TODO(human): create the `invoke_agent` span around `graph.ainvoke` in `GraphAttendant.reply` (design.md, decision 8.1). The agent leaves the marker and a Learn by Doing note in `attendant.py`. Verify the 2.1 tests pass.

## 3. Model span (`chat`)

- [ ] 3.1 Give `call_model` the run `config` so it can read `thread_id` (design.md, decision 2), with no behavior change. Verify the existing `tests/unit/agents/test_nodes.py` and `test_graph.py` pass.
- [ ] 3.2 Check which `response_metadata` keys `langchain-anthropic` 1.7.5 and `langchain-openai` 1.6.7 fill for response model, response id and finish/stop reason. Read the installed source and record the keys in the Learn by Doing note for 3.4. Verify by quoting the source lines in the step summary.
- [ ] 3.3 Write failing unit tests:
  - one `chat claude-haiku-4-5` span per model call, kind CLIENT, child of `invoke_agent`;
  - provider and request model read from the chat model's `_get_ls_params()` (`ScriptedChatModel` overrides it to return `anthropic`/`claude-haiku-4-5`), and `fornada.prompt.version`;
  - a test over the real `ChatAnthropic` and `ChatOpenAI` classes that `_get_ls_params()` gives `anthropic`/`claude-haiku-4-5` and `openai`/`gpt-5-mini`, so a LangChain change breaks a test;
  - conversation and session ids;
  - `gen_ai.usage.input_tokens`/`output_tokens` as ints when `usage_metadata` is set, and absent when it is not;
  - finish reasons as an array;
  - an ERROR span with `error.type` when the model raises;
  - no attribute holding the customer's text.

  Extend `ScriptedChatModel` only if it needs to return usage or metadata. Verify they fail.
- [ ] 3.4 TODO(human): create the `chat` span around `model_with_tools.ainvoke` in `call_model` and set the response attributes (design.md, decisions 6 and 8.2). Verify the 3.3 tests pass.

## 4. Tool spans (`execute_tool`) and the full-day rule

- [ ] 4.1 Add an `awrap_tool_call` hook to the `ToolNode` in `build_graph` that, for now, only calls the handler (design.md, decision 2). Verify existing graph and tool tests pass unchanged.
- [ ] 4.2 Write failing unit tests:
  - one `execute_tool {name}` span per call, kind INTERNAL, child of `invoke_agent`, with tool name, call id, `gen_ai.tool.type=function`, and conversation and session ids;
  - two calls in one answer give two sibling spans with their own call ids;
  - the waterfall order chat → tools → chat by start time;
  - an error `ToolMessage` (e.g. `calculate_quote` with 2.3 kg) gives an ERROR tool span with `error.type`, while `invoke_agent` is not ERROR;
  - no tool arguments or results on any span.

  Use stub tools in the scripted graph. Verify they fail.
- [ ] 4.3 TODO(human): create the `execute_tool` span in the wrapper and decide the status rule and `error.type` value for error results (design.md, decisions 7 and 8.3). Verify the 4.2 tests pass.
- [ ] 4.4 Write failing tests for the full-day rule. With a fake capacity service (or the real tool over the existing service fakes), `check_capacity` for a date with 0 kg free gives an UNSET `execute_tool check_capacity` span with `fornada.capacity.free_kg = 0.0`, and a date with 6.5 kg free gives `6.5`. Verify they fail.
- [ ] 4.5 TODO(human): set `fornada.capacity.free_kg` on the current span inside the `check_capacity` tool, and decide whether the lead-time flags also become attributes (design.md, decisions 7 and 8.4). Verify the 4.4 tests pass and `uv run task check` passes.

## 5. Docs and end-to-end check

- [ ] 5.1 Update `apps/api/README.md` ("Tracing"):
  - the agent span tree (`invoke_agent` → `chat` / `execute_tool`, the httpx2 span under `chat`);
  - the attributes each span carries, and that no conversation text is recorded;
  - how to open a conversation's session in Langfuse (Sessions, filtered by the conversation id);
  - the full-day status rule.

  Verify every attribute in the spec appears in the README.
- [ ] 5.2 Maintainer predicts in one sentence the waterfall Langfuse will show for "Quero um bolo de chocolate de 2 kg para sábado, dá?". Then, with tracing on, run `uv run task dev` and post 3 messages to one conversation id, so that one turn calls `check_capacity` for a full date (insert or reuse a seeded full date). In Langfuse (http://localhost:3000, project Fornada) confirm:
  - each trace's waterfall matches the graph (agent → chat → tool(s) → chat, with the HTTP span under its chat);
  - each generation shows model, tokens and a non-zero cost;
  - the three traces sit in one session named by the conversation id;
  - the full-day `check_capacity` observation is not marked as an error and shows `fornada.capacity.free_kg = 0`.

  This is the "Pronto quando". Compare with the prediction. If cost is 0, add a custom model definition in the dev Langfuse project and document it in the README (design.md, Risks).
- [ ] 5.3 Agent, in the dev container: before and after 5.2, read `curl -s edot-collector:8888/metrics | grep spans` and confirm `otelcol_exporter_sent_spans{exporter="otlphttp/langfuse"}` grows and `send_failed_spans` does not. Time the same scripted turn with `TELEMETRY__ENABLED=true` and `false` (5 runs each) and report the latency difference (design.md, decision 9). Paste the readings and timings in the step summary.

## Workflow follow-up

- One commit per group, with maintainer approval before each: `test:`/`refactor:` for 1, `feat:` for 2–4, `docs:` for 5.1.
- Archive the change after 5.2 passes, and sync `agent-tracing` into `openspec/specs/`.
- After archiving, remind the maintainer that content capture (open question in phase 3) and the step B Collector work (redaction, `langfuse.version` copy, Elasticsearch fan-out) are the next changes.
