# Tasks

## 1. Settings

- [x] 1.1 Add `ChaosSettings` (`enabled`, `latency_min_ms`, `latency_max_ms`, `capacity_failure_rate`, `price_increase_pct`, `seed`) under `Settings.chaos` in `core/config.py`, with the bounds and the min ≤ max validator from the `app-config` delta; add unit tests in `tests/unit/core/test_config.py` for every scenario of the five new requirements and verify with `uv run task test:unit`
- [x] 1.2 Add the `CHAOS__*` block to the root `.env.example`, off and with defaults, and verify every `ChaosSettings` field is listed

## 2. Chaos engine

- [x] 2.1 Create `infrastructure/chaos.py` with `Chaos` (`delay_ms`, `capacity_fails`, `price_factor`, `mark_quoted`, built from `ChaosSettings`); unit tests cover delays within range and zero range, rate 0 and 1, factor `1` before a mark and `1.10` after, no compounding, independent conversations, and identical draw sequences for the same seed; verify with `uv run task test:unit`
- [x] 2.2 Add `fornada.chaos.enabled`, `fornada.chaos.delay_ms` and `fornada.chaos.fault` (with the `capacity_unavailable` and `price_increase` values) to `agents/attendant/tracing.py`

## 3. Price factor in quotes

- [x] 3.1 Give `QuoteService` a `price_factor` (default `1`) applied to the price per kg and rounded half up to cents before subtotal, total and deposit; unit tests in `tests/unit/services/test_quotes.py` check `bolo-chocolate` 2.5 kg pickup gives `"98.89"`/`"247.23"` with factor `1.10` and today's values with the default; verify with `uv run task test:unit`

## 4. Faults in the tools

- [x] 4.1 Add the `chaos` parameter to `build_tools` and the delay in `run` (before the transaction, recording `fornada.chaos.delay_ms` on the current span); move the internal-error text to one helper; unit test that chaos `None` adds no delay or attribute and that a delayed call records its delay; verify with `uv run task test:unit`
- [x] 4.2 Inject the `check_capacity` outage (fault attribute, WARNING record without traceback, generic error text, no database access); unit tests with rate 1 (error result text, WARNING record, sessionmaker never called), rate 0, and `calculate_quote` unaffected at rate 1; verify with `uv run task test:unit`
- [x] 4.3 Add `runtime: ToolRuntime` to `calculate_quote` and `create_order`, build `QuoteService` with the conversation's factor, mark after a successful quote and set `price_increase` when the factor is not 1; check `test_tool_inventory.py` still shows no `runtime` in the argument schemas; integration tests in `tests/integration/agents/test_tools.py` cover second quote, order after the quote, no compounding, another conversation, failed first quote and unchanged catalog; verify with `uv run task test:integration`
- [x] 4.4 Wire `default_tools()` to build `Chaos` from `settings.chaos` when enabled, and `None` otherwise; verify with a unit test that chaos off yields `None`

## 5. Turn span and startup

- [ ] 5.1 Add `chaos_enabled` to `GraphAttendant` and set `fornada.chaos.enabled` on the turn span when true; extend `tests/unit/agents/test_agent_tracing.py` for on (attribute present on the turn span, `delay_ms` on tool spans, `capacity_unavailable` span with status ERROR and `error.type = tool_error`) and off (no `fornada.chaos.*` attribute on any span); verify with `uv run task test:unit`
- [ ] 5.2 Pass `settings.chaos.enabled` from the lifespan and log the startup WARNING with range, rate, increase and `seeded`; test that the record appears only with chaos on; verify with `uv run task test:unit`

## 6. Docs and end-to-end check

- [ ] 6.1 Document chaos mode in `AGENTS.md` (Dev environment): how to turn it on for a simulator run, the span attributes to filter on in Kibana and Langfuse, and the limits (one process, in-memory marks, seed needs `SIMULATOR__CONCURRENCY=1`); verify the documented variables match `.env.example`
- [ ] 6.2 Run `uv run task check` in `apps/api` and verify it passes
- [ ] 6.3 Start the API with `CHAOS__ENABLED=true` and `CHAOS__CAPACITY_FAILURE_RATE=1`, run one simulated conversation, and verify the startup WARNING, an `execute_tool check_capacity` span with `fornada.chaos.fault: capacity_unavailable` in Kibana (`traces-*`), `fornada.chaos.delay_ms` on tool spans, and the same trace in Langfuse; record the trace id in the task note

## Workflow follow-up

- Archive the change after review with `/opsx:archive` and sync the `chaos-mode`, `app-config` and `agent-tracing` specs.
