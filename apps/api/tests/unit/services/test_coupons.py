import pytest

from fornada_api.services.coupons import CouponService
from fornada_api.services.errors import (
    CouponExpired,
    CouponInactive,
    CouponNotAllowed,
    CouponNotFound,
    CouponNotYetValid,
    CouponUsedUp,
    DomainError,
)
from tests.unit.services.fakes import CLOCK, FakeCouponRepository, seeded_db

pytestmark = pytest.mark.anyio


@pytest.fixture
def service() -> CouponService:
    return CouponService(FakeCouponRepository(seeded_db()), CLOCK)


async def test_valid_coupon_in_lowercase(service: CouponService) -> None:
    coupon = await service.validate(" amigo5 ")
    assert (coupon.code, coupon.percent_off) == ("AMIGO5", 5)


@pytest.mark.parametrize(
    ("code", "error"),
    [
        ("DESCONTO30", CouponNotFound),
        ("ANTIGO5", CouponInactive),
        ("VERAO8", CouponNotYetValid),
        ("PASCOA10", CouponExpired),
        ("PRIMEIRA10", CouponUsedUp),
        ("GERAL30", CouponNotAllowed),
    ],
)
async def test_each_failure_has_its_own_error(
    service: CouponService, code: str, error: type[DomainError]
) -> None:
    with pytest.raises(error):
        await service.validate(code)
