"""Declarative base. Models mirror `.devcontainer/db/schema.sql`, which stays
the only source of DDL: nothing here creates or alters tables."""

import datetime as dt
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Numeric, Text
from sqlalchemy.orm import DeclarativeBase

from fornada_api.models.enums import AllergenKind, Fulfillment, OrderStatus


def _text_enum(enum_cls: type[StrEnum]) -> Enum:
    # Plain `text` in Postgres, checked by the schema's CHECK constraint;
    # stored by value (`pending_payment`), not by member name.
    return Enum(
        enum_cls,
        native_enum=False,
        create_constraint=False,
        values_callable=lambda members: [m.value for m in members],
    )


class Base(DeclarativeBase):
    type_annotation_map = {
        str: Text(),
        Decimal: Numeric(asdecimal=True),
        dt.datetime: DateTime(timezone=True),
        OrderStatus: _text_enum(OrderStatus),
        Fulfillment: _text_enum(Fulfillment),
        AllergenKind: _text_enum(AllergenKind),
    }
