"""Order rules: create, look up, cancel under the refund policy, apply a coupon.

v0 is naive on purpose (see the `agent-tools` spec): creation checks neither
capacity, lead time, past dates nor confirmation, and repeated calls create
repeated orders. Look-ups trust the phone they are given.
"""

import datetime as dt
import secrets
from dataclasses import dataclass
from decimal import Decimal

from fornada_api.models import Customer, Fulfillment, Order, OrderStatus
from fornada_api.services.clock import Clock
from fornada_api.services.coupons import CouponService
from fornada_api.services.errors import (
    AddressRequired,
    CouponNotApplicable,
    OrderNotCancellable,
    OrderNotFound,
)
from fornada_api.services.money import ZERO, round_money
from fornada_api.services.phones import normalize_phone
from fornada_api.services.ports import CustomerRepository, OrderRepository
from fornada_api.services.quotes import Quote, QuoteService, deposit_for, total_for

# `.example` is a reserved TLD: the link can never resolve.
PAYMENT_LINK_BASE = "https://pagamento.fornada.example"
# A confirmed order cancelled at least this many days before delivery gets
# its deposit back; later than that, nothing.
REFUND_NOTICE_DAYS = 2
CANCELLABLE = (OrderStatus.PENDING_PAYMENT, OrderStatus.CONFIRMED)


@dataclass(frozen=True)
class CreatedOrder:
    order_id: int
    status: OrderStatus
    customer_name: str
    phone: str
    delivery_date: dt.date
    quote: Quote
    payment_link: str


@dataclass(frozen=True)
class OrderDetails:
    order_id: int
    status: OrderStatus
    customer_name: str
    product_slug: str
    product_name: str
    weight_kg: Decimal
    pan_size: str
    delivery_date: dt.date
    fulfillment: Fulfillment
    neighborhood: str | None
    address: str | None
    reference_photo_description: str | None
    notes: str | None
    price_per_kg: Decimal
    subtotal: Decimal
    delivery_fee: Decimal
    discount: Decimal
    total: Decimal
    deposit: Decimal
    coupon_code: str | None
    payment_link: str | None
    refund_amount: Decimal | None


@dataclass(frozen=True)
class Cancellation:
    order_id: int
    status: OrderStatus
    refund_amount: Decimal
    reason: str


@dataclass(frozen=True)
class CouponApplied:
    order_id: int
    coupon_code: str
    percent_off: int
    discount: Decimal
    total: Decimal
    deposit: Decimal


def refund_for(order: Order, today: dt.date) -> Decimal:
    notice_days = (order.delivery_date - today).days
    if order.status == OrderStatus.CONFIRMED and notice_days >= REFUND_NOTICE_DAYS:
        return order.deposit
    return ZERO


def _details(order: Order) -> OrderDetails:
    return OrderDetails(
        order_id=order.id,
        status=order.status,
        customer_name=order.customer.name,
        product_slug=order.product.slug,
        product_name=order.product.name,
        weight_kg=order.weight_kg,
        pan_size=order.pan_size_code,
        delivery_date=order.delivery_date,
        fulfillment=order.fulfillment,
        neighborhood=order.neighborhood.name if order.neighborhood else None,
        address=order.address,
        reference_photo_description=order.reference_photo_description,
        notes=order.notes,
        price_per_kg=order.price_per_kg,
        subtotal=order.subtotal,
        delivery_fee=order.delivery_fee,
        discount=order.discount,
        total=order.total,
        deposit=order.deposit,
        coupon_code=order.coupon_code,
        payment_link=order.payment_link,
        refund_amount=order.refund_amount,
    )


