# Dev database

Plain SQL for the `fornada` database in the dev container. No migrations: while the model is still changing, the schema is dropped and recreated.

| File | What it is |
|---|---|
| `schema.sql` | Drops and recreates the 11 app tables, by name, in one transaction. Other tables in the database (for example the LangGraph checkpointer's) are left alone. |
| `seed.sql` | Fictional bakery data: catalog, neighborhoods, coupons, holiday overrides, customers, orders and confirmation messages. Generated, do not edit by hand. |
| `generate_seed.py` | Writes `seed.sql`. Fixed random seeds, so the output is reproducible. |

## Reset

From inside the dev container, back to a fresh seed:

```sh
psql "$DATABASE_URI" -v ON_ERROR_STOP=1 -f .devcontainer/db/schema.sql -f .devcontainer/db/seed.sql
```

The seed also runs by itself, once, when Postgres starts on an empty data volume. An existing volume is never re-seeded automatically, so use the command above.

## Dates are relative

The seed sets `America/Sao_Paulo` and writes every date as an offset from today, so it stays fresh whenever it runs:

- orders are delivered from 90 days ago to 14 days ahead;
- days +3 and +4 are full (15.0 kg) and day +5 has 2 kg free, all beyond the 48 h lead time;
- fixed-day holidays (capacity 0) exist for this year and the next, plus a 25 kg override on Dec 24.

Holiday caveat: if a run lands so that day +3..+5 falls on a holiday (for example, on Dec 22), the "full" day overlaps a closed one. A check of `orders > capacity` still refuses it.

## Regenerate

```sh
uv run .devcontainer/db/generate_seed.py > .devcontainer/db/seed.sql
```

The script declares its own dependency (`faker`) inline, so it adds nothing to the workspace. A newer Faker can change the generated names. The committed `seed.sql` is the source of truth: regenerate only on purpose and review the diff.

## Design notes

- Money is `numeric(10,2)` in BRL. Read it as `Decimal`, never `float`.
- The database checks integrity only (keys, shapes, non-negative amounts). Business rules such as totals, capacity, lead time and the coupon limit belong to the tools, so `v0` can break them and the failure can be observed.
- Any schema edit wipes dev data. Run the reset command afterwards.
