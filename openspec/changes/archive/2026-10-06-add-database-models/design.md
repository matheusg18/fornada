# Design

## Context

`apps/api` has `core/config.py` (pydantic-settings, `LLM`/`APP`/`LOG` namespaces, cached `get_settings()`) and `core/logging.py` (JSON to stdout). `main()` only logs a startup line; there is no FastAPI app yet. The 11 app tables are defined in `.devcontainer/db/schema.sql` and filled by `seed.sql`; the `bakery-data-model` spec says the database enforces integrity only and business rules live in the tools. The dev container exposes `DATABASE_URI=postgresql://fornada:…@postgres:5432/fornada`. LangGraph's Postgres checkpointer, which a later change adds to the same database, uses `psycopg` 3.

Requirements live in `specs/database-access`, `specs/api-service` and `specs/app-config`. This is phase 1 periphery: no defense, nothing to measure in ASR, false positives, p95 or cost.

## Goals / Non-Goals

**Goals:**
- Models the nine tools can query directly, with types that make the money and date rules easy to get right.
- A session dependency the tool layer can reuse without knowing about FastAPI internals.
- A quick, repeatable way to prove the models match the live schema.

**Non-Goals:**
- Migrations (Alembic) or `metadata.create_all()`. `schema.sql` stays the DDL source.
- Repositories, services or any query beyond what the health check needs. The tools change writes them.
- Mirroring `CHECK` constraints in Python. The database already enforces them, and business rules belong in the tools.
- Pydantic response schemas for the models or any CRUD endpoint. Exposing customers or orders over HTTP would leak third-party data.
- OpenTelemetry instrumentation of SQLAlchemy or FastAPI (phase 2).

## Decisions

### Layout: `infrastructure/`, `dependencies/` and `models/` at the package top level
The maintainer chose top-level packages over `core/` for everything database-related (`core/` keeps settings and logging):

```
fornada_api/
├─ infrastructure/
│  ├─ __init__.py
│  └─ engine.py        # URL rewrite, get_engine(), get_sessionmaker()
├─ dependencies/
│  ├─ __init__.py      # re-exports DbSessionDep
│  └─ database.py      # get_db_session, DbSessionDep (consumes infrastructure/engine.py)
└─ models/
   ├─ __init__.py      # imports every model, exports Base and the enums
   ├─ base.py          # DeclarativeBase + type_annotation_map
   ├─ catalog.py       # Product, Allergen, ProductAllergen, PanSize
   ├─ operations.py    # Neighborhood, CapacityOverride, Coupon
   ├─ customers.py     # Customer
   ├─ orders.py        # Order
   └─ side_effects.py  # SentMessage, Escalation
```

`infrastructure/` owns resources that talk to the outside world; `dependencies/` owns what FastAPI injects. The split lets the LangGraph tools, which run outside a request, use `get_sessionmaker()` directly without going through `Depends`.

`models/__init__.py` imports every module so that `Base.metadata` is complete as soon as `fornada_api.models` is imported; relationships use string targets to avoid import cycles. Grouping follows the `bakery-data-model` spec sections. Alternative: one `models.py`. Rejected: about 250 lines with `Order` alone near 60; small files read better and diff better.

### SQLAlchemy 2.0, not SQLModel
The FastAPI skill prefers SQLModel, but the maintainer asked for SQLAlchemy. It also fits better here: models are read-mostly mirrors of a hand-written schema, the tools will want `select()` with joins and `FOR UPDATE` for capacity, and we do not want table models doubling as API schemas (that is how private columns such as `cost_per_kg` leak). Use the typed declarative style (`Mapped[...]`, `mapped_column`).

### Async engine with `psycopg` 3
`create_async_engine("postgresql+psycopg://…")`. LangGraph runs async, FastAPI endpoints for the chat will be async, and the checkpointer already pulls in `psycopg` 3, so one driver serves both. Alternatives: `asyncpg` (fast, but a second driver next to psycopg) and sync SQLAlchemy in threadpool `def` endpoints (simpler, but every tool call from the async graph would need a thread hop).

`DB__URL` stays in the plain `postgresql://` form so the same value as `DATABASE_URI` works. `database.py` rewrites the scheme to `postgresql+psycopg://` with `sqlalchemy.engine.make_url(...).set(drivername="postgresql+psycopg")`. The engine sets `connect_args={"application_name": "fornada-api"}`, which lets the shutdown test find the API's connections in `pg_stat_activity`, and `pool_pre_ping=True` so a restarted Postgres does not break the first request.

### Engine and sessionmaker as cached accessors, session per request through `Depends`
`infrastructure/engine.py` exposes `get_engine()` and `get_sessionmaker()`, both wrapped in `functools.cache` like `get_settings()`. `get_engine()` builds the engine from `get_settings().db`; `get_sessionmaker()` returns `async_sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)`. `dependencies/database.py` consumes them:

```python
async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session

DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
```

`async with` closes the session on success and on error, and closing rolls back anything not committed, which gives "no implicit commits" with no extra code. Default `scope="request"` is fine. `expire_on_commit=False` is needed with async: after a commit, touching an expired attribute would trigger lazy IO, which async sessions do not allow.

The app lifespan calls `get_engine()` on startup (so a bad configuration fails before serving) and `await get_engine().dispose()` on shutdown. Engine creation does not connect, so startup does not need the database to be up. Tests that point at another database call `get_settings.cache_clear()` and `get_engine.cache_clear()` / `get_sessionmaker.cache_clear()`.

