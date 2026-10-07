"""The fakes must satisfy the same protocols the real repositories do."""

import pytest

from fornada_api.services import ports
from tests.unit.services.fakes import (
    TODAY,
    FakeCapacityRepository,
    FakeCatalogRepository,
    FakeCouponRepository,
    FakeCustomerRepository,
    FakeOrderRepository,
    FakeSideEffectRepository,
    seeded_db,
)

pytestmark = pytest.mark.anyio


async def test_fakes_match_protocols() -> None:
    db = seeded_db()
    catalog: ports.CatalogRepository = FakeCatalogRepository(db)
    capacity: ports.CapacityRepository = FakeCapacityRepository(db)
    customers: ports.CustomerRepository = FakeCustomerRepository(db)
    orders: ports.OrderRepository = FakeOrderRepository(db)
    coupons: ports.CouponRepository = FakeCouponRepository(db)
    side_effects: ports.SideEffectRepository = FakeSideEffectRepository(db)

    assert [p.code for p in await catalog.list_pan_sizes()] == ["P", "M", "G"]
    assert len(await catalog.list_products()) == 3
    assert await capacity.get_override(TODAY) is None
    assert await customers.get_by_phone("+5581987654321") is not None
    assert (await orders.get(1)) is not None
    assert await coupons.count_uses("PRIMEIRA10") == 5
    assert side_effects is not None
