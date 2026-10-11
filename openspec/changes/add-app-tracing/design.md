# Design

## Context

See proposal.md for motivation. The current state, checked on 2026-10-11:

- **Lifespan.** `apps/api/src/fornada_api/main.py` already uses `@asynccontextmanager` with `FastAPI(lifespan=...)`. It loads settings, configures logging, opens the checkpointer, builds the graph, and on the way out closes the checkpointer and disposes the engine.
- **FastAPI native OpenTelemetry.** FastAPI 0.142.0 (2026-09-29) added native OTel support. It is configured with `FastAPI(telemetry={...})` and the defaults are on: `tracing`, `metrics`, `logs`, `operation_spans` and `auto_configure` are all `True`. On every request it reads the provider in `telemetry["tracer_provider"]`, or the global provider when that is `None`, and emits one SERVER span (`http.request.method`, `http.route`, `http.response.status_code`, schema 1.44.0). With `operation_spans` it also emits child spans for dependency resolution, the endpoint and serialization. It does nothing while the global provider is still the API's no-op proxy. If the contrib `OpenTelemetryMiddleware` is in the middleware stack, FastAPI turns its own tracing off.
- **FastAPI 0.143.0** (2026-10-08) made `auto_configure` opt-in. With `auto_configure` on, FastAPI's lifespan wrapper reads `OTEL_EXPORTER_OTLP_*` and attaches its own `BatchSpanProcessor` to the global provider. The repo is on 0.142.2.
- **LLM SDKs use `httpx2`, not `httpx`.** `anthropic` 1.12.0 and `openai` 3.26.0 import `httpx2` (pydantic/httpx2, "the next generation HTTP client"). `opentelemetry-instrumentation-httpx` 0.66b1 ships two instrumentors: `HTTPXClientInstrumentor` (patches `httpx`) and `HTTPX2ClientInstrumentor` (patches `httpx2`). Both wrap `HTTPTransport.handle_request` and `AsyncHTTPTransport.handle_async_request` at class level. Plain `httpx` is still installed in the API, but nothing on a conversation turn sends a request through it.
- **HTTP semconv mismatch.** The contrib instrumentations default to the old HTTP conventions (`http.method`, `http.url`) unless `OTEL_SEMCONV_STABILITY_OPT_IN` contains `http`. FastAPI native always emits the stable ones. The opt-in is read from `os.environ` once per process, the first time any instrumentation initializes.
- **Settings.** `pydantic-settings` reads the root `.env` into the `Settings` object, not into `os.environ`. So standard `OTEL_*` variables written in `.env` are invisible to the SDK.
- **Tests.** `tests/unit/test_conversations.py` runs the real app, lifespan included, with `TestClient`. CI has no Collector.
- **Installed already** (via `fastapi[standard]`): `opentelemetry-sdk` 1.45.1, `opentelemetry-exporter-otlp-proto-http` 1.45.1. Latest on PyPI is the same. `opentelemetry-instrumentation-httpx` latest is 0.66b1.

## Goals / Non-Goals

**Goals:**
- A hand-built trace pipeline in the app: Resource → TracerProvider → BatchSpanProcessor → OTLP/HTTP exporter → Collector.
- One SERVER span per request and CLIENT spans for the LLM HTTP calls, in one trace.
- One owner for exporter setup: the app's code, never an implicit path through environment variables.
- Tracing off by default, so tests and CI are unaffected.

**Non-Goals:**
- Turn, LLM-call and tool spans with `gen_ai.*` attributes, sessions, prompt version. These come in the next step-A changes.
- Collector → Langfuse, logs and metrics providers, trace id in JSON logs (step B).
- Instrumenting SQLAlchemy/psycopg or LangChain.
- Tracing in `apps/chat` and `apps/simulator`. They call the API with plain `httpx`. Instrumenting them would start the trace on the client side and propagate `traceparent` to the API, so each simulated conversation could be tied to its persona (useful in phase 3). That is a separate change, and it also brings the sampler's ParentBased choice into play. Moving those apps from `httpx` to `httpx2` belongs to that change too (Starlette 1.7 already warns that `httpx` in its `testclient` is deprecated in favor of `httpx2`).
- Sampling other than "keep everything". At dev volume every trace is wanted.
- PII redaction. Nothing leaves the dev network yet: the Collector only prints to its own log. Request bodies and message text are not recorded as attributes by this change.

