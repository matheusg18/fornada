# Design

## Context

The nine tools live in `agents/attendant/tools.py`. `build_tools` takes a session factory, a clock and the daily capacity, and every tool goes through one `run(name, call)` helper that opens a transaction, builds the services and turns errors into `ToolException` (the "internal error in {name}; try again later or escalate to a human" text for anything that is not a `DomainError`). `ToolNode` runs each call inside the `execute_tool` span opened by `make_wrap_tool_call`, so a tool can add attributes to the current span, as `check_capacity` already does with `fornada.capacity.free_kg`. `escalate_to_human` already reads the conversation id from `ToolRuntime`, which LangGraph injects and hides from the model's argument schema. Prices come from `QuoteService.price`, which both `calculate_quote` and `create_order` use.

Chaos mode is periphery work in the AGENTS.md table. The new span attributes follow the pattern the maintainer set in phase 2 (`fornada.*` names in `tracing.py`, set on the span the wrapper opened), so they carry no `TODO(human)`.

## Goals / Non-Goals

**Goals:**
- The three frozen-scope faults, opt-in for the whole process, with knobs and an optional seed.
- Faults that look real to the model: an outage reads like any other unexpected failure.
- Every injected fault visible in Langfuse and Kibana, so phase 3 can separate "the agent handled an outage badly" from "the agent failed on its own".
- Zero behavior change with chaos off; existing tests pass untouched.

**Non-Goals:**
- Per-conversation or per-request selection of faults (decided: whole process, env var).
- Latency on model calls, failures in other tools, database faults.
- Any reaction to the faults in the prompt or the graph. That is what phases 3–4 measure.
- Persisting the price state across restarts.
- Metrics for chaos. Span attributes are enough to count faults in Kibana; a counter can come with the phase 2 step B meters if needed.

## Decisions

### 1. One `Chaos` object, built from settings, passed to `build_tools`

A new module `fornada_api/infrastructure/chaos.py` holds a `Chaos` class with the settings and a `random.Random(seed)`:

- `delay_ms() -> int`: uniform integer in `[min, max]`.
- `capacity_fails() -> bool`: `random() < rate`.
- `price_factor(conversation_id) -> Decimal`: `1` until the conversation is marked, then `1 + pct/100`.
- `mark_quoted(conversation_id)`.

`build_tools(..., chaos: Chaos | None = None)`; `None` means off, so every existing caller and test keeps today's behavior. `default_tools()` builds it from `settings.chaos` when enabled.

*Alternative:* scattering `if settings.chaos.enabled` checks in the tools and services. Rejected: harder to test, and the services would read global settings, which none of them do today.

*Why `infrastructure/`:* it is a test harness for the environment, not a business rule. Services only receive a price factor (decision 4) and stay unaware of chaos.

### 2. Delay inside `run`, before the transaction

`run` awaits `asyncio.sleep(delay_ms / 1000)` first, then sets `fornada.chaos.delay_ms` on the current span. Sleeping before the session opens means the delay holds no database connection. Because `run` executes inside the `execute_tool` span, the delay shows in the span's duration, which is the Kibana latency spike phase 2 wants to trace.

*Alternative:* a delay in the `ToolNode` wrapper (`nodes.py`). Rejected: that puts chaos in the graph's tracing code, and the graph is meant to stay as v0 built it.

### 3. Outage in `check_capacity`, raised as the generic internal error

`check_capacity` asks `chaos.capacity_fails()` after the delay and before `run` reaches the database. On a hit it sets `fornada.chaos.fault = "capacity_unavailable"`, logs a WARNING (`"chaos fault injected"`, extra `tool` and `fault`) and raises `ToolException` with exactly the text `run` uses for unexpected failures. The wrapper then marks the span ERROR with `error.type = tool_error`, as for any error result. The text constant moves to one helper so both paths cannot drift apart.

*Alternative:* raise a real exception inside the transaction so the generic path handles it. Rejected: it would log a traceback with `logger.exception` and claim a database failure that did not happen.

### 4. Price factor through `QuoteService`, per conversation, in memory

