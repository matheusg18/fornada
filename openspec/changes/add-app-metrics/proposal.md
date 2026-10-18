# Proposal

## Why

Phase 2's "done when" asks that a Kibana latency spike can be traced to the trace and log that explain it, and the final dashboard puts cost per conversation, p95 latency and tool error rate next to `v0`. Today the API exports traces and logs but no metrics. The only latency numbers in Kibana come from the `elasticapm` connector, which knows HTTP transactions and nothing about models, tools, tokens or money. Cost per conversation, a first-class metric under the US$ 20/month ceiling, cannot be read anywhere without summing spans by hand. This change adds the API's metrics and a Kibana dashboard that shows cost per conversation, p95 latency and error rate per tool.

This is **phase 2 (instrumentation), step B, last change**, after `add-elastic-stack`, `add-redacted-elastic-traces`, `add-correlated-logs` and `add-database-spans`. It stays within the frozen scope: it adds no tool and does not change agent behavior or replies.

## What Changes

- **`MeterProvider` in the API:** same `service.name` resource as traces and logs, OTLP/HTTP exporter to `/v1/metrics`, periodic export off the request path, **delta temporality** (Elasticsearch drops cumulative histograms), flushed at shutdown. Same switch as the other signals, `TELEMETRY__ENABLED`.
- **GenAI semconv instruments**, following `open-telemetry/semantic-conventions-genai` at commit `547934a` (2026-10-18). The conventions moved since the spans were written: `gen_ai.client.token.usage` and `gen_ai.client.operation.duration` for model calls were replaced by the `gen_ai.client.inference.*` family. The API records:
  - `gen_ai.client.inference.duration` (s) per model call;
  - `gen_ai.client.inference.operation.input_tokens` and `.output_tokens` ({token}) per model call;
  - `gen_ai.invoke_agent.duration` (s) per turn, the latency the dashboard's p95 reads;
  - `gen_ai.execute_tool.duration` (s) per tool call.
  Each uses the semconv explicit bucket boundaries.
- **Fornada's own instruments**, where semconv has none:
  - `fornada.tool.calls`: a counter of tool calls, with `error.type` on the failed ones. It is the tool error counter and its own denominator.
  - `fornada.gen_ai.cost` (USD): a counter of model spend per model call, priced from per-provider settings (USD per million input and output tokens).
  - `fornada.conversations`: a counter of conversations started (first successful turn).
  Cost per conversation = `sum(fornada.gen_ai.cost) / sum(fornada.conversations)` over the dashboard's time range.
- **Low-cardinality dimensions only:** the semconv ones (`gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.agent.name`, `gen_ai.tool.name`, `error.type`) plus the persona. Never a conversation id, session id, phone, call id or any content.
- **Persona reaches the API through W3C Baggage.** **BREAKING** for the `client-tracing` spec, which today forbids the API from reading the persona. The simulator adds `fornada.simulator.persona.id` to the baggage of each post. The API reads it only as a metric dimension, mapped through an allowlist of the five persona ids (anything else becomes `other`, no baggage becomes `none`), and never puts it on a span. Baggage stops at the API: it is not forwarded to the model provider.
- **Metrics pipeline in the Collector:** `metrics/elastic`, from the OTLP receiver to Elasticsearch, with a guard that drops any high-cardinality or personal attribute that slips into a data point. Langfuse gets no metrics.
- **Kibana dashboard, versioned:** a saved-objects NDJSON in the repo, imported on every start by a one-shot compose service, with three panels: cost per conversation, p95 turn latency, and error rate per tool, each splittable by model and persona.

**Done when:** after a simulator batch with chaos mode on, the Kibana dashboard shows cost per conversation, p95 turn latency and a non-zero error rate for `check_capacity`, and each panel can be split by persona.

Out of scope:
- FastAPI's native HTTP metrics (`telemetry={"metrics": ...}` stays off) and the database client metrics.
- The `gen_ai.client.inference.usage.*` token counters; cost is the spend metric here.
- Metrics from the chat or the simulator.
- Alerts. They come with online evals in phase 6.
- Prompt version as a dimension (design.md, Non-Goals).

## Capabilities

### New Capabilities

- `app-metrics`: the API's metrics: what switches them on, the instruments, their units and buckets, the allowed dimensions, how cost is priced, the persona dimension, export temporality and flushing at shutdown.
- `kibana-dashboards`: dashboards kept as versioned saved objects and loaded into the dev Kibana, starting with the metrics dashboard.

### Modified Capabilities

- `client-tracing`: the simulator propagates the persona in W3C Baggage; the API may read it for metrics but still puts it on no span.
- `telemetry-collector`: a metrics pipeline to Elasticsearch with an attribute guard; metric delivery is observable from the dev container.
- `app-config`: `TELEMETRY__ENABLED` also switches metric export; new per-provider token price settings.

## Impact

- `apps/api`:
  - `core/telemetry.py`: `build_meter_provider`, `setup_metrics`, `shutdown_metrics`, `metrics_url`.
  - New `agents/attendant/metrics.py`: instrument names, the instruments and the persona allowlist, next to `tracing.py`.
  - `agents/attendant/nodes.py` and `attendant.py`: record measurements where the spans already end; read and drop the baggage at the turn boundary.
  - `core/config.py`: token prices per provider.
  - `main.py`: lifespan wiring and shutdown order.
  - Tests with `InMemoryMetricReader`.
  - Root `.env.example`.
  - New dependency: none expected; `opentelemetry-exporter-otlp-proto-http` already holds the metric exporter.
- `apps/simulator/client.py`: baggage on each post.
- `.devcontainer/otel-collector/config.yaml`: `metrics/elastic` pipeline and guard. **Core** (`TODO(human)`).
- `.devcontainer/compose.yaml` and `.devcontainer/kibana/`: the dashboard NDJSON and a `kibana-setup` one-shot service.
- `AGENTS.md`: metrics, the dashboard, and how to check metric delivery.
- Data: Elasticsearch gets `metrics-*` data streams from the app; a handful of series, one data point per series every export interval.
- Cost: no token cost. One more export thread in the API.
