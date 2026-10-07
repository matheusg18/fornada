"""In-memory repositories for service unit tests.

`seeded_db()` holds a small copy of the dev seed, with dates relative to
`TODAY` so tests do not depend on the real clock.
"""

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from fornada_api.models import (
    Allergen,
    AllergenKind,
    CapacityOverride,
    Coupon,
    Customer,
    Escalation,
    Fulfillment,
    Neighborhood,
    Order,
    OrderStatus,
    PanSize,
    Product,
    ProductAllergen,
    SentMessage,
)
from fornada_api.services.clock import FixedClock

TODAY = dt.date(2026, 10, 7)
CLOCK = FixedClock(TODAY)
CUSTOMER_PHONE = "+5581987654321"
OTHER_PHONE = "+5581911112222"


@dataclass
class FakeDb:
    products: list[Product] = field(default_factory=list)
    pan_sizes: list[PanSize] = field(default_factory=list)
    neighborhoods: list[Neighborhood] = field(default_factory=list)
    overrides: list[CapacityOverride] = field(default_factory=list)
    coupons: list[Coupon] = field(default_factory=list)
    customers: list[Customer] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    messages: list[SentMessage] = field(default_factory=list)
    escalations: list[Escalation] = field(default_factory=list)
    saves: int = 0


class FakeCatalogRepository:
    def __init__(self, db: FakeDb) -> None:
        self.db = db

    async def list_products(self) -> Sequence[Product]:
        return [p for p in self.db.products if p.active]

    async def get_product(self, slug: str) -> Product | None:
        return next((p for p in self.db.products if p.slug == slug), None)

    async def list_pan_sizes(self) -> Sequence[PanSize]:
        return sorted(self.db.pan_sizes, key=lambda p: p.min_kg)

    async def list_neighborhoods(self) -> Sequence[Neighborhood]:
        return sorted((n for n in self.db.neighborhoods if n.active), key=lambda n: n.name)

    async def get_neighborhood(self, name: str) -> Neighborhood | None:
        wanted = name.casefold()
        return next((n for n in self.db.neighborhoods if n.name.casefold() == wanted), None)


class FakeCapacityRepository:
    def __init__(self, db: FakeDb) -> None:
        self.db = db

    async def get_override(self, day: dt.date) -> CapacityOverride | None:
        return next((o for o in self.db.overrides if o.date == day), None)

    async def used_kg(self, day: dt.date) -> Decimal:
        return sum(
            (
                o.weight_kg
                for o in self.db.orders
                if o.delivery_date == day and o.status != OrderStatus.CANCELLED
            ),
            Decimal("0.0"),
        )


class FakeCustomerRepository:
    def __init__(self, db: FakeDb) -> None:
        self.db = db

    async def get_by_phone(self, phone: str) -> Customer | None:
        return next((c for c in self.db.customers if c.phone == phone), None)

    async def add(self, customer: Customer) -> Customer:
        customer.id = len(self.db.customers) + 1
        self.db.customers.append(customer)
        return customer


class FakeOrderRepository:
    def __init__(self, db: FakeDb) -> None:
        self.db = db

    async def get(self, order_id: int) -> Order | None:
        return next((o for o in self.db.orders if o.id == order_id), None)

    async def add(self, order: Order) -> Order:
        order.id = max((o.id for o in self.db.orders), default=0) + 1
        _link(self.db, order)
        self.db.orders.append(order)
        return order

    async def save(self, order: Order) -> None:
        self.db.saves += 1


class FakeCouponRepository:
    def __init__(self, db: FakeDb) -> None:
        self.db = db

    async def get(self, code: str) -> Coupon | None:
        wanted = code.upper()
        return next((c for c in self.db.coupons if c.code.upper() == wanted), None)

    async def count_uses(self, code: str) -> int:
        return sum(
            1 for o in self.db.orders if o.coupon_code == code and o.status != OrderStatus.CANCELLED
        )


class FakeSideEffectRepository:
    def __init__(self, db: FakeDb) -> None:
        self.db = db

    async def add_message(self, message: SentMessage) -> SentMessage:
        message.id = len(self.db.messages) + 1
        self.db.messages.append(message)
        return message

    async def add_escalation(self, escalation: Escalation) -> Escalation:
        escalation.id = len(self.db.escalations) + 1
        self.db.escalations.append(escalation)
        return escalation


def _link(db: FakeDb, order: Order) -> None:
    """Set the relations a real repository would load."""
    order.customer = next(c for c in db.customers if c.id == order.customer_id)
    order.product = next(p for p in db.products if p.id == order.product_id)
    order.pan_size = next(p for p in db.pan_sizes if p.code == order.pan_size_code)
    order.neighborhood = next((n for n in db.neighborhoods if n.id == order.neighborhood_id), None)


def _product(
    id: int,
    slug: str,
    name: str,
    price: str,
    cost: str,
    allergens: dict[str, AllergenKind],
    *,
    description: str = "",
    is_custom: bool = False,
    active: bool = True,
) -> Product:
    product = Product(
        id=id,
        slug=slug,
        name=name,
        description=description or name,
        price_per_kg=Decimal(price),
        cost_per_kg=Decimal(cost),
        is_custom=is_custom,
        active=active,
    )
    product.allergen_links = [
        ProductAllergen(allergen_code=code, kind=kind, allergen=ALLERGENS[code])
        for code, kind in allergens.items()
    ]
    return product


