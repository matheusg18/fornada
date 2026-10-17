# Design

## Context

See proposal.md for the motivation. Current state:

- **Two database paths, one driver.** The tools use the async SQLAlchemy engine (`infrastructure/engine.py`, `postgresql+psycopg`, `hide_parameters=True` and the `drop_server_detail` `handle_error` listener). LangGraph's `AsyncPostgresSaver` uses its own `psycopg_pool.AsyncConnectionPool` (`infrastructure/checkpointer.py`). Underneath, both open `psycopg.AsyncConnection`s.
- **Tracing setup** (`core/telemetry.py`): `setup_tracing` registers the global provider, sets `OTEL_SEMCONV_STABILITY_OPT_IN` with `setdefault("…", "http")` and instruments `httpx2`. `shutdown_tracing` uninstruments, then shuts the provider down. Tests build providers with an in-memory exporter and never register the global one more than once per process.
- **Lifespan order today** (`main.py`): `get_engine()`, then `Checkpointer(url)`, then `setup_tracing`, then `checkpointer.open()`.
- **Instrumentations, as read from the 0.66b1 wheels:**
  - `opentelemetry-instrumentation-sqlalchemy`: `SQLAlchemyInstrumentor().instrument(engine=…, tracer_provider=…)` adds `before/after_cursor_execute` and `handle_error` listeners to that engine. One CLIENT span per statement, named `<first SQL word> <database>`. On error, its `handle_error` listener sets status ERROR with `str(original_exception)` and records no exception event. `instrument()` also always wraps `create_engine`, `create_async_engine` and `Engine.connect` process-wide; the last one makes a `connect` CLIENT span on every connection checkout. It creates the `db.client.connections.usage` counter from the meter provider (the global one by default).
  - `opentelemetry-instrumentation-psycopg`: `PsycopgInstrumentor().instrument()` wraps `psycopg.connect`, `Connection.connect` and `AsyncConnection.connect` process-wide. `PsycopgInstrumentor.instrument_connection(conn, tracer_provider=…)` instead swaps one connection's `cursor_factory` for a traced subclass of `AsyncCursor`, so `execute`, `executemany` and `callproc` make spans. It accepts async connections. `capture_parameters` defaults to off. It is built on `opentelemetry-instrumentation-dbapi`, whose spans record the exception as an event and use its message as the status description. `db.client.operation.duration` is only emitted with the database semconv opt-in.
- **The checkpointer** opens cursors with `conn.cursor(binary=True, row_factory=dict_row)` and writes in pipeline mode (`conn.pipeline()` with `executemany`).

## Goals / Non-Goals

**Goals:**

- Database CLIENT spans on both paths, each statement once, in the turn's trace.
- No bound values in database spans. On the engine path, no `DETAIL:` line either.
- Explicit tracer provider everywhere, so tests can use an in-memory one.

**Non-Goals:**

- Metrics. The instrumentations will emit them once a meter provider exists, which is the next change.
- sqlcommenter (`enable_commenter`). It rewrites the SQL sent to PostgreSQL to append trace context. Nothing here reads it.
- The span-event gap on the checkpointer path (see Risks). It is the same gap already recorded for phase 6.

## Decisions

### 1. SQLAlchemy instrumentation on the engine, not psycopg for everything

`SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine, tracer_provider=provider)`.

The alternative was one global `PsycopgInstrumentor().instrument()`, which covers both paths with a single package and no duplicates. It was rejected because of the error path. The psycopg span ends inside `cursor.execute`, before SQLAlchemy's `handle_error` event runs. So `drop_server_detail` would strip `DETAIL:` from the log but not from the span, which would keep PostgreSQL's row values in its status description and exception event. SQLAlchemy's own listener is registered after `drop_server_detail` (the engine is built first), and listeners run in registration order. So it sees the already-cleaned message, and it records no exception event at all. SQLAlchemy is also where the pool metrics come from.

What comes with it: `instrument()` wraps `Engine.connect` for the whole process. Each session checkout gets a short `connect` CLIENT span, which includes the `pool_pre_ping` round trip. That is accepted: it is where a slow or saturated pool would show up.

### 2. psycopg instrumentation per connection, through the pool's `configure` callback