Alternatives: engine on `app.state`, built in the lifespan (clean per-app lifetime, but the tools outside FastAPI would need the app object to reach it) and a module-level global created at import (impossible to point at another database in tests).

### Types: `Decimal`, `date`, aware `datetime`, `StrEnum`
`Base.type_annotation_map` maps `Decimal` to `Numeric(asdecimal=True)` and `datetime` to `DateTime(timezone=True)`; columns that need precision (`numeric(10,2)`, `numeric(4,1)`) declare it in `mapped_column` so the model documents the schema. `date` maps to `Date`. psycopg already returns `Decimal` for `numeric` and aware datetimes for `timestamptz`.

`OrderStatus`, `Fulfillment` and `AllergenKind` are `enum.StrEnum`s mapped with `Enum(..., native_enum=False, create_constraint=False, values_callable=lambda e: [m.value for m in e], length=None)`. The column stays plain `text` in Postgres, the existing `CHECK` does the enforcement, and Python code compares `order.status == OrderStatus.CANCELLED` instead of a bare string. Alternative: `Mapped[str]`. Rejected: typos in status strings are exactly the kind of bug tools will hit.

Identity primary keys use `mapped_column(Identity(always=True), primary_key=True)` so SQLAlchemy never tries to insert an id. `server_default=func.now()` on `created_at` and `server_default=true()` on `active`/`is_custom` mirror the schema defaults so inserts from tools can omit them.

### Relationships, lazy loading off
Relationships: `Order.customer/product/pan_size/neighborhood/coupon`, `Customer.orders`, `Product.allergen_links` → `ProductAllergen.allergen`. All use `lazy="raise"`: in async, an accidental lazy load fails anyway, and `raise` makes it fail with a clear message at the line that did it. Queries opt in with `selectinload`/`joinedload`. Alternative: `AsyncAttrs` with `awaitable_attrs`. Rejected for now; explicit loading keeps the number of queries per tool call visible, which matters for p95 later.

### `DB` settings namespace
`DbSettings.url: SecretStr` with a validator that accepts only `postgresql://` and `postgres://` schemes (the error names `DB__URL`). `SecretStr` and not `PostgresDsn` because the URL holds the password and must be masked in logs, like the API keys. `Settings.db: DbSettings` has no default, so a missing `DB__URL` fails through the existing `ConfigError` path. The existing unit tests build `Settings` without a DB URL, so they need a `DB__URL` set in their fixture; this is a test-only change.

### `main.py` and the FastAPI CLI
`fornada_api/main.py` creates `app = FastAPI(title="Fornada API", lifespan=lifespan)`. The lifespan calls `get_settings()` and `configure_logging()` first, then `get_engine()`, so a bad configuration fails startup before any request. `[tool.fastapi] entrypoint = "fornada_api.main:app"` goes in `apps/api/pyproject.toml`; from the repo root the dev command is `uv run --package fornada-api fastapi dev apps/api/src/fornada_api/main.py` unless the CLI picks up the member's `[tool.fastapi]` (checked during apply; the README documents whichever works). The existing `fornada-api` script entry stays, now calling `uvicorn.run("fornada_api.main:app")`, so `uv run --package fornada-api fornada-api` serves without reload.

### `GET /health/db`
In a `health` router (`fornada_api/health.py`, `prefix="/health"`, `tags=["health"]`). For each mapped class in `Base.registry.mappers`, it runs `select(func.count()).select_from(Model)` and `select(Model).limit(1)`; the second one makes the database return every mapped column, so a misnamed column or a type that cannot load fails here. Returns a pydantic model `{"status": "ok", "tables": {"products": 12, …}}`. On `SQLAlchemyError` or `OSError` it logs the exception and returns 503 `{"status": "unavailable", "tables": {}}`. The endpoint never returns rows, so it adds no data-leak surface.

### Tests
- `tests/unit/core/test_config.py`: new `DB__URL` scenarios; existing tests get `DB__URL` from a fixture.
- `tests/integration/`, marked `integration` and skipped when `DATABASE_URI` is not set. They use the dev container's seeded database: column-by-column comparison of `Base.metadata` with `sqlalchemy.inspect` on the live tables; loading every row of every model; decimal, date and enum types; relationships; uncommitted insert discarded; `/health/db` through FastAPI's `TestClient` used as a context manager, so the lifespan runs; 503 with an unreachable URL (`postgresql://x:y@127.0.0.1:1/x`); no `fornada-api` rows in `pg_stat_activity` after shutdown.

## Risks / Trade-offs

- [Models drift from `schema.sql` when someone edits one and not the other] → The column comparison test fails on any name or nullability difference; `/health/db` catches it at runtime.
- [Integration tests depend on seed state] → Tests assert only counts the seed fixes (12 products, 8 neighborhoods) and read-only properties; the insert test never commits. Reset command is in `.devcontainer/db/README.md`.
- [`lazy="raise"` makes tool code more verbose] → Accepted; explicit loading is cheaper to reason about and to trace in phase 2.
- [Requiring `DB__URL` breaks `fornada-api` for anyone with an old `.env`] → The error names the variable; `.env.example` shows the value to copy from `DATABASE_URI`.
- [`fastapi[standard]` pulls in more than needed, including its own OpenTelemetry pieces] → Accepted for the CLI and dev server. Phase 2 decides whether FastAPI's native telemetry or the plain SDK instrumentation is used; nothing is enabled in this change.
