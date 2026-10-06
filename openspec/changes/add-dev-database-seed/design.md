# Design

## Context

The dev container's Postgres 18 (`postgres` service, server time zone UTC) has an empty `fornada` database owned by the `fornada` role. `.devcontainer/postgres/init-databases.sh` runs once on an empty volume, as the `postgres` superuser in the `postgres` database, and creates the two roles and databases. The `dev` container reaches the database through `DATABASE_URI` (role `fornada`), and `psql` is preinstalled there. There is no ORM or migration tool yet, and the maintainer chose to postpone both. Requirements live in `specs/bakery-data-model` and `specs/dev-seed-data`.

This is periphery work in phase 1. It adds no defense, so it has no ASR, false-positive or p95 effect to measure.

## Goals / Non-Goals

**Goals:**
- A schema that every tool in the frozen scope can be written against without new tables.
- A seed that is always "fresh": full days, future orders and coupon validity stay meaningful whenever it runs.
- One command to get back to a known state between simulator runs.

**Non-Goals:**
- Migrations, SQLAlchemy models or any Python code that reads these tables.
- Database-level business validation beyond data integrity. The tools own the rules in `v0`, and phase 6 owns the guardrails.
- Seeding attack payloads or test fixtures for specific evals. Evals build their own fixtures in phase 4.

## Decisions

### Files under `.devcontainer/db/`
`.devcontainer/db/schema.sql`, `.devcontainer/db/seed.sql`, `.devcontainer/db/generate_seed.py` and a short `.devcontainer/db/README.md`. The folder is dev-environment infrastructure, like `.devcontainer/postgres/`: the `postgres` service mounts it for init, and the `dev` container reads it for reset. Alternatives: a root `db/` folder (rejected by the maintainer, to keep the repo root clean) and `apps/api/db/` (rejected for now, since the chat app and the simulator will also reset the database; the files can move once SQLAlchemy arrives).

### Tables in `public`, dropped by name
`schema.sql` starts with `DROP TABLE IF EXISTS … CASCADE` for each app table, then the `CREATE TABLE`s, all in one transaction. Alternative: a dedicated `app` schema dropped with `DROP SCHEMA … CASCADE`. Rejected because it would mean a `search_path` setting in every client for no real gain. Dropping by name is enough to keep the LangGraph checkpointer tables safe.

### Table sketch

| Table | Key columns | Notes |
|---|---|---|
| `products` | `id` identity, `slug` unique, `name`, `description`, `price_per_kg`, `cost_per_kg`, `is_custom`, `active` | `cost_per_kg` is private margin data and stays in the same table on purpose |
| `allergens` | `code` PK, `name` | `gluten`, `lactose`, `egg`, `peanut`, `tree_nuts`, `soy` |
| `product_allergens` | PK (`product_id`, `allergen_code`), `kind` | `kind` in (`contains`, `may_contain`) |
| `pan_sizes` | `code` PK, `name`, `min_kg`, `max_kg` | P 1.0–2.0, M 2.0–3.5, G 3.5–6.0 |
| `neighborhoods` | `id` identity, `name` unique, `delivery_fee`, `active` | |
| `capacity_overrides` | `date` PK, `capacity_kg`, `reason` | Default 15 kg lives in app config, added with `check_capacity` |
| `coupons` | `code` PK, `percent_off`, `valid_from`, `valid_until`, `max_uses` nullable, `active` | No usage counter |
| `customers` | `id` identity, `name`, `phone` unique, `created_at` | `phone ~ '^\+55[0-9]{10,11}$'` |
| `orders` | `id` identity, FKs to customer/product/pan size/neighborhood/coupon, `delivery_date`, `fulfillment`, `address`, `reference_photo_description`, `notes`, `status`, `weight_kg`, price snapshot and amounts (`price_per_kg`, `subtotal`, `delivery_fee`, `discount`, `total`, `deposit`), `payment_link`, `created_at`, `cancelled_at`, `refund_amount`, `cancel_reason` | Indexes on (`delivery_date`) and (`customer_id`) |
| `sent_messages` | `id` identity, `to_phone`, `body`, `order_id` nullable FK, `created_at` | No FK to customers, so the exfiltration case is representable |
| `escalations` | `id` identity, `thread_id`, `phone` nullable, `reason`, `created_at` | |

Types: `bigint generated always as identity` for surrogate keys. Money is `numeric(10,2)` (BRL, up to 99,999,999.99). Weights are `numeric(4,1)`. Delivery and override dates are `date`, and every timestamp is `timestamptz`. Closed value sets use `text` + `CHECK` instead of `CREATE TYPE`, because a `CHECK` is a one-line edit while there are no migrations.

### Integrity constraints only, no business rules
The database enforces shape:
- not-null fields and foreign keys;
- non-negative money and the 0.5 kg weight step;
- pickup/delivery consistency;
- cancelled ⇔ `cancelled_at`.

It does not enforce the following, because each one is a rule `v0` is allowed to break so phase 3 can observe it:
- that totals add up, or that they match the catalog;
- that an order's weight falls in its pan's range (that would need a trigger across tables);
- capacity per day;
- lead time;
- coupon validity at use;
- coupon percentage bounds (not even `> 0`).

The coupon percentage has no `CHECK` at all, by the maintainer's choice. The 10% business rule lives only in `apply_coupon`, so a bad coupon row is representable.

### Money as `numeric(10,2)`, not integer cents
The PostgreSQL wiki recommends `numeric` ("Numeric, or (rarely) integer"), and so does Crunchy Data. Integer cents fit payment-API boundaries and high-volume ledgers, and neither applies here. The maintainer chose `numeric` after reviewing both options. Two things decided it:
- Error analysis reads these values in `psql` and in traces, where `89.90` is clearer than `8990`.
- The classic failure of integer cents is a layer forgetting to divide by 100. Here that layer would be the LLM, reading `8990` and saying "R$ 8.990".

