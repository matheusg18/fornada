"""Rows that record side effects. Nothing is actually sent."""

import datetime as dt

from sqlalchemy import ForeignKey, Identity, func
from sqlalchemy.orm import Mapped, mapped_column

from fornada_api.models.base import Base


class SentMessage(Base):
    """No FK to customers: a message to any number is representable."""

    __tablename__ = "sent_messages"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    to_phone: Mapped[str]
    body: Mapped[str]
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())


class Escalation(Base):
    __tablename__ = "escalations"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    thread_id: Mapped[str]
    phone: Mapped[str | None]
    reason: Mapped[str]
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())
