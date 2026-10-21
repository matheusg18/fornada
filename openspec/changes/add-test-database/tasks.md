# Tasks

## 1. Seed run day as a parameter

- [x] 1.1 Change `.devcontainer/db/generate_seed.py` so it emits the `fornada.seed_day` setup and format check (design decision 2) and uses `current_setting('fornada.seed_day')::date` wherever it emitted `CURRENT_DATE`, holiday years included; regenerate `seed.sql` and verify a second run is byte-identical and `grep -c CURRENT_DATE` matches only the fallback
- [x] 1.2 Verify the pinned day, in a scratch schema on the dev server: with `PGOPTIONS='-c fornada.seed_day=2026-03-09'`, non-cancelled orders on 2026-03-12 and 2026-03-13 total 15.0 kg, 2026-03-14 totals 13.0 kg, and the stored holidays are those of 2026 and 2027; with `09/03/2026` the seed fails before inserting rows
- [x] 1.3 Verify no regression without the setting: load the old `seed.sql` (from `main`) and the new one into two scratch schemas on the same day and diff every seeded table (excluding generated ids and `created_at`); expect no differences, then drop both schemas
- [x] 1.4 Document the parameter in `.devcontainer/db/README.md` (how to pin the day from `psql` and from a driver, the format check, the `created_at` limit) and verify the documented `psql` command runs as written

## 2. Test-only PostgreSQL service

- [x] 2.1 Add `POSTGRES_TEST_PASSWORD` and `FORNADA_TEST_DB_PASSWORD` to `.devcontainer/init-env.sh` with `ensure_secret`, and to `.devcontainer/.env.example`; verify by reading the script that an existing `.env` only gets the two lines appended
- [x] 2.2 Add `.devcontainer/postgres-test/init-test-database.sh` (role `fornada_test` and database `fornada_test`, owned by it) and the `postgres-test` service in `.devcontainer/compose.yaml` (design decision 1), with `TEST_DATABASE_URI` and `depends_on` on `dev`; verify `docker compose -f .devcontainer/compose.yaml config` parses (on the host, by the maintainer)
- [x] 2.3 Maintainer rebuilds the dev container; verify from inside it that `psql "$TEST_DATABASE_URI" -c 'SELECT version()'` reports the dev server's version, the role cannot reach the `fornada` database, and after `docker compose restart postgres-test` (host) the database has no app tables
- [x] 2.4 Document the service in `AGENTS.md` (Dev environment: services, memory limits, `TEST_DATABASE_URI` in the "Environment files" note on what `dev` receives) and verify the described commands match the compose file

## 3. API integration tests on the test database

- [x] 3.1 In `apps/api/tests/integration/conftest.py`: read `TEST_DATABASE_URI` (skip reason names it; no fallback to `DATABASE_URI`), add `SEED_DAY = dt.date(2026, 3, 9)`, a session-scoped autouse fixture that loads `schema.sql` and `seed.sql` with `fornada.seed_day` set, and make `full_day` return `SEED_DAY + 3 days`; add a test that the seed day's +3 holds 15.0 kg; verify with `uv run task test:integration`
- [x] 3.2 Replace `SystemClock(...).today()` with `FixedClock(SEED_DAY)` in `repositories/test_repositories.py` and `agents/test_tools.py`; verify `uv run task check` in `apps/api` passes with 442 + 1 tests and 0 skipped integration tests
- [ ] 3.3 Verify independence from the dev database and the calendar: count the dev database's orders before and after `uv run task test:integration` (unchanged); commit an extra order into the test database by hand and rerun (same results); then run `uv run task check` in `apps/chat`, `apps/simulator` (counts unchanged)

## Workflow follow-up

- Update `add-eval-harness` (design decision 3, tasks 3.x) to use `TEST_DATABASE_URI` and a fixed run day, then merge `main` into `feat/evals` (no rebase) and resume its task 4.1.
- Archive this change after review, syncing `test-database` and `dev-seed-data`.
