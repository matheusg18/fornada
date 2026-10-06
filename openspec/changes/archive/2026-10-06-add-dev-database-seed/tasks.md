# Tasks

## 1. Schema (`bakery-data-model`)

- [x] 1.1 Write `.devcontainer/db/schema.sql`: one transaction, `DROP TABLE IF EXISTS … CASCADE` for the 11 app tables, then `CREATE TABLE` with the columns, keys, `CHECK`s and indexes from design.md. Verify that running it twice with `psql "$DATABASE_URI" -v ON_ERROR_STOP=1 -f .devcontainer/db/schema.sql` succeeds, and that a scratch table created between the runs survives
- [x] 1.2 Check the constraint scenarios in `specs/bakery-data-model` with a throwaway SQL script in the scratchpad: exact `89.90` round-trip and `89.90 * 2.5 = 224.750`, negative price, duplicate slug or phone, unknown allergen or link kind, inverted pan range, second override for a date, coupon at 60% accepted, malformed phone, 2.3 kg weight, delivery without address, pickup with neighborhood, unknown status, cancelled without timestamp, message to an unknown phone, escalation without phone. Verify that each rejected insert fails and each accepted one succeeds, then rerun `schema.sql` to clean up

## 2. Seed generator and data (`dev-seed-data`)

- [x] 2.1 Write `.devcontainer/db/generate_seed.py` (PEP 723 metadata with `faker`, fixed seeds): constants for allergens, 12 products (2 custom, 1 without wheat flour marked `may_contain` gluten), 3 pan sizes, 8 Recife neighborhoods, coupons in the five states, and holidays plus the Dec 24 override. Verify that `uv run .devcontainer/db/generate_seed.py` prints SQL and that `git status` shows no change to `pyproject.toml` or `uv.lock`
- [x] 2.2 Add customers and orders to the generator: about 120 customers, capacity fixtures (+3 and +4 at 15.0 kg, +5 at 13.0 kg), about 200 orders over −90..+14 with status by date, weights inside the pan range and amounts following the quote rule. Also add one confirmation message per non-cancelled order and the used-up coupon reaching its limit on past orders. Write `.devcontainer/db/seed.sql` and verify that two consecutive runs produce identical output (`diff`)
- [x] 2.3 Apply `schema.sql` and then `seed.sql` with `psql "$DATABASE_URI"`, and verify every `dev-seed-data` scenario with SQL queries: counts, cross-contamination product, used-up coupon count, status vs date, returning customers, the +3 and +5 kg sums, quote-rule amounts, one message per order to the right phone, empty escalations, and dates in the São Paulo calendar
- [x] 2.4 Write `.devcontainer/db/README.md` (what each file is, the reset command, how to regenerate, the holiday overlap caveat). Verify that the reset command runs as written

## 3. Dev environment wiring

- [x] 3.1 Mount `./db` read-only at `/fornada-db` in the `postgres` service in `.devcontainer/compose.yaml`, and extend `init-databases.sh` to run `SET ROLE fornada` with schema and seed on the `fornada` database. Verify with `bash -n` on the script. Then run the script's `fornada` psql invocation by hand through `DATABASE_URI`, with the paths pointing at `.devcontainer/db/` (`SET ROLE fornada` is a no-op for that role), and confirm that `\dt` lists every app table owned by `fornada`. The real empty-volume path is checked by the maintainer (see follow-up)
- [x] 3.2 Update AGENTS.md (dev environment section) with one line about the seed on an empty volume and the reset command. Verify that the command in AGENTS.md matches `.devcontainer/db/README.md`

## Workflow follow-up

- The maintainer verifies the fresh-volume path on the host (recreate the Postgres volume, rebuild, check `\dt` and the row counts), because the dev container has no Docker socket.
- Commit with a Conventional Commits message (`feat: add dev database schema and seed`).
- Archive the change with `/opsx:archive` after review.
