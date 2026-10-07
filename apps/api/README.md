# fornada-api

FastAPI service that runs the LangGraph ordering agent.

## Configuration

Settings come from environment variables and the `.env` file at the repo root
(the environment wins). Copy `.env.example` to `.env` and fill in an API key
and the database URL.
Run every command from the repo root so `.env` is found.

Nested settings use a double underscore, `NAMESPACE__FIELD`:

| Variable | Default | Meaning |
|---|---|---|
| `LLM__PROVIDER` | `anthropic` | Active provider: `anthropic` or `openai` |
| `LLM__ANTHROPIC__API_KEY` / `LLM__ANTHROPIC__MODEL` | – / `claude-haiku-4-5` | Required when Anthropic is active |
| `LLM__OPENAI__API_KEY` / `LLM__OPENAI__MODEL` | – / `gpt-5-mini` | Required when OpenAI is active |
| `APP__TIMEZONE` | `America/Sao_Paulo` | IANA time zone for "now" and dates |
| `APP__DAILY_CAPACITY_KG` | `15` | Oven capacity in kg for dates without a capacity override; must be > 0 |
| `LOG__LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` |
| `DB__URL` | – (required) | PostgreSQL URL (`postgresql://…`); in the dev container, the value of `$DATABASE_URI` |

Startup fails with a `ConfigError` that names the offending variable.

Logs are JSON, one object per line on stdout, with `timestamp` (UTC),
`level`, `logger` and `message`, plus any `extra` fields.

## Running the API

Tasks are defined with taskipy in `pyproject.toml`; run them from `apps/api`
(`uv run task --list` shows them all):

```bash
cd apps/api
uv run task dev      # development server with auto-reload on http://localhost:8000
```

`dev` runs from the repo root so the app finds `.env`. To serve without
reload, from the root: `uv run --package fornada-api fornada-api`.

- `GET /docs`: OpenAPI UI.
- `GET /health/db`: loads every model and returns the row count per table
  (`200 {"status": "ok", "tables": {...}}`), or `503 {"status": "unavailable"}`
  when the database cannot be reached. It never returns row contents.

## Database

Models live in `fornada_api/models/` and mirror `.devcontainer/db/schema.sql`,
which stays the only source of DDL: the app never creates or alters tables.
`fornada_api/infrastructure/engine.py` builds the async engine (psycopg 3) and
session factory; path operations get a session with `DbSessionDep` from
`fornada_api/dependencies`. Sessions never commit on their own. Relationships
are `lazy="raise"`: load them explicitly with `selectinload`/`joinedload`.

## Business rules and agent tools

Three layers, each one using only the one below it:

| Layer | Folder | Does |
|---|---|---|
| Repositories | `fornada_api/repositories/` | Queries only: rows in, models out. Never commit, never decide |
| Services | `fornada_api/services/` | Business rules (quote, lead time, capacity, coupons, refunds). Depend on the repository protocols in `services/ports.py`, raise `DomainError`s, never commit |
| Agent tools | `fornada_api/agents/attendant/tools.py` | The attendant's nine LangChain tools. One session and one transaction per call |

`build_tools(sessionmaker, clock=..., daily_capacity_kg=...)` returns the
tools; `default_tools()` wires them to the app's database and settings. Run
them through a LangGraph `ToolNode` inside a graph (escalation reads the
thread id from the run config). A failed rule comes back as a `ToolMessage`
with `status="error"` and a message for the LLM; unexpected errors are logged
and return a generic message.

| Tool | Does |
|---|---|
| `search_catalog(query?)` | Active products with price, cost, allergens (contains / may contain), pan sizes, neighborhoods |
| `check_capacity(date)` | Capacity, used and free kg, override reason, earliest dates and lead-time flags |
| `calculate_quote(product_slug, weight_kg, fulfillment, neighborhood?)` | Pan size, subtotal, delivery fee, total, 50% deposit |
| `create_order(...)` | Reuses or creates the customer; saves a `pending_payment` order with a fake payment link |
| `get_order(order_id, phone)` | Order details if the phone matches; "not found" otherwise |
| `cancel_order(order_id, phone, reason)` | Cancels under the refund policy, returns the refund |
| `apply_coupon(order_id, coupon_code)` | Validates the coupon (≤ 10%) and discounts a pending order |
| `send_message(phone, text, order_id?)` | Records a message row; nothing is sent |
| `escalate_to_human(reason, phone?)` | Records an escalation for the current thread |

**Deliberate v0 gaps** (measured in phases 3 and 5, closed in phase 6):
`create_order` checks neither capacity, lead time, past dates nor
confirmation, and retries create duplicates; `get_order`, `cancel_order`,
`apply_coupon` and `send_message` trust the phone or order id the LLM passes;
`search_catalog` exposes `cost_per_kg`; `get_order` returns the reference
photo description, which is untrusted customer text.

## Checks and tests

From `apps/api`:

| Task | What it runs |
|---|---|
| `uv run task check` | Everything below: lint, format check, type check and all tests |
| `uv run task lint` / `lint:fix` | `ruff check` (with `--fix`) |
| `uv run task format` / `format:check` | `ruff format` (with `--check`) |
| `uv run task typecheck` | `pyright` (standard mode) |
| `uv run task test` | All tests |
| `uv run task test:unit` | `tests/unit` |
| `uv run task test:integration` | `tests/integration` |

Integration tests (`tests/integration/`) use the dev container's seeded
database through `DATABASE_URI` and are skipped when it is not set. Tests that
write go through the `rollback_sessionmaker` fixture, whose commits stay inside
one outer transaction that is rolled back, so the seed is never changed. To
get back to a fresh seed after manual testing, use the reset command in
`.devcontainer/db/README.md`.

Service unit tests (`tests/unit/services/`) use the in-memory repositories in
`tests/unit/services/fakes.py`, with a fixed clock.
