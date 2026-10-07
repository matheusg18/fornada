from decimal import Decimal

import pytest

from fornada_api.models import Fulfillment
from fornada_api.services.errors import (
    InvalidWeight,
    NeighborhoodNotServed,
    NeighborhoodRequired,
    ProductNotFound,
)
from fornada_api.services.quotes import QuoteService
from tests.unit.services.fakes import FakeCatalogRepository, seeded_db

pytestmark = pytest.mark.anyio

DELIVERY, PICKUP = Fulfillment.DELIVERY, Fulfillment.PICKUP


@pytest.fixture
def service() -> QuoteService:
    return QuoteService(FakeCatalogRepository(seeded_db()))


# --- weight and pan size -------------------------------------------------------


async def test_off_step_weight(service: QuoteService) -> None:
    with pytest.raises(InvalidWeight, match=r"steps of 0\.5 kg"):
        await service.quote("bolo-chocolate", Decimal("2.3"), PICKUP)


@pytest.mark.parametrize("weight", ["8", "0.5", "0", "-1", "6.5"])
async def test_weight_outside_pans(service: QuoteService, weight: str) -> None:
    with pytest.raises(InvalidWeight, match=r"from 1\.0 to 6\.0 kg"):
        await service.quote("bolo-chocolate", Decimal(weight), PICKUP)


@pytest.mark.parametrize(
    ("weight", "pan"),
    [("1.0", "P"), ("2.0", "P"), ("2.5", "M"), ("3.5", "M"), ("4.5", "G"), ("6.0", "G")],
)
async def test_pan_size_from_weight(service: QuoteService, weight: str, pan: str) -> None:
    quote = await service.quote("bolo-chocolate", Decimal(weight), PICKUP)
    assert quote.pan_size == pan


# --- amounts -------------------------------------------------------------------


async def test_delivery_quote(service: QuoteService) -> None:
    quote = await service.quote("bolo-chocolate", Decimal("2.5"), DELIVERY, "Ipsep")
    assert quote.price_per_kg == Decimal("89.90")
    assert quote.subtotal == Decimal("224.75")
    assert quote.delivery_fee == Decimal("10.00")
    assert quote.discount == Decimal("0.00")
    assert quote.total == Decimal("234.75")
    assert quote.deposit == Decimal("117.38")
    assert quote.neighborhood == "Ipsep"


async def test_pickup_quote_ignores_neighborhood(service: QuoteService) -> None:
    quote = await service.quote("bolo-chocolate", Decimal("2.5"), PICKUP, "Olinda")
    assert quote.delivery_fee == Decimal("0.00")
    assert quote.total == quote.subtotal == Decimal("224.75")
    assert quote.neighborhood is None


async def test_neighborhood_is_case_insensitive(service: QuoteService) -> None:
    quote = await service.quote("bolo-chocolate", Decimal("2.5"), DELIVERY, " ipsep ")
    assert quote.neighborhood == "Ipsep"


# --- prerequisites ---------------------------------------------------------------


@pytest.mark.parametrize("slug", ["bolo-de-pistache", "bolo-antigo"])
async def test_unknown_or_inactive_product(service: QuoteService, slug: str) -> None:
    with pytest.raises(ProductNotFound):
        await service.quote(slug, Decimal("2.0"), PICKUP)


@pytest.mark.parametrize("name", ["Olinda", "Casa Forte"])
async def test_delivery_outside_the_area(service: QuoteService, name: str) -> None:
    with pytest.raises(NeighborhoodNotServed, match="Imbiribeira, Ipsep"):
        await service.quote("bolo-chocolate", Decimal("2.0"), DELIVERY, name)


async def test_delivery_without_neighborhood(service: QuoteService) -> None:
    with pytest.raises(NeighborhoodRequired, match="Ipsep"):
        await service.quote("bolo-chocolate", Decimal("2.0"), DELIVERY, None)
