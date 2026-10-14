# Tasks

The task marked `TODO(human)` is core (AGENTS.md, phase 2: "the pipelines in the Collector config"). The agent leaves the marker with the commented sketch from design.md, then stops and waits for the maintainer. The `LoggerProvider` mirrors the maintainer's `build_tracer_provider`, so the agent writes it to match (design.md, Context). Run `uv run task check` from `apps/api` at the end of each app group.

## 1. Dependency

- [x] 1.1 Run `uv add --package fornada-api opentelemetry-instrumentation-logging` (design.md, decision 1). Verify it is a direct dependency in `apps/api/pyproject.toml`, `uv.lock` resolves it, and `from opentelemetry.instrumentation.logging.handler import LoggingHandler` imports with no `DeprecationWarning`.

## 2. Logger provider and the OTLP handler

- [x] 2.1 Write failing unit tests in `tests/unit/core/test_telemetry.py` and `tests/unit/core/test_logging.py` (`app-log-export` delta), using `InMemoryLogRecordExporter` with `SimpleLogRecordProcessor`:
  - body, severity, logger name, an `extra` attribute, and `exception.type`/`exception.stacktrace` for a record logged in an `except` block;
  - `service.name` = `fornada-api` on the record's resource;
  - trace id and span id equal to an active span's, and no trace id outside a span;
  - a record below `LOG__LEVEL` is neither exported nor written to stdout;
  - a record from logger `opentelemetry.exporter.otlp` reaches stdout and is not exported;
  - two `configure_logging` calls with a provider give one stdout line and one exported record;
  - `configure_logging` without a provider adds no OTLP handler;
  - with `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` set, the built exporter targets `<TELEMETRY__OTLP_ENDPOINT>/v1/logs`.

  Verify they fail.
- [x] 2.2 In `core/telemetry.py`, factor out the resource and add `logs_url` and `build_logger_provider(settings, exporter=None)` (`BatchLogRecordProcessor`, `OTLPLogExporter`, no `set_logger_provider`), mirroring `build_tracer_provider` and its comments. Also add `shutdown_logging(provider)` (design.md, decisions 4 and 5). In `core/logging.py`, give `configure_logging` an optional `logger_provider`. When it is set, it adds an `otlp` handler to the `dictConfig` through a `"()"` factory, with no formatter, with the `opentelemetry` logger filter, and on the root logger next to `stdout` (decisions 2 and 3). Update the module docstrings. Verify the 2.1 tests pass and `uv run task check` passes.

## 3. Lifespan wiring

- [x] 3.1 Write failing tests in `tests/unit/test_tracing.py` (or a sibling `test_log_export.py` that follows its spy pattern):
  - with telemetry off, the lifespan builds no logger provider and the root logger has only the stdout handler;
  - with telemetry on (the builder spied to use an in-memory exporter), a request whose attendant raises gives a `"turn failed"` ERROR record with the SERVER span's trace id;
  - with a `traceparent` header, that record carries the header's trace id;
  - at shutdown the OTLP handler is removed before the provider shuts down, and the provider shuts down after tracing.

  Verify they fail.
- [x] 3.2 Wire `main.py`: when `settings.telemetry.enabled`, build the logger provider, call `configure_logging(settings.log, logger_provider)`, then set up tracing as today. At shutdown, run tracing shutdown, then `configure_logging(settings.log)`, then `shutdown_logging` (design.md, decision 5). Rewrite the comment on FastAPI's `logs` option as a decision with its reason (decision 6). Verify the 3.1 tests pass and `uv run task check` passes.
- [x] 3.3 Update the telemetry block in the root `.env.example`: `TELEMETRY__ENABLED` turns on traces and logs, and the app appends `/v1/logs` as well as `/v1/traces` (`app-config` delta). Verify by reading the file against `TelemetrySettings`.

## 4. No bound parameters in database errors

