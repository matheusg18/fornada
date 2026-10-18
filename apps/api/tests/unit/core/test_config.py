import traceback
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from fornada_api.core.config import ConfigError, Settings

REPO_ROOT = Path(__file__).resolve().parents[5]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test with none of the app's variables set."""
    import os

    for name in list(os.environ):
        if name.upper().startswith(("LLM__", "APP__", "LOG__", "DB__", "TELEMETRY__", "CHAOS__")):
            monkeypatch.delenv(name)


DB_URL = "postgresql://fornada:db-secret@postgres:5432/fornada"


@pytest.fixture
def with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The required settings: an Anthropic key and a database URL."""
    monkeypatch.setenv("LLM__ANTHROPIC__API_KEY", "sk-ant-test")
    monkeypatch.setenv("DB__URL", DB_URL)


def load(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)


# --- sources -----------------------------------------------------------------


def test_value_from_env_file(tmp_path: Path, with_key: None) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("LOG__LEVEL=DEBUG\n")
    assert Settings(_env_file=env_file).log.level == "DEBUG"


def test_environment_overrides_env_file(
    tmp_path: Path, with_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("LOG__LEVEL=DEBUG\n")
    monkeypatch.setenv("LOG__LEVEL", "WARNING")
    assert Settings(_env_file=env_file).log.level == "WARNING"


def test_missing_env_file_is_not_an_error(with_key: None, tmp_path: Path) -> None:
    assert Settings(_env_file=tmp_path / "nope.env").log.level == "INFO"


# --- namespaces --------------------------------------------------------------


def test_nested_provider_key(with_key: None) -> None:
    key = load().llm.anthropic.api_key
    assert key is not None and key.get_secret_value() == "sk-ant-test"


def test_lowercase_variable_name(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("app__timezone", "UTC")
    assert load().app.timezone == ZoneInfo("UTC")


# --- provider ----------------------------------------------------------------


def test_default_provider(with_key: None) -> None:
    assert load().llm.provider == "anthropic"


def test_switch_to_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM__PROVIDER", "openai")
    monkeypatch.setenv("LLM__OPENAI__API_KEY", "sk-oa-test")
    monkeypatch.setenv("DB__URL", DB_URL)
    settings = load()
    assert settings.llm.provider == "openai"
    assert settings.llm.active.model == "gpt-5-mini"


def test_unknown_provider(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM__PROVIDER", "gemini")
    with pytest.raises(ConfigError, match="LLM__PROVIDER"):
        load()


def test_model_defaults(with_key: None) -> None:
    llm = load().llm
    assert llm.anthropic.model == "claude-haiku-4-5"
    assert llm.openai.model == "gpt-5-mini"


def test_model_override(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM__ANTHROPIC__MODEL", "claude-sonnet-5-5")
    assert load().llm.anthropic.model == "claude-sonnet-5-5"


def test_price_defaults(with_key: None) -> None:
    llm = load().llm
    assert llm.anthropic.input_usd_per_mtok == Decimal("1.00")
    assert llm.anthropic.output_usd_per_mtok == Decimal("5.00")
    assert llm.openai.input_usd_per_mtok == Decimal("0.25")
    assert llm.openai.output_usd_per_mtok == Decimal("2.00")


def test_price_override(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM__ANTHROPIC__INPUT_USD_PER_MTOK", "3")
    assert load().llm.anthropic.input_usd_per_mtok == Decimal("3")


def test_negative_price(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM__OPENAI__OUTPUT_USD_PER_MTOK", "-1")
    with pytest.raises(ConfigError, match="LLM__OPENAI__OUTPUT_USD_PER_MTOK"):
        load()


def test_zero_price_is_allowed(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    # A free local model is a valid setup.
    monkeypatch.setenv("LLM__OPENAI__INPUT_USD_PER_MTOK", "0")
    assert load().llm.openai.input_usd_per_mtok == Decimal("0")


@pytest.mark.parametrize(
    ("model", "expected"), [("claude-haiku-4-5", True), ("claude-sonnet-5-5", False)]
)
def test_default_prices_match_model(
    model: str, expected: bool, with_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM__ANTHROPIC__MODEL", model)
    assert load().llm.anthropic.prices_match_model is expected


def test_overridden_prices_match_any_model(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM__ANTHROPIC__MODEL", "claude-sonnet-5-5")
    monkeypatch.setenv("LLM__ANTHROPIC__INPUT_USD_PER_MTOK", "2")
    assert load().llm.anthropic.prices_match_model is True


def test_active_provider_without_key() -> None:
    with pytest.raises(ConfigError, match="LLM__ANTHROPIC__API_KEY"):
        load()


def test_active_provider_with_empty_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM__ANTHROPIC__API_KEY", "  ")
    with pytest.raises(ConfigError, match="LLM__ANTHROPIC__API_KEY"):
        load()


def test_inactive_provider_without_key(with_key: None) -> None:
    assert load().llm.openai.api_key is None


# --- secrets -----------------------------------------------------------------


def test_api_key_is_masked(with_key: None) -> None:
    settings = load()
    for text in (str(settings), repr(settings), str(settings.model_dump())):
        assert "sk-ant-test" not in text


def test_config_error_does_not_leak_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    # Active provider has no key; the inactive one does. The printed
    # traceback must not carry the raw input that pydantic echoes back.
    monkeypatch.setenv("LLM__PROVIDER", "openai")
    monkeypatch.setenv("LLM__ANTHROPIC__API_KEY", "sk-SEC")
    with pytest.raises(ConfigError) as exc_info:
        load()
    printed = "".join(traceback.format_exception(exc_info.value))
    assert "LLM__OPENAI__API_KEY" in printed
    assert "sk-SEC" not in printed


# --- database ----------------------------------------------------------------


def test_missing_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM__ANTHROPIC__API_KEY", "sk-ant-test")
    with pytest.raises(ConfigError, match="DB__URL"):
        load()


def test_empty_database_url(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB__URL", "")
    with pytest.raises(ConfigError, match="DB__URL"):
        load()


def test_non_postgres_database_url(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB__URL", "mysql://user:pass-SEC@host/db")
    with pytest.raises(ConfigError, match="DB__URL") as exc_info:
        load()
    assert "pass-SEC" not in "".join(traceback.format_exception(exc_info.value))


def test_plain_postgres_url(with_key: None) -> None:
    assert load().db.url.get_secret_value() == DB_URL


def test_database_password_is_masked(with_key: None) -> None:
    settings = load()
    for text in (str(settings), repr(settings), str(settings.model_dump())):
        assert "db-secret" not in text


# --- time zone and log level -------------------------------------------------


def test_default_timezone(with_key: None) -> None:
    assert load().app.timezone == ZoneInfo("America/Sao_Paulo")


def test_invalid_timezone(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP__TIMEZONE", "Mars/Olympus")
    with pytest.raises(ConfigError, match="APP__TIMEZONE"):
        load()


# --- daily capacity ------------------------------------------------------------


def test_default_daily_capacity(with_key: None) -> None:
    capacity = load().app.daily_capacity_kg
    assert isinstance(capacity, Decimal)
    assert capacity == Decimal("15")


def test_daily_capacity_override(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP__DAILY_CAPACITY_KG", "20.5")
    assert load().app.daily_capacity_kg == Decimal("20.5")


@pytest.mark.parametrize("value", ["0", "-3", "lots"])
def test_invalid_daily_capacity(
    value: str, with_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP__DAILY_CAPACITY_KG", value)
    with pytest.raises(ConfigError, match="APP__DAILY_CAPACITY_KG"):
        load()


def test_default_log_level(with_key: None) -> None:
    assert load().log.level == "INFO"


def test_lowercase_log_level(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG__LEVEL", "debug")
    assert load().log.level == "DEBUG"


def test_invalid_log_level(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG__LEVEL", "LOUD")
    with pytest.raises(ConfigError, match="LOG__LEVEL"):
        load()


# --- telemetry -----------------------------------------------------------------


def test_telemetry_namespace(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEMETRY__ENABLED", "true")
    assert load().telemetry.enabled is True


def test_tracing_off_by_default(with_key: None) -> None:
    assert load().telemetry.enabled is False


@pytest.mark.parametrize("value", ["maybe", "2"])
def test_invalid_tracing_switch(
    value: str, with_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TELEMETRY__ENABLED", value)
    with pytest.raises(ConfigError, match="TELEMETRY__ENABLED"):
        load()


def test_content_capture_off_by_default(with_key: None) -> None:
    assert load().telemetry.capture_content is False


def test_content_capture_on(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEMETRY__ENABLED", "true")
    monkeypatch.setenv("TELEMETRY__CAPTURE_CONTENT", "true")
    assert load().telemetry.capture_content is True


@pytest.mark.parametrize("value", ["maybe", "2"])
def test_invalid_content_capture_switch(
    value: str, with_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TELEMETRY__CAPTURE_CONTENT", value)
    with pytest.raises(ConfigError, match="TELEMETRY__CAPTURE_CONTENT"):
        load()


def test_default_otlp_endpoint(with_key: None) -> None:
    assert load().telemetry.otlp_endpoint == "http://edot-collector:4318"


def test_otlp_endpoint_override(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEMETRY__OTLP_ENDPOINT", "http://localhost:4318")
    assert load().telemetry.otlp_endpoint == "http://localhost:4318"


def test_otlp_endpoint_trailing_slash_is_dropped(
    with_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The signal path is appended to this value; a trailing slash would double it.
    monkeypatch.setenv("TELEMETRY__OTLP_ENDPOINT", "https://collector.example:4318/")
    assert load().telemetry.otlp_endpoint == "https://collector.example:4318"


@pytest.mark.parametrize(
    "value", ["edot-collector:4317", "grpc://edot-collector:4317", "http://", ""]
)
def test_invalid_otlp_endpoint(value: str, with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEMETRY__OTLP_ENDPOINT", value)
    with pytest.raises(ConfigError, match="TELEMETRY__OTLP_ENDPOINT"):
        load()


# --- chaos -------------------------------------------------------------------


def test_chaos_off_by_default(with_key: None) -> None:
    assert load().chaos.enabled is False


def test_chaos_on(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAOS__ENABLED", "true")
    assert load().chaos.enabled is True


def test_invalid_chaos_switch(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAOS__ENABLED", "maybe")
    with pytest.raises(ConfigError, match="CHAOS__ENABLED"):
        load()


def test_default_chaos_latency(with_key: None) -> None:
    chaos = load().chaos
    assert (chaos.latency_min_ms, chaos.latency_max_ms) == (200, 2000)


@pytest.mark.parametrize("name", ["CHAOS__LATENCY_MIN_MS", "CHAOS__LATENCY_MAX_MS"])
def test_negative_chaos_latency(name: str, with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(name, "-1")
    with pytest.raises(ConfigError, match=name):
        load()


def test_chaos_latency_min_above_max(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAOS__LATENCY_MIN_MS", "3000")
    monkeypatch.setenv("CHAOS__LATENCY_MAX_MS", "2000")
    with pytest.raises(ConfigError, match="CHAOS__LATENCY_MIN_MS"):
        load()


def test_chaos_zero_latency_range(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAOS__LATENCY_MIN_MS", "0")
    monkeypatch.setenv("CHAOS__LATENCY_MAX_MS", "0")
    chaos = load().chaos
    assert (chaos.latency_min_ms, chaos.latency_max_ms) == (0, 0)


def test_default_chaos_failure_rate(with_key: None) -> None:
    assert load().chaos.capacity_failure_rate == 0.1


@pytest.mark.parametrize("value", ["1.5", "-0.1", "often"])
def test_invalid_chaos_failure_rate(
    value: str, with_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHAOS__CAPACITY_FAILURE_RATE", value)
    with pytest.raises(ConfigError, match="CHAOS__CAPACITY_FAILURE_RATE"):
        load()


def test_default_chaos_price_increase(with_key: None) -> None:
    increase = load().chaos.price_increase_pct
    assert isinstance(increase, Decimal)
    assert increase == Decimal("10")


@pytest.mark.parametrize("value", ["0", "-5", "100.5"])
def test_invalid_chaos_price_increase(
    value: str, with_key: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHAOS__PRICE_INCREASE_PCT", value)
    with pytest.raises(ConfigError, match="CHAOS__PRICE_INCREASE_PCT"):
        load()


def test_chaos_has_no_seed_by_default(with_key: None) -> None:
    assert load().chaos.seed is None


def test_chaos_seed(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAOS__SEED", "42")
    assert load().chaos.seed == 42


def test_invalid_chaos_seed(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAOS__SEED", "abc")
    with pytest.raises(ConfigError, match="CHAOS__SEED"):
        load()


# --- template ----------------------------------------------------------------


def test_env_example_loads() -> None:
    settings = Settings(_env_file=REPO_ROOT / ".env.example")
    assert settings.llm.active.api_key is not None
