# Design

## Context

- The API's tracing is in `apps/api/src/fornada_api/core/telemetry.py`: `service.name` = `fornada-api`, sampler `ParentBased(ALWAYS_ON)`, `BatchSpanProcessor` with an OTLP/HTTP exporter, behind `TELEMETRY__ENABLED`.
  - FastAPI's native telemetry already calls `propagate.extract` on the request headers with the global propagator, which is the default W3C tracecontext + baggage. So an incoming `traceparent` already makes the SERVER span a child. Nothing changes in the API; a test pins the behavior.
- The chat (`apps/chat`) and the simulator (`apps/simulator`) have no OpenTelemetry code. Both post through a near-identical `client.send_message(http, conversation_id, text)` on `httpx2`.
  - The simulator's settings are pydantic-settings and read the root `.env`, with `extra="ignore"`.
  - The chat reads `CHAT__API_URL` straight from `os.environ`. Chainlit loads `apps/chat/.env`, not the root one.
- The simulator's persona model is `ChatAnthropic` or `ChatOpenAI`, whose SDKs also use `httpx2`.
- The notebook's single-conversation cell builds a plain `httpx.AsyncClient`. It works only because `send_message` uses no API that is specific to `httpx2`.
- Chainlit 2.12 builds its own FastAPI app (`chainlit/server.py`). FastAPI 0.143 traces every request through the **global** provider by default, and no environment variable turns that off. Found at apply: with the chat's provider registered globally, the socket.io websocket became a `WS /ws/socket.io/{path}` span open for the whole tab. Each message ran inside it, so a tab was one trace whose root arrived only on disconnect. See decision 11.
- Chainlit 2.12 pulls in `literalai` → `traceloop-sdk`. `Traceloop.init` runs only when the Literal AI data layer is configured (`LITERAL_API_KEY`), which this project never sets. So the chat process gets no OpenTelemetry provider of its own.
- Langfuse v4 queries observations, not traces. An attribute filters or groups an observation only when that span carries it. So `session.id` must be on the client root span too, not only on the agent's spans.

## Goals / Non-Goals

**Goals:**
- Every turn posted by a client is one trace with the client span as its only root, joined to the API's spans through `traceparent`.
- Simulated conversations can be found in Langfuse by persona and batch.
- No client span is lost when the simulator exits right after a batch.

**Non-Goals:**
- Tracing Chainlit's own server work (websocket, UI) or the persona's LLM calls.
- Baggage, or any value other than `traceparent` read by the API from the client.
- Metrics and logs from the clients, which are step B.
- A shared telemetry package across apps.

## Decisions

### 1. One trace per turn; the client span is the root (maintainer's choice)
- The client span wraps only the `POST` of one customer message. The conversation is the Langfuse session, as on the API side.
- **Alternative:** one long `conversation` span per conversation. It stays open for minutes, and if the process dies before it ends, its children reach Langfuse without their root: exactly the "broken trace" this change must prevent. Langfuse sessions already group turns.

### 2. A hand-made CLIENT span plus `propagate.inject`, not the httpx2 instrumentor
- `send_message` opens the span and calls `propagate.inject(headers)`, then posts with those headers. Only this request is affected, and it works on both `httpx` and `httpx2`.
- **Alternatives:**
  - The global `HTTPX2ClientInstrumentor().instrument()` also instruments the Anthropic and OpenAI SDKs under the persona model. Each persona call would become a root trace with no session, which contradicts decision 4.
  - `HTTPX2ClientInstrumentor.instrument_client(http)` limits it to the API client. But the automatic span starts without `session.id` or the persona, so it needs either a `request_hook` that reads context from a contextvar, or a second span of ours on top. Two spans per turn on the client buy nothing the hand-made one lacks.
- The notebook still moves to `httpx2`, for consistency with the package. The choice above does not depend on it.

### 3. HTTP client semconv, not `invoke_agent` CLIENT
- **Span name:** `POST /conversations/{conversation_id}/messages`, the semconv `{method} {url.template}`, so no id in the name.
- **Attributes:**
  - `http.request.method`, `url.template`, `server.address`, `server.port`;
  - `http.response.status_code` when there is a response;
  - `session.id` and `gen_ai.conversation.id`;
  - on the simulator, `fornada.simulator.persona.id` and `fornada.simulator.run.id`.
- **Alternative:** semconv's remote-agent variant `invoke_agent fornada-attendant` of kind CLIENT. Langfuse would show two AGENT observations per turn, and the client does not know what the agent did, only that it posted to an HTTP API. The HTTP shape also lines up client and SERVER spans for Kibana APM's service map in step B.
- *TODO(human) at apply:* the final attribute set on the client span.

### 4. Persona attributes stay on the client span; the persona's model is not traced (maintainer's choice)
- The API trusts nothing from the client but `traceparent`.
  - Copying baggage into API spans would let any HTTP client write values into the traces.
  - The batch JSONL already links each conversation id to its persona for phase 3.
- With no instrumentor in the simulator, the persona's LLM calls make no spans. A session's Langfuse cost stays the agent's cost.

