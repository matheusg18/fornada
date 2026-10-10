import pytest

from fornada_simulator.settings import ConfigError, Settings

KEY = "sk-ant-super-secret-value"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for name in list(os.environ):
        if name.upper().startswith("SIMULATOR__"):
            monkeypatch.delenv(name)


def load() -> Settings:
    # `_env_file=None`: a developer's real `.env` must not leak into the tests.
    return Settings(_env_file=None)


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMULATOR__ANTHROPIC__API_KEY", KEY)
    sim = load().simulator
    assert sim.provider == "anthropic"
    assert sim.active.model == "claude-haiku-4-5"
    assert sim.api_url == "http://localhost:8000"
    assert (sim.max_turns, sim.concurrency, sim.runs_per_persona) == (12, 1, 4)


def test_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMULATOR__PROVIDER", "openai")
    monkeypatch.setenv("SIMULATOR__OPENAI__API_KEY", KEY)
    monkeypatch.setenv("SIMULATOR__OPENAI__MODEL", "gpt-x")
    monkeypatch.setenv("SIMULATOR__API_URL", "http://api:9000")
    monkeypatch.setenv("SIMULATOR__MAX_TURNS", "5")
    monkeypatch.setenv("SIMULATOR__CONCURRENCY", "3")
    monkeypatch.setenv("SIMULATOR__RUNS_PER_PERSONA", "2")
    sim = load().simulator
    assert sim.active.model == "gpt-x"
    assert sim.api_url == "http://api:9000"
    assert (sim.max_turns, sim.concurrency, sim.runs_per_persona) == (5, 3, 2)


def test_missing_key_names_the_variable() -> None:
    with pytest.raises(ConfigError, match="SIMULATOR__ANTHROPIC__API_KEY is required"):
        load()


def test_missing_key_of_chosen_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMULATOR__PROVIDER", "openai")
    monkeypatch.setenv("SIMULATOR__ANTHROPIC__API_KEY", KEY)
    with pytest.raises(ConfigError, match="SIMULATOR__OPENAI__API_KEY"):
        load()


def test_errors_never_contain_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMULATOR__ANTHROPIC__API_KEY", KEY)
    monkeypatch.setenv("SIMULATOR__MAX_TURNS", "0")
    with pytest.raises(ConfigError) as info:
        load()
    assert "SIMULATOR__MAX_TURNS" in str(info.value)
    assert KEY not in str(info.value)
