# Design

## Context

`fornada-api` has typed async models (`models/`), a cached `get_sessionmaker()` that the engine docstring already reserves for the LangGraph tools, and settings with an `APP` namespace (time zone). There is no business logic and no LangChain dependency yet. The schema enforces only integrity; the archived `add-dev-database-seed` design leaves capacity, lead time, coupon rules and quote math to the tools. Requirements are in `specs/bakery-rules`, `specs/agent-tools` and `specs/app-config`.

This is phase 1 work. It adds no guardrail, so it has no ASR, false-positive or p95 effect to measure. The `v0` gaps it leaves on purpose are listed in `specs/agent-tools` so phases 3 and 5 can measure them.

The layering (repository → service, no controller, an `agents/` folder) was chosen by the maintainer. The agent folder is `agents/attendant/`, chosen over `fornada`, `main` and `order_taker`, because it names the role and does not repeat the package name.

## Goals / Non-Goals

**Goals:**
- Business rules live in one layer that is testable without a database or an LLM.
- Tools are thin adapters, so phase 2 can wrap them in spans and phase 6 can change what they pass to services without touching the rules.
- Every tool works under LangGraph's `ToolNode` and with `bind_tools`.

**Non-Goals:**
- The graph, state, system prompt and model wiring. Those are core work and come in the next change.
- Chaos mode (random latency, `check_capacity` failures, price change). It is in the frozen scope but gets its own change.
- HTTP endpoints for the tools, and any controller layer.
- Authorization, idempotency and confirmation checks (phase 6, after phase 5 measures the attacks).

## Decisions

### Package layout

```
fornada_api/
├─ repositories/          # data access, one module per aggregate
│  ├─ catalog.py          # products + allergens, pan sizes, neighborhoods
│  ├─ capacity.py         # overrides, used kg per date
│  ├─ customers.py
│  ├─ orders.py
│  ├─ coupons.py          # coupon + usage count
│  └─ side_effects.py     # sent messages, escalations
├─ services/              # business rules
│  ├─ errors.py           # DomainError and subclasses
│  ├─ money.py            # Decimal helpers: round half up, quantize
│  ├─ phones.py           # E.164 normalization
│  ├─ clock.py            # today() in APP__TIMEZONE, injectable
│  ├─ catalog.py          # search
│  ├─ capacity.py         # lead time + free kg
│  ├─ quotes.py           # weight check, pan size, quote, deposit
│  ├─ orders.py           # create, get, cancel (refund policy), apply coupon
│  └─ messaging.py        # send_message, escalate
└─ agents/
   └─ attendant/
      └─ tools.py         # the nine @tool functions + build_tools()
```

The existing project groups by technical layer (`models/`, `infrastructure/`, `dependencies/`), so layer folders fit better than per-feature folders. Alternative: one `services.py` with every rule. Rejected because quotes, capacity and orders each grow their own tests, and phase 6 edits orders.

### Repositories take a session and hold no rules
Each repository is a small class built with an `AsyncSession`. It runs queries and returns models (or scalars such as used kg and coupon usage). It never commits, and it never decides whether something is allowed. Eager loading (`selectinload`) happens here, because the models use `lazy="raise"`.

### Services take repositories, return result objects, raise domain errors
Services receive their repositories (and a `Clock` and the daily capacity) in their constructor, so unit tests pass in-memory fakes. A `typing.Protocol` per repository keeps pyright happy with the fakes. Services return frozen dataclasses (`Quote`, `CapacityReport`, `OrderSummary`…), never ORM objects, so tools cannot lazy-load by accident.

A failed rule raises a `DomainError` subclass (`ProductNotFound`, `InvalidWeight`, `NeighborhoodNotServed`, `CouponExpired`, `OrderNotFound`, `OrderNotCancellable`…) with an English message for the LLM. Alternative: result types (`Ok | Err`). Rejected as heavier than the project's style for no gain at this size.

Services do not commit. The transaction belongs to the caller, the same convention the FastAPI session dependency already follows.

### Rules are code constants, except the daily capacity
Lead times (2 and 5 days), the 1–10% coupon cap, the 50% deposit and the 2-day refund notice are module constants in `services/`. Only the default daily capacity becomes a setting (`APP__DAILY_CAPACITY_KG`, `Decimal`, `gt=0`), as the seed design planned. Moving the others to settings would invite tuning rules through the environment, which nothing needs yet.

