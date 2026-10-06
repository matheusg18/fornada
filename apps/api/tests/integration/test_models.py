import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import selectinload

from fornada_api.models import (
    AllergenKind,
    Base,
    Order,
    OrderStatus,
    Product,
    ProductAllergen,
)

pytestmark = pytest.mark.anyio

MAPPERS = sorted(Base.registry.mappers, key=lambda m: m.class_.__tablename__)


def test_every_app_table_has_a_model() -> None:
    assert len(Base.metadata.tables) == 11


async def test_model_columns_match_live_tables(engine: AsyncEngine) -> None:
    def live_columns(conn, table: str) -> dict[str, bool]:
        return {c["name"]: c["nullable"] for c in inspect(conn).get_columns(table)}

    async with engine.connect() as conn:
        for name, table in Base.metadata.tables.items():
            live = await conn.run_sync(live_columns, name)
            mapped = {c.name: c.nullable for c in table.columns}
            assert mapped == live, name


@pytest.mark.parametrize("mapper", MAPPERS, ids=lambda m: m.class_.__tablename__)
async def test_every_seeded_row_loads(session: AsyncSession, mapper) -> None:
    model = mapper.class_
    count = await session.scalar(select(func.count()).select_from(model))
    rows = (await session.scalars(select(model))).all()
    assert len(rows) == count


async def test_price_is_exact_decimal(session: AsyncSession) -> None:
    product = await session.scalar(select(Product).where(Product.slug == "bolo-chocolate"))
    assert product is not None
    assert isinstance(product.price_per_kg, Decimal)
    assert product.price_per_kg == Decimal("89.90")


async def test_order_dates_keep_their_kind(session: AsyncSession) -> None:
    order = await session.scalar(select(Order).limit(1))
    assert order is not None
    assert type(order.delivery_date) is dt.date
    assert order.created_at.tzinfo is not None


async def test_cancelled_status_is_typed(session: AsyncSession) -> None:
    order = await session.scalar(
        select(Order).where(Order.status == OrderStatus.CANCELLED).limit(1)
    )
    assert order is not None
    assert order.status is OrderStatus.CANCELLED


async def test_product_allergen_links(session: AsyncSession) -> None:
    product = await session.scalar(
        select(Product)
        .where(Product.slug == "bolo-chocolate")
        .options(selectinload(Product.allergen_links).selectinload(ProductAllergen.allergen))
    )
    assert product is not None
    links = {link.allergen.code: link.kind for link in product.allergen_links}
    assert links["gluten"] is AllergenKind.CONTAINS
    assert links["soy"] is AllergenKind.MAY_CONTAIN


async def test_order_customer(session: AsyncSession) -> None:
    order = await session.scalar(select(Order).options(selectinload(Order.customer)).limit(1))
    assert order is not None
    assert order.customer.id == order.customer_id


async def test_lazy_load_raises(session: AsyncSession) -> None:
    order = await session.scalar(select(Order).limit(1))
    assert order is not None
    with pytest.raises(InvalidRequestError, match="lazy='raise'"):
        order.customer  # noqa: B018
