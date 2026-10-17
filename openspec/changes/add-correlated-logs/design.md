# Design

## Context

- **Logging today** (`core/logging.py`): `configure_logging` calls `dictConfig` with one root handler that writes JSON lines to stdout (`python-json-logger`). `dictConfig` replaces the root handlers, which makes the setup idempotent. The lifespan calls it first, before tracing is set up.
- **What the app logs:** a handful of records. `"fornada-api starting"` (model, provider, prompt version), `"conversation turn"` (conversation id, text length, never the text), `"turn failed"` and `"tool failed"` with tracebacks, and `"database health check failed"`. Libraries add their own records, for example `httpx` request lines and the OTel SDK's export warnings.
- **Tracing** (`core/telemetry.py`): `build_tracer_provider` has no global side effects and takes an optional exporter for tests. `setup_tracing` registers it globally because FastAPI's native telemetry looks it up per request. The resource is `service.name=fornada-api` only. The lifespan shuts tracing down last.
- **OTel Python logs API** (SDK 1.45.1): `LoggerProvider`, `BatchLogRecordProcessor` and `OTLPLogExporter` (`exporter.otlp.proto.http._log_exporter`). The `LoggingHandler` in `opentelemetry-sdk` now raises a `DeprecationWarning` and points to the one in `opentelemetry-instrumentation-logging` (0.66b1). That package is in the lockfile today only through a transitive dependency. Its handler:
  - takes the trace context from the active OTel context at `emit` time;
  - turns every non-reserved `LogRecord` attribute (the `extra` keys) into an OTel attribute;
  - adds `exception.type`, `exception.message` and `exception.stacktrace` when `exc_info` is set;
  - uses `record.getMessage()` as the body unless a formatter is attached;
  - has a recursion guard against records produced while emitting.
- **FastAPI's native telemetry** has a `logs` option, off in `main.py`. When on, it emits a record for request validation failures and unhandled exceptions, with messages and stack traces. A validation error echoes the invalid input, which can be the customer's message.
- **Collector:** one OTLP receiver, `traces/langfuse`, `traces/elastic` (with `transform/redact` then `elasticapm`) and `metrics/apm`. The `otel_writer` role already grants `auto_configure` and `create_doc` on `logs-*-*` (decision 7 of `add-redacted-elastic-traces`). In `otel` mapping mode, the `elasticsearch` exporter writes log records to `logs-generic.otel-default`, with `trace_id`, `span_id`, `severity_text`, the body and `attributes.*`.
- **SQLAlchemy** renders bound parameters into `DBAPIError` messages by default (`[parameters: (...)]`). `"tool failed"` logs these errors with their traceback. For a failed `create_order`, that would put a customer's name, phone and address into the log.
- **Core and periphery:** "the pipelines in the Collector config" are core in phase 2, so the `logs/elastic` pipeline and its redaction statements are a `TODO(human)` with a commented sketch. The `LoggerProvider` mirrors the maintainer's `build_tracer_provider` (resource, batch processor, OTLP/HTTP exporter, injectable exporter for tests). It repeats decisions the maintainer already made, so the agent writes it to match and gets no marker.

## Goals / Non-Goals

**Goals:**
- One log record, two outputs: the stdout JSON line stays as it is, and the OTLP copy goes to Elasticsearch with the trace context.
- The OTLP handler cannot be dropped or doubled by reconfiguring logging.
- Elasticsearch gets logs under the same redaction rules as traces, so "Elasticsearch never sees content or a clear phone" stays true for every signal.

**Non-Goals:**
- Trace ids in the stdout lines. They are a convenience for the terminal, not part of "done when".
- A global logger provider for other libraries' native OTel logging.
- Changing what the app logs. The records listed above stay the same.

## Decisions

### 1. Handler from `opentelemetry-instrumentation-logging`, attached directly, not through `LoggingInstrumentor`

The API adds the package with `uv add --package fornada-api opentelemetry-instrumentation-logging` and builds `LoggingHandler(logger_provider=provider)` itself.

