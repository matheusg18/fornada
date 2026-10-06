# Proposal

## Why

Every tool in the frozen scope reads or writes bakery data: catalog, capacity, delivery fees, coupons, customers and orders. The `fornada` database in the dev container is empty, so no tool can be written or tried yet. This change adds the first data model and a repeatable seed. That gives the agent something to read and lets the simulator run conversations against realistic data, including other customers' orders, which are the private-data leg of the trifecta.

This change belongs to **phase 1 (naive foundation)**. It stays within the frozen scope: it adds tables and seed data that the 9 existing tools need, and no tool, feature or defense. Migrations and an ORM are deliberately out of scope. The schema is plain SQL that can be dropped and recreated while the model is still changing.

## What Changes

- New `.devcontainer/db/schema.sql`. Drops and recreates the app tables:
  - Catalog: `products`, `allergens`, `product_allergens`, `pan_sizes`.
  - Rules: `neighborhoods`, `capacity_overrides`, `coupons`.
  - Customer data: `customers`, `orders`.
  - Side effects: `sent_messages`, `escalations`.
  - One cake per order. Weight is free inside the pan size's range (for example, 4 kg in a G pan).
  - Money as exact decimals in BRL with 2 places (`numeric(10,2)`).
  - A coupon's percentage has no database bound. `apply_coupon` owns that rule.
- New `.devcontainer/db/seed.sql`, generated once and committed.
  - Seed data: 12 products (2 custom), 3 pan sizes, 8 Recife neighborhoods, a few coupons (valid, expired, used up, inactive), capacity overrides for holidays, about 120 fake customers and about 200 orders with their confirmation messages.
  - Order dates are relative to the day the seed runs, so some days just past the lead time are always full or nearly full.
- New `.devcontainer/db/generate_seed.py`, a standalone script (Faker, locale `pt_BR`, fixed random seed) that writes `.devcontainer/db/seed.sql`. It is committed for reproducibility. It runs with `uv run` and its inline script metadata, so it adds no dependency to any workspace member.
- `.devcontainer/postgres/init-databases.sh` runs schema and seed on the `fornada` database as the `fornada` role. This happens only on the first start of an empty data volume. `compose.yaml` mounts `.devcontainer/db/` read-only into the Postgres container.
- Documented reset command: `psql "$DATABASE_URI" -f .devcontainer/db/schema.sql -f .devcontainer/db/seed.sql`.

Not in this change: SQLAlchemy models, migrations, tool code, the default daily capacity (15 kg) and grams-per-serving settings (these arrive with the tools that use them), an audit log table (phase 7), and idempotency keys on orders (a fix waiting for an observed failure).

## Capabilities

### New Capabilities
- `bakery-data-model`: the tables, columns and integrity constraints that hold the catalog, business rules, customers, orders and recorded side effects.
- `dev-seed-data`: what the dev database contains after seeding, how the seed is generated, and when and how it is applied.

### Modified Capabilities

None. The existing `app-config` and `structured-logging` specs are unaffected.

## Impact

- **Files:** new `.devcontainer/db/schema.sql`, `.devcontainer/db/seed.sql`, `.devcontainer/db/generate_seed.py`, `.devcontainer/db/README.md`.
- **Dev environment:** `.devcontainer/postgres/init-databases.sh` and `.devcontainer/compose.yaml` (one read-only volume mount). An existing Postgres volume is not re-seeded automatically. Run the reset command, or recreate the volume on the host.
- **Dependencies:** none added to `pyproject.toml`. Faker is resolved by `uv run` only when the generator runs.
- **Code:** none. `apps/api` is unchanged.
