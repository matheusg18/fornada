import datetime as dt
from decimal import Decimal

import pytest

from fornada_api.models import Fulfillment, OrderStatus
from fornada_api.services.coupons import CouponService
from fornada_api.services.errors import (
    AddressRequired,
    CouponNotApplicable,
    CouponNotFound,
    InvalidPhone,
    OrderNotCancellable,
    OrderNotFound,
)
from fornada_api.services.orders import OrderService
from fornada_api.services.quotes import QuoteService
from tests.unit.services.fakes import (
    CLOCK,
    CUSTOMER_PHONE,
    OTHER_PHONE,
    TODAY,
    FakeCatalogRepository,
    FakeCouponRepository,
    FakeCustomerRepository,
    FakeDb,
    FakeOrderRepository,
    add_order,
    seeded_db,
)

pytestmark = pytest.mark.anyio

DAY = dt.timedelta(days=1)


@pytest.fixture
def db() -> FakeDb:
    return seeded_db()


@pytest.fixture
def service(db: FakeDb) -> OrderService:
    return OrderService(
        FakeCustomerRepository(db),
        FakeOrderRepository(db),
        QuoteService(FakeCatalogRepository(db)),
        CouponService(FakeCouponRepository(db), CLOCK),
        CLOCK,
    )


async def create(
    service: OrderService,
    *,
    phone: str = "(81) 97777-6666",
    customer_name: str = "Ana Paula",
    delivery_date: dt.date = TODAY + 10 * DAY,
    fulfillment: Fulfillment = Fulfillment.DELIVERY,
    address: str = "Rua das Flores, 10",
) -> int:
    created = await service.create_order(
        customer_name=customer_name,
        phone=phone,
        product_slug="bolo-chocolate",
        weight_kg=Decimal("2.5"),
        delivery_date=delivery_date,
        fulfillment=fulfillment,
        neighborhood="Ipsep",
        address=address,
    )
    return created.order_id


# --- create ----------------------------------------------------------------------


async def test_new_customer_and_pending_order(service: OrderService, db: FakeDb) -> None:
    created = await service.create_order(
        customer_name="Ana Paula",
        phone="(81) 97777-6666",
        product_slug="bolo-chocolate",
        weight_kg=Decimal("2.5"),
        delivery_date=TODAY + 10 * DAY,
        fulfillment=Fulfillment.DELIVERY,
        neighborhood="Ipsep",
        address="Rua das Flores, 10",
        reference_photo_description="Bolo com unicórnio rosa",
    )
    customer = db.customers[-1]
    assert (customer.name, customer.phone) == ("Ana Paula", "+5581977776666")
    order = db.orders[-1]
    assert order.id == created.order_id
    assert order.customer_id == customer.id
    assert order.status == OrderStatus.PENDING_PAYMENT
    assert order.reference_photo_description == "Bolo com unicórnio rosa"
    assert created.payment_link.startswith(f"https://pagamento.fornada.example/{order.id}/")
    assert order.payment_link == created.payment_link


async def test_amounts_come_from_the_quote(service: OrderService, db: FakeDb) -> None:
    order_id = await create(service)
    quote = await service.quotes.quote(
        "bolo-chocolate", Decimal("2.5"), Fulfillment.DELIVERY, "Ipsep"
    )
    order = next(o for o in db.orders if o.id == order_id)
    assert (order.subtotal, order.delivery_fee, order.discount, order.total, order.deposit) == (
        quote.subtotal,
        quote.delivery_fee,
        quote.discount,
        quote.total,
        quote.deposit,
    )
    assert (order.pan_size_code, order.neighborhood_id) == ("M", 2)


async def test_existing_customer_is_reused(service: OrderService, db: FakeDb) -> None:
    await create(service, customer_name="Outro Nome", phone="81 98765 4321")
    assert len(db.customers) == 2
    assert db.orders[-1].customer_id == 1
    assert db.customers[0].name == "Maria Souza"


async def test_identical_calls_create_two_orders(service: OrderService, db: FakeDb) -> None:
    before = len(db.orders)
    first, second = await create(service), await create(service)
    assert first != second
    assert len(db.orders) == before + 2


async def test_v0_ignores_capacity_and_dates(service: OrderService) -> None:
    # Past date and a closed holiday: v0 accepts both on purpose.
    await create(service, delivery_date=TODAY - DAY)
    await create(service, delivery_date=dt.date(2026, 12, 25))


async def test_pickup_drops_neighborhood_and_address(service: OrderService, db: FakeDb) -> None:
    await create(service, fulfillment=Fulfillment.PICKUP)
    order = db.orders[-1]
    assert (order.neighborhood_id, order.address, order.delivery_fee) == (None, None, Decimal(0))


async def test_delivery_needs_address(service: OrderService) -> None:
    with pytest.raises(AddressRequired):
        await create(service, address="  ")


async def test_invalid_phone(service: OrderService) -> None:
    with pytest.raises(InvalidPhone):
        await create(service, phone="123")


# --- get -------------------------------------------------------------------------


async def test_get_with_matching_phone(service: OrderService, db: FakeDb) -> None:
    order = add_order(db, delivery_date=TODAY + 5 * DAY)
    details = await service.get_order(order.id, "(81) 98765-4321")
    assert details.customer_name == "Maria Souza"
    assert details.product_name == "Bolo de chocolate"
    assert details.total == Decimal("179.80")


