# Tasks

## 1. Setup

- [x] 1.1 Run `uv add --package fornada-api "sqlalchemy[asyncio]" "psycopg[binary]" "fastapi[standard]"` from the repo root; verify `uv sync` succeeds and `uv.lock` lists the three packages
- [x] 1.2 Register a pytest `integration` marker in the root `pyproject.toml` and create `apps/api/tests/integration/conftest.py` that skips the module when `DATABASE_URI` is unset and sets `DB__URL` from it; verify `uv run --package fornada-api pytest` still passes and reports the new directory as collected with zero tests

## 2. Database settings (`app-config`)

- [ ] 2.1 Add `DbSettings` (`url: SecretStr`, scheme validator for `postgresql://`/`postgres://`) and the required `db` field to `Settings`; update the existing unit-test fixture to set `DB__URL`; verify the existing `test_config.py` tests pass
- [ ] 2.2 Add unit tests for the `app-config` delta scenarios (missing `DB__URL`, non-PostgreSQL URL, plain URL accepted, password masked in `str`/`repr`/dump); verify they pass
- [ ] 2.3 Add `DB__URL` to `.env.example` with a placeholder and a comment pointing to `DATABASE_URI`, and update the README "Configuration" section; verify the `.env.example` loading test still passes

## 3. Models (`database-access`)

- [ ] 3.1 Create `models/base.py` (`Base`, `type_annotation_map`) and the `OrderStatus`, `Fulfillment` and `AllergenKind` `StrEnum`s; verify `python -c "import fornada_api.models"` works
- [ ] 3.2 Implement the catalog models (`Product`, `Allergen`, `ProductAllergen`, `PanSize`) and operations models (`Neighborhood`, `CapacityOverride`, `Coupon`) mirroring `schema.sql`; verify `Base.metadata.tables` lists the 7 tables
- [ ] 3.3 Implement `Customer`, `Order`, `SentMessage` and `Escalation` with the relationships from the design (`lazy="raise"`); verify `Base.metadata.tables` lists all 11 app tables and `sqlalchemy.orm.configure_mappers()` raises nothing
- [ ] 3.4 Write `tests/integration/test_models.py`: live column names and nullability match `Base.metadata` for every table; every row of every model loads and the count matches; `bolo-chocolate` price is `Decimal("89.90")`; order dates are `date` and aware `datetime`; a cancelled order has `OrderStatus.CANCELLED`; `bolo-chocolate` allergen links include `gluten`/`contains` and `soy`/`may_contain`; an order's customer id matches; verify all pass against the seeded database

## 4. Connection dependency (`database-access`)

- [ ] 4.1 Implement `infrastructure/engine.py`: URL rewrite to `postgresql+psycopg`, cached `get_engine()` (`application_name="fornada-api"`, `pool_pre_ping=True`) and cached `get_sessionmaker()` (`expire_on_commit=False`, `autoflush=False`); verify a unit test that the rewrite keeps user, password, host, port and database
- [ ] 4.2 Implement `dependencies/database.py` with `get_db_session` (consumes `get_sessionmaker()`) and `DbSessionDep`; re-export `DbSessionDep` from `dependencies/__init__.py`; verify `python -c "from fornada_api.dependencies import DbSessionDep"` works
- [ ] 4.3 Write `tests/integration/test_session.py`: a session that adds a `SentMessage` and closes without commit leaves no row; a session closed after an exception returns its connection to the pool (`engine.pool.checkedout() == 0`); verify both pass

## 5. FastAPI app (`api-service`)

- [ ] 5.1 Create `fornada_api/main.py` with the lifespan (settings, logging, `get_engine()` on startup, `await get_engine().dispose()` on exit) and `fornada_api/health.py` with `GET /health/db` (count + `select(Model).limit(1)` per mapper, 503 `unavailable` on `SQLAlchemyError`/`OSError`, exception logged); include the router; verify `uv run --package fornada-api python -c "from fornada_api.main import app"` works
- [ ] 5.2 Add `[tool.fastapi] entrypoint` to `apps/api/pyproject.toml`, point the `fornada-api` script at `uvicorn.run("fornada_api.main:app")`, and find the dev command that works from the repo root; verify `curl localhost:8000/health/db` returns 200 with that command running
- [ ] 5.3 Write `tests/integration/test_health.py`: 200 with `status == "ok"`, 11 tables, `products == 12`, `neighborhoods == 8`; body contains no seeded customer name or phone; 503 `unavailable` with `DB__URL=postgresql://x:secret@127.0.0.1:1/x` (after clearing the settings and engine caches) and the body lacks `secret` and `127.0.0.1`; no `pg_stat_activity` row with `application_name = 'fornada-api'` after the `TestClient` context exits; startup without `DB__URL` raises `ConfigError` naming it; verify all pass
- [ ] 5.4 Document running the API (dev command, `/docs`, `/health/db`) and the integration tests in `apps/api/README.md`; verify every documented command runs as written

## 6. Integration check

- [ ] 6.1 Run the full suite from the repo root (`uv run --package fornada-api pytest`) inside the dev container, then reset the database with the command in `.devcontainer/db/README.md` and run it again; verify both runs pass and no test left rows behind

## Workflow follow-up

- Commit each step with a Conventional Commits message (for example `feat: add database models and session dependency`).
- Archive the change with `/opsx:archive` after review.
