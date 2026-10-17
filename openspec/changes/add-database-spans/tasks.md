# Tasks

Which spans and attributes exist is core for phase 2 (AGENTS.md). Those choices are in design.md, and the maintainer reviews them there. The calls themselves mirror the maintainer's `httpx2` instrumentation in `setup_tracing`, so the agent writes them to match, with no `TODO(human)`. Run `uv run task check` from `apps/api` at the end of each app group.

## 1. Dependencies

- [x] 1.1 Run `uv add --package fornada-api opentelemetry-instrumentation-sqlalchemy opentelemetry-instrumentation-psycopg`. Verify both are direct dependencies in `apps/api/pyproject.toml`, `uv.lock` resolves them at 0.66b1 (with `opentelemetry-instrumentation-dbapi`), and `uv tree --invert --package opentelemetry-instrumentation-sqlalchemy` now lists `fornada-api`.

## 2. Engine path: tool statements

- [x] 2.1 Make the database semconv opt-in reachable from tests. The opt-in is read once per process, by the first instrumentor that initializes, so the test session must set `OTEL_SEMCONV_STABILITY_OPT_IN` before any instrumentor runs (for example, in the root `tests/conftest.py`, from the same constant `setup_tracing` uses). Verify that a test asserting `db.query.text` sees the stable name whichever test file runs first (`pytest -p no:randomly` in both orders of the two test files).
- [x] 2.2 Write failing integration tests in `tests/integration/test_database_spans.py` (`app-tracing` delta). Use a fixture that instruments the app engine with an in-memory provider and uninstruments it at teardown:
  - a `select` gives one CLIENT span with `db.system.name` = `postgresql`, `db.namespace` = `fornada` and the statement in `db.query.text`;
  - an insert of `Maria Teste`, `+5581999991234` and a known address through the rollback sessionmaker leaves none of these values in any attribute of any span;
  - a duplicate-phone insert gives a span with status ERROR whose description has no `DETAIL:` line and no inserted value.

  Verify they fail.
- [x] 2.3 In `core/telemetry.py`, give `setup_tracing` the engine and instrument it with `SQLAlchemyInstrumentor` and the provider (design.md, decisions 1 and 4). Change the opt-in default to `http,database` (decision 3). Uninstrument it in `shutdown_tracing` before `provider.shutdown()`. Update the module docstring. Verify the 2.2 tests pass and `uv run task check` passes.

## 3. Checkpointer path: conversation-state statements

- [x] 3.1 Write failing integration tests for `Checkpointer` (`tests/integration/`):
  - with an in-memory provider, `ensure_setup` followed by a put and a get of a checkpoint gives CLIENT spans whose `db.query.text` holds the checkpointer's SQL;
  - with no provider, the same calls give no span.

  Verify they fail.
- [x] 3.2 Give `Checkpointer` an optional `tracer_provider`. When it is set, pass the pool a `configure` callback that calls `PsycopgInstrumentor.instrument_connection(conn, tracer_provider=…)` (design.md, decision 2), with a comment on why it is not the global instrumentor. Verify the 3.1 tests pass, the existing `tests/unit/infrastructure/test_checkpointer.py` still passes, and `uv run task check` passes.

## 4. Lifespan wiring

- [x] 4.1 Write failing tests in `tests/unit/test_tracing.py`, following its spy pattern:
  - with telemetry off, the lifespan leaves `SQLAlchemyInstrumentor().is_instrumented_by_opentelemetry` false and builds the `Checkpointer` with no provider;
  - with telemetry on, the engine is instrumented and the `Checkpointer` gets the provider `setup_tracing` returned;
  - at shutdown, SQLAlchemy is uninstrumented.

  Verify they fail.
- [x] 4.2 Wire `main.py`: call `setup_tracing(settings.telemetry, engine)` before building the `Checkpointer`, and pass it the provider (design.md, decision 4). Verify the 4.1 tests pass and `uv run task check` passes.
- [x] 4.3 Write an integration test that runs one graph turn with the scripted chat model calling `search_catalog`, against the real database and a real checkpointer, with an in-memory provider (`app-tracing` delta):
  - the tool's statements are CLIENT spans whose ancestor is the `execute_tool search_catalog` span;
  - checkpoint statements are in the same trace;
  - no `db.query.text` appears twice for the same execution, that is, no two database spans with the same `db.query.text` overlap in time (a second instrumentation of one statement is a sibling span running inside the first, not its child).

  Verify it passes, and fails if the global `PsycopgInstrumentor().instrument()` is called instead (try it, then revert).
- [x] 4.4 Document in `AGENTS.md`, in the Logs and redaction paragraphs:
  - a turn's trace now has database spans, from the tools (under `execute_tool …`) and from the checkpointer;
  - `db.query.text` carries placeholders only;
  - the checkpointer path's errors keep PostgreSQL's `DETAIL:` line in the span's status and exception event, an extension of the phase 6 known gap (design.md, Risks).

  Verify by reading the section against the code.

## 5. End-to-end verification

- [ ] 5.1 With the dev environment up and `TELEMETRY__ENABLED=true`, run `uv run task dev` and send a turn that makes the agent call `search_catalog` and then `create_order` with a known phone. Verify the following, and record the trace id here:
  - `curl -s edot-collector:8888/metrics | grep spans` shows no new `send_failed_spans`;
  - in Langfuse, the trace shows the database spans under the tool spans.
- [ ] 5.2 In Kibana (Playwright MCP), open that trace in APM. Verify that the database spans show their statement and the PostgreSQL dependency appears. If APM does not read the stable `db.*` names, switch the default to `http,database/dup` (design.md, decision 3), rerun 5.1, and record the outcome here.
- [ ] 5.3 In Kibana Dev Tools, run `GET traces-*/_search` with a `query_string` for the phone used in 5.1, and for the customer name. Verify that both return 0 hits.

## Workflow follow-up

- Open the PR, then archive with spec sync after merge (`/opsx:archive`).
