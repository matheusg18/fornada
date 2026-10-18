"""Application settings, read from the environment and the root `.env`.

Settings are grouped into namespaces. A nested value is addressed in the
environment with a double underscore: `LLM__ANTHROPIC__API_KEY`.
"""

from decimal import Decimal
from functools import cache
from typing import Any, Literal, Self
from urllib.parse import urlsplit
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
    # US dollars per million tokens, for the cost metric. Each provider's
    # defaults are the published standard-tier prices of its default model.
    input_usd_per_mtok: Decimal = Field(ge=0)
    output_usd_per_mtok: Decimal = Field(ge=0)

    @property
    def prices_match_model(self) -> bool:
        """False when the model was changed but the prices were left at the
        default model's, so the cost metric is likely wrong."""
        default_model = type(self).model_fields["model"].default
        prices_set = {"input_usd_per_mtok", "output_usd_per_mtok"} & self.model_fields_set
        return self.model == default_model or bool(prices_set)


class AnthropicSettings(ProviderSettings):
    model: str = "claude-haiku-4-5"
    # claude-api skill model table, cached 2026-10-06.
    input_usd_per_mtok: Decimal = Field(default=Decimal("1.00"), ge=0)
    output_usd_per_mtok: Decimal = Field(default=Decimal("5.00"), ge=0)


class OpenAISettings(ProviderSettings):
    model: str = "gpt-5-mini"
    # developers.openai.com/api/docs/pricing, standard tier, read 2026-10-18.
    input_usd_per_mtok: Decimal = Field(default=Decimal("0.25"), ge=0)
    output_usd_per_mtok: Decimal = Field(default=Decimal("2.00"), ge=0)


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
    # Oven capacity for dates without a row in `capacity_overrides`.
    daily_capacity_kg: Decimal = Field(default=Decimal("15"), gt=0)


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


class TelemetrySettings(BaseModel):
    # Off by default so tests and CI never try to reach a Collector.
    enabled: bool = False
    # Base URL of the Collector's OTLP/HTTP receiver; the signal path
    # (`/v1/traces`) is appended by the telemetry setup.
    otlp_endpoint: str = "http://edot-collector:4318"
    # Message text, tool arguments and results, and customer phones on agent
    # spans. Off by default: the GenAI semconv makes content opt-in, and the
    # Collector strips it before Elasticsearch, not before Langfuse.
    capture_content: bool = False

    @field_validator("otlp_endpoint")
    @classmethod
    def _http_url(cls, url: str) -> str:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("must be an http(s) URL (http://host:4318)")
        return url.rstrip("/")


class ChaosSettings(BaseModel):
    # Fault injection for simulator runs (random tool latency, `check_capacity`
    # outages, a price rise after a conversation's first quote). Off by default;
    # the other fields are validated even while it is off.
    enabled: bool = False
    latency_min_ms: int = Field(default=200, ge=0)
    latency_max_ms: int = Field(default=2000, ge=0)
    capacity_failure_rate: float = Field(default=0.1, ge=0, le=1)
    price_increase_pct: Decimal = Field(default=Decimal("10"), gt=0, le=100)
    seed: int | None = None

    @model_validator(mode="after")
    def _latency_range(self) -> Self:
        if self.latency_min_ms > self.latency_max_ms:
            raise ValueError(
                f"CHAOS__LATENCY_MIN_MS ({self.latency_min_ms}) must not exceed "
                f"CHAOS__LATENCY_MAX_MS ({self.latency_max_ms})"
            )
        return self


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
    telemetry: TelemetrySettings = TelemetrySettings()
    chaos: ChaosSettings = ChaosSettings()

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