### 5. Error status on the client span
- ERROR, with no description, for:
  - a transport failure;
  - a timeout;
  - a non-200 status;
  - a 200 body that cannot be read as replies (the client's `bad_body` kind).
- `error.type` follows HTTP semconv: the status code as a string for a non-200, otherwise a low-cardinality kind. `set_status_on_exception=False`, as on the agent spans, so no exception message reaches the status.
- *TODO(human) at apply:* the `error.type` values for transport and body failures (the exception class name or the client's `ApiError.kind`).

### 6. One small `telemetry.py` per client, not a shared package
- Each app gets `build_tracer_provider(settings, exporter=None)` and `setup_tracing(...)`, mirroring the API's module: resource with `service.name`, `ParentBased(ALWAYS_ON)`, `BatchSpanProcessor` with OTLP/HTTP to `{endpoint}/v1/traces`. Spans come from `trace.get_tracer(__name__)`, which is a no-op until setup registers the provider.
- **Alternative:** a fourth workspace member just for about 40 lines. It would couple three apps with different settings loaders.
- *TODO(human) at apply:* the provider in each client (resource, sampler, processor), with a commented suggestion. Core per AGENTS.md.

### 7. Settings
- The simulator gets `TelemetrySettings` (`enabled: bool = False`, `otlp_endpoint`) in its `Settings` as a `telemetry` field, so it reads the same `TELEMETRY__*` lines from the root `.env` as the API.
- The chat reads `TELEMETRY__ENABLED` and `TELEMETRY__OTLP_ENDPOINT` from `os.environ`, as it does `CHAT__API_URL`, with the same defaults.
- One switch for the whole dev stack.

### 8. Flushing and shutdown
- `run_batch` ends with `force_flush()` on the global provider, when it is an SDK provider. That covers the CLI and the notebook alike.
- `__main__` calls `shutdown()` in a `finally`, and the notebook's batch cell needs nothing extra.
- The chat registers `@cl.on_app_shutdown` to shut its provider down, and `@cl.on_app_startup` to set it up.
- **Alternative:** `SimpleSpanProcessor` exports every span synchronously. Nothing is lost, but each turn waits on the Collector. Batch plus an explicit flush keeps the export off the turn path.

### 9. Setup is idempotent per process
- `trace.set_tracer_provider` works once per process. Re-running the notebook's setup cell, or Chainlit's reload (`-w`), must not stack providers.
- `setup_tracing` returns the provider already registered when there is one, so spans are not lost to a second provider that is never registered.

### 11. The chat keeps its provider private, and client spans are always roots (found at apply)
- The chat does not call `trace.set_tracer_provider`. `setup_tracing` builds the provider once per process and keeps it in the telemetry module. The startup hook hands it to `client.py`, whose tracer is a no-op until then.
  - With the global provider left unconfigured, Chainlit's FastAPI telemetry creates no spans, and neither would any other library in the process (Traceloop through `literalai`).
  - This departs from decisions 6 and 9 for the chat only: the API and the simulator own their whole process, while the chat shares its process with Chainlit.
- Both clients start their span with an empty parent context (`context=Context()`), so the span is a root whatever span happens to be current. That keeps the "one trace per turn" shape safe from any future ambient span, in the simulator too.
- **Alternatives:**
  - Only the empty parent: each message is a root again, but every tab still exports a `WS` span, which shows up as an extra trace with no session and no cost.
  - Only the private provider: no `WS` span, but a root then depends on there being no current span, an assumption nobody would notice breaking.

### 10. Verification of "done when"
- Run the default batch (20 conversations) with tracing on in all three apps. Then, for each conversation id in the batch JSONL, query Langfuse `/api/public/v2/observations?sessionId=<id>` and check:
  - every observation has the same `sessionId`;
  - each `traceId` has exactly one observation with no parent, and it comes from `fornada-simulator`;
  - every `parentObservationId` is present in the same trace.
- The script is a one-off in the scratchpad. Its result goes in the PR.

## Risks / Trade-offs

- **[A Collector or Langfuse outage drops client roots but not API spans, leaving the API spans without a root]** → Same pipeline for both, so they fail together. The verification step counts orphan observations.
- **[The default batch costs tokens: about 20 conversations × up to 12 turns, agent + persona]** → Run it once, at the end, after asking the maintainer. Earlier checks use one conversation.
- **[Turns run at concurrency > 1 interleave in one process]** → The span context lives in contextvars, so each `asyncio` task has its own current span. A test runs two conversations concurrently and checks the trace ids are disjoint.
- **[Chainlit's `literalai` turns Traceloop on if `LITERAL_API_KEY` is ever set]** → Traceloop registers its own global provider, so Chainlit's FastAPI spans and Traceloop's would appear. The chat's spans are unaffected (private provider, decision 11). The chat README names the variable as unsupported.
- **[Client clock skew against the API container]** → Same dev container and same clock today. Accepted.

## Migration Plan

No data migration. The `TELEMETRY__*` switch defaults off in both clients, so CI and existing runs are unchanged. Roll back by unsetting `TELEMETRY__ENABLED` or reverting the PR.
