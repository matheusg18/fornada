# Proposal

## Why

Phase 2, step A. Traces reach Langfuse today, but a conversation turn shows up only as the FastAPI SERVER span and an anonymous HTTP CLIENT span to the LLM provider. Langfuse cannot tell which tool ran, how many tokens a call used, what it cost, which prompt version answered, or which turns belong to the same conversation. Phase 3 error analysis reads these traces one by one, so without this change there is nothing useful to annotate.

## What Changes

- **Decision: spans are created by hand**, with the OpenTelemetry tracer API in the agent code. No LangChain instrumentation library is added. The OTel project ships no official LangChain instrumentation. Traceloop's `opentelemetry-instrumentation-langchain` 0.62.4 creates its own span tree (one span per node and runnable), adds `traceloop.*` attributes and records message text by default. OpenInference uses `llm.*`/`openinference.*` instead of `gen_ai.*`. Choosing which spans and attributes exist is core work in phase 2 (AGENTS.md), and the reasoning is recorded in design.md.
- Each conversation turn gets one `invoke_agent` span. Under it, each model call gets a `chat` span and each tool call gets an `execute_tool` span, following the OpenTelemetry GenAI semantic conventions (development status, checked on 2026-10-11 in `open-telemetry/semantic-conventions-genai`).
- `chat` spans carry the provider and the requested and response model (read from the LangChain chat model itself), input and output tokens, finish reasons and `fornada.prompt.version`. Langfuse turns these spans into generations and computes their cost from model and usage.
- Every agent span carries the conversation id twice: as `gen_ai.conversation.id` (semconv) and as `session.id`, which Langfuse maps to a session. All turns of one conversation are grouped in one Langfuse session.
- Span status rules. Exceptions and tool results with `status="error"` mark the span ERROR and set `error.type`. A `check_capacity` result for a full day is a correct business answer: the span status stays UNSET and the free capacity is recorded as an attribute.
- No message text, tool arguments or tool results go on spans. Content capture (`gen_ai.input.messages` and similar opt-in attributes) waits for the redaction work in step B and phase 6.

Phase: **2 (instrumentation), step A**. Frozen scope: unchanged. No tool, feature or UI change, and the agent's behavior and replies stay the same. Only telemetry is added.

## Capabilities

### New Capabilities

- `agent-tracing`: the spans the attendant agent emits for a turn, model calls and tool calls. Covers their names, kinds, nesting, `gen_ai.*` and `fornada.*` attributes, the conversation/session id and the status rules.

### Modified Capabilities

_None._ `app-tracing` (pipeline, HTTP SERVER/CLIENT spans) and `prompt-versioning` (where the version comes from) keep their requirements. `agent-tracing` builds on both.

## Impact

- **Code:** `apps/api/src/fornada_api/agents/attendant/` (`attendant.py` for the turn span, `nodes.py` for the model span, `graph.py` for a `ToolNode` tool-call wrapper) and a new tracing helper module for the attendant.
- **Dependencies:** none new. `opentelemetry-api` is already present through `opentelemetry-sdk`. Semconv attribute names are written as string constants, because the `gen_ai.*` names in `opentelemetry-semantic-conventions` 0.66b1 lag behind the current GenAI registry.
- **Telemetry:** about 3–8 more spans per turn. Langfuse shows generations, tool observations, cost and sessions. The Collector config does not change.
- **Tests:** new unit tests with the scripted chat model and an in-memory exporter. Existing tests are unaffected.
- **Docs:** `apps/api/README.md` ("Tracing") lists the agent spans and how to find a session in Langfuse.
