"""Values the schema limits with `CHECK` constraints on `text` columns."""

from enum import StrEnum


class OrderStatus(StrEnum):
    PENDING_PAYMENT = "pending_payment"
    CONFIRMED = "confirmed"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class Fulfillment(StrEnum):
    PICKUP = "pickup"
    DELIVERY = "delivery"


class AllergenKind(StrEnum):
    CONTAINS = "contains"
    MAY_CONTAIN = "may_contain"