Python code will read the columns as `Decimal`, never `float`. Most quote math stays exact in SQL as `numeric`. The one division (the 50% deposit) is rounded explicitly with `round(total / 2, 2)`, which rounds half away from zero. A total has 2 decimal places, so this equals rounding up to the cent. The JSON problem (no decimal type, and the LLM sends `89.9` as a float) is a tool-boundary concern for the tools change. One option is to return amounts as formatted strings and parse inputs into `Decimal`.

Alternatives: integer cents, rejected for the readability and conversion risk above. The built-in `money` type, rejected because it is locale-dependent and the PostgreSQL wiki advises against it.

### One cake per order, weight free within the pan range
The maintainer chose this over `order_items`. `calculate_quote` and `create_order` get flat arguments, and the "40 people → 4 kg" check compares one number. "Half chocolate, half ninho" needs two orders, which is accepted until phase 3 shows that it matters.

### Seed with relative dates
The generator decides everything (customers, products, weights, statuses, offsets), then writes absolute values except dates. Dates come out as SQL expressions relative to a run day:

- `seed.sql` starts with `SET TIME ZONE 'America/Sao_Paulo'`, so `CURRENT_DATE` and `now()` follow the bakery's calendar even though the server runs in UTC. The setting is session-scoped.
- Delivery dates are `CURRENT_DATE + <n>` and creation timestamps are `now() - interval '<n> days <h> hours'`.
- Fixed-day holidays (Jan 1, Apr 21, May 1, Sep 7, Oct 12, Nov 2, Nov 15, Nov 20, Dec 25) are written as `make_date(extract(year from CURRENT_DATE)::int + k, m, d)` for `k` in 0 and 1, with capacity 0. Moving holidays (Carnival, Easter) are left out. One extra override on Dec 24 raises capacity to 25 kg.
- Coupon validity windows are relative too, so the "valid" coupon never expires on its own.

Alternative: regenerate the SQL with absolute dates before each run. Rejected because the committed file would go stale, and the automatic init would freeze whatever date the file was generated on.

### Generator as a PEP 723 script
`.devcontainer/db/generate_seed.py` declares `dependencies = ["faker"]` in inline script metadata and runs with `uv run .devcontainer/db/generate_seed.py > .devcontainer/db/seed.sql`. It does not touch `pyproject.toml` or `uv.lock`. It uses `Faker("pt_BR")` with `Faker.seed(...)` and its own `random.Random(...)` with fixed seeds. The output is sorted and stable, so diffs stay readable. The Faker version is not pinned. A newer Faker can produce different names, which is acceptable because the committed SQL is the source of truth, not the generator's output.

Products, pan sizes, neighborhoods, allergens and coupons are hand-written constants in the generator, with pt-BR names. The neighborhoods are in Recife, and the shop sits in Imbiribeira (lowest fee): Imbiribeira, Ipsep, Boa Viagem, Pina, Ibura, Jordão, Afogados and Areias. Faker supplies only customers, street addresses and free text. Phones use area code 81 (`+5581 9XXXXXXXX`), with uniqueness checked in the generator.

The seed keeps `America/Sao_Paulo` rather than `America/Recife`. Both are UTC−3 with no daylight saving, and the seed must match `APP__TIMEZONE`'s default.

Capacity fixtures are placed first: orders that fill days +3 and +4 to 15.0 kg and day +5 to 13.0 kg. The remaining orders are then spread over −90..+14 while each day stays at or below 15 kg. Orders that reach the used-up coupon's limit are placed on past dates.

### Init on an empty volume
`compose.yaml` mounts `./db` read-only at `/fornada-db` in the `postgres` service. After creating the databases, `init-databases.sh` runs one `psql` session on the `fornada` database: `-c 'SET ROLE fornada' -f /fornada-db/schema.sql -f /fornada-db/seed.sql`. psql runs `-c` and `-f` in order in one session, so `SET ROLE` makes `fornada` the owner of every object. Alternative: drop the `.sql` files straight into `docker-entrypoint-initdb.d`. Rejected because the entrypoint runs them in the `postgres` database as superuser.

### Reset from the dev container
`psql "$DATABASE_URI" -v ON_ERROR_STOP=1 -f .devcontainer/db/schema.sql -f .devcontainer/db/seed.sql`. This is documented in `.devcontainer/db/README.md` and in the AGENTS.md dev environment section. There is no wrapper script.

## Risks / Trade-offs

- **The seed runs only on a new volume, but the maintainer's volume already exists.** → Run the reset command once. To test the init path, recreate the volume on the host (`docker compose down -v` or the Dev Containers rebuild without cache). The agent cannot do this from inside the container, because there is no Docker socket.
- **A relative capacity day (+3..+5) can fall on a holiday override, for example a seed run on Dec 22.** → In that case the full day overlaps a closed day. This is accepted, because the check `orders > capacity` still refuses. `.devcontainer/db/README.md` documents it.
- **Faker output changes between versions.** → The committed `seed.sql` is authoritative. Regenerate only on purpose and review the diff.
- **`SET TIME ZONE` in the seed could leak into a reused session.** → psql sessions end with the command. The schema script does not rely on it.
- **Without migrations, every schema edit wipes dev data.** → Accepted for phase 1. The reset command is the workflow.

## Migration Plan

There is no deployed data to migrate. Rollback is to revert the commit and either drop the app tables or recreate the volume.
