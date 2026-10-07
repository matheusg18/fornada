import datetime as dt
from decimal import Decimal

import pytest

from fornada_api.models import OrderStatus
from fornada_api.services.capacity import CapacityService
from tests.unit.services.fakes import (
    CLOCK,
    TODAY,
    FakeCapacityRepository,
    FakeDb,
    add_order,
    seeded_db,
)

pytestmark = pytest.mark.anyio

DAY = dt.timedelta(days=1)


@pytest.fixture
def db() -> FakeDb:
    return seeded_db()


def service(db: FakeDb) -> CapacityService:
    return CapacityService(FakeCapacityRepository(db), CLOCK, Decimal("15"))


async def test_full_day(db: FakeDb) -> None:
    for _ in range(5):
        add_order(db, delivery_date=TODAY + 3 * DAY, weight_kg="3.0")
    report = await service(db).check(TODAY + 3 * DAY)
    assert (report.capacity_kg, report.used_kg, report.free_kg) == (
        Decimal("15.0"),
        Decimal("15.0"),
        Decimal("0.0"),
    )
    assert report.override_reason is None
    assert report.meets_regular_lead_time


async def test_holiday(db: FakeDb) -> None:
    report = await service(db).check(dt.date(2026, 12, 25))
    assert report.capacity_kg == Decimal("0.0")
    assert report.free_kg == Decimal("0.0")
    assert report.override_reason == "Natal"


async def test_free_never_below_zero(db: FakeDb) -> None:
    add_order(db, delivery_date=dt.date(2026, 12, 25), weight_kg="2.0")
    report = await service(db).check(dt.date(2026, 12, 25))
    assert report.used_kg == Decimal("2.0")
    assert report.free_kg == Decimal("0.0")


async def test_cancelled_orders_free_capacity(db: FakeDb) -> None:
    day = TODAY + 6 * DAY
    order = add_order(db, delivery_date=day, weight_kg="2.0")
    before = await service(db).check(day)
    order.status = OrderStatus.CANCELLED
    after = await service(db).check(day)
    assert after.free_kg - before.free_kg == Decimal("2.0")


async def test_lead_times(db: FakeDb) -> None:
    report = await service(db).check(TODAY + DAY)
    assert report.earliest_regular_date == dt.date(2026, 10, 9)
    assert report.earliest_custom_date == dt.date(2026, 10, 12)
    assert not report.meets_regular_lead_time
    assert not report.meets_custom_lead_time


@pytest.mark.parametrize(
    ("offset", "regular", "custom"), [(2, True, False), (4, True, False), (5, True, True)]
)
async def test_lead_time_boundaries(db: FakeDb, offset: int, regular: bool, custom: bool) -> None:
    report = await service(db).check(TODAY + offset * DAY)
    assert (report.meets_regular_lead_time, report.meets_custom_lead_time) == (regular, custom)


async def test_default_capacity_comes_from_settings(db: FakeDb) -> None:
    custom = CapacityService(FakeCapacityRepository(db), CLOCK, Decimal("20.5"))
    report = await custom.check(TODAY + 10 * DAY)
    assert report.capacity_kg == Decimal("20.5")
