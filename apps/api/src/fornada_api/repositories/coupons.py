from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fornada_api.models import Coupon, Order, OrderStatus


class CouponRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, code: str) -> Coupon | None:
        return await self.session.scalar(
            select(Coupon).where(func.upper(Coupon.code) == func.upper(code))
        )

    async def count_uses(self, code: str) -> int:
        count = await self.session.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.coupon_code == code, Order.status != OrderStatus.CANCELLED)
        )
        return count or 0
