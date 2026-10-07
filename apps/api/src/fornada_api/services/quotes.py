"""Quote rules: valid weight, pan size, subtotal, delivery fee, total, deposit."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from fornada_api.models import Fulfillment, Neighborhood, PanSize, Product
from fornada_api.services.errors import (
    InvalidWeight,
    NeighborhoodNotServed,
    NeighborhoodRequired,
    ProductNotFound,
)
from fornada_api.services.money import ZERO, round_money, round_weight
from fornada_api.services.ports import CatalogRepository

WEIGHT_STEP = Decimal("0.5")


@dataclass(frozen=True)
class Quote:
    product_slug: str
    product_name: str
    is_custom: bool
    weight_kg: Decimal
    pan_size: str
    fulfillment: Fulfillment
    neighborhood: str | None
    price_per_kg: Decimal
    subtotal: Decimal
    delivery_fee: Decimal
    discount: Decimal
    total: Decimal
    deposit: Decimal


@dataclass(frozen=True)
class PricedCake:
    """A quote plus the rows an order references."""

    quote: Quote
    product: Product
    pan_size: PanSize
    neighborhood: Neighborhood | None


def deposit_for(total: Decimal) -> Decimal:
    return round_money(total / 2)


def total_for(subtotal: Decimal, delivery_fee: Decimal, discount: Decimal) -> Decimal:
    return round_money(subtotal + delivery_fee - discount)


def pan_for_weight(weight_kg: Decimal, pans: Sequence[PanSize]) -> PanSize:
    """The smallest pan whose range holds the weight; a boundary uses the smaller pan.

    Raises `InvalidWeight` off the 0.5 kg step or outside the pans' range.
    """
    by_size = sorted(pans, key=lambda p: (p.min_kg, p.max_kg))
    low, high = by_size[0].min_kg, max(p.max_kg for p in by_size)
    if weight_kg % WEIGHT_STEP == 0 and low <= weight_kg <= high:
        for pan in by_size:
            if pan.min_kg <= weight_kg <= pan.max_kg:
                return pan
    raise InvalidWeight(
        f"invalid weight {weight_kg} kg: cakes go from {round_weight(low)} to "
        f"{round_weight(high)} kg in steps of {WEIGHT_STEP} kg"
    )


class QuoteService:
    def __init__(self, catalog: CatalogRepository) -> None:
        self.catalog = catalog

    async def quote(
        self,
        product_slug: str,
        weight_kg: Decimal,
        fulfillment: Fulfillment,
        neighborhood: str | None = None,
    ) -> Quote:
        priced = await self.price(product_slug, weight_kg, fulfillment, neighborhood)
        return priced.quote

    async def price(
        self,
        product_slug: str,
        weight_kg: Decimal,
        fulfillment: Fulfillment,
        neighborhood: str | None = None,
    ) -> PricedCake:
        product = await self.catalog.get_product(product_slug)
        if product is None or not product.active:
            raise ProductNotFound(
                f"product {product_slug!r} not found; use search_catalog for valid slugs"
            )
        pan = pan_for_weight(weight_kg, await self.catalog.list_pan_sizes())

        place: Neighborhood | None = None
        delivery_fee = ZERO
        if fulfillment == Fulfillment.DELIVERY:
            place = await self._served_neighborhood(neighborhood)
            delivery_fee = place.delivery_fee

        subtotal = round_money(product.price_per_kg * weight_kg)
        total = total_for(subtotal, delivery_fee, ZERO)
        quote = Quote(
            product_slug=product.slug,
            product_name=product.name,
            is_custom=product.is_custom,
            weight_kg=round_weight(weight_kg),
            pan_size=pan.code,
            fulfillment=fulfillment,
            neighborhood=place.name if place else None,
            price_per_kg=product.price_per_kg,
            subtotal=subtotal,
            delivery_fee=round_money(delivery_fee),
            discount=ZERO,
            total=total,
            deposit=deposit_for(total),
        )
        return PricedCake(quote=quote, product=product, pan_size=pan, neighborhood=place)

    async def _served_neighborhood(self, name: str | None) -> Neighborhood:
        if name:
            place = await self.catalog.get_neighborhood(name.strip())
            if place is not None and place.active:
                return place
        served = ", ".join(n.name for n in await self.catalog.list_neighborhoods())
        if not name:
            raise NeighborhoodRequired(f"delivery needs a neighborhood; we deliver to: {served}")
        raise NeighborhoodNotServed(f"we do not deliver to {name!r}; we deliver to: {served}")
