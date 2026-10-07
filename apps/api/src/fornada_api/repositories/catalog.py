from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fornada_api.models import Neighborhood, PanSize, Product, ProductAllergen


class CatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_products(self) -> Sequence[Product]:
        result = await self.session.scalars(
            select(Product)
            .where(Product.active)
            .options(selectinload(Product.allergen_links).selectinload(ProductAllergen.allergen))
            .order_by(Product.id)
        )
        return result.all()

    async def get_product(self, slug: str) -> Product | None:
        return await self.session.scalar(select(Product).where(Product.slug == slug))

    async def list_pan_sizes(self) -> Sequence[PanSize]:
        result = await self.session.scalars(
            select(PanSize).order_by(PanSize.min_kg, PanSize.max_kg)
        )
        return result.all()

    async def list_neighborhoods(self) -> Sequence[Neighborhood]:
        result = await self.session.scalars(
            select(Neighborhood).where(Neighborhood.active).order_by(Neighborhood.name)
        )
        return result.all()

    async def get_neighborhood(self, name: str) -> Neighborhood | None:
        return await self.session.scalar(
            select(Neighborhood).where(func.lower(Neighborhood.name) == func.lower(name))
        )
