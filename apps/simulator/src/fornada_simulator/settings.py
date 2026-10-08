"""Simulator settings, read from the environment and the repo's root `.env`.

Variables live under the `SIMULATOR__` namespace and nested values use a double
underscore: `SIMULATOR__ANTHROPIC__API_KEY`. The simulator's model is configured
apart from the agent's (`LLM__*`).
"""

from functools import cache
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LlmProvider = Literal["anthropic", "openai"]


def _find_env_file() -> Path | None:
    """The nearest `.env` from the working directory upwards.

    The notebook runs from `apps/simulator/notebooks`, the batch task from the
    repo root; both must find the root `.env`.
    """
    here = Path.cwd().resolve()
    for folder in (here, *here.parents):
        candidate = folder / ".env"
        if candidate.is_file():
            return candidate
    return None


class ProviderSettings(BaseModel):
    api_key: SecretStr | None = None
    model: str


class AnthropicSettings(ProviderSettings):
    model: str = "claude-haiku-4-5"


class OpenAISettings(ProviderSettings):
    model: str = "gpt-5-mini"


class SimulatorSettings(BaseModel):
    provider: LlmProvider = "anthropic"
    anthropic: AnthropicSettings = AnthropicSettings()
    openai: OpenAISettings = OpenAISettings()
    api_url: str = "http://localhost:8000"
    # Customer messages before a conversation is cut off.
    max_turns: int = Field(default=12, ge=1)
    concurrency: int = Field(default=1, ge=1)
    runs_per_persona: int = Field(default=4, ge=1)

    @property
    def active(self) -> ProviderSettings:
        return getattr(self, self.provider)

    @model_validator(mode="after")
    def _active_provider_has_key(self) -> Self:
        key = self.active.api_key
        if key is None or not key.get_secret_value().strip():
            raise ValueError(
                f"SIMULATOR__{self.provider.upper()}__API_KEY is required "
                f"when SIMULATOR__PROVIDER={self.provider}"
            )
        return self


class ConfigError(ValueError):
    """Settings failed validation. The message names environment variables."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    simulator: SimulatorSettings

    @model_validator(mode="before")
    @classmethod
    def _namespace_present(cls, data: object) -> object:
        # Without any SIMULATOR__* variable the error would point at `SIMULATOR`.
        if isinstance(data, dict) and "simulator" not in data:
            data = {**data, "simulator": {}}
        return data

    def __init__(self, **kwargs: Any) -> None:
        try:
            super().__init__(**kwargs)
        except ValidationError as exc:
            lines = []
            for err in exc.errors():
                # `simulator.max_turns` -> `SIMULATOR__MAX_TURNS`
                where = "__".join(str(part) for part in err["loc"]).upper()
                msg = err["msg"].removeprefix("Value error, ")
                lines.append(f"{where}: {msg}" if where else msg)
            # `from None`: the original error echoes raw input, API keys included.
            raise ConfigError("Invalid settings:\n" + "\n".join(lines)) from None


@cache
def get_settings() -> Settings:
    return Settings()
