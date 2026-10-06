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
        if name.upper().startswith(("LLM__", "APP__", "LOG__")):
            monkeypatch.delenv(name)


@pytest.fixture
def with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM__ANTHROPIC__API_KEY", "sk-ant-test")


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


# --- time zone and log level -------------------------------------------------


def test_default_timezone(with_key: None) -> None:
    assert load().app.timezone == ZoneInfo("America/Sao_Paulo")


def test_invalid_timezone(with_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP__TIMEZONE", "Mars/Olympus")
    with pytest.raises(ConfigError, match="APP__TIMEZONE"):
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


# --- template ----------------------------------------------------------------


def test_env_example_loads() -> None:
    settings = Settings(_env_file=REPO_ROOT / ".env.example")
    assert settings.llm.active.api_key is not None
