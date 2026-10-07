# Tasks

## 1. Setup and settings (`app-config`)

- [x] 1.1 Run `uv add --package fornada-api langgraph` from the repo root, after checking its latest version and the current `ToolRuntime`/`ToolException` docs; verify `uv run --package fornada-api python -c "from langchain_core.tools import tool, ToolException; from langgraph.prebuilt import ToolNode"` works
- [x] 1.2 Add `daily_capacity_kg: Decimal` (`gt=0`, default `15`) to `AppSettings`, list `APP__DAILY_CAPACITY_KG` in `.env.example` and the `apps/api/README.md` configuration section; add unit tests for the default (exactly `Decimal("15")`), `20.5`, and `0` failing with an error naming `APP__DAILY_CAPACITY_KG`; verify `uv run task test:unit` passes
- [x] 1.3 Create the empty packages `repositories/`, `services/`, `agents/` and `agents/attendant/` (each with `__init__.py`) and matching `tests/unit/services/` and `tests/integration/{repositories,agents}/` folders; verify `uv run task check` passes

## 2. Service foundations (`bakery-rules`)

- [ ] 2.1 Implement `services/errors.py` (`DomainError` and the subclasses named in the design), `services/money.py` (round half up to 2 places, weight to 1 place, `Decimal` to string), `services/phones.py` (E.164 normalization for Brazilian numbers) and `services/clock.py` (`Clock` protocol, system clock in `APP__TIMEZONE`, fixed clock for tests); add unit tests: `89.90 × 2.5 = 224.75`, `234.75 / 2 → 117.38`, `(81) 98765-4321 → +5581987654321`, an unparseable phone raises, the late-evening-UTC case gives the São Paulo date; verify `uv run task test:unit` passes
- [ ] 2.2 Define the repository `Protocol`s the services depend on and in-memory fakes in `tests/unit/services/fakes.py`, loaded with a small copy of the seed catalog (pans P/M/G, `bolo-chocolate`, one custom product, `Ipsep` at `10.00`, the five seed coupons); verify `uv run task typecheck` passes

## 3. Quotes, capacity and catalog rules (`bakery-rules`)

- [ ] 3.1 Implement `services/quotes.py`: weight validation (0.5 step, 1.0–6.0 from the pan table), pan size from weight (boundary → smaller pan), quote with delivery fee, discount `0.00`, total and deposit; unknown/inactive product and missing/unknown neighborhood errors (the latter listing served neighborhoods); add unit tests for every `bakery-rules` scenario on weight, pan size, quote, deposit and quote prerequisites; verify they pass
- [ ] 3.2 Implement `services/capacity.py`: capacity from override or default setting, used kg from non-cancelled orders, free kg floored at zero, override reason, earliest regular (+2) and custom (+5) dates and the two lead-time flags; add unit tests for the full day, holiday, cancelled-order and lead-time scenarios with a fixed clock; verify they pass
- [ ] 3.3 Implement `services/catalog.py`: search active products by case-insensitive name/description match (all without a query), with allergens split into contains / may contain, cost per kg, pan sizes and active neighborhoods; add unit tests for the no-query and `sem farinha` cases; verify they pass

## 4. Order, coupon and messaging rules (`bakery-rules`)

