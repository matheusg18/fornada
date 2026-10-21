# Proposal

## Why

Phase 3 error analysis is done by reading conversations in Langfuse, and today they are hard to read. A turn's trace has 44 observations, and 38 of them are HTTP, FastAPI and SQL spans that phase 2 added for Kibana. The agent sits four levels deep. The trace root (the client's HTTP span) has no input or output, so the trace list and the session page show `null` for every turn. And every trace has the same name, `POST /conversations/{conversation_id}/messages`. The session page stacks every observation's input and output, so the same text appears three or four times per turn.

This belongs to phase 2 (instrumentation), and it is needed now for phase 3. It stays within the frozen scope: it adds no tool or feature to the agent, only changes what telemetry shows in Langfuse.

## What Changes

- In the Collector's Langfuse pipeline only, every span that is not a GenAI operation (no `gen_ai.operation.name`), is not a trace root and did not fail is marked with Langfuse's `DEBUG` level. Langfuse's trace tree and graph hide `DEBUG` observations by default and show their children under the nearest visible ancestor, so a turn reads as turn → `invoke_agent` → model calls and tools. The infrastructure spans stay in Langfuse (lower the tree's "Min Level" to see them) and reach Elasticsearch unchanged.
- In the same pipeline, the root span of a turn is renamed `turn`, so the trace list tells turns from other traces. The span keeps its HTTP name in Elasticsearch, where Kibana APM uses it as the transaction name.
- The chat and the simulator gain the content-capture switch the API already has (`TELEMETRY__CAPTURE_CONTENT`, off by default). With it on, the client's root span carries the customer's message as `gen_ai.input.messages` and the bot's replies as `gen_ai.output.messages`. Langfuse shows these as the root's input and output. **BREAKING** for the `client-tracing` requirement that client spans carry no conversation content: it now holds only while capture is off.
- Elasticsearch still receives no conversation content: the existing redaction already deletes both attributes from every service's spans.
- `AGENTS.md` documents how to read a conversation in Langfuse: the session view filtered to root observations, and the "Min Level" switch on the trace page.

Evidence: a manual probe on 2026-10-20 sent a synthetic trace shaped like a real turn straight to Langfuse v4.53. With five `DEBUG` spans between the root and the agent, the tree showed `turn` → `invoke_agent` → `chat` / `calculate_quote` / `chat`, with "5 hidden observations below DEFAULT level". A second probe showed that `gen_ai.input.messages` and `gen_ai.output.messages` on a plain root span become its input and output, with no `langfuse.*` attribute.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `client-tracing`: client root spans carry the turn's message and replies when content capture is on, instead of never carrying content; the chat and the simulator read the capture switch.
- `telemetry-collector`: the Langfuse pipeline marks infrastructure spans as `DEBUG` and names the turn's root `turn`; "Langfuse keeps the content" allows these presentation changes while content stays as the app sent it.

## Impact

- `.devcontainer/otel-collector/config.yaml`: a new transform processor in `traces/langfuse` (that pipeline has none today).
- `apps/chat` and `apps/simulator`: the capture setting, and the two content attributes on the client span, with unit tests.
- `.env.example` and `AGENTS.md`: the capture switch now also applies to the clients; how to read traces in Langfuse.
- No change to the API, the agent, Elasticsearch documents or Kibana dashboards. Traces already in Langfuse keep their old shape.
- LGPD: conversation text now leaves two more processes (chat and simulator), only to the Collector, and only when capture is on. It reaches Langfuse, which already holds the same text from the API's spans.