## Decisions

**Keep `@asynccontextmanager` for the lifespan.** The maintainer suspected it was deprecated. It is not. The FastAPI docs ("Lifespan Events", checked 2026-10-11) still show exactly this pattern as the recommended one, and the stdlib does not deprecate `contextlib.asynccontextmanager`. What FastAPI deprecates is `@app.on_event("startup"/"shutdown")` and the `on_startup`/`on_shutdown` parameters. VS Code reports no diagnostic on `main.py`. No change to the lifespan's shape. Tracing setup and teardown go inside it.

**FastAPI's native telemetry for the SERVER span, not `opentelemetry-instrumentation-fastapi`.** Chosen by the maintainer. It is first-party, already installed, maintained with FastAPI, and uses the stable HTTP conventions. The contrib instrumentor would be a second package that only works by making FastAPI switch its own tracing off. Cost: fewer blog posts and examples use it. The `opentelemetry-instrumentation-asgi` docs do not apply.

**Explicit `telemetry={...}` on `FastAPI(...)`, with `auto_configure: False`.** Even on 0.143, where it is already off by default, it is written out. With auto-configure on and `OTEL_EXPORTER_OTLP_ENDPOINT` in the environment (the EDOT or Langfuse docs may suggest setting it), FastAPI would attach a second exporter to the same provider and every span would be sent twice. The other keys are a modeling decision (see the `TODO(human)` list below).

**Global provider set in the lifespan, not passed in `telemetry["tracer_provider"]`.** `app = FastAPI(...)` runs at import time, before settings are loaded and before the lifespan runs, so there is no provider to pass yet. FastAPI looks up the global provider on every request, so registering it with `trace.set_tracer_provider()` in the lifespan is enough. The global is also what the `httpx2` instrumentor and, later, the LangChain spans use. Trade-off: the OTel API lets the global provider be set only once per process. A second call logs a warning and is ignored. `fastapi dev` restarts the process on reload, so this only matters in tests (see Risks).

**Setup lives in `fornada_api/core/telemetry.py`, called from the lifespan right after `configure_logging`.** That is before the chat model is built, so instrumentation is in place before any LLM client exists. The class-level patches would also cover clients created earlier, but the order makes it obvious. The function receives `TelemetrySettings` and returns what the lifespan must shut down (the provider), or nothing when tracing is disabled. Shutdown goes in the lifespan's `finally`. It flushes the `BatchSpanProcessor` (`TracerProvider.shutdown()` calls `shutdown()` on every processor, which exports what is buffered) and uninstruments `httpx2`.

**OTLP over HTTP/protobuf to `:4318`, not gRPC to `:4317`.** `opentelemetry-exporter-otlp-proto-http` is already installed through `fastapi[standard]`. The gRPC exporter would add `grpcio`, a large native wheel, to the API for no gain on a local network. The Collector accepts both.

**Endpoint and switch in a `TELEMETRY` settings namespace, not standard `OTEL_*` variables.** The root `.env` is loaded by `pydantic-settings` only, so `OTEL_EXPORTER_OTLP_ENDPOINT` in `.env` would never reach the SDK. A typed setting also keeps the app-config rule "one typed source of configuration" and gets the same validation and fail-fast as `DB__URL`. The setting holds the base URL (`http://edot-collector:4318`), like `OTEL_EXPORTER_OTLP_ENDPOINT`. The code appends `/v1/traces`, because the HTTP span exporter's `endpoint=` argument expects the full signal URL. The namespace is `TELEMETRY`, not `OTEL`, so `OTEL__…` is never confused with the standard `OTEL_…` variables. Alternative: read `OTEL_*` from the process environment and export them in the shell. Rejected because it splits configuration across two sources.

**Tracing off by default.** The existing unit tests run the full lifespan. With tracing on by default they would try to reach `edot-collector`, and shutdown would block up to the exporter timeout (10 s) per test client. The dev `.env.example` turns it on.

