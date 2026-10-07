"""Coupon validity. The 1-10% cap lives here: the database accepts any percentage."""

from fornada_api.models import Coupon
from fornada_api.services.clock import Clock
from fornada_api.services.errors import (
    CouponExpired,
    CouponInactive,
    CouponNotAllowed,
    CouponNotFound,
    CouponNotYetValid,
    CouponUsedUp,
)
from fornada_api.services.ports import CouponRepository

MIN_PERCENT_OFF = 1
MAX_PERCENT_OFF = 10


class CouponService:
    def __init__(self, coupons: CouponRepository, clock: Clock) -> None:
        self.coupons = coupons
        self.clock = clock

    async def validate(self, code: str) -> Coupon:
        """The coupon, if it can be used today. Each failure raises its own error."""
        coupon = await self.coupons.get(code.strip())
        if coupon is None:
            raise CouponNotFound(f"coupon {code!r} does not exist")
        if not coupon.active:
            raise CouponInactive(f"coupon {coupon.code} is no longer active")
        today = self.clock.today()
        if today < coupon.valid_from:
            raise CouponNotYetValid(
                f"coupon {coupon.code} is only valid from {coupon.valid_from.isoformat()}"
            )
        if today > coupon.valid_until:
            raise CouponExpired(f"coupon {coupon.code} expired on {coupon.valid_until.isoformat()}")
        if not MIN_PERCENT_OFF <= coupon.percent_off <= MAX_PERCENT_OFF:
            raise CouponNotAllowed(
                f"coupon {coupon.code} cannot be applied: discounts are limited to "
                f"{MAX_PERCENT_OFF}%"
            )
        uses_left = coupon.max_uses is None or (
            await self.coupons.count_uses(coupon.code) < coupon.max_uses
        )
        if not uses_left:
            raise CouponUsedUp(f"coupon {coupon.code} has reached its usage limit")
        return coupon
