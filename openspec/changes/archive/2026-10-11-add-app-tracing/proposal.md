# Proposal

## Why

The Collector already accepts OTLP and prints spans with its `debug` exporter, but only `telemetrygen` sends it anything. The API emits no telemetry, so a conversation cannot be explained yet. This change makes the API emit traces with a hand-built SDK pipeline (Resource, TracerProvider, BatchSpanProcessor, OTLP exporter). Then an HTTP request to the conversation endpoint shows up in the Collector as a SERVER span, and the outgoing LLM HTTP calls show up as CLIENT spans under it. It is the base that later phase 2 steps add the turn, LLM-call and tool spans with `gen_ai.*` attributes to.

**Phase:** 2 (instrumentation), step A, first app-side piece. Setting up the `TracerProvider`, the sampler and choosing which spans and attributes exist are core (AGENTS.md), so the maintainer writes them and the tasks mark them `TODO(human)`. Dependencies, settings, tests and docs are periphery.

**Scope:** stays within the frozen scope. It adds no tool, agent feature or defense. The agent's behavior does not change.

## What Changes

- The API sets up OpenTelemetry tracing at startup, in the existing FastAPI lifespan. A `Resource` with `service.name` goes into an SDK `TracerProvider` that is registered as the global provider. The provider exports through a `BatchSpanProcessor` and an OTLP/HTTP span exporter that points at the Collector.
- At shutdown the lifespan calls `shutdown()` on the provider, which flushes buffered spans before the process exits.
- **FastAPI server spans come from FastAPI's own native OpenTelemetry support** (added in FastAPI 0.142, on by default, using the global provider), not from `opentelemetry-instrumentation-fastapi`. The app configures it explicitly: automatic exporter setup from `OTEL_*` variables is off, so the hand-built pipeline is the only exporter.
- Outgoing `httpx2` requests (the transport under the Anthropic and OpenAI SDKs) are traced with the `httpx2` instrumentor from `opentelemetry-instrumentation-httpx`, so they appear as CLIENT spans inside the request's trace. Plain `httpx` is not instrumented: no request on a conversation turn goes through it.
- New `TELEMETRY` settings namespace: tracing on/off and the Collector's OTLP endpoint. Tracing is off by default, so tests and CI never try to reach a Collector. The root `.env.example` turns it on for the dev container.
- `fastapi` is upgraded to the latest release (0.143), where automatic exporter setup is opt-in.
- The lifespan keeps `@asynccontextmanager`, but its return annotation changes from `AsyncIterator[None]`, which typeshed deprecates for this decorator, to `AsyncGenerator[None]`. Pyright's `reportDeprecated` is turned on in `apps/api` so deprecated APIs fail `task check` (see design.md).

## Capabilities

### New Capabilities
- `app-tracing`: how the API produces and exports traces: the resource that identifies it, the export pipeline to the Collector, which components are traced automatically (incoming HTTP requests, outgoing `httpx2` calls), and the tracing lifecycle at startup and shutdown. Later phase 2 steps extend it with the turn, LLM-call and tool spans.

### Modified Capabilities
- `app-config`: the settings namespaces requirement gains `TELEMETRY`, plus new requirements for the tracing switch and the OTLP endpoint.

## Impact

- **Code:** `apps/api/src/fornada_api/main.py` (lifespan and `FastAPI(telemetry=...)`), a new telemetry setup module under `apps/api/src/fornada_api/core/`, `core/config.py`.
- **Dependencies (fornada-api):** `fastapi` upgraded to 0.143.x; `opentelemetry-instrumentation-httpx` added (it holds the `httpx2` instrumentor too). `opentelemetry-sdk` and `opentelemetry-exporter-otlp-proto-http` already come with `fastapi[standard]`. They become direct dependencies, since the app imports them.
- **Config:** root `.env.example` gets the `TELEMETRY` block.
- **Tests:** the existing unit tests that start the app with `TestClient` keep tracing off (the default), so they need no Collector. New unit tests cover the tracing setup with an in-memory exporter.
- **Dev environment:** none. The Collector at `edot-collector:4318` is already running from the previous change.
- **Docs:** `apps/api/README.md` gets how to turn tracing on and check spans in the Collector.
