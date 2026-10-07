import datetime as dt
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from fornada_api.services.clock import FixedClock, SystemClock
from fornada_api.services.errors import DomainError, InvalidPhone
from fornada_api.services.money import money_str, round_money, weight_str
from fornada_api.services.phones import normalize_phone

# --- money -------------------------------------------------------------------


def test_subtotal_is_exact() -> None:
    assert round_money(Decimal("89.90") * Decimal("2.5")) == Decimal("224.75")


def test_deposit_rounds_half_up() -> None:
    assert round_money(Decimal("234.75") / 2) == Decimal("117.38")


def test_rounding_is_not_bankers() -> None:
    assert round_money(Decimal("0.125")) == Decimal("0.13")


def test_amounts_as_strings() -> None:
    assert money_str(Decimal("10")) == "10.00"
    assert weight_str(Decimal("2.50")) == "2.5"
    assert weight_str(Decimal("0")) == "0.0"


# --- phones ------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["(81) 98765-4321", "81987654321", "+55 81 98765-4321", "5581987654321", "081 98765 4321"],
)
def test_phone_normalized_to_e164(raw: str) -> None:
    assert normalize_phone(raw) == "+5581987654321"


def test_landline_without_ninth_digit() -> None:
    assert normalize_phone("(81) 3333-4444") == "+558133334444"


@pytest.mark.parametrize("raw", ["", "123", "+1 415 555 0100", "abc"])
def test_unparseable_phone(raw: str) -> None:
    with pytest.raises(InvalidPhone) as exc_info:
        normalize_phone(raw)
    assert isinstance(exc_info.value, DomainError)


# --- clock -------------------------------------------------------------------

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def test_late_evening_in_utc_uses_local_date() -> None:
    # 22:00 on 2026-10-07 in São Paulo is 01:00 UTC on 2026-10-08.
    clock = SystemClock(SAO_PAULO, utcnow=lambda: dt.datetime(2026, 10, 8, 1, tzinfo=dt.UTC))
    assert clock.today() == dt.date(2026, 10, 7)
    assert clock.now().tzinfo is not None


def test_fixed_clock() -> None:
    clock = FixedClock(dt.date(2026, 10, 7))
    assert clock.today() == dt.date(2026, 10, 7)
    assert clock.now().date() == dt.date(2026, 10, 7)