`AsyncConnectionPool(…, configure=…)` runs an async callback on each new connection. It calls `PsycopgInstrumentor.instrument_connection(conn, tracer_provider=provider)`. Only the checkpointer's connections get traced cursors, and the engine's connections, which SQLAlchemy already traces, do not. That is what keeps one span per statement. A global `PsycopgInstrumentor().instrument()` would wrap `AsyncConnection.connect`, which the SQLAlchemy psycopg dialect also calls, and every tool statement would get two spans.

`Checkpointer` takes an optional `tracer_provider`. With `None`, the default when tracing is off, the pool gets no `configure` callback.

### 3. Stable database conventions: `OTEL_SEMCONV_STABILITY_OPT_IN=http,database`

`setup_tracing` changes its default from `http` to `http,database`. It is still a `setdefault`, so the real environment wins. Spans then carry `db.system.name`, `db.namespace`, `db.query.text` and `db.operation.name`, not the deprecated `db.system`, `db.name` and `db.statement`. This matches the choice already made for HTTP. It is also the only mode in which psycopg emits `db.client.operation.duration` once metrics arrive.

The opt-in is read once per process, when the first instrumentor initializes. It is already set before the `httpx2` instrumentor, and both database instrumentors come after it.

Alternative: `database/dup`, which emits both the old and the new names. It is kept as the fallback if Kibana APM turns out to read only the old names (task 5.2 checks this). It doubles the attributes on every database span.

### 4. Explicit tracer provider and lifespan order

Both instrumentations get the provider from `setup_tracing`, not the global one, the same way `httpx2` does. The lifespan therefore calls `setup_tracing` before it builds the `Checkpointer`. `setup_tracing(settings, engine)` instruments the engine. `shutdown_tracing` uninstruments SQLAlchemy next to `httpx2`, before `provider.shutdown()`. The checkpointer's per-connection instrumentation goes away when its pool closes.

With tracing off, `setup_tracing` returns `None` before it instruments anything, so the process-wide SQLAlchemy wrappers are not installed either.

### 5. No parameters, ever

Neither instrumentation is given `capture_parameters`, which already defaults to off. The span attribute carries the statement as sent to the driver, with `%(name)s` or `%s` placeholders. Every value the app sends is bound: the ORM always binds, and the checkpointer's SQL is constant text with `%s`. The privacy test inserts a known name, phone and address, and searches every attribute of every database span for them.

## Risks / Trade-offs

- **[Checkpointer errors keep PostgreSQL's `DETAIL:` line.]** The dbapi span records the exception event and uses the driver message as the status description, before any code of ours can clean it. A NOT NULL violation's "Failing row contains (…)" would put a checkpoint row, which includes conversation messages, into the span. The checkpointer's SQL is generated by the library, so this is unlikely. → Recorded in AGENTS.md next to the existing span-event gap, for phase 6. The Collector cannot fix it today either, because the redaction does not reach span events or status messages.
- **[Pipelined statements understate their duration.]** In pipeline mode, `executemany` returns when the statements are queued, so the span ends before PostgreSQL answers. The wait then shows in the parent span, not in a database span. → Documented. The checkpointer's reads, which dominate a turn, are not pipelined.
- **[Span volume.]** A turn gains about a dozen short spans in both backends, including Langfuse's LLM view. → Accepted for phase 3, which wants every detail. A filter in the Langfuse pipeline is a Collector change for later if it gets in the way.
- **[Kibana APM may not map the stable `db.*` names.]** → Task 5.2 checks the span detail and the Dependencies view. Fallback: `database/dup` (Decision 3).
- **[The SQLAlchemy instrumentor declares `sqlalchemy < 2.1.0`.]** The project uses 2.1.3, and outside its range the instrumentor instruments nothing. → `instrument()` is called with `skip_dep_check=True`, and the engine integration tests catch a break. Fallback: pin `sqlalchemy<2.1`.
- **[Beta instrumentations (0.66b1).]** → Pinned in the lockfile next to the other 0.66b1 instrumentations. Imports go through `core/telemetry.py` and `infrastructure/checkpointer.py` only.
- **[The SQLAlchemy instrumentor is a process-wide singleton.]** A second `instrument()` call is ignored with a warning. → Tests uninstrument in a fixture's teardown, and the app instruments once per lifespan, as it does with `httpx2`.

## Migration Plan

None beyond deploying. To roll back, revert the change. No data or schema is touched.