- [ ] 4.1 Implement order creation in `services/orders.py`: normalize phone, reuse or create the customer, compute amounts through the quote service, status `pending_payment`, payment link `https://pagamento.fornada.example/<id>/<token>`; no capacity, lead-time, past-date or duplicate checks; add unit tests that amounts equal the quote, an existing customer is reused, and two identical calls create two orders; verify they pass
- [ ] 4.2 Implement `get_order` and `cancel_order` in `services/orders.py`: lookup by id plus phone with one `OrderNotFound` for missing or mismatched, refund policy (pending → `0.00`; confirmed with ≥2 days' notice → deposit; otherwise `0.00`; delivered/cancelled → `OrderNotCancellable`), setting status, `cancelled_at`, refund and reason; add unit tests for each refund-policy scenario and the mismatched phone; verify they pass
- [ ] 4.3 Implement coupon validation and `apply_coupon`: case-insensitive code, active, window inclusive, usage below limit, percent 1–10, each failure its own error; only `pending_payment` orders without a coupon; discount on subtotal, total and deposit recomputed; add unit tests for every coupon scenario (including `AMIGO5` → discount `11.24`, total `223.51`, deposit `111.76`, and a 30% coupon refused); verify they pass
- [ ] 4.4 Implement `services/messaging.py`: record a sent message to any normalized phone (optional order id) and an escalation with thread id, optional phone and reason; add unit tests; verify `uv run task test:unit` passes

## 5. Repositories (`bakery-rules`, `agent-tools`)

- [ ] 5.1 Add the integration-test fixture from the design: a sessionmaker bound to a connection in an outer transaction with `join_transaction_mode="create_savepoint"`, rolled back after each test; verify a test that inserts a sent message and commits leaves no row afterwards
- [ ] 5.2 Implement the repositories (catalog, capacity, customers, orders, coupons, side effects) satisfying the service protocols, with `selectinload` where services read relations; add integration tests against the seed: 12 active products with allergens, 3 pans, 8 neighborhoods, used kg on run day + 3 is `15.0` and on + 5 is `13.0`, Dec 25 override has capacity 0, `PRIMEIRA10` usage equals its limit, an order loads by id with its customer; verify `uv run task test:integration` passes

## 6. Tools (`agent-tools`)

- [ ] 6.1 Implement the tool scaffolding in `agents/attendant/tools.py`: `build_tools(sessionmaker)`, the per-call `session.begin()` wrapper, the error mapping (`DomainError` → `ToolException(message)`; anything else → logged, generic `ToolException`), `handle_tool_error=True`, and `Decimal`/`date` serialization of results; verify with a test that the tool set holds exactly the nine names, each with a description and an argument schema
- [ ] 6.2 Implement the read-only tools `search_catalog`, `check_capacity` and `calculate_quote`; add integration tests that run them through `ToolNode` against the seed: full catalog counts, `cost_per_kg` `"32.00"` on `bolo-chocolate`, run day + 3 free `"0.0"`, tomorrow meets no lead time, the `Ipsep` quote (`M`, `"224.75"`, `"10.00"`, `"234.75"`, `"117.38"`), `weight_kg` sent as a JSON number, 2.3 kg returning an error `ToolMessage` that mentions the 0.5 kg step; verify they pass
- [ ] 6.3 Implement `create_order`, `get_order`, `cancel_order` and `apply_coupon`; add integration tests through `ToolNode`: new customer and pending order created, amounts match `calculate_quote`, photo description stored verbatim, order on the full day created, duplicate call creates two orders, `get_order` with the right phone returns details and with another customer's phone returns not-found, a pending order cancels with refund `"0.00"`, `AMIGO5` applies and `DESCONTO30` fails leaving the order unchanged; verify they pass
- [ ] 6.4 Implement `send_message` and `escalate_to_human` (thread id from `ToolRuntime`); add integration tests: message to an unknown number recorded with normalized phone and verbatim text, escalation recorded with thread id `t-123` from the run config, escalation without a thread id returns an error `ToolMessage`; verify they pass
- [ ] 6.5 Add failure-path tests: `create_order` failing after the customer insert leaves neither row (for example, a delivery order with an unknown neighborhood for a new phone), and a tool built with a sessionmaker pointing at `postgresql://x:secret@127.0.0.1:1/x` returns an error `ToolMessage` without `secret` or `127.0.0.1` and logs the exception; verify they pass
- [ ] 6.6 Document the layers (`repositories/`, `services/`, `agents/attendant/`), the nine tools and the deliberate `v0` gaps in `apps/api/README.md`; verify the documented commands run as written

## 7. Integration check

- [ ] 7.1 From `apps/api`, run `uv run task check`; then reset the database with the command in `.devcontainer/db/README.md`, run `uv run task test:integration` again, and confirm with `psql` that the row counts of `orders`, `customers`, `sent_messages` and `escalations` match the fresh seed; verify all pass

## Workflow follow-up

- Commit each step with a Conventional Commits message, after the maintainer approves it (for example `feat: add bakery rule services`, `feat: add attendant agent tools`).
- Archive the change with `/opsx:archive` once review is done.
