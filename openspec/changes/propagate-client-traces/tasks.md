# Tasks

## 1. API continues the caller's trace

- [x] 1.1 Add an API test that posts a message with a fixed `traceparent` and asserts the SERVER span's trace id and parent span id, and that `invoke_agent` shares the trace id. Add a second test where no header gives a root SERVER span. Verify with `uv run task check` in `apps/api` (no production code change expected; design decision 1).

## 2. Simulator tracing

- [x] 2.1 Add `opentelemetry-sdk` and `opentelemetry-exporter-otlp-proto-http` to `fornada-simulator` with `uv add --package`, and verify `uv sync` succeeds.
- [x] 2.2 Add `TelemetrySettings` (`enabled`, `otlp_endpoint`, same validation as the API) as the `telemetry` field of the simulator's `Settings`, reading `TELEMETRY__*`. Verify with `test_settings.py` cases for the default-off value and an invalid URL.
- [x] 2.3 Add `fornada_simulator/telemetry.py` with `build_tracer_provider` and an idempotent `setup_tracing`, leaving a `TODO(human)` with a commented suggestion for the provider (resource `fornada-simulator`, sampler, processor; design decisions 6 and 9). Verify with an in-memory exporter test of the resource and of a second setup reusing the first provider.
- [ ] 2.4 Wrap the `POST` in `client.send_message` in a CLIENT span named `POST /conversations/{conversation_id}/messages`. Inject `traceparent` with `propagate.inject`, and take `persona_id` and `run_id` as optional arguments that `run_conversation` passes. Leave `TODO(human)` markers with suggestions for the attribute set and for the error status and `error.type` mapping (design decisions 3 and 5). Verify with unit tests against a mock transport:
  - the header is present and names the span;
  - session, conversation, persona and run attributes;
  - no message text in any attribute;
  - ERROR on 500, connect failure and bad body, UNSET on 200;
  - no header when tracing is off.
- [ ] 2.5 Make `run_batch` flush the global SDK provider before returning, and make `__main__` set tracing up from settings and shut it down in a `finally`. Verify with a test: after `run_batch` returns, the in-memory exporter already holds every client span. A second test runs two conversations at concurrency 2 and checks their trace ids are disjoint.
- [ ] 2.6 Move the notebook to `httpx2` and set tracing up in its first cell. Verify the notebook runs one conversation against the dev API with tracing on, and commit it with outputs cleared.
- [ ] 2.7 Document tracing in `apps/simulator/README.md`: variables, span shape, flush behavior. Verify `uv run task check` passes in `apps/simulator`.

## 3. Chat tracing

- [ ] 3.1 Add the same two OpenTelemetry packages to `fornada-chat` with `uv add --package`, and verify `uv sync` succeeds.
- [ ] 3.2 Add `fornada_chat/telemetry.py`: settings from `TELEMETRY__ENABLED` and `TELEMETRY__OTLP_ENDPOINT` in `os.environ`, `build_tracer_provider` with a `TODO(human)` suggestion for the provider (resource `fornada-chat`), and an idempotent `setup_tracing`. Verify with unit tests for default-off, the endpoint and the resource.
- [ ] 3.3 Wrap the `POST` in the chat's `client.send_message` in the same CLIENT span and inject. Session and conversation attributes; no persona. Same error mapping as the simulator. Verify with unit tests mirroring 2.4, minus the persona.
- [ ] 3.4 Register `@cl.on_app_startup` (setup) and `@cl.on_app_shutdown` (shutdown) in `app.py`. Verify by starting `uv run task dev` with tracing on, sending one message in the browser through Playwright, and finding a `fornada-chat` root with the API's spans under it in Langfuse.
- [ ] 3.5 Document tracing in `apps/chat/README.md`: the variables, and that `LITERAL_API_KEY` is unsupported because it turns Traceloop on. Verify `uv run task check` passes in `apps/chat`.

## 4. Configuration and end-to-end check

- [ ] 4.1 Update `.env.example` so the `TELEMETRY__*` block says it is read by the API, the simulator and the chat (the chat from its shell or `apps/chat/.env`). Verify the simulator picks it up from the root `.env` with one conversation.
- [ ] 4.2 With the maintainer's go-ahead (token cost), run the default batch of 20 conversations with tracing on in the API and the simulator. Run the one-off Langfuse check from design decision 10 over the batch's conversation ids. Verify:
  - 20 sessions;
  - every trace has exactly one root, from `fornada-simulator`;
  - no observation points to a parent missing from its trace.

  Record the numbers for the PR.

## Workflow follow-up

- Commit the OpenSpec artifacts early, then one commit per task group after `uv run task check` passes in each touched app.
- Archive the change and sync the `client-tracing` and `app-tracing` specs after review; open the PR with the batch verification numbers.
