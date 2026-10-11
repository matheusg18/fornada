# Tasks

Tasks marked `TODO(human)` are core (AGENTS.md, phase 2: "`TracerProvider`, sampler, which spans and attributes exist"). The agent leaves the marker, a short "Learn by Doing" note and the tests, then stops and waits for the maintainer. Everything else is periphery.

## 1. Dependencies

- [x] 1.1 Read the FastAPI 0.143.0 release notes, then upgrade with `uv add --package fornada-api "fastapi[standard]" --upgrade-package fastapi` so it resolves the latest release. Verify `uv.lock` has `fastapi` ≥ 0.143.0 and `uv run task check` (in `apps/api`) passes unchanged.
- [x] 1.2 Add `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http` and `opentelemetry-instrumentation-httpx` as direct dependencies with `uv add --package fornada-api …`, after checking their latest versions on PyPI (1.45.1, 1.45.1 and 0.66b1 on 2026-10-11). Verify that `uv run python -c "from opentelemetry.instrumentation.httpx import HTTPX2ClientInstrumentor"` succeeds and `uv run task check` passes.

## 2. Telemetry settings (`app-config`: namespaces, tracing switch, OTLP endpoint)

- [ ] 2.1 Write failing unit tests in `tests/unit/core/test_config.py` for every scenario in the `app-config` delta: `TELEMETRY` namespace, `TELEMETRY__ENABLED` default off / `true` / invalid value names the variable, `TELEMETRY__OTLP_ENDPOINT` default `http://edot-collector:4318` / override / non-HTTP value names the variable. Verify they fail with `uv run task test:unit`.
- [ ] 2.2 Add `TelemetrySettings` (`enabled: bool = False`, `otlp_endpoint` as an `http`/`https` URL with the default above) and the `telemetry` field on `Settings`. Verify the 2.1 tests pass.
- [ ] 2.3 Add the `TELEMETRY` block to the root `.env.example` (`TELEMETRY__ENABLED=true` for the dev container, the endpoint, a comment that spans reach the Collector a few seconds late) and the two rows to the settings table in `apps/api/README.md`. Verify every `TelemetrySettings` field appears in both.

## 3. Tracing setup module (`app-tracing`: service identity, OTLP export, single exporter, flush at shutdown)

- [ ] 3.1 Write failing unit tests in `tests/unit/core/test_telemetry.py`, using an `InMemorySpanExporter`, without touching the global provider: a span from the built provider carries `service.name=fornada-api`; with tracing disabled, setup returns nothing and leaves the global provider unchanged; after shutdown the buffered spans have been exported; the OTLP exporter targets `<TELEMETRY__OTLP_ENDPOINT>/v1/traces`. Shape the setup API (build vs. register, how the exporter is injected) so the tests can do this, as design.md says. Verify they fail.
- [ ] 3.2 Create `fornada_api/core/telemetry.py` as a skeleton: the public functions the tests call, the module docstring, the URL join for `/v1/traces`, and the `HTTPX2ClientInstrumentor` call plus its `uninstrument()` at shutdown (periphery; plain `httpx` is not instrumented, see design.md). Leave `TODO(human)` markers and a "Learn by Doing" note for 3.3–3.5. Verify `uv run task lint typecheck` passes on the skeleton.
- [ ] 3.3 TODO(human): build the `Resource`, with `service.name` plus whatever else the maintainer chooses (design.md, core decision 1).
- [ ] 3.4 TODO(human): build the `TracerProvider` (sampler choice, core decision 2), the OTLP/HTTP span exporter and the `BatchSpanProcessor` (decision 3), and register the provider globally.
- [ ] 3.5 TODO(human): decide the HTTP semconv opt-in (`OTEL_SEMCONV_STABILITY_OPT_IN`, decision 5) and where it is set, so it is in place before the instrumentors initialize.
- [ ] 3.6 Agent reviews 3.3–3.5 only for mistakes that break the tests or startup, and asks questions instead of fixing. Verify the 3.1 tests pass and `uv run task check` passes.

## 4. Wire tracing into the app (`app-tracing`: switch, server span, flush at shutdown)

- [ ] 4.1 Write failing unit tests for the app: with tracing disabled, starting and stopping the app registers no SDK provider (spec: tracing disabled). With an in-memory SDK provider registered once for the test session, a `TestClient` POST to `/conversations/{id}/messages` yields exactly one SERVER span with method `POST`, route `/conversations/{conversation_id}/messages` and status code, and two posts with different ids share that route and no span name contains an id. Verify they fail where wiring is missing.
- [ ] 4.2 TODO(human): pass `telemetry={...}` to `FastAPI(...)` in `main.py`: `auto_configure: False` (design.md) plus the maintainer's choice for `operation_spans`, `metrics` and `logs` (core decision 4), with a one-line comment for each choice.
- [ ] 4.3 TODO(human): call the tracing setup in the lifespan right after `configure_logging`, and shut it down in the `finally` block. The maintainer decides the order relative to `checkpointer.close()` and `engine.dispose()`. Keep `@asynccontextmanager` (design.md: it is not deprecated). Verify the 4.1 tests and `uv run task check` pass.

## 5. End-to-end check (all `app-tracing` requirements)

- [ ] 5.1 Document in `apps/api/README.md` how to see spans: set `TELEMETRY__ENABLED=true`, run `uv run task dev`, post a message, read `curl -s edot-collector:8888/metrics | grep spans` in the container and `docker compose -p <project> logs edot-collector` on the host, and expect a batch delay of about 5 s. Verify the commands run as written.
- [ ] 5.2 Maintainer predicts in one sentence which spans the Collector log will show for one customer message. Then, with tracing on, `uv run task dev` and a POST to `/conversations/<uuid>/messages`: the Collector log shows one SERVER span with `service.name=fornada-api`, the route template and status 200, plus a CLIENT span for the LLM HTTP call in the same trace, under the SERVER span. This is the "Pronto quando". Compare with the prediction.
- [ ] 5.3 Agent, in the dev container: before and after 5.2, `curl -s edot-collector:8888/metrics` shows `otelcol_receiver_accepted_spans` going up by the number of spans in the log. Paste both readings in the step summary.
- [ ] 5.4 Flush and resilience: post a message and stop the server (Ctrl+C) within 1 s. The request's spans still reach the Collector. Then set `TELEMETRY__OTLP_ENDPOINT=http://localhost:4318` (nothing listening), post a message, and get the normal reply with only an exporter warning in the log. Record both outcomes in the step summary.

## Workflow follow-up

- One commit per group, with maintainer approval before each: `chore:` for 1, `feat:` for 2–4, `docs:` for the README in 5.1.
- Archive the change after 5.2 passes, and sync `app-tracing` and `app-config` into `openspec/specs/`.
- After archiving, remind the maintainer to move `apps/chat` and `apps/simulator` from `httpx` to `httpx2`. Pair it with the client-side tracing change noted in design.md (Non-Goals).
