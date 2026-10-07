"""Domain errors. Each one is a business rule or lookup that failed.

The message is written for the LLM that called the tool, in English, and
never carries connection details or stack traces.
"""


class DomainError(Exception):
    """Base class. `str(error)` is the message the tool returns."""


class InvalidPhone(DomainError):
    pass


class InvalidWeight(DomainError):
    pass


class ProductNotFound(DomainError):
    pass


class NeighborhoodRequired(DomainError):
    pass


class NeighborhoodNotServed(DomainError):
    pass


class AddressRequired(DomainError):
    pass


class OrderNotFound(DomainError):
    pass


class OrderNotCancellable(DomainError):
    pass


class CouponNotFound(DomainError):
    pass


class CouponInactive(DomainError):
    pass


class CouponNotYetValid(DomainError):
    pass


class CouponExpired(DomainError):
    pass


class CouponUsedUp(DomainError):
    pass


class CouponNotAllowed(DomainError):
    """The coupon exists but its percentage is outside the allowed range."""


class CouponNotApplicable(DomainError):
    """The order cannot take a coupon (status, or it already has one)."""
