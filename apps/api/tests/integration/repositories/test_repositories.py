"""Repositories against the seeded database (see the `dev-seed-data` spec)."""

import datetime as dt
from collections.abc import AsyncIterator
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fornada_api.models import Customer, Order, SentMessage
from fornada_api.repositories import (
    CapacityRepository,
    CatalogRepository,
    CouponRepository,
    CustomerRepository,
    OrderRepository,
    SideEffectRepository,
)
from fornada_api.services import ports
from fornada_api.services.clock import SystemClock

pytestmark = pytest.mark.anyio

RUN_DAY = SystemClock(ZoneInfo("America/Sao_Paulo")).today()
DAY = dt.timedelta(days=1)


@pytest.fixture
async def db(
    rollback_sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with rollback_sessionmaker() as session:
        yield session


async def test_repositories_match_protocols(db: AsyncSession) -> None:
    catalog: ports.CatalogRepository = CatalogRepository(db)
    capacity: ports.CapacityRepository = CapacityRepository(db)
    customers: ports.CustomerRepository = CustomerRepository(db)
    orders: ports.OrderRepository = OrderRepository(db)
    coupons: ports.CouponRepository = CouponRepository(db)
    side_effects: ports.SideEffectRepository = SideEffectRepository(db)
    assert all((catalog, capacity, customers, orders, coupons, side_effects))


# --- catalog -------------------------------------------------------------------------


async def test_products_with_allergens(db: AsyncSession) -> None:
    products = await CatalogRepository(db).list_products()
    assert len(products) == 12
    chocolate = next(p for p in products if p.slug == "bolo-chocolate")
    links = {(link.allergen.code, link.kind.value) for link in chocolate.allergen_links}
    assert {("gluten", "contains"), ("soy", "may_contain")} <= links


async def test_product_by_slug(db: AsyncSession) -> None:
    repo = CatalogRepository(db)
    product = await repo.get_product("bolo-chocolate")
    assert product is not None and product.price_per_kg == Decimal("89.90")
    assert await repo.get_product("bolo-de-pistache") is None


async def test_pans_smallest_first(db: AsyncSession) -> None:
    assert [p.code for p in await CatalogRepository(db).list_pan_sizes()] == ["P", "M", "G"]


async def test_neighborhoods(db: AsyncSession) -> None:
    repo = CatalogRepository(db)
    assert len(await repo.list_neighborhoods()) == 8
    place = await repo.get_neighborhood("boa viagem")
    assert place is not None and place.name == "Boa Viagem"
    assert await repo.get_neighborhood("Olinda") is None


# --- capacity ------------------------------------------------------------------------


async def test_used_kg_on_the_full_day(db: AsyncSession, full_day: dt.date) -> None:
    assert await CapacityRepository(db).used_kg(full_day) == Decimal("15.0")


async def test_used_kg_matches_sql(db: AsyncSession) -> None:
    repo = CapacityRepository(db)
    for offset in range(-5, 15):
        day = RUN_DAY + offset * DAY
        expected = await db.scalar(
            select(func.coalesce(func.sum(Order.weight_kg), 0)).where(
                Order.delivery_date == day, Order.status != "cancelled"
            )
        )
        assert await repo.used_kg(day) == expected
    assert await repo.used_kg(RUN_DAY + 400 * DAY) == Decimal(0)


async def test_christmas_override(db: AsyncSession) -> None:
    override = await CapacityRepository(db).get_override(dt.date(RUN_DAY.year, 12, 25))
    assert override is not None
    assert override.capacity_kg == Decimal("0.0")


# --- coupons -------------------------------------------------------------------------


async def test_coupon_lookup_is_case_insensitive(db: AsyncSession) -> None:
    coupon = await CouponRepository(db).get("amigo5")
    assert coupon is not None and coupon.code == "AMIGO5"


async def test_used_up_coupon_usage(db: AsyncSession) -> None:
    repo = CouponRepository(db)
    coupon = await repo.get("PRIMEIRA10")
    assert coupon is not None and coupon.max_uses is not None
    assert await repo.count_uses("PRIMEIRA10") == coupon.max_uses


# --- customers, orders, side effects -------------------------------------------------


async def test_order_loads_with_relations(db: AsyncSession) -> None:
    order_id = await db.scalar(select(func.min(Order.id)))
    assert order_id is not None
    order = await OrderRepository(db).get(order_id)
    assert order is not None
    assert order.customer.id == order.customer_id
    assert order.product.id == order.product_id
    assert order.pan_size.code == order.pan_size_code
    assert await OrderRepository(db).get(10**9) is None


async def test_add_customer_and_message(db: AsyncSession) -> None:
    customer = await CustomerRepository(db).add(Customer(name="Teste", phone="+5581900000001"))
    assert customer.id is not None
    assert await CustomerRepository(db).get_by_phone("+5581900000001") is customer
    message = await SideEffectRepository(db).add_message(
        SentMessage(to_phone="+5581900000001", body="oi")
    )
    assert message.id is not None