- *Alternative: the SDK's `LoggingHandler`.* Rejected. It is deprecated and warns on every construction, and the replacement has the same interface.
- *Alternative: `LoggingInstrumentor().instrument()`.* Rejected. It attaches the handler to the root logger and also wraps `logging.config.dictConfig`, `fileConfig` and `basicConfig` globally to keep its handler alive. It reads `OTEL_PYTHON_LOG_*` variables, too. That conflicts with `app-log-export`'s "only the configured exporter" requirement, and the patching leaks across tests. A handler we build and place ourselves does neither.
- No formatter on the OTLP handler, so the body is the plain message. The JSON formatter belongs to stdout, where the record has no other structure.
- `log_code_attributes` stays off. File, function and line are already in the stack trace when they matter, and turning them on adds three attributes to every record.

### 2. The handler is part of `configure_logging`'s `dictConfig`

`configure_logging(settings, logger_provider=None)` adds an `otlp` handler to the same `dictConfig` (through a `"()"` factory) when a provider is given. Both handlers sit on the root logger, at the root's level.

- Idempotency comes for free. A second call replaces both handlers, as it already does for stdout, so nothing is duplicated, and there is no handler living outside the config that a later `dictConfig` could drop.
- The level filter is the root's (`LOG__LEVEL`), so stdout and OTLP always get the same records. The spec requires this.
- *Alternative: `root.addHandler()` in `setup_telemetry` after `configure_logging`.* Rejected. Any later `dictConfig` call (a second `configure_logging`, or uvicorn's `--log-config`) would silently remove it, and calling the setup twice would add it twice.

### 3. SDK records stay local through a filter on the OTLP handler

The `otlp` handler gets a filter that rejects records whose logger name is `opentelemetry` or starts with `opentelemetry.`. While the Collector is down, the batch exporter logs a warning on each failed export. Without the filter, that warning would be queued for the next export, which would fail and log again. The loop would stay small, about one record per export interval, but it would never end, and those records would bury the app's own records once the Collector comes back. The stdout handler still writes them, and stdout is where an export problem has to be visible.

- *Alternative: rely on the handler's recursion guard.* It only covers records produced synchronously inside `emit`. The export warning comes later, from the batch thread.

### 4. Logger provider: non-global, built like the tracer provider, same switch

- `core/telemetry.py` gains `build_logger_provider(settings, exporter=None)`: the same `Resource` (factored out with the tracer's), a `BatchLogRecordProcessor` and an `OTLPLogExporter(endpoint=f"{otlp_endpoint}/v1/logs")`. Batch defaults are an export every 1 s or 512 records, with a queue of 2048. They are kept: the volume is a few records per turn.
- The provider is **not** registered with `set_logger_provider`. The handler receives it directly. The global would only matter to FastAPI's `logs` option (which stays off, decision 6) or to libraries emitting OTel logs natively (none here). Keeping it local also avoids the set-once-per-process problem that `test_tracing.py` works around for traces.
- `TELEMETRY__ENABLED` switches both signals. A separate `TELEMETRY__LOGS_ENABLED` would add a state, traces without logs, that no phase needs, and one more line in the LGPD map.
- An explicit `endpoint=` overrides `OTEL_EXPORTER_OTLP_*`. The SDK adds no handler on its own. So no `OTEL_*` variable adds a second log path, which the spec requires.
- Lifespan order: build the logger provider, call `configure_logging(settings.log, logger_provider)`, then set up tracing as today. Building does not connect, so this stays cheap and does not fail at startup.

### 5. Shutdown: tracing first, then logs, with the handler detached before the provider stops

At the end of the lifespan:
1. Close the checkpointer and the engine (unchanged).
2. Shut down tracing (unchanged).
3. Call `configure_logging(settings.log)` without a provider, which puts stdout back as the only handler.
4. Shut down the logger provider, which drains the batch queue.

Logs go last so that records written while tracing shuts down, such as an export warning, are still captured on stdout. Detaching the handler first means no record is handed to a provider that has already shut down; the SDK would drop it and warn.

### 6. FastAPI's native `logs` option stays off

Unhandled exceptions are already logged by our own code (`"turn failed"` with the traceback, inside the request's span). The only thing FastAPI's option would add is request validation failures, and their error detail includes the invalid input, which can be customer text. The comment in `main.py` is updated: "off until step B" becomes "off by decision", with the reason. `metrics` stays off until the metrics change.

### 7. Database errors lose bound values and the server's `DETAIL`

Two things carry customer values in a database error, and each needs its own fix:
- `create_async_engine(..., hide_parameters=True)` removes the `[parameters: ...]` line SQLAlchemy renders. The SQL text, with its placeholders, stays; that is enough to tell which statement failed.
- PostgreSQL writes the offending values into the error's `DETAIL:` line (`Failing row contains (305, Maria Teste, +55...)`, `Key (phone)=(...) already exists`). `hide_parameters` does not touch it. Found in task 4.1, when the integration test still failed after the first fix. A `handle_error` listener on the engine (`drop_server_detail`) removes the `DETAIL:` lines from the driver's exception and from SQLAlchemy's copy of its message, which it builds before the event runs.

- It applies to stdout too, which is intended. The values are customer data in either place.
- *Alternative: only `hide_parameters`, with the spec narrowed.* Rejected. The values would still reach logs and Elasticsearch.
- *Alternative: an OTTL `replace_pattern` on `exception.message` and `exception.stacktrace` in the Collector.* Rejected. It would need a pattern for what a `DETAIL` line holds, which is Presidio's job in phase 6, and stdout would still carry the values.
- The checkpointer uses its own psycopg pool, not this engine, so the listener does not cover it. Its tables hold LangGraph state, and an error there is logged by `turn failed`; the section 9 search over `logs-*` is the check.

### 8. Collector: `logs/elastic` with its own redaction processor

Sketch (core: the maintainer writes the final version):

```
logs/elastic:  otlp → transform/redact_logs → elasticsearch/otel
```

```yaml
transform/redact_logs:
  error_mode: propagate
  log_statements:
    - delete_matching_keys(log.attributes, "^gen_ai\\.(input\\.messages|output\\.messages|system_instructions|tool\\.call\\.(arguments|result))$")
    - set(log.attributes["fornada.customer.phone"], SHA256(Concat(["${env:PHONE_HASH_SALT}", log.attributes["fornada.customer.phone"]], ""))) where IsString(log.attributes["fornada.customer.phone"])
    - delete_key(log.attributes, "fornada.customer.phone") where log.attributes["fornada.customer.phone"] != nil and not IsString(log.attributes["fornada.customer.phone"])
```

- The same denylist, salt and fail-closed mode as `transform/redact`, on log attributes. Today the app puts none of these attributes on a log record. The statements are there so the guarantee holds per signal, not per call site: a future `logger.info(..., extra={"fornada.customer.phone": ...})` is hashed with no further change.
- A separate processor, not `transform/redact` with a `log_statements` block added. Either works, because a `transform` processor carries statements per signal. Keeping them separate lets each pipeline's error count point to its own statements. The maintainer decides.
- No `elasticapm` processor in the logs pipeline. *Checked (task 5.1):* the EDOT standalone/gateway reference config page (`elastic.co/docs/reference/edot-collector/config/default-config-standalone`) says "While logs and metrics are exported verbatim into Elasticsearch, traces require two additional components", and its logs pipelines list no `elasticapm`.
- No logs pipeline to Langfuse. Langfuse's OTLP endpoint accepts traces only.
- The body is not redacted. The app's bodies are fixed strings, and the variable parts go in `extra`. Library bodies (such as `httpx`'s `HTTP Request: POST https://api.anthropic.com/... "HTTP/1.1 200 OK"`) carry no customer data. The verification search (section 9) is the check.

### 9. Verification split

- **Unit (agent):** with an `InMemoryLogRecordExporter` and a `SimpleLogRecordProcessor`:
  - body, severity, logger name, extras and exception attributes;
  - trace id and span id inside a span, and none outside;
  - level filtering;
  - SDK records filtered out;
  - the double `configure_logging` call;
  - telemetry off means no OTLP handler;
  - an endpoint variable in the environment does not change the export.
- **Integration (agent):**
  - A request through the app with an in-memory span exporter and an in-memory log exporter, where a scripted model makes a tool fail. The `"tool failed"` and `"turn failed"` records share the SERVER span's trace id.
  - A `traceparent` request, where the trace id comes from the header.
  - A database-error test showing no parameter values in the logged traceback.
- **Pipeline (agent, from `dev`):** start the API with telemetry on and an invalid LLM key (`LLM__ANTHROPIC__API_KEY=sk-ant-invalid`, set in the shell for that run only). Post one message. The provider returns 401, the endpoint answers 503 and logs `"turn failed"` with the traceback inside the SERVER span. Record the trace id from the `traceparent` sent with the request. Then check the Collector's `otelcol_receiver_accepted_log_records` and `otelcol_exporter_sent_log_records`. This needs no code change and no LLM spend.
- **Kibana (maintainer):**
  - In Discover on `logs-*`, filter `severity_text: ERROR` and `service.name: fornada-api`, then open the record and copy its trace id.
  - In APM, open that trace (Kibana's trace link or search by `trace.id`), and find the same id in Langfuse.
  - Check whether the OTel logs template exposes `trace.id` as an alias of `trace_id`, and whether APM's trace view lists the log under "Logs".
  - Run the redaction search: `GET logs-*/_search` with a `query_string` for the phone digits and a message word must return 0 hits, and a `telemetrygen logs` run with `--telemetry-attributes` for `gen_ai.input.messages` and `fornada.customer.phone` must show the attribute deleted and the phone hashed.

## Risks / Trade-offs

- [Span events are not redacted. `transform/redact` and `transform/redact_logs` act on attributes only, so an `exception` event's `exception.message` and `exception.stacktrace` reach Elasticsearch whole, and `elasticapm` turns each one into an error document in `logs-generic.otel-default` (observed in task 6.3)] → Out of scope here: today's exceptions carry provider errors, and database errors lose their bound values and `DETAIL:` line (decision 7). Recorded as a known gap in AGENTS.md for phase 6 (Presidio before Elasticsearch, or `span_event` statements in the Collector).
- [`opentelemetry-instrumentation-logging` is beta (0.66b1), and the logs SDK is still `_logs`, so it is not stable] → Pinned in the lockfile, like the other `0.66b1` instrumentations. The import goes through one module (`core/telemetry.py`).
- [Non-primitive `extra` values (`Decimal`, `datetime`, `UUID`) are not valid OTel attribute values; the SDK drops them with a warning] → The app's current extras are `str` and `int`, and `conversation_id` is already logged as `str(...)`. The stdout line keeps the string form as before. If an extra disappears in Kibana, convert it at the call site.
- [Exception messages from the LLM provider SDKs could carry content] → `add-agent-spans` judged provider errors free of customer text. The section 9 search over `logs-*` is the check, and a hit becomes an OTTL statement on `exception.*` here.
- [Log volume grows with `LOG__LEVEL=DEBUG`, since `httpx`, `httpcore` and `psycopg` debug output would all be exported] → The level is shared with stdout on purpose. DEBUG is a local, short-lived setting. Elasticsearch's 512 MiB heap is the limit to watch.
- [Trace correlation in Kibana depends on field names: OTel mapping writes `trace_id`, while some Kibana views look up `trace.id`] → Section 9 checks it. If the alias is missing, the done-when still holds through Discover (copy `trace_id`, then search it in APM). Any alias or data view setup would be a follow-up, with no app change. *Observed (task 6.1):* the OTel logs template exposes `trace.id` as an alias, the APM trace sample's Logs tab lists the record, and `/app/apm/link-to/trace/<id>` opens the trace from a copied id. No follow-up needed.
- [`hide_parameters=True` makes some database errors harder to debug] → The statement and the error stay, which is usually enough. A local repro can turn it off temporarily. In this project, the customer data matters more.

## Migration Plan

1. `uv sync` picks up the new direct dependency. Restart the API; the Collector restarts with the new config.
2. No secret, compose or role change, because `otel_writer` already covers `logs-*-*`.
3. Rollback: revert the commit and restart. The `logs-*` data streams can be deleted from Dev Tools.
