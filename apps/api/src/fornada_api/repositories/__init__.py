"""Data access: queries that turn rows into models. No business rules, no commits.

Each class implements the matching protocol in `fornada_api.services.ports`.
"""

from fornada_api.repositories.capacity import CapacityRepository
from fornada_api.repositories.catalog import CatalogRepository
from fornada_api.repositories.coupons import CouponRepository
from fornada_api.repositories.customers import CustomerRepository
from fornada_api.repositories.orders import OrderRepository
from fornada_api.repositories.side_effects import SideEffectRepository

__all__ = [
    "CapacityRepository",
    "CatalogRepository",
    "CouponRepository",
    "CustomerRepository",
    "OrderRepository",
    "SideEffectRepository",
]