class OrderService:
    def __init__(
        self,
        customers: CustomerRepository,
        orders: OrderRepository,
        quotes: QuoteService,
        coupons: CouponService,
        clock: Clock,
    ) -> None:
        self.customers = customers
        self.orders = orders
        self.quotes = quotes
        self.coupons = coupons
        self.clock = clock

    async def create_order(
        self,
        *,
        customer_name: str,
        phone: str,
        product_slug: str,
        weight_kg: Decimal,
        delivery_date: dt.date,
        fulfillment: Fulfillment,
        neighborhood: str | None = None,
        address: str | None = None,
        reference_photo_description: str | None = None,
        notes: str | None = None,
    ) -> CreatedOrder:
        customer = await self._customer(customer_name, normalize_phone(phone))
        priced = await self.quotes.price(product_slug, weight_kg, fulfillment, neighborhood)
        delivery = fulfillment == Fulfillment.DELIVERY
        if delivery and not (address and address.strip()):
            raise AddressRequired("delivery needs the customer's street address")

        quote = priced.quote
        order = await self.orders.add(
            Order(
                customer_id=customer.id,
                product_id=priced.product.id,
                pan_size_code=priced.pan_size.code,
                neighborhood_id=priced.neighborhood.id if priced.neighborhood else None,
                coupon_code=None,
                delivery_date=delivery_date,
                fulfillment=fulfillment,
                address=address if delivery else None,
                reference_photo_description=reference_photo_description,
                notes=notes,
                status=OrderStatus.PENDING_PAYMENT,
                weight_kg=quote.weight_kg,
                price_per_kg=quote.price_per_kg,
                subtotal=quote.subtotal,
                delivery_fee=quote.delivery_fee,
                discount=quote.discount,
                total=quote.total,
                deposit=quote.deposit,
            )
        )
        payment_link = f"{PAYMENT_LINK_BASE}/{order.id}/{secrets.token_urlsafe(8)}"
        order.payment_link = payment_link
        await self.orders.save(order)
        return CreatedOrder(
            order_id=order.id,
            status=order.status,
            customer_name=customer.name,
            phone=customer.phone,
            delivery_date=delivery_date,
            quote=quote,
            payment_link=payment_link,
        )

    async def get_order(self, order_id: int, phone: str) -> OrderDetails:
        return _details(await self._owned_order(order_id, phone))

    async def cancel_order(self, order_id: int, phone: str, reason: str) -> Cancellation:
        order = await self._owned_order(order_id, phone)
        if order.status not in CANCELLABLE:
            raise OrderNotCancellable(f"order {order.id} is {order.status} and cannot be cancelled")
        refund = refund_for(order, self.clock.today())
        order.status = OrderStatus.CANCELLED
        order.cancelled_at = self.clock.now()
        order.refund_amount = refund
        order.cancel_reason = reason
        await self.orders.save(order)
        return Cancellation(
            order_id=order.id, status=order.status, refund_amount=refund, reason=reason
        )

    async def apply_coupon(self, order_id: int, code: str) -> CouponApplied:
        # v0: no ownership check, any order id the LLM passes is accepted.
        order = await self.orders.get(order_id)
        if order is None:
            raise OrderNotFound(f"order {order_id} not found")
        if order.status != OrderStatus.PENDING_PAYMENT:
            raise CouponNotApplicable(
                f"order {order.id} is {order.status}; coupons apply only to orders awaiting payment"
            )
        if order.coupon_code is not None:
            raise CouponNotApplicable(
                f"order {order.id} already has coupon {order.coupon_code}; only one per order"
            )
        coupon = await self.coupons.validate(code)
        order.coupon_code = coupon.code
        order.discount = round_money(order.subtotal * coupon.percent_off / 100)
        order.total = total_for(order.subtotal, order.delivery_fee, order.discount)
        order.deposit = deposit_for(order.total)
        await self.orders.save(order)
        return CouponApplied(
            order_id=order.id,
            coupon_code=coupon.code,
            percent_off=coupon.percent_off,
            discount=order.discount,
            total=order.total,
            deposit=order.deposit,
        )

    async def _customer(self, name: str, phone: str) -> Customer:
        customer = await self.customers.get_by_phone(phone)
        if customer is None:
            customer = await self.customers.add(Customer(name=name.strip(), phone=phone))
        return customer

    async def _owned_order(self, order_id: int, phone: str) -> Order:
        """The order if its customer has this phone. Missing and mismatched look the same."""
        order = await self.orders.get(order_id)
        if order is None or order.customer.phone != normalize_phone(phone):
            raise OrderNotFound(f"order {order_id} not found for this phone number")
        return order
