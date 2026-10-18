# Design

## Context

- **Telemetry today** (`core/telemetry.py`): `build_tracer_provider` and `build_logger_provider` have no global side effects and take an optional exporter for tests. Both use `build_resource()` (`service.name=fornada-api`) and an explicit OTLP/HTTP `endpoint=` so no `OTEL_*` variable redirects them. `setup_tracing` registers the tracer provider globally; the logger provider stays local. The lifespan shuts tracing down, then logging.
- **Where measurements can come from:** the three hand-made spans already sit at the right boundaries.
  - `GraphAttendant.reply` (`attendant.py`) wraps the turn in `invoke_agent fornada-attendant`, sets `error.type` to the exception class on failure, and reads the graph's final state.
  - `call_model` (`nodes.py`) wraps each model call in `chat {model}`, knows `gen_ai.provider.name` and `gen_ai.request.model` from `_get_ls_params()`, reads `gen_ai.response.model` and token usage from the answer, and sets `error.type` to the exception class on failure.
  - `wrap_tool_call` (`nodes.py`) wraps each tool call in `execute_tool {tool}`. A tool fails by returning a `ToolMessage` with `status="error"`, which marks the span ERROR with `error.type=tool_error`; a raised exception sets the class name. A full day is not an error (`agent-tracing` spec).
- **Semconv**, `open-telemetry/semantic-conventions-genai` at commit `547934a` (2026-10-18), all in development status:
  - model calls: `gen_ai.client.inference.duration` (histogram, s), `gen_ai.client.inference.operation.input_tokens` and `.output_tokens` (histograms, {token}), plus `gen_ai.client.inference.usage.*` counters. `gen_ai.client.operation.duration` "SHOULD NOT be reported for inference operations", and `gen_ai.client.token.usage` is gone;
  - `gen_ai.invoke_agent.duration` and `gen_ai.execute_tool.duration` (histograms, s);
  - explicit bucket boundaries are given for every one of them; none defines cost;
  - required attributes: `gen_ai.operation.name` and `gen_ai.provider.name` on inference, `gen_ai.tool.name` on tool duration; `error.type` when the operation failed.
  The span names in `tracing.py` were read at an earlier commit (`6fd0d76`). This change does not rename spans.
- **Elasticsearch exporter** (EDOT 9.5.5, `otel` mapping): histograms and exponential histograms are **delta only**; cumulative ones are dropped with a warning. Explicit-bucket histograms are stored as a `histogram` field, on which Kibana computes percentiles. Counters become numeric fields. The `otel_writer` role already grants `metrics-*-*`.
- **Persona:** only the simulator knows it, on its client span (`fornada.simulator.persona.id`). The ids are `apressada`, `indecisa`, `pechincheira`, `mae_alergica` and `malandro` (`apps/simulator/.../personas.py`). The clients already call `propagate.inject(headers)` with the default propagator (`tracecontext,baggage`), and the API's FastAPI native telemetry extracts with the same global propagator. The httpx2 instrumentor injects with it too, on every call to the model provider.
- **Pricing:** no price lives anywhere in the code. `LlmSettings` has per-provider `api_key` and `model`.
- **Core and periphery:** phase 2 core is "`TracerProvider`, sampler, which spans and attributes exist, the pipelines in the Collector config". The `MeterProvider` is new ground (temporality and reader are decisions the maintainer has not made yet), so are the instruments and the Collector metrics pipeline. Recording calls next to existing spans, settings, the simulator baggage, the dashboard and compose are periphery or repeat earlier decisions.

## Goals / Non-Goals

**Goals:**
- Every measurement is taken where its span ends, with the same attributes the span already carries (minus the high-cardinality ones), so a metric outlier and its traces agree.
- Bounded series: at most providers × models × 9 tools × 2 outcomes × 7 persona values.
- Nothing personal leaves through metrics, even if a later change adds a bad attribute: the Collector guard is a second line.

**Non-Goals:**
- `fornada.prompt.version` as a dimension. It is low-cardinality and would help compare `v0` with later versions, but the dimensions asked for are tool, model and persona; the `v0`-vs-current dashboard (phase 4) is where it belongs, together with eval results.
- Renaming spans to the newer semconv commit.
- `gen_ai.client.inference.usage.*` counters, FastAPI HTTP metrics, database metrics, exemplars.
- A Kibana dashboard per persona or per model: filters on one dashboard are enough.

## Decisions

### 1. `MeterProvider` built like the other two, registered globally, delta, 10 s

