# Design

## Context

See proposal.md, Why. Current state that shapes the approach:

- **Dev Postgres.** `.devcontainer/compose.yaml` runs one `postgres` service (`postgres:18.6-trixie`, `TZ=UTC`). Its `init-databases.sh` creates the `fornada` and `langfuse` roles and databases and loads `schema.sql` and `seed.sql` once, on an empty volume. `dev` gets only `DATABASE_URI`.
- **The seed's dates.**
  - `generate_seed.py` emits every date as `CURRENT_DATE + n` (525 occurrences).
  - Timestamps are `CURRENT_DATE + n + TIME 'hh:mm'`.
  - Holidays are `make_date(extract(year FROM CURRENT_DATE)::int + k, m, d)`.
  - The file starts with `SET TIME ZONE 'America/Sao_Paulo'`.
  - `schema.sql` drops and recreates the 11 app tables by name and leaves the LangGraph checkpointer's tables alone.
- **The API's integration tests.**
  - They read `DATABASE_URI`.
  - Writes are rolled back through `rollback_sessionmaker`, but the endpoint tests commit through the app's own engine.
  - "Today" comes from `SystemClock(America/Sao_Paulo).today()` in `repositories/test_repositories.py` and `agents/test_tools.py`.
  - The full day comes from a query (`full_day` in `conftest.py`) that skips when the seed has aged past it.
  - The endpoint, span and memory tests do not depend on dates.
- **The dev container is the coding agent's sandbox.** It has no Docker socket, so it cannot start containers, and the test database must come from compose.

## Goals / Non-Goals

**Goals:**
- An integration test session gives the same result on any calendar day and after any amount of dev work, with no manual reset.
- The test server is the same PostgreSQL build as dev, and as CI later.
- The same `schema.sql` and `seed.sql` serve dev and tests.

**Non-Goals:**
- **Per-test isolation inside the API suite.** It keeps its rollback fixture. Per-run isolation for concurrent eval runs stays in `add-eval-harness` (schema per run), now on this server.
- **Running two API test sessions at once.** The same session-start reload serves one session at a time (see Risks).
- **Freezing the server clock.** Column defaults such as `created_at` keep the real `now()`.
- **CI.** `add-ci-eval-gate` reuses the fixtures with a `services:` container.

## Decisions

### 1. A `postgres-test` compose service on tmpfs

```yaml
postgres-test:
  image: docker.io/postgres:18.6-trixie   # same tag as `postgres`; Dependabot bumps both
  restart: unless-stopped
  command: ["postgres", "-c", "fsync=off", "-c", "synchronous_commit=off",
            "-c", "full_page_writes=off"]
  environment:
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: ${POSTGRES_TEST_PASSWORD:?}
    FORNADA_TEST_DB_PASSWORD: ${FORNADA_TEST_DB_PASSWORD:?}
    TZ: UTC                                # as the dev server
    PGTZ: UTC
  tmpfs:
    - /var/lib/postgresql                  # PG 18 keeps PGDATA under a versioned subdirectory
  volumes:
    - ./postgres-test/init-test-database.sh:/docker-entrypoint-initdb.d/init-test-database.sh:ro
  mem_limit: 512m
  healthcheck: { test: ["CMD-SHELL", "pg_isready -U postgres"], interval: 3s, timeout: 3s, retries: 10 }
```

- **Empty on every start.** The data directory is on tmpfs, so the image's entrypoint runs `initdb` and the init script on every start. A restart is a full reset.
- **The init script only creates the role and the database.** It creates `fornada_test` (LOGIN, password) and the database `fornada_test`, owned by it. The test session loads tables and the seed (decision 4), so the seed can never be stale from an earlier start.
- **Durability off:** `fsync`, `synchronous_commit` and `full_page_writes`. A crash loses only test data.
- **Memory.** tmpfs pages count against the container's memory limit. The seeded database is a few MB, and the default `shared_buffers` is 128 MB, so 512 MiB leaves headroom. A killed container restarts empty, which is harmless.
- **No published port.** The service is reachable from `dev` as `postgres-test:5432`.
- **Wiring.** `dev` gets `TEST_DATABASE_URI=postgresql://fornada_test:${FORNADA_TEST_DB_PASSWORD}@postgres-test:5432/fornada_test`, and depends on the service being healthy, as it does on `postgres`.
- **Secrets.** `init-env.sh` adds `POSTGRES_TEST_PASSWORD` and `FORNADA_TEST_DB_PASSWORD` with `ensure_secret`, so existing `.devcontainer/.env` files get them on the next start.

*Alternatives:*
- **testcontainers.** It needs the Docker socket (forbidden) or privileged Docker-in-Docker inside the sandbox. In CI it adds nothing over a service container.
- **A `fornada_test` database on the dev server.** No new service, but tests would share the dev server's state and load.
- **A Postgres server installed in the dev image, with `pytest-postgresql`'s `postgresql_proc`.** It needs no socket and the process lives only for the session. But it grows the image and its build, and its Postgres package can drift from the compose image's tag.
- **A profile so the service starts on demand.** Nothing inside the dev container can start it (no socket), so it would become a manual step on the host.

