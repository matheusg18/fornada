"""Exact decimal helpers for BRL amounts and cake weights. No floats."""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
TENTH = Decimal("0.1")
ZERO = Decimal("0.00")


def round_money(value: Decimal) -> Decimal:
    """Round half up to two decimal places: `117.375` -> `117.38`."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def round_weight(value: Decimal) -> Decimal:
    return value.quantize(TENTH, rounding=ROUND_HALF_UP)


def money_str(value: Decimal) -> str:
    """`Decimal("10")` -> `"10.00"`."""
    return format(round_money(value), "f")


def weight_str(value: Decimal) -> str:
    """`Decimal("2.50")` -> `"2.5"`."""
    return format(round_weight(value), "f")