`core/telemetry.py` gains `metrics_url`, `build_meter_provider(settings, exporter=None)` returning a `MeterProvider` with the shared resource and one `PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=metrics_url(settings), preferred_temporality=<delta for Counter, Histogram, ObservableCounter>), export_interval_millis=10_000)`, plus `setup_metrics` (calls `metrics.set_meter_provider`) and `shutdown_metrics` (`provider.shutdown()`, which collects and exports one last time).

- **Global**, unlike the logger provider: instruments are created at import time from `metrics.get_meter(__name__)`, the same proxy pattern as `tracing.tracer`. With metrics off the proxy stays a no-op and recording costs almost nothing. Tests that need the SDK use the same workaround `test_tracing.py` uses for the set-once global, or inject an `InMemoryMetricReader` through `build_meter_provider`.
- **Delta in the app**, not `cumulativetodelta` in the Collector: one place, and the SDK does not keep cumulative state for series nobody reads. *Alternative: Collector processor.* Rejected: it keeps per-series state in the Collector and a Collector restart resets it, losing a point.
- **10 s interval** instead of the 60 s default: a simulator batch lasts a few minutes, and with 60 s the p95 panel would have a handful of points. Volume stays tiny (a few dozen series).
- *Alternative: `UpDownCounter`/gauges for cost.* Rejected: spend only grows, a counter is what Kibana sums.
- **Instrumentors' metrics dropped** (found in task 5.2): once the global provider exists, the httpx2, SQLAlchemy and psycopg instrumentors record their default metrics (`http.client.request.duration`, `db.client.*`) through it. The Collector guard strips all their attributes, so they arrived as unlabeled totals, and APM already derives database and HTTP dependency latency from the spans. The provider drops their meters with `View(meter_name=..., aggregation=DropAggregation())`; psycopg's `instrument_connection` takes no meter provider, so a view is the one switch for all three. Turn one back on, with its attributes in the guard, when an observed failure needs it (e.g. `db.client.connections.usage` for pool exhaustion).

`TODO(human)` with a commented sketch: the reader, temporality map and interval.

### 2. Instruments in `agents/attendant/metrics.py`, next to `tracing.py`

The module holds metric names, units, bucket lists (semconv advisory `explicit_bucket_boundaries_advisory`), the instruments, and the persona allowlist. Same rule as `tracing.py`: names are plain strings, so a convention bump is one diff here.

| Instrument | Kind | Unit | Recorded in | Attributes |
|---|---|---|---|---|
| `gen_ai.client.inference.duration` | Histogram | `s` | `call_model` | operation, provider, request model, response model, error.type, persona |
| `gen_ai.client.inference.operation.input_tokens` | Histogram | `{token}` | `call_model` | same |
| `gen_ai.client.inference.operation.output_tokens` | Histogram | `{token}` | `call_model` | same |
| `gen_ai.invoke_agent.duration` | Histogram | `s` | `GraphAttendant.reply` | operation, agent name, request model, error.type, persona |
| `gen_ai.execute_tool.duration` | Histogram | `s` | `wrap_tool_call` | tool name, tool type, agent name, error.type, persona |
| `fornada.tool.calls` | Counter | `{call}` | `wrap_tool_call` | tool name, error.type, persona |
| `fornada.gen_ai.cost` | Counter (float) | `USD` | `call_model` | provider, request model, persona |
| `fornada.conversations` | Counter | `{conversation}` | `GraphAttendant.reply` | agent name, persona |

- Durations come from `time.perf_counter()` around the same awaited call the span wraps, not from the span (a no-op span has no times). They match the span within a few ms.
- `GraphAttendant` needs the request model for `gen_ai.invoke_agent.duration`: `main.py` passes `settings.llm.active.model` to it.
- `error.type` on metrics is exactly the value the span gets, in the same branch.

`TODO(human)` with a commented sketch: the instrument definitions (names, kinds, units, buckets). The recording calls next to the spans are written by the agent.

### 3. One `fornada.tool.calls` counter, not a separate error counter

The request is "a tool error counter". A counter of all calls with `error.type` on failures gives the errors (filter `error.type: *`) **and** the denominator for an error rate in one series family. An errors-only counter would need the denominator from the `gen_ai.execute_tool.duration` histogram's count, which Lens formulas handle poorly on `histogram` fields.

- *Alternative: only `gen_ai.execute_tool.duration` with `error.type`.* Rejected for the same Lens reason; it stays for tool latency.

### 4. Cost: priced in the app, per provider settings, a counter

