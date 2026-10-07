import datetime as dt
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fornada_api.models import CapacityOverride, Order, OrderStatus


class CapacityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_override(self, day: dt.date) -> CapacityOverride | None:
        return await self.session.get(CapacityOverride, day)

    async def used_kg(self, day: dt.date) -> Decimal:
        used = await self.session.scalar(
            select(func.coalesce(func.sum(Order.weight_kg), 0)).where(
                Order.delivery_date == day, Order.status != OrderStatus.CANCELLED
            )
        )
        return Decimal(used or 0)
