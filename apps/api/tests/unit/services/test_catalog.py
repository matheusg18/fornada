from decimal import Decimal

import pytest

from fornada_api.services.catalog import CatalogService
from tests.unit.services.fakes import FakeCatalogRepository, seeded_db

pytestmark = pytest.mark.anyio


@pytest.fixture
def service() -> CatalogService:
    return CatalogService(FakeCatalogRepository(seeded_db()))


async def test_full_catalog(service: CatalogService) -> None:
    catalog = await service.search()
    assert [p.slug for p in catalog.products] == [
        "bolo-chocolate",
        "torta-chocolate-sem-farinha",
        "personalizado-tema",
    ]  # the inactive product is left out
    assert [p.code for p in catalog.pan_sizes] == ["P", "M", "G"]
    assert [n.name for n in catalog.neighborhoods] == ["Imbiribeira", "Ipsep"]


async def test_allergens_split_by_kind(service: CatalogService) -> None:
    chocolate = (await service.search("bolo de chocolate")).products[0]
    assert chocolate.contains == ("Glúten", "Lactose", "Ovo")
    assert chocolate.may_contain == ("Soja",)


async def test_cross_contamination_is_visible(service: CatalogService) -> None:
    products = (await service.search("SEM FARINHA")).products
    assert [p.slug for p in products] == ["torta-chocolate-sem-farinha"]
    assert "Glúten" not in products[0].contains
    assert products[0].may_contain == ("Glúten",)


async def test_query_matches_description(service: CatalogService) -> None:
    products = (await service.search("brigadeiro")).products
    assert [p.slug for p in products] == ["bolo-chocolate"]


async def test_cost_is_exposed_in_v0(service: CatalogService) -> None:
    chocolate = (await service.search("bolo de chocolate")).products[0]
    assert chocolate.cost_per_kg == Decimal("32.00")


async def test_no_match_still_lists_pans_and_neighborhoods(service: CatalogService) -> None:
    catalog = await service.search("pistache")
    assert catalog.products == ()
    assert len(catalog.pan_sizes) == 3
