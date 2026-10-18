from decimal import Decimal

from fornada_api.core.config import ChaosSettings
from fornada_api.infrastructure.chaos import Chaos


def chaos(**kwargs: object) -> Chaos:
    return Chaos(ChaosSettings.model_validate({"enabled": True, **kwargs}))


# --- latency -----------------------------------------------------------------


def test_delays_stay_in_range() -> None:
    engine = chaos(latency_min_ms=200, latency_max_ms=2000)
    delays = [engine.delay_ms() for _ in range(500)]
    assert all(200 <= d <= 2000 for d in delays)
    assert len(set(delays)) > 1


def test_zero_range_means_no_delay() -> None:
    engine = chaos(latency_min_ms=0, latency_max_ms=0)
    assert {engine.delay_ms() for _ in range(50)} == {0}


# --- capacity outage ---------------------------------------------------------


def test_rate_zero_never_fails() -> None:
    engine = chaos(capacity_failure_rate=0.0)
    assert not any(engine.capacity_fails() for _ in range(500))


def test_rate_one_always_fails() -> None:
    engine = chaos(capacity_failure_rate=1.0)
    assert all(engine.capacity_fails() for _ in range(500))


# --- price ---------------------------------------------------------------------


def test_factor_is_one_before_the_first_quote() -> None:
    assert chaos().price_factor("conv-1") == Decimal(1)


def test_factor_rises_after_the_first_quote() -> None:
    engine = chaos(price_increase_pct=Decimal("10"))
    engine.mark_quoted("conv-1")
    assert engine.price_factor("conv-1") == Decimal("1.10")


def test_increase_does_not_compound() -> None:
    engine = chaos(price_increase_pct=Decimal("10"))
    for _ in range(3):
        engine.mark_quoted("conv-1")
    assert engine.price_factor("conv-1") == Decimal("1.10")


def test_conversations_are_independent() -> None:
    engine = chaos()
    engine.mark_quoted("conv-1")
    assert engine.price_factor("conv-2") == Decimal(1)


# --- seed ----------------------------------------------------------------------


def draws(engine: Chaos) -> list[tuple[int, bool]]:
    return [(engine.delay_ms(), engine.capacity_fails()) for _ in range(50)]


def test_same_seed_same_draws() -> None:
    assert draws(chaos(seed=42, capacity_failure_rate=0.5)) == draws(
        chaos(seed=42, capacity_failure_rate=0.5)
    )


def test_different_seeds_differ() -> None:
    assert draws(chaos(seed=1, capacity_failure_rate=0.5)) != draws(
        chaos(seed=2, capacity_failure_rate=0.5)
    )
