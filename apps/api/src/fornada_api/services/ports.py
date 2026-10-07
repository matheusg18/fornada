"""What the services need from data access. `repositories/` implements these
against Postgres, and unit tests implement them in memory.

Repositories return models with the relations noted below already loaded.
`add` and `save` flush, so generated ids are set; they never commit.
"""

import datetime as dt
from collections.abc import Sequence
from decimal import Decimal
from typing import Protocol

from fornada_api.models import (
    CapacityOverride,
    Coupon,
    Customer,
    Escalation,
    Neighborhood,
    Order,
    PanSize,
    Product,
    SentMessage,
)


class CatalogRepository(Protocol):
    async def list_products(self) -> Sequence[Product]:
        """Active products by id, with `allergen_links` and each link's `allergen`."""
        ...

    async def get_product(self, slug: str) -> Product | None:
        """By exact slug, active or not, without relations."""
        ...

    async def list_pan_sizes(self) -> Sequence[PanSize]:
        """Every pan size, smallest first."""
        ...

    async def list_neighborhoods(self) -> Sequence[Neighborhood]:
        """Active neighborhoods by name."""
        ...

    async def get_neighborhood(self, name: str) -> Neighborhood | None:
        """By name, case-insensitively, active or not."""
        ...


class CapacityRepository(Protocol):
    async def get_override(self, day: dt.date) -> CapacityOverride | None: ...

    async def used_kg(self, day: dt.date) -> Decimal:
        """Total weight of the day's orders that are not cancelled."""
        ...


class CustomerRepository(Protocol):
    async def get_by_phone(self, phone: str) -> Customer | None: ...

    async def add(self, customer: Customer) -> Customer: ...


class OrderRepository(Protocol):
    async def get(self, order_id: int) -> Order | None:
        """With `customer`, `product`, `pan_size` and `neighborhood` loaded."""
        ...

    async def add(self, order: Order) -> Order: ...

    async def save(self, order: Order) -> None:
        """Flush changes made to an order returned by `get` or `add`."""
        ...


class CouponRepository(Protocol):
    async def get(self, code: str) -> Coupon | None:
        """By code, case-insensitively."""
        ...

    async def count_uses(self, code: str) -> int:
        """Orders that reference the coupon and are not cancelled."""
        ...


class SideEffectRepository(Protocol):
    async def add_message(self, message: SentMessage) -> SentMessage: ...

    async def add_escalation(self, escalation: Escalation) -> Escalation: ...