@pytest.mark.parametrize("phone", [OTHER_PHONE, "81900000000"])
async def test_get_with_other_phone_is_not_found(
    service: OrderService, db: FakeDb, phone: str
) -> None:
    order = add_order(db, delivery_date=TODAY + 5 * DAY)
    with pytest.raises(OrderNotFound) as other:
        await service.get_order(order.id, phone)
    with pytest.raises(OrderNotFound) as missing:
        await service.get_order(9999, CUSTOMER_PHONE)
    # Same wording either way, so the error does not reveal that the order exists.
    assert str(other.value).replace(str(order.id), "N") == str(missing.value).replace("9999", "N")


# --- cancel ----------------------------------------------------------------------


async def test_cancel_confirmed_with_notice(service: OrderService, db: FakeDb) -> None:
    order = add_order(db, delivery_date=TODAY + 5 * DAY, deposit="117.38")
    result = await service.cancel_order(order.id, CUSTOMER_PHONE, "mudou de ideia")
    assert (result.status, result.refund_amount) == (OrderStatus.CANCELLED, Decimal("117.38"))
    assert order.status == OrderStatus.CANCELLED
    assert order.cancelled_at is not None
    assert (order.refund_amount, order.cancel_reason) == (Decimal("117.38"), "mudou de ideia")


@pytest.mark.parametrize(("offset", "refund"), [(2, "89.90"), (1, "0.00"), (0, "0.00")])
async def test_refund_notice_boundary(
    service: OrderService, db: FakeDb, offset: int, refund: str
) -> None:
    order = add_order(db, delivery_date=TODAY + offset * DAY)
    result = await service.cancel_order(order.id, CUSTOMER_PHONE, "imprevisto")
    assert result.refund_amount == Decimal(refund)


async def test_cancel_pending_refunds_nothing(service: OrderService, db: FakeDb) -> None:
    order = add_order(db, delivery_date=TODAY + 9 * DAY, status=OrderStatus.PENDING_PAYMENT)
    result = await service.cancel_order(order.id, CUSTOMER_PHONE, "desistiu")
    assert (result.status, result.refund_amount) == (OrderStatus.CANCELLED, Decimal("0.00"))


@pytest.mark.parametrize("status", [OrderStatus.DELIVERED, OrderStatus.CANCELLED])
async def test_cannot_cancel_closed_order(
    service: OrderService, db: FakeDb, status: OrderStatus
) -> None:
    order = add_order(db, delivery_date=TODAY - 3 * DAY, status=status)
    with pytest.raises(OrderNotCancellable):
        await service.cancel_order(order.id, CUSTOMER_PHONE, "quero cancelar")
    assert order.status == status
    assert order.refund_amount is None


async def test_cancel_with_other_phone(service: OrderService, db: FakeDb) -> None:
    order = add_order(db, delivery_date=TODAY + 5 * DAY)
    with pytest.raises(OrderNotFound):
        await service.cancel_order(order.id, OTHER_PHONE, "golpe")
    assert order.status == OrderStatus.CONFIRMED


# --- apply coupon ------------------------------------------------------------------


async def test_five_percent_off(service: OrderService, db: FakeDb) -> None:
    order_id = await create(service)
    result = await service.apply_coupon(order_id, "amigo5")
    assert (result.coupon_code, result.percent_off) == ("AMIGO5", 5)
    assert (result.discount, result.total, result.deposit) == (
        Decimal("11.24"),
        Decimal("223.51"),
        Decimal("111.76"),
    )
    order = next(o for o in db.orders if o.id == order_id)
    assert (order.coupon_code, order.discount, order.total, order.deposit) == (
        "AMIGO5",
        Decimal("11.24"),
        Decimal("223.51"),
        Decimal("111.76"),
    )
    assert order.delivery_fee == Decimal("10.00")


async def test_second_coupon_refused(service: OrderService, db: FakeDb) -> None:
    order_id = await create(service)
    await service.apply_coupon(order_id, "AMIGO5")
    with pytest.raises(CouponNotApplicable):
        await service.apply_coupon(order_id, "AMIGO5")
    order = next(o for o in db.orders if o.id == order_id)
    assert order.discount == Decimal("11.24")


async def test_coupon_on_confirmed_order(service: OrderService, db: FakeDb) -> None:
    order = add_order(db, delivery_date=TODAY + 5 * DAY)
    with pytest.raises(CouponNotApplicable):
        await service.apply_coupon(order.id, "AMIGO5")
    assert (order.coupon_code, order.total) == (None, Decimal("179.80"))


async def test_invalid_coupon_leaves_order_unchanged(service: OrderService, db: FakeDb) -> None:
    order_id = await create(service)
    with pytest.raises(CouponNotFound):
        await service.apply_coupon(order_id, "DESCONTO30")
    order = next(o for o in db.orders if o.id == order_id)
    assert (order.coupon_code, order.discount) == (None, Decimal("0.00"))


async def test_coupon_unknown_order(service: OrderService) -> None:
    with pytest.raises(OrderNotFound):
        await service.apply_coupon(9999, "AMIGO5")
