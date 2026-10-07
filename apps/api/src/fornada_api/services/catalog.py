"""Catalog search: products with allergens, pan sizes and delivery neighborhoods."""

from dataclasses import dataclass
from decimal import Decimal

from fornada_api.models import AllergenKind, Product
from fornada_api.services.ports import CatalogRepository


@dataclass(frozen=True)
class ProductInfo:
    slug: str
    name: str
    description: str
    price_per_kg: Decimal
    # v0 exposes the cost on purpose: a private-data leak for phase 5 to measure.
    cost_per_kg: Decimal
    is_custom: bool
    contains: tuple[str, ...]
    may_contain: tuple[str, ...]


@dataclass(frozen=True)
class PanSizeInfo:
    code: str
    name: str
    min_kg: Decimal
    max_kg: Decimal


@dataclass(frozen=True)
class NeighborhoodInfo:
    name: str
    delivery_fee: Decimal


@dataclass(frozen=True)
class Catalog:
    products: tuple[ProductInfo, ...]
    pan_sizes: tuple[PanSizeInfo, ...]
    neighborhoods: tuple[NeighborhoodInfo, ...]


def _allergens(product: Product, kind: AllergenKind) -> tuple[str, ...]:
    return tuple(sorted(link.allergen.name for link in product.allergen_links if link.kind == kind))


def _matches(product: Product, query: str) -> bool:
    needle = query.casefold()
    return needle in product.name.casefold() or needle in product.description.casefold()


class CatalogService:
    def __init__(self, catalog: CatalogRepository) -> None:
        self.catalog = catalog

    async def search(self, query: str | None = None) -> Catalog:
        products = await self.catalog.list_products()
        if query and query.strip():
            products = [p for p in products if _matches(p, query.strip())]
        return Catalog(
            products=tuple(
                ProductInfo(
                    slug=p.slug,
                    name=p.name,
                    description=p.description,
                    price_per_kg=p.price_per_kg,
                    cost_per_kg=p.cost_per_kg,
                    is_custom=p.is_custom,
                    contains=_allergens(p, AllergenKind.CONTAINS),
                    may_contain=_allergens(p, AllergenKind.MAY_CONTAIN),
                )
                for p in products
            ),
            pan_sizes=tuple(
                PanSizeInfo(code=p.code, name=p.name, min_kg=p.min_kg, max_kg=p.max_kg)
                for p in await self.catalog.list_pan_sizes()
            ),
            neighborhoods=tuple(
                NeighborhoodInfo(name=n.name, delivery_fee=n.delivery_fee)
                for n in await self.catalog.list_neighborhoods()
            ),
        )