**Only `httpx2` is instrumented in the API, with `HTTPX2ClientInstrumentor`.** The LLM SDKs call through `httpx2`, so this instrumentor is what produces the CLIENT spans the spec asks for. Plain `httpx` has no request on a conversation turn in the API. `langchain-openai` uses it only for an SSRF-safe image-URL fetcher we do not use. `langgraph`'s retry code imports it only for an `isinstance` check on exceptions. `TestClient` and `fastapi-cloud-cli` are tooling. An `HTTPXClientInstrumentor` would emit nothing, so it is left out. Without the `httpx2` instrumentor the LLM calls would be invisible, and nothing would fail. That is why the spec requires the CLIENT span for the LLM call by behavior, not by library. Alternative: instrument both "just in case". Rejected because an instrumentation that produces no span is one more thing to understand and to uninstrument for no signal.

**Resource built explicitly with `service.name = "fornada-api"`.** It is not taken from `OTEL_SERVICE_NAME`, for the same `.env` reason. `Resource.create({...})` still merges the SDK's defaults (`telemetry.sdk.*`) and any `OTEL_RESOURCE_ATTRIBUTES` from the process environment.

### Core decisions left as `TODO(human)` for the maintainer

These are "TracerProvider, sampler, which spans and attributes exist" (AGENTS.md, phase 2 core). The tasks mark them; the design only frames the options.

1. **Resource attributes beyond `service.name`.** For example `service.version` (from package metadata) and `deployment.environment.name`. Weigh: they cost nothing per span (they are on the resource) and later help filter `v0` against the current version on dashboards.
2. **Sampler.** The SDK default is `ParentBased(ALWAYS_ON)`. Weigh: dev volume is tiny, and phase 3 needs every trace for error analysis. Should a client-sent `traceparent` decide sampling (ParentBased) or not?
3. **`BatchSpanProcessor` vs `SimpleSpanProcessor`.** The proposal names Batch. The maintainer writes the construction and may tune `schedule_delay_millis`, which defaults to 5 s and is why spans appear in the Collector log a few seconds late.
4. **FastAPI `telemetry` keys besides `auto_configure`.** `operation_spans` (children for dependency resolution, endpoint and serialization: useful or noise next to the future turn and LLM spans?), `metrics` and `logs`. These are no-ops until step B sets meter and logger providers. But `logs` records exception messages and stack traces, which can carry customer text: decide now or note it for step B.
5. **HTTP semconv opt-in.** Whether and how to set `OTEL_SEMCONV_STABILITY_OPT_IN=http` so the `httpx2` CLIENT spans use the same stable attribute names as FastAPI's SERVER span. It must be in `os.environ` before the first instrumentor initializes (e.g. `os.environ.setdefault(...)` in the setup function, or the dev container env). The same variable later carries `gen_ai_latest_experimental`, which AGENTS.md requires opting into explicitly.

## Risks / Trade-offs

- [Global provider is set once per process. A unit test that enables tracing, then another that enables it again, gets the first provider and a warning] → Unit tests for the setup function build the provider without registering it globally (the function separates "build" from "register"), or use an in-memory exporter on a provider passed explicitly to a small test app's `telemetry={"tracer_provider": ...}`. App-level tests keep tracing disabled.
- [FastAPI native telemetry is three weeks old. Attribute names or behavior may shift between minor releases (0.142.3 and 0.142.4 were already telemetry fixes)] → `uv.lock` pins the version, and the requirement in spec is behavioral (one SERVER span, method, route, status), checked by a test.
- [`httpx2` instrumentation is new in contrib 0.66b1 and beta] → The spec scenario and a manual check confirm a CLIENT span for the LLM call shows up.
- [The Collector is down or the endpoint is wrong] → `BatchSpanProcessor` exports in a background thread and drops spans after the timeout. Requests are unaffected, and the exporter logs a warning. The Collector's `otelcol_receiver_accepted_spans` metric is the quick check.
- [Spans arrive at the Collector up to ~5 s after the request] → Expected with Batch. The README says so, so a "missing" span is not misdiagnosed.
- [Upgrading FastAPI 0.142.2 → 0.143.0 brings other changes] → Read the 0.143.0 release notes during apply. `uv run task check` must pass before anything else.

## Migration Plan

No data or deployment migration. Rollback is `TELEMETRY__ENABLED=false` (the default) or reverting the commit. Developers add the `TELEMETRY` block from `.env.example` to their `.env` to see spans.
