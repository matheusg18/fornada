# Tasks

## 1. Collector: the Langfuse view

- [x] 1.1 Check the OTTL paths in design.md decision 1 (`span.parent_span_id`, `span.status.code`, `span.name`) against the transform processor docs for EDOT 9.5.5 / Collector core v0.161.0, and record the result in the processor's comment
- [x] 1.2 Add `transform/langfuse_view` to `.devcontainer/otel-collector/config.yaml` (DEBUG level on non-root, non-GenAI, non-error spans; root of `/conversations/{conversation_id}/messages` renamed `turn`; `error_mode: ignore`) and wire it into `traces/langfuse` only, updating the header and pipeline comments; verify the Collector starts cleanly after the maintainer restarts it on the host (`docker compose -p fornada_devcontainer logs edot-collector` shows no config error)
- [ ] 1.3 Send a chat turn with tracing on and verify in Langfuse that the trace is named `turn` and its default tree shows `turn` → `invoke_agent` → `chat` / tool observations, with the hidden-observations note; verify in Kibana Dev Tools (`GET traces-*/_search` by trace id) that the same spans keep their HTTP names and carry no `langfuse.observation.level`
- [ ] 1.4 Verify the smoke test (`telemetrygen`) traces keep their names in Langfuse, and that a failed tool statement's span stays at `DEFAULT` (force one, e.g. against a stopped database or a broken statement in a scratch run, and read its level with the observations API)

## 2. Chat: content on the client span

- [ ] 2.1 Add `capture_content` to the chat's `TelemetrySettings`, read from `TELEMETRY__CAPTURE_CONTENT` with the same truthy values as `TELEMETRY__ENABLED`, off by default; verify with unit tests for unset, true and tracing off
- [ ] 2.2 With capture on, set `gen_ai.input.messages` on the client span before the post and `gen_ai.output.messages` after the replies are read, in the API's JSON shape with `ensure_ascii=False`; verify with unit tests for two replies in order, a failed post keeping the input only, accents kept, and the existing "no message text" test still passing with capture off

## 3. Simulator: content on the client span

- [ ] 3.1 Add `capture_content` to the simulator's `TelemetrySettings` (pydantic, `TELEMETRY__CAPTURE_CONTENT`), off by default; verify with a settings unit test
- [ ] 3.2 Set the same two attributes on the simulator's client span when capture is on; verify with unit tests mirroring 2.2, plus one asserting the persona's goal text never appears in any attribute with capture on
- [ ] 3.3 Run `uv run task check` in `apps/chat` and `apps/simulator` and verify both pass

## 4. Docs and end-to-end check

- [ ] 4.1 Update `.env.example` so `TELEMETRY__CAPTURE_CONTENT` says it applies to the API, the chat and the simulator; update `AGENTS.md` (the Collector and redaction bullets, plus a short "Reading a conversation in Langfuse" note: session page filtered by **Is Root Observation = true**, the trace page's "Min Level", and why not to filter by output); verify the documented filter on a real session
- [ ] 4.2 Run a short simulator batch with capture on and verify: the session page filtered to root observations shows one block per turn with the customer's message and the bot's replies; `GET traces-*/_search` with a phone used in the conversation returns 0 hits in Elasticsearch

## Workflow follow-up

- Archive the change after review (`/opsx:archive`).
