import datetime as dt
from decimal import Decimal

import psycopg
import pytest
from fornada_api.repositories import CapacityRepository
from fornada_api.services.capacity import CapacityReport, CapacityService
from fornada_api.services.clock import FixedClock
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fornada_evals.isolation import isolated_database, sweep

pytestmark = pytest.mark.anyio

DAILY_CAPACITY_KG = Decimal(15)
# The Monday the seed is pinned to (design.md, decision 3); day +3 is full.
SEED_DAY = dt.date(2026, 3, 9)


async def capacity(
    sessionmaker: async_sessionmaker[AsyncSession], run_day: dt.date, day: dt.date
) -> CapacityReport:
    async with sessionmaker() as session:
        service = CapacityService(
            CapacityRepository(session), FixedClock(run_day), DAILY_CAPACITY_KG
        )
        return await service.check(day)


async def add_order(sessionmaker: async_sessionmaker[AsyncSession], day: dt.date) -> None:
    """A 2 kg pickup order on `day`, copied from a seed order's customer and product."""
    async with sessionmaker() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO orders (customer_id, product_id, pan_size_code, delivery_date,"
                " fulfillment, status, weight_kg, price_per_kg, subtotal, delivery_fee,"
                " discount, total, deposit)"
                " SELECT customer_id, product_id, 'P', :day, 'pickup', 'pending_payment', 2,"
                " price_per_kg, 0, 0, 0, 0, 0 FROM orders LIMIT 1"
            ),
            {"day": day},
        )


def schemas(database_url: str) -> set[str]:
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'eval\\_%'"
        ).fetchall()
    return {row[0] for row in rows}


def public_orders(database_url: str) -> int | None:
    """Orders in `public`, or None when it has no `orders` table (the API's tests create it)."""
    with psycopg.connect(database_url) as conn:
        row = conn.execute("SELECT to_regclass('public.orders')").fetchone()
        if not row or row[0] is None:
            return None
        row = conn.execute("SELECT count(*) FROM public.orders").fetchone()
    assert row
    return row[0]


async def test_schema_gets_the_seed(database_url: str) -> None:
    async with isolated_database(database_url) as db:
        async with db.sessionmaker() as session:
            products = await session.scalar(text("SELECT count(*) FROM products"))

        assert products == 12
        full_day = await capacity(db.sessionmaker, db.run_day, db.run_day + dt.timedelta(3))
        assert full_day.free_kg == 0


async def test_orders_do_not_leak(database_url: str) -> None:
    before = public_orders(database_url)
    async with isolated_database(database_url) as first, isolated_database(database_url) as second:
        day = first.run_day + dt.timedelta(8)
        seed_used = (await capacity(second.sessionmaker, second.run_day, day)).used_kg

        await add_order(first.sessionmaker, day)

        assert (await capacity(first.sessionmaker, first.run_day, day)).used_kg == seed_used + 2
        assert (await capacity(second.sessionmaker, second.run_day, day)).used_kg == seed_used
    assert public_orders(database_url) == before


async def test_schema_is_dropped_after_the_run(database_url: str) -> None:
    async with isolated_database(database_url) as db:
        assert db.schema in schemas(database_url)

    assert db.schema not in schemas(database_url)


async def test_schema_is_dropped_when_the_run_raises(database_url: str) -> None:
    name = ""
    with pytest.raises(RuntimeError, match="boom"):
        async with isolated_database(database_url) as db:
            name = db.schema
            raise RuntimeError("boom")

    assert name
    assert name not in schemas(database_url)


async def test_sweep_drops_leftover_schemas(database_url: str) -> None:
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("CREATE SCHEMA eval_leftover")

    dropped = await sweep(database_url)

    assert "eval_leftover" in dropped
    assert "eval_leftover" not in schemas(database_url)


async def test_run_day_is_the_seed_day(database_url: str) -> None:
    async with isolated_database(database_url) as db:
        assert db.run_day == SEED_DAY
        full_day = await capacity(db.sessionmaker, db.run_day, SEED_DAY + dt.timedelta(3))
        assert full_day.free_kg == 0