### 2. The seed's run day comes from a session setting

`generate_seed.py` emits, right after `SET TIME ZONE`:

```sql
SELECT set_config('fornada.seed_day',
                  coalesce(nullif(current_setting('fornada.seed_day', true), ''),
                           CURRENT_DATE::text),
                  false);
DO $$ BEGIN
  IF current_setting('fornada.seed_day') !~ '^\d{4}-\d{2}-\d{2}$' THEN
    RAISE EXCEPTION 'fornada.seed_day must be YYYY-MM-DD, got %', current_setting('fornada.seed_day');
  END IF;
END $$;
```

Every `CURRENT_DATE` in a value becomes `current_setting('fornada.seed_day')::date`; the holiday years take theirs from it too.

- **Callers:**
  - Without the setting, as in the dev reset, `init-databases.sh` and the simulator's runs, the day is today in São Paulo, as before.
  - From `psql`: `PGOPTIONS='-c fornada.seed_day=2026-03-09'`.
  - From a driver: `SET fornada.seed_day = '2026-03-09'` in the session before the file.
- **Why the format check.** A cast alone would accept `09/03/2026` and read it per `DateStyle` (`MDY`: 3 September), silently seeding the wrong day.
- **The generated file is longer but plain SQL,** still applied by `psql` alone. The generator stays reproducible. With no setting, the rows equal today's file's rows; task 2.3 checks this.

*Alternatives:*
- **A psql variable (`:seed_day`).** Only `psql` expands it; psycopg would send `:seed_day` as text.
- **A temporary function (`pg_temp.seed_day()`).** Shorter expressions, but it needs schema-qualified calls and a `CREATE FUNCTION` in every session. It adds nothing over the setting.
- **Freezing the date in the server.** Postgres has no clock override (`pg_mockable` exists but does not reach column defaults), and it would also affect the checkpointer.

### 3. One fixed seed day: Monday 2026-03-09

- **Why a fixed day.** A seed relative to the wall clock rotates its weekday daily. A test can pass on Monday and fail on Friday.
- **Why this one.** It is a Monday, after Carnaval (16–17 Feb 2026). Days +3..+5 (12–14 March), the full and nearly full days, hit no fixed holiday.
- **Where it lives.** `SEED_DAY` in `apps/api/tests/integration/conftest.py`. The eval suite will define its own constant with the same value when `add-eval-harness` adopts this server. The value is documented in `.devcontainer/db/README.md`.

### 4. The API's integration tests seed the test database per session

In `apps/api/tests/integration/conftest.py`:

- **Environment.** `TEST_DATABASE_URI` replaces `DATABASE_URI`. The skip reason names it, and `db_env` sets `DB__URL` to it, so the app's engine and checkpointer use the test database too.
- **Seeding.** A session-scoped autouse fixture runs once per session over psycopg with autocommit, in one session: `SET fornada.seed_day`, then `schema.sql`, then `seed.sql`. This is the same pattern as `fornada_evals.isolation`. It takes about 0.3 s.
- **The full day.** `full_day` becomes `SEED_DAY + timedelta(3)`, with no query and no skip.
- **The clock.** Tests that need today use `FixedClock(SEED_DAY)` instead of `SystemClock(...)`; test_tools passes it to `build_tools`.

The endpoint tests build the app with its own `SystemClock`. They assert no seeded dates today; any future endpoint test that does needs the clock injected through the app settings, which is out of scope here.

## Risks / Trade-offs

- **[Two API test sessions at once, for example the maintainer's and the agent's]** Each one reloads the `public` tables at start, so one can reset the tables under the other. → Documented. The suite takes seconds, and the eval suite, which can run long, isolates each run in its own schema.
- **[A forgotten `fornada.seed_day` in a test path]** The seed would fall back to today, and date assertions would drift again. → The session fixture sets it explicitly. A test asserts that the seed day's +3 holds 15.0 kg, so a wrong day fails loudly.
- **[tmpfs counts against memory]** → `mem_limit: 512m`. An OOM kill restarts an empty server, and the next session reseeds.
- **[The first rebuild]** Existing environments need `init-env.sh` to append the two secrets and the dev container to be rebuilt. → Both happen on the next "Rebuild Container", and the notes in `AGENTS.md` say so.
- **[`created_at` keeps the real date]** A future rule that reads it would disagree with the seed day. → Listed as a known limit in the proposal and in `.devcontainer/db/README.md`.

## Migration Plan

1. Land the generator change and the regenerated seed. The dev database is unaffected until its next reset, which behaves as today.
2. Add the service and the secrets. The maintainer rebuilds the dev container once.
3. Point the API's integration tests at `TEST_DATABASE_URI`.

Rollback: revert the commits. The dev database never changes.

Follow-up: switch `add-eval-harness` decision 3 to `TEST_DATABASE_URI` and the fixed day, then resume its task 4.1.
