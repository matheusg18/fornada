# Proposal

## Why

A conversation turn talks to PostgreSQL through two paths: the SQLAlchemy engine the tools use, and the separate psycopg pool behind LangGraph's checkpointer, which reads and writes the conversation state on every turn. Neither produces a span today, so a trace shows gaps where the database time goes. Phase 2 is done only when a Kibana latency spike can be traced to the trace that explains it, and a slow query or a slow checkpoint write is a likely cause that the trace cannot show yet.

This change belongs to **phase 2 (instrumentation)**, step B. It comes before the `MeterProvider` change on purpose: once a meter provider exists, the same instrumentations also emit database client metrics (`db.client.connections.usage` from SQLAlchemy, `db.client.operation.duration` from psycopg), so the metrics change picks them up without touching the database code again.

It stays within the frozen scope: no tool, feature or UI changes. It only adds telemetry.

## What Changes

- Each SQL statement the tools run through the SQLAlchemy engine produces a CLIENT span, a child of the tool's `execute_tool` span.
- Each statement the checkpointer runs through its own psycopg pool produces a CLIENT span in the turn's trace.
- Each statement is traced once. The two instrumentations are scoped to their own connections, so a tool query is not traced again at the psycopg level.
- Database spans carry the SQL text with its placeholders and never the bound values. A failed statement's span keeps the error class but not PostgreSQL's `DETAIL:` line on the engine path.
- The database spans use the stable OpenTelemetry database conventions (`db.query.text`, `db.namespace`, `db.system.name`), opted in the same way the HTTP conventions already are.
- With tracing off, nothing is instrumented.
- `opentelemetry-instrumentation-sqlalchemy` and `opentelemetry-instrumentation-psycopg` become direct dependencies of `fornada-api`. Today a copy of the SQLAlchemy one is in the virtualenv only as a transitive dependency of Chainlit, which the API must not rely on.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `app-tracing`: adds requirements for database CLIENT spans on both database paths, one span per statement, no bound values in spans, and no instrumentation when tracing is off.

## Impact

- **Code:** `apps/api/src/fornada_api/core/telemetry.py` (instrument and uninstrument the engine, and the database semconv opt-in), `infrastructure/checkpointer.py` (instrument each pooled connection), `main.py` (lifespan order: the engine and the checkpointer are instrumented after the tracer provider exists).
- **Dependencies:** `opentelemetry-instrumentation-sqlalchemy` and `opentelemetry-instrumentation-psycopg` (0.66b1, the same release line as the existing instrumentations). The latter pulls in `opentelemetry-instrumentation-dbapi`.
- **Telemetry volume:** a turn gains roughly a dozen short spans, in Langfuse and in Elasticsearch alike. Langfuse's pipeline has no filter, so they also appear in the LLM view.
- **Collector:** no config change. `db.query.text` holds placeholders, not values, so the existing redaction still covers every content attribute.
- **Docs:** `AGENTS.md`, Logs and traces section: how to find a turn's database spans.
