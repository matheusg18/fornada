import datetime as dt
from decimal import Decimal

from sqlalchemy import Identity, Numeric, true
from sqlalchemy.orm import Mapped, mapped_column

from fornada_api.models.base import Base


class Neighborhood(Base):
    __tablename__ = "neighborhoods"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    delivery_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    active: Mapped[bool] = mapped_column(server_default=true())


class CapacityOverride(Base):
    """Dates without a row use the default daily capacity."""

    __tablename__ = "capacity_overrides"

    date: Mapped[dt.date] = mapped_column(primary_key=True)
    capacity_kg: Mapped[Decimal] = mapped_column(Numeric(5, 1))
    reason: Mapped[str]


class Coupon(Base):
    """No usage counter: usage is the number of orders with this code."""

    __tablename__ = "coupons"

    code: Mapped[str] = mapped_column(primary_key=True)
    percent_off: Mapped[int]
    valid_from: Mapped[dt.date]
    valid_until: Mapped[dt.date]
    max_uses: Mapped[int | None]
    active: Mapped[bool] = mapped_column(server_default=true())
