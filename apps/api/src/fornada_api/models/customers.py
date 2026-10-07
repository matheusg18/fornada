from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import Identity, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fornada_api.models.base import Base

if TYPE_CHECKING:
    from fornada_api.models.orders import Order


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    name: Mapped[str]
    phone: Mapped[str] = mapped_column(unique=True)  # E.164, +55 and 10-11 digits
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())

    orders: Mapped[list[Order]] = relationship(back_populates="customer", lazy="raise")
