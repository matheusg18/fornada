# Proposal

## Why

The models and the seeded database exist, but nothing reads or writes them on the agent's behalf. The LangGraph agent of phase 1 needs its nine tools before the graph can be wired and `v0` can run 20 simulated conversations. The business rules those tools use (quote math, lead time, capacity, coupon validity, refunds) also need one home that later phases can test and guard, instead of logic spread across tool functions.

**Phase:** 1 (naive foundation). The tools are deliberately naive: they trust the arguments the LLM passes and add no defense. Phase 6 adds the guardrails.

**Scope:** stays within the frozen scope. It adds exactly the nine tools in AGENTS.md and no others. The only new setting, the default daily capacity, was already planned to live in app config (see the archived `add-dev-database-seed` design).

## What Changes

- Three new layers in `fornada-api`:
  - `repositories/`: data access only. One repository per aggregate (catalog, capacity, customers, orders, coupons, messages, escalations) that turns queries into model objects. No business rules.
  - `services/`: business rules. Services use repositories and return plain result objects. They raise typed domain errors when a rule fails. They do not commit.
  - `agents/attendant/`: the main agent's package. For now it holds only `tools.py`, the nine LangChain/LangGraph tools. Each tool opens one database session, calls a service, commits, and turns domain errors into tool error messages.
- No controller layer and no graph yet. The graph (nodes, state, prompt) is core work for a later change.
- New setting `APP__DAILY_CAPACITY_KG` (default 15).
- New dependency: `langgraph` (brings `langchain-core`, which defines `@tool`).
- Deliberate `v0` weaknesses, recorded so phases 3 and 5 can measure them:
  - `get_order`, `cancel_order` and `send_message` trust the phone the LLM passes.
  - `create_order` does not check capacity, lead time or confirmation, and it has no idempotency.
  - `search_catalog` returns each product's cost per kg alongside its price.

## Capabilities

### New Capabilities
- `bakery-rules`: the bakery's business rules as the services enforce them: pan size from weight, quote and deposit math, lead time, daily capacity, coupon validity and discount, cancellation refund policy.
- `agent-tools`: the nine tools the agent can call: names, arguments, results, how errors reach the LLM, which side effects each one records, and which checks `v0` deliberately leaves out.

### Modified Capabilities
- `app-config`: adds `APP__DAILY_CAPACITY_KG`, the default daily oven capacity used when a date has no capacity override.

## Impact

- **Code:** new `apps/api/src/fornada_api/repositories/`, `services/` and `agents/attendant/`. `core/config.py` and `.env.example` change for the new setting. No change to models, schema or HTTP endpoints.
- **Dependencies:** `langgraph` in `fornada-api`, added with `uv add`.
- **Database:** none. Tools write `orders`, `customers`, `sent_messages` and `escalations` through the existing models.
- **Tests:** unit tests for services with fake repositories, and integration tests for repositories and tools against the seeded database. Tool tests write rows, so they roll back or the developer resets with the documented `psql` command.
- **Later phases:** phase 2 instruments tool calls and phase 6 moves authorization into the services. Keeping rules in services and tools thin makes both changes local.
