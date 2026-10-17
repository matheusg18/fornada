# Proposal

## Why

Phase 2's "done when" asks that a Kibana latency spike can be traced to "the trace and log that explain it". Traces already reach Kibana APM, but logs do not. The API writes JSON lines to stdout only, and those lines carry no trace id. So when a turn fails (`turn failed`, `tool failed`, `database health check failed`), the traceback lives in a terminal and cannot be joined with the trace that shows which turn, tool call and LLM call it belongs to. This change sends the API's logs through the Collector to Elasticsearch, each one stamped with the trace and span that were active when it was written.

This is **phase 2 (instrumentation), step B, third change**, after `add-elastic-stack` and `add-redacted-elastic-traces`. It stays within the frozen scope. It adds no tool and does not change agent behavior or replies.

## What Changes

- **Log export from the API:** a `LoggerProvider` (same `service.name` resource as the traces, OTLP/HTTP exporter to `/v1/logs`, batched off the request path) and an OpenTelemetry `LoggingHandler` attached to the root stdlib logger, next to the existing stdout JSON handler. Every record that passes the configured level is exported. A record written while a span is active carries that span's trace id and span id.
- **Same switch as tracing:** `TELEMETRY__ENABLED` now turns on traces and logs together. With it off, nothing changes: JSON on stdout only, no connection to a Collector.
- **No feedback loop:** records from the OpenTelemetry SDK's own loggers (for example "failed to export" while the Collector is down) stay on stdout and are not exported.
- **Flush at shutdown:** buffered log records are exported before the process exits, after the last spans.
- **SQL parameters out of exceptions:** the SQLAlchemy engine stops rendering bound parameters in error messages, so a database error logged with its traceback no longer carries customer names, phones or addresses. This affects stdout too.
- **Logs pipeline in the Collector:** a `logs/elastic` pipeline from the same OTLP receiver to Elasticsearch, with the same redaction rules as `traces/elastic` (content attributes deleted, `fornada.customer.phone` hashed with the salt, fail closed). Langfuse does not ingest logs, so there is no Langfuse logs pipeline.
- FastAPI's native telemetry `logs` option stays off. It records request validation failures, whose errors echo the request body (the customer's message).

**Done when:** an ERROR log from a failed turn, opened in Kibana, shows a trace id, and that trace id leads to the same trace in Kibana APM (and in Langfuse).

Out of scope:
- `MeterProvider` and the metrics pipeline (cost, latency and tool-error metrics): the next step B change.
- Logs from the chat and the simulator. They are clients; their spans already join the API's trace.
- Trace and span ids in the stdout JSON lines.
- Detecting PII inside free text in log bodies or exception messages (Presidio, phase 6).

## Capabilities

### New Capabilities

- `app-log-export`: how the API exports its stdlib log records over OTLP: what switches it on, the service identity, trace correlation, which records are kept local, and flushing at shutdown.

### Modified Capabilities

- `telemetry-collector`: a logs pipeline to Elasticsearch, and the redaction requirements ("no conversation content", "phone only as a salted hash", outage isolation) now cover log records as well as spans.
- `app-config`: `TELEMETRY__ENABLED` turns on log export as well as tracing.
- `database-access`: database errors do not include bound parameter values.

## Impact

- `apps/api`:
  - `core/telemetry.py`: build and shut down the logger provider; shared resource.
  - `core/logging.py`: `configure_logging` optionally adds the OTLP handler, so a second call still does not duplicate output.
  - `main.py`: lifespan wiring and shutdown order; the comment on FastAPI's `logs` option.
  - `infrastructure/engine.py`: `hide_parameters=True`.
  - New dependency: `opentelemetry-instrumentation-logging`, which holds the `LoggingHandler` now that the one in `opentelemetry-sdk` is deprecated. Today it is only installed as a transitive dependency.
  - Tests with an in-memory log exporter.
  - Root `.env.example`: the telemetry comment mentions logs.
- `.devcontainer/otel-collector/config.yaml`: the `logs/elastic` pipeline and its redaction processor. **Core:** the pipeline and the OTTL statements are written by the maintainer (`TODO(human)`).
- `AGENTS.md`: the Collector and redaction sections mention logs and how to go from a log to its trace.
- No compose or secret changes: the `otel_writer` role already grants `logs-*-*`.
- Data: Elasticsearch gets `logs-*` data streams. Volume is small (a few records per turn).
- Cost: no token cost. One more batch exporter thread in the API.
