# Proposal

## Why

The schema and seed exist (`.devcontainer/db/`), but the API has no way to read or write them. The nine tools of phase 1 all touch these tables, so they need typed models and a database session first. A minimal FastAPI app that loads the models against the seeded database proves the mapping before any tool is built on it.

**Phase:** 1 (naive foundation). This is periphery plumbing (FastAPI, data access); it adds no defense and changes no agent behavior.

**Scope:** stays within the frozen scope. It adds no tool and no feature; it maps the existing tables and exposes one health endpoint for the developer, not for customers.

## What Changes

- Add SQLAlchemy 2.0 (async, `psycopg` 3 driver) to `fornada-api`.
- New `fornada_api/infrastructure/engine.py` that builds the async engine and session factory from settings.
- New `fornada_api/dependencies/database.py` with `get_db_session`, a FastAPI dependency (`yield`) that hands one session per request from that factory.
- New `fornada_api/models/` package with one declarative model per app table in `schema.sql` (11 tables: catalog, allergens, pan sizes, neighborhoods, capacity overrides, coupons, customers, orders, sent messages, escalations). Models mirror the schema; they never create or alter tables.
- New `DB` settings namespace with a required `DB__URL`, added to `.env.example`.
- New `fornada_api/main.py` with the FastAPI `app`: a lifespan that opens and disposes the engine, and `GET /health/db`, which loads every model and returns row counts per table.
- `fornada-api` gains the FastAPI CLI entrypoint (`[tool.fastapi]`), so `fastapi dev` serves the app.

## Capabilities

### New Capabilities
- `database-access`: how the API connects to PostgreSQL, the per-request session, and the ORM models that mirror the app tables.
- `api-service`: the FastAPI application itself, its startup and shutdown, and the database health endpoint.

### Modified Capabilities
- `app-config`: adds the `DB` namespace and the required `DB__URL` setting.

## Impact

- **Code:** `apps/api/src/fornada_api/infrastructure/`, `dependencies/`, `models/`, `core/config.py`, new `main.py` and `health.py`; tests under `apps/api/tests/`.
- **Dependencies:** `sqlalchemy[asyncio]`, `psycopg[binary]`, `fastapi[standard]` in `fornada-api`; `httpx` comes with FastAPI for tests.
- **Configuration:** root `.env` must define `DB__URL`. Inside the dev container it is the same URI as `DATABASE_URI`.
- **Database:** none. `schema.sql` stays the single source of truth for DDL; no migrations tool yet.
- **Tests:** integration tests need the dev container's Postgres with the seed loaded.