### "48h" means calendar days
`delivery_date` is a date without time, so lead time compares dates: earliest = today + 2 (regular) or today + 5 (custom), with today in `APP__TIMEZONE`. This matches the seed, whose full days start at day + 3.

### Pan size is derived, not an argument
`calculate_quote` and `create_order` take only a weight. The service picks the smallest pan whose range contains it. That gives the LLM one fewer argument to get wrong, and phase 4 asserts it with one comparison.

### Money at the tool boundary
Tool argument schemas type amounts and weights as `Decimal`. Pydantic turns a JSON number `2.5` into `Decimal("2.5")` through its string form, so no float error reaches the rules. Results serialize `Decimal` as fixed-place strings (`"224.75"`, weights `"2.5"`), which the archived seed design suggested to keep the LLM from reformatting amounts.

### Tools: one session per call, built by a factory
`build_tools(sessionmaker) -> list[BaseTool]` returns the nine tools as closures over the session factory. The app passes `get_sessionmaker()`, and tests pass one bound to a test engine. Each tool body is:

1. `async with sessionmaker() as session, session.begin():`
2. build repositories and the service,
3. call the service and return its result as a dict.

`session.begin()` commits on success and rolls back on any exception, which gives "one call, one transaction" with no partial writes. Tools are `async`, because the engine is async.

Alternative: module-level `@tool` functions that call `get_sessionmaker()` directly. Rejected because tests could not point them at another database without clearing global caches.

### Errors become error ToolMessages inside the tool
Tools raise `ToolException` and set `handle_tool_error=True`, so LangChain turns the exception into a `ToolMessage` with `status="error"` whatever graph runs them (`ToolNode` or a custom node). A shared wrapper maps:
- `DomainError` → `ToolException(str(error))`;
- any other exception → `logger.exception(...)` and `ToolException("internal error in <tool>; try again or escalate")`, so no driver text, URL or password reaches the LLM.

Alternative: LangChain's `ToolErrorMiddleware`. Rejected because it belongs to `create_agent`, and the project uses an explicit graph. Error status on the message also feeds phase 2's tool-error metric.

### Thread id from the runtime, not from the LLM
`escalate_to_human` declares a `ToolRuntime` parameter, which LangChain injects and hides from the LLM's schema, and reads the thread id from it. That is the only conversation-bound value in `v0`. Phase 6 will use the same mechanism to bind the customer's phone.

### Tool descriptions in English
Tool names, descriptions and argument docs are in English, like the rest of the code. The LLM reads them, but customers never see them. The pt-BR rule covers the system prompt and replies, which come in the next change. If phase 3 shows the model mixing languages because of this, it becomes a dataset case first.

### Payment link
`https://pagamento.fornada.example/<order id>/<random token>`. The `.example` TLD is reserved, so the link can never resolve.

### Dependency
`uv add --package fornada-api langgraph`. It brings `langchain-core` (`@tool`, `ToolException`, `ToolRuntime`) and `ToolNode`, which the integration tests use to run the tools the way the graph will. Check the latest version and the `ToolRuntime` API in the docs at implementation time.

## Risks / Trade-offs

- **Integration tests that create orders change capacity and coupon usage for later tests.** → Tool tests run against a sessionmaker whose connection is in an outer transaction that is rolled back after each test (SQLAlchemy's "join an external transaction" recipe, `join_transaction_mode="create_savepoint"`). The documented `psql` reset covers manual runs.
- **Tests that depend on "today" break around midnight or holidays.** → Services take a `Clock`. Unit tests use a fixed date. Integration tests compare against the seed's relative days (run day + 3, + 5).
- **Exposing `cost_per_kg` in `search_catalog` leaks margin data from day one.** → It is a deliberate `v0` gap, chosen by the maintainer, for phase 5 to measure. The spec records it so it is not mistaken for a bug.
- **`get_order` returns the reference photo description, which is untrusted text.** → That is the indirect-injection path AGENTS.md describes. It stays in `v0`; phase 6 handles it.
- **The refund policy is invented here, since AGENTS.md does not define one.** → It is the simplest policy that makes "refunds outside policy" testable: deposit back with 2 days' notice, otherwise nothing. The maintainer can change it in review.
- **`ToolRuntime` is newer API and its import path may move.** → Confine it to `escalate_to_human` and check the current docs during implementation.

## Migration Plan

No data migration. The new setting has a default, so existing `.env` files keep working. Rollback is reverting the commits.