`QuoteService(catalog, price_factor=Decimal(1))`. In `price`, the effective price per kg is `round_money(product.price_per_kg * price_factor)`; subtotal, total and deposit follow from it, and the `Quote` returns that price, so `create_order` snapshots it on the order. With factor `1` the arithmetic is the same as today.

`calculate_quote` and `create_order` gain a `runtime: ToolRuntime` parameter to read the `thread_id`, as `escalate_to_human` does. `services(session, conversation_id)` builds `QuoteService` with `chaos.price_factor(conversation_id)`. After a successful `calculate_quote`, the tool calls `chaos.mark_quoted(conversation_id)`. A call whose factor is not `1` sets `fornada.chaos.fault = "price_increase"`. The mark goes after success only, so a failed first quote does not raise the price (spec scenario "Failed first quote").

The set of marked conversations lives in the `Chaos` object, in process memory. The tool node can run two calls of one answer concurrently; both read the factor before either marks, which is acceptable (the spec defines "later calls", and a concurrent pair is not later).

*Alternative:* store the mark in the LangGraph state. Rejected: tools would have to return `Command` updates, which changes the tool contract and the graph for a test fault. *Alternative:* write the new price to `products`. Rejected by the maintainer: it dirties the seed and leaks across conversations.

### 5. Turn span flag via `GraphAttendant`

`GraphAttendant(..., chaos_enabled: bool = False)` adds `fornada.chaos.enabled = true` to the turn span's initial attributes. `main.py` passes `settings.chaos.enabled`. With chaos off the attribute is absent (not `false`), so a Kibana filter `fornada.chaos.enabled: true` isolates chaos runs and older traces are not affected.

### 6. Settings namespace `chaos`

`ChaosSettings` in `core/config.py`, with the fields and validation in the `app-config` delta: `enabled: bool = False`, `latency_min_ms: int = Field(200, ge=0)`, `latency_max_ms: int = Field(2000, ge=0)`, `capacity_failure_rate: float = Field(0.1, ge=0, le=1)`, `price_increase_pct: Decimal = Field(10, gt=0, le=100)`, `seed: int | None = None`, plus a model validator for min ≤ max that reports `CHAOS__LATENCY_MIN_MS`. Settings validate even when chaos is off, so a bad value is caught before someone turns it on.

### 7. Startup warning

In the lifespan, after the "fornada-api starting" record, one `logger.warning("chaos mode enabled", extra={...})` with the range, rate, increase and `seeded: bool` (not the seed value; nothing secret, but it keeps the record the same shape across runs).

### How the effect is observed

This change adds no guardrail or eval. Its output is fault frequency, readable from traces: in Kibana, `execute_tool check_capacity` spans with `fornada.chaos.fault: capacity_unavailable` over all `check_capacity` spans should sit near the configured rate, and tool p95 should rise by roughly the latency range. Phase 3 annotates what the agent did after each fault.

## Risks / Trade-offs

- [The marked-conversation set grows without bound] → One UUID per conversation; 150 simulated conversations is a few KB. Restarting the API clears it. Acceptable for a dev-only mode.
- [A restart forgets marks, so a resumed conversation sees the old price again until its next quote] → Documented; phase 3 runs do not restart the API mid-run.
- [With concurrency > 1 the seed does not reproduce a run: the order of draws depends on scheduling] → The spec only promises reproducibility for the same order of calls. For a reproducible run, use `SIMULATOR__CONCURRENCY=1`; documented in AGENTS.md.
- [Multiple API workers would each have their own marks and random stream] → The dev server runs one process; noted in the AGENTS.md entry.
- [Delays slow the simulator] → Default 0.2–2 s per tool call, about 1 s average; with ~10 tool calls per conversation, 150 conversations add roughly 25 minutes at concurrency 1. The range is configurable.
- [Someone leaves chaos on] → Off by default, absent from tests, startup WARNING, and the turn span flag makes affected traces easy to exclude.

## Migration Plan

None: new settings default to off, no schema change. Rollback is reverting the change or leaving `CHAOS__ENABLED` unset.