`fornada.gen_ai.cost += input_tokens × input_price / 1e6 + output_tokens × output_price / 1e6`, with prices from `LLM__<PROVIDER>__INPUT_USD_PER_MTOK` and `__OUTPUT_USD_PER_MTOK` (`Decimal`, `ge=0`, converted to float when recorded). Defaults are the published prices of each provider's default model, checked at implementation time and cited in a comment with the date.

- Cache tokens: LangChain's input count already includes cache reads and writes (decision 6 of `add-agent-spans`) and the app does not enable prompt caching, so input × input price is the bill. If caching is turned on later, this overstates cost; recorded in Risks.
- If `LLM__<PROVIDER>__MODEL` differs from the default and no price is set, the API logs a WARNING at startup (`app-config` delta). It does not refuse to start: a wrong cost number is better than no agent in a simulator run.
- *Alternative: price in Kibana from token counters.* Rejected: Lens would need a price table per model in every formula, and the token histograms are explicitly "not for total usage or cost" in semconv.
- *Alternative: price in Langfuse.* Langfuse already computes cost from `gen_ai.usage.*` on spans, but that number stays in Langfuse; Kibana is where the final dashboard and latency live. The two numbers should agree; a mismatch is a pricing bug.

### 5. Cost per conversation = sum of cost ÷ conversations started

