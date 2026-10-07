"""Application settings, read from the environment and the root `.env`.

Settings are grouped into namespaces. A nested value is addressed in the
environment with a double underscore: `LLM__ANTHROPIC__API_KEY`.
"""

from functools import cache
from typing import Any, Literal, Self
from zoneinfo import ZoneInfo

from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

LlmProvider = Literal["anthropic", "openai"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class ProviderSettings(BaseModel):
    api_key: SecretStr | None = None
    model: str


class AnthropicSettings(ProviderSettings):
    model: str = "claude-haiku-4-5"


class OpenAISettings(ProviderSettings):
    model: str = "gpt-5-mini"


class LlmSettings(BaseModel):
    provider: LlmProvider = "anthropic"
    anthropic: AnthropicSettings = AnthropicSettings()
    openai: OpenAISettings = OpenAISettings()

    @property
    def active(self) -> ProviderSettings:
        return getattr(self, self.provider)

    @model_validator(mode="after")
    def _active_provider_has_key(self) -> Self:
        key = self.active.api_key
        if key is None or not key.get_secret_value().strip():
            raise ValueError(
                f"LLM__{self.provider.upper()}__API_KEY is required "
                f"when LLM__PROVIDER={self.provider}"
            )
        return self


class AppSettings(BaseModel):
    timezone: ZoneInfo = ZoneInfo("America/Sao_Paulo")


class LogSettings(BaseModel):
    level: LogLevel = "INFO"

    @model_validator(mode="before")
    @classmethod
    def _normalize_level(cls, data: object) -> object:
        if isinstance(data, dict) and isinstance(data.get("level"), str):
            data = {**data, "level": data["level"].upper()}
        return data


class DbSettings(BaseModel):
    # Secret because the URL carries the database password.
    url: SecretStr

    @field_validator("url")
    @classmethod
    def _postgres_scheme(cls, url: SecretStr) -> SecretStr:
        # Never echo the value: it holds the password.
        if not url.get_secret_value().startswith(("postgresql://", "postgres://")):
            raise ValueError("must be a PostgreSQL URL (postgresql://user:pass@host:port/db)")
        return url


class ConfigError(ValueError):
    """Settings failed validation. The message names environment variables."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    llm: LlmSettings = Field(default_factory=LlmSettings)
    app: AppSettings = AppSettings()
    log: LogSettings = LogSettings()
    db: DbSettings

    @model_validator(mode="before")
    @classmethod
    def _db_namespace_present(cls, data: object) -> object:
        # Without any DB__* variable the error would point at `DB`, not `DB__URL`.
        if isinstance(data, dict) and "db" not in data:
            data = {**data, "db": {}}
        return data

    def __init__(self, **kwargs: Any) -> None:
        try:
            super().__init__(**kwargs)
        except ValidationError as exc:
            lines = []
            for err in exc.errors():
                # `llm.provider` -> `LLM__PROVIDER`
                where = "__".join(str(part) for part in err["loc"]).upper()
                lines.append(f"{where}: {err['msg']}" if where else err["msg"])
            # `from None`: the original error echoes raw input, API keys included.
            raise ConfigError("Invalid settings:\n" + "\n".join(lines)) from None


@cache
def get_settings() -> Settings:
    return Settings()