ALLERGENS = {
    "gluten": Allergen(code="gluten", name="Glúten"),
    "lactose": Allergen(code="lactose", name="Lactose"),
    "egg": Allergen(code="egg", name="Ovo"),
    "soy": Allergen(code="soy", name="Soja"),
}
C, M = AllergenKind.CONTAINS, AllergenKind.MAY_CONTAIN


def seeded_db() -> FakeDb:
    db = FakeDb()
    db.pan_sizes = [
        PanSize(code="G", name="Forma grande", min_kg=Decimal("3.5"), max_kg=Decimal("6.0")),
        PanSize(code="P", name="Forma pequena", min_kg=Decimal("1.0"), max_kg=Decimal("2.0")),
        PanSize(code="M", name="Forma média", min_kg=Decimal("2.0"), max_kg=Decimal("3.5")),
    ]
    db.products = [
        _product(
            1,
            "bolo-chocolate",
            "Bolo de chocolate",
            "89.90",
            "32.00",
            {"gluten": C, "lactose": C, "egg": C, "soy": M},
            description="Massa de chocolate com recheio e cobertura de brigadeiro.",
        ),
        _product(
            9,
            "torta-chocolate-sem-farinha",
            "Torta de chocolate sem farinha",
            "119.90",
            "45.00",
            {"lactose": C, "egg": C, "gluten": M},
            description="Torta densa de chocolate meio amargo, feita sem farinha de trigo.",
        ),
        _product(
            11,
            "personalizado-tema",
            "Bolo personalizado com tema",
            "139.90",
            "55.00",
            {"gluten": C},
            is_custom=True,
        ),
        _product(20, "bolo-antigo", "Bolo fora de linha", "50.00", "20.00", {}, active=False),
    ]
    db.neighborhoods = [
        Neighborhood(id=1, name="Imbiribeira", delivery_fee=Decimal("8.00"), active=True),
        Neighborhood(id=2, name="Ipsep", delivery_fee=Decimal("10.00"), active=True),
        Neighborhood(id=9, name="Casa Forte", delivery_fee=Decimal("25.00"), active=False),
    ]
    db.overrides = [
        CapacityOverride(date=dt.date(2026, 12, 25), capacity_kg=Decimal("0.0"), reason="Natal"),
    ]
    day = dt.timedelta(days=1)
    db.coupons = [
        Coupon(code="AMIGO5", percent_off=5, valid_from=TODAY - 60 * day,
               valid_until=TODAY + 120 * day, max_uses=None, active=True),
        Coupon(code="PASCOA10", percent_off=10, valid_from=TODAY - 120 * day,
               valid_until=TODAY - 60 * day, max_uses=None, active=True),
        Coupon(code="PRIMEIRA10", percent_off=10, valid_from=TODAY - 120 * day,
               valid_until=TODAY + 180 * day, max_uses=5, active=True),
        Coupon(code="VERAO8", percent_off=8, valid_from=TODAY + 30 * day,
               valid_until=TODAY + 90 * day, max_uses=None, active=True),
        Coupon(code="ANTIGO5", percent_off=5, valid_from=TODAY - 200 * day,
               valid_until=TODAY + 200 * day, max_uses=None, active=False),
        Coupon(code="GERAL30", percent_off=30, valid_from=TODAY - 10 * day,
               valid_until=TODAY + 10 * day, max_uses=None, active=True),
    ]  # fmt: skip
    db.customers = [
        Customer(id=1, name="Maria Souza", phone=CUSTOMER_PHONE),
        Customer(id=2, name="João Lima", phone=OTHER_PHONE),
    ]
    # PRIMEIRA10 reaches its usage limit with past delivered orders.
    for _ in range(5):
        add_order(db, delivery_date=TODAY - 30 * day, status=OrderStatus.DELIVERED,
                  coupon_code="PRIMEIRA10")  # fmt: skip
    return db


def add_order(
    db: FakeDb,
    *,
    delivery_date: dt.date,
    status: OrderStatus = OrderStatus.CONFIRMED,
    weight_kg: str = "2.0",
    customer_id: int = 1,
    coupon_code: str | None = None,
    subtotal: str = "179.80",
    delivery_fee: str = "0.00",
    discount: str = "0.00",
    total: str = "179.80",
    deposit: str = "89.90",
) -> Order:
    """Store an order directly, as the seed would, with its relations set."""
    order = Order(
        id=max((o.id for o in db.orders), default=0) + 1,
        customer_id=customer_id,
        product_id=1,
        pan_size_code="P",
        neighborhood_id=None,
        coupon_code=coupon_code,
        delivery_date=delivery_date,
        fulfillment=Fulfillment.PICKUP,
        address=None,
        reference_photo_description=None,
        notes=None,
        status=status,
        weight_kg=Decimal(weight_kg),
        price_per_kg=Decimal("89.90"),
        subtotal=Decimal(subtotal),
        delivery_fee=Decimal(delivery_fee),
        discount=Decimal(discount),
        total=Decimal(total),
        deposit=Decimal(deposit),
        payment_link=None,
        cancelled_at=None,
        refund_amount=None,
        cancel_reason=None,
    )
    _link(db, order)
    db.orders.append(order)
    return order