The API does not know when a conversation ends (the client stops posting). `fornada.conversations` grows by 1 when a turn completes and no model answer without tool calls (a turn's final reply) comes before its customer message, i.e. it was the conversation's first successful turn. A failed turn never reaches a final reply, but the checkpointer does keep its customer message and any tool round it finished (checked during apply: after a failed model call the state holds the `HumanMessage`), so counting customer messages would miss a conversation whose first message failed and was retried.

- Gives the **mean** per conversation over any time range, filterable by model and persona. The distribution (p95 conversation cost) comes from traces: sum `gen_ai.usage.*` per `session.id` in Langfuse.
- A conversation that spans the edge of the selected range is split; with ranges of a batch or longer the error is small.
- *Alternatives:* a per-turn cost histogram (gives cost per turn, not per conversation) and an explicit end-of-conversation signal (adds API surface; frozen scope). Rejected; the maintainer chose the ratio.

### 6. Persona: W3C Baggage in, allowlist, then dropped

- **Simulator:** around each post, when tracing is enabled, it attaches a context with `baggage.set_baggage("fornada.simulator.persona.id", persona_id)`; the existing `propagate.inject(headers)` then writes both `traceparent` and `baggage`. With tracing off, it sets no baggage, so the default propagator writes nothing (the `client-tracing` "tracing off" scenarios). The run id stays on the span only. The chat does not change.
- **API, at the turn boundary** (`GraphAttendant.reply`): read the entry from the current context (FastAPI's native telemetry extracted it), map it through the allowlist (`other` / `none`), store the result in a `ContextVar` the recording helpers read, then `context.attach(baggage.clear())` for the rest of the turn and detach at the end. LangGraph runs nodes in asyncio tasks, which copy both the `ContextVar` and the cleared OTel context.
- **Why clear it:** the httpx2 instrumentor injects with the global propagator, so without this every call to Anthropic or OpenAI would carry the client's baggage. The persona id is harmless, but baggage is untrusted input of any size and content, and forwarding it to a third party is a free side channel. Clearing it at the boundary also keeps it off any future span processor that copies baggage.
- **Why an allowlist:** a client could send any value and create a series per request (a cardinality attack on Elasticsearch). The API keeps its own copy of the five ids; a test in the simulator app asserts its ids match the API's list, so adding a persona fails CI until both change.
- *Alternative: a custom `X-Fornada-Persona` header.* Rejected: baggage is the standard carrier, already injected by the clients' propagator, and needs no API schema change.
- *Alternative: persona metrics only in the simulator.* Rejected by the maintainer: cost per persona would be impossible.

### 7. Collector `metrics/elastic` pipeline with an attribute guard

```yaml
processors:
  transform/metrics_guard:
    error_mode: propagate
    metric_statements:
      - keep_matching_keys(datapoint.attributes, "^(gen_ai\\.(operation\\.name|provider\\.name|request\\.model|response\\.model|agent\\.name|tool\\.name|tool\\.type)|error\\.type|fornada\\.simulator\\.persona\\.id)$")
service:
  pipelines:
    metrics/elastic:
      receivers: [otlp]
      processors: [transform/metrics_guard]
      exporters: [elasticsearch/otel]
```

- An allowlist (keep), not a denylist like the trace redaction: metrics have a closed set of dimensions, so anything else is a bug, and dropping it is safe. Denylisting would miss the next new high-cardinality attribute.
- Fails closed, like the other transforms. No `elasticapm` processor: it is for traces.
- `metrics/apm` (the connector's output) is untouched.
- Langfuse gets no metrics pipeline: it has no OTLP metrics ingestion and computes its own from traces.

`TODO(human)` with this sketch commented in `config.yaml`.

### 8. Dashboard as saved objects, imported by a one-shot `kibana-setup`

- `.devcontainer/kibana/fornada-metrics.ndjson`: one data view (`metrics-*`, time field `@timestamp`) and one dashboard with Lens panels:
  - **Cost per conversation** (metric + line over time): formula `sum(metrics.fornada.gen_ai.cost) / sum(metrics.fornada.conversations)`, filter `service.name: fornada-api`.
    The line uses running sums, `cumulative_sum(sum(...cost)) / cumulative_sum(sum(...conversations))`: per time bucket the plain ratio is meaningless, since a conversation is counted on its first turn but costs on every turn (found in task 6.2).
  - **p95 turn latency** (line): `percentile(metrics.gen_ai.invoke_agent.duration, percentile=95)`, broken down optionally by model.
  - **Error rate per tool** (bar): `sum(metrics.fornada.tool.calls, kql='attributes.error.type: *') / sum(metrics.fornada.tool.calls)`, broken down by `attributes.gen_ai.tool.name`.
  - Dashboard-level controls for `attributes.gen_ai.request.model` and `attributes.fornada.simulator.persona.id`.
  Field paths follow the exporter's `otel` mapping and are checked against real documents before the panels are built.
- The panels are built in Kibana's UI against real data from a simulator batch, then exported (`POST /api/saved_objects/_export`) into the file. Hand-writing Lens JSON is brittle.
- `kibana-setup` compose service: Elasticsearch image (for curl, like `elasticsearch-setup`), `restart: "no"`, `depends_on: kibana: service_healthy`, `POST /api/saved_objects/_import?overwrite=true` as `elastic` with `ELASTIC_PASSWORD`. Nothing depends on it, so `dev` never waits and a failure only shows in its logs.
- *Alternative: document a manual import.* Rejected: a fresh volume would lose the dashboard, and "done when" should hold after `docker compose down -v`.

### 9. Verification

- Unit tests with `InMemoryMetricReader` (`build_meter_provider` takes a reader in tests instead of an exporter): each instrument, its attributes, delta temporality, bucket boundaries, persona mapping, no baggage on the outgoing provider request (httpx2 mock transport), first-turn counting, no attribute outside the allowlist with content capture on.
- End to end: a simulator batch with `CHAOS__ENABLED=true` and telemetry on, then the dashboard; the Collector's `otelcol_exporter_sent_metric_points`; the Langfuse cost of the same batch next to the Kibana sum, as a cross-check on pricing.

## Risks / Trade-offs

- [Semconv metric names change again] → Names live in one module; spec cites the commit. The spans keep the older names until a dedicated change.
- [Default prices go stale, or prompt caching is turned on] → Prices are settings with a dated comment; the Langfuse cost cross-check in verification catches drift; caching would need cache-token attributes and a new price pair (a later change).
- [Baggage extraction depends on FastAPI's native telemetry using the global propagator] → A unit test posts with a `baggage` header through the real app and asserts the persona on the measurement; if it fails, extract explicitly in the endpoint.
- [Persona allowlist drifts from the simulator] → Cross-app test (decision 6); unknown values degrade to `other`, never a new series.
- [Mean cost per conversation hides the tail] → The tail comes from traces per session; the dashboard labels the panel as a mean.
- [10 s export adds load] → A few dozen series; negligible next to the trace volume.
- [`kibana-setup` uses the `elastic` superuser] → Same as `elasticsearch-setup`, inside the compose network, one-shot; a dedicated Kibana role would add a user and a secret for one import.
- [Lens on `histogram` fields from the OTel exporter] → Checked on real data before the dashboard is exported; fallback is ES|QL `PERCENTILE` in the panel.

## Migration Plan

Additive. With `TELEMETRY__ENABLED=false` nothing changes. Rollback: revert the commits; the `metrics-*` data streams can be deleted from Kibana's Dev Tools, and the dashboard from Saved Objects. The `client-tracing` change only adds a header that the API ignores before this change.