- [x] 4.1 Write a failing integration test (`tests/integration/`) that makes an insert into `customers` fail with a phone `+5581999991234` and name `Maria Teste` (for example, a duplicate phone, or a value that breaks a constraint), logs the error with `logger.exception`, and asserts that neither value appears in `str(error)` or in the captured log output (`database-access` delta). Verify it fails.
- [x] 4.2 Set `hide_parameters=True` in `create_async_engine` in `infrastructure/engine.py`, and add a `handle_error` listener that drops the server's `DETAIL:` lines (design.md, decision 7). Verify the 4.1 test passes and `uv run task check` passes.

## 5. Collector logs pipeline

- [x] 5.1 Check the EDOT 9.5.5 docs (gateway reference config and the `elasticapm` processor) for whether the logs pipeline should include the `elasticapm` processor, and record the answer in design.md decision 8 as "checked". Verify the design.md note cites the doc page.
- [ ] 5.2 TODO(human): write `transform/redact_logs` (or `log_statements` in `transform/redact`) and the `logs/elastic` pipeline in `.devcontainer/otel-collector/config.yaml` (design.md, decision 8). The agent leaves the marker with the sketch from design.md commented out, and updates the header comment ("Logs and metrics pipelines come later" becomes logs present, metrics later). Verify the Collector starts cleanly (maintainer: `docker compose -p fornada_devcontainer logs edot-collector`). Then, after one API log record with telemetry on, `curl -s edot-collector:8888/metrics | grep log_records` shows `otelcol_receiver_accepted_log_records` and `otelcol_exporter_sent_log_records` for `elasticsearch/otel` growing, with no failed records.
- [ ] 5.3 Update AGENTS.md: the Collector bullet (logs pipeline to Elasticsearch only), the redaction bullet (the same rules on log records), and a short "from a log to its trace" recipe in Kibana (Discover on `logs-*`, filter `severity_text: ERROR`, copy `trace_id`, open it in APM and Langfuse). Verify the documented queries run as written in Kibana Dev Tools (maintainer).

## 6. End-to-end verification

- [ ] 6.1 Failed turn ("Pronto quando"): start the API with `TELEMETRY__ENABLED=true` and an invalid `LLM__ANTHROPIC__API_KEY` set in the shell for that run only. Post one message with a known `traceparent`. Expect a 503, and stdout shows the `"turn failed"` JSON line with the traceback. In Kibana, the maintainer finds the ERROR record in Discover (`logs-*`, `service.name: fornada-api`), reads its trace id (the one from the `traceparent`), opens that trace in Kibana APM, and finds the same trace id in Langfuse. Record whether `trace.id` works as an alias and whether APM's trace view lists the log (design.md, Risks). Verify with the maintainer's observations, recorded in this task.
- [ ] 6.2 Redaction on logs: send one log record from `dev` with a short Python OTLP script in the scratchpad (same approach as `add-redacted-elastic-traces` task 6.1). It carries `gen_ai.input.messages` with a customer message and `fornada.customer.phone` = `+5581999991234`. In Kibana Dev Tools, the record has no content attribute and has the same 64-hex phone hash that span `f7732a8e564b611a3818154a8911191e` got. `GET logs-*/_search` for `"5581999991234"` and for a word from the message returns 0 hits. Also search `logs-*` for the phone digits and customer names from a real simulator run with telemetry on, and expect 0 hits. Verify with the queries and hit counts, recorded in this task.
- [ ] 6.3 Outage: with `langfuse-web` stopped, a failed turn's log record still reaches Elasticsearch. With the Collector stopped, a turn still answers normally, stdout shows the SDK's export warnings, and the warnings do not show up in Elasticsearch after the Collector is back (`app-log-export`: SDK records stay local). Verify with the Collector's `log_records` metrics and a `logs-*` search for `logger`/scope `opentelemetry.*` returning 0 hits.

## Workflow follow-up

- Archive the change after the maintainer's review, and sync the `app-log-export`, `telemetry-collector`, `app-config` and `database-access` specs.
- Remind the maintainer that the next step B change is metrics (`MeterProvider`, the metrics pipeline: cost, latency and tool-error metrics).
