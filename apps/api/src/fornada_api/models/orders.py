from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Identity, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fornada_api.models.base import Base
from fornada_api.models.enums import Fulfillment, OrderStatus

if TYPE_CHECKING:
    from fornada_api.models.catalog import PanSize, Product
    from fornada_api.models.customers import Customer
    from fornada_api.models.operations import Coupon, Neighborhood

Money = Numeric(10, 2)


class Order(Base):
    """One cake. Amounts are snapshots taken at creation time."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    pan_size_code: Mapped[str] = mapped_column(ForeignKey("pan_sizes.code"))
    neighborhood_id: Mapped[int | None] = mapped_column(ForeignKey("neighborhoods.id"))
    coupon_code: Mapped[str | None] = mapped_column(ForeignKey("coupons.code"))
    delivery_date: Mapped[dt.date]
    fulfillment: Mapped[Fulfillment]
    address: Mapped[str | None]
    reference_photo_description: Mapped[str | None]  # untrusted customer text
    notes: Mapped[str | None]
    status: Mapped[OrderStatus]
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    price_per_kg: Mapped[Decimal] = mapped_column(Money)
    subtotal: Mapped[Decimal] = mapped_column(Money)
    delivery_fee: Mapped[Decimal] = mapped_column(Money)
    discount: Mapped[Decimal] = mapped_column(Money)
    total: Mapped[Decimal] = mapped_column(Money)
    deposit: Mapped[Decimal] = mapped_column(Money)
    payment_link: Mapped[str | None]
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())
    cancelled_at: Mapped[dt.datetime | None]
    refund_amount: Mapped[Decimal | None] = mapped_column(Money)
    cancel_reason: Mapped[str | None]

    customer: Mapped[Customer] = relationship(back_populates="orders", lazy="raise")
    product: Mapped[Product] = relationship(lazy="raise")
    pan_size: Mapped[PanSize] = relationship(lazy="raise")
    neighborhood: Mapped[Neighborhood | None] = relationship(lazy="raise")
    coupon: Mapped[Coupon | None] = relationship(lazy="raise")
