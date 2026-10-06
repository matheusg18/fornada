# Design

## Context

`apps/api` holds only `fornada_api/__init__.py` with a `main()` that prints a greeting. The package has no dependencies and no tests. The uv workspace runs every command from the repository root (`uv run --package fornada-api …`), and the root `.env` is gitignored and reserved for application settings (AGENTS.md, "Environment files"). The dev container already sets `TZ=America/Sao_Paulo` for the OS, but the app must not depend on the host's time zone. Requirements live in `specs/app-config` and `specs/structured-logging`.

This is periphery work in phase 1: it adds no defense and has no ASR, false-positive or p95 effect to measure.

## Goals / Non-Goals

**Goals:**
- One typed settings object, loaded once and reusable as a FastAPI dependency later.
- Fail at startup, not at the first LLM call, when configuration is wrong.
- Log format that phase 2 can extend with trace and span ids without changing the field names that already exist.

**Non-Goals:**
- Building LangChain chat model objects or adding `langchain-anthropic` / `langchain-openai`. The agent change will read `settings.llm` to build them.
- OpenTelemetry `LoggerProvider` or trace correlation (phase 2).
- A frozen or injectable clock for deterministic tests. Add it only when an eval needs it (phase 4 rule: no fix without an observed failure).
- Human-readable text log format for local development.

## Decisions

### Package layout: `fornada_api/core/`
`core/__init__.py`, `core/config.py`, `core/logging.py`. Inside the package, `import logging` in `core/logging.py` still resolves to the standard library (absolute imports), so the module name mirrors what it configures. Tests go in `apps/api/tests/core/`.

### `pydantic-settings` with nested models and `__` delimiter
A root `Settings(BaseSettings)` with three nested `BaseModel` fields: `llm: LlmSettings`, `app: AppSettings`, `log: LogSettings`. `LlmSettings` has `provider` plus `anthropic: ProviderSettings` and `openai: ProviderSettings`. `model_config` sets `env_nested_delimiter="__"`, `env_file=".env"`, `env_file_encoding="utf-8"`, `case_sensitive=False` and `extra="ignore"`.

- **No `env_prefix`.** Names stay short (`LLM__PROVIDER`), and the namespaces already avoid clashes with common variables. Alternative `FORNADA_` prefix was rejected: `FORNADA_LLM__ANTHROPIC__API_KEY` is long and adds nothing in a single-app container.
- **`extra="ignore"`.** The environment also holds `DATABASE_URI`, `TZ` and tooling variables; failing on them would be noise.
- **`env_file=".env"` relative to the working directory.** Every workspace command runs from the repo root, so this resolves to the root `.env`. Alternative: compute the path from `__file__`. Rejected because it breaks once the package is installed outside the source tree.
- **Alternative: plain `os.environ` + dataclasses.** Rejected: we would rewrite parsing, nesting, `.env` loading and validation errors by hand.

### Provider selection and key validation
`provider: Literal["anthropic", "openai"] = "anthropic"`. API keys are `SecretStr | None = None`. A `model_validator(mode="after")` on `LlmSettings` checks that the active provider's key is present and non-empty and raises a `ValueError` naming `LLM__<PROVIDER>__API_KEY`. The inactive key stays optional so a developer with only one account can run the app. `LlmSettings` exposes an `active` property that returns the active `ProviderSettings`, so callers do not branch on the provider name.

Model defaults: Anthropic `claude-haiku-4-5` (Haiku class, as AGENTS.md asks for the agent) and OpenAI `gpt-5-mini` (the maintainer's choice; the equivalent cheap tier).

### Validation errors name environment variables
`Settings.__init__` catches pydantic's `ValidationError` and re-raises `ConfigError` with one line per problem, the location rendered as the environment variable (`llm.provider` becomes `LLM__PROVIDER`). This is what the specs mean by "an error that names `LLM__PROVIDER`". A missing `llm` namespace falls back to its defaults, so the missing-key error comes from the validator with the full variable name.

Nested env values arrive as partial dicts that replace field defaults, so each provider has its own model class (`AnthropicSettings`, `OpenAISettings`) with the default `model` on the field.

### Time zone as `ZoneInfo`
`AppSettings.timezone: ZoneInfo = ZoneInfo("America/Sao_Paulo")`. Pydantic validates IANA names into `ZoneInfo` and rejects unknown ones. Business code will compute "now" as `datetime.now(settings.app.timezone)`, never `datetime.now()`. Log timestamps stay in UTC (see below), so the two never mix.

### Settings access
`get_settings()` wrapped in `functools.cache` returns the singleton. Tests build `Settings(_env_file=None)` with `monkeypatch.setenv`, so the developer's real `.env` never leaks into a test, and call `get_settings.cache_clear()` when they go through the accessor.

### `python-json-logger` for the JSON formatter
Use `pythonjsonlogger.json.JsonFormatter` (package `python-json-logger`, maintained by nhairs, v4). It already merges `extra` into top-level fields, serializes exceptions and handles common non-JSON types. Configuration:

- `fmt` with `levelname`, `name` and `message` (`style="{"`), and `rename_fields={"levelname": "level", "name": "logger", "exc_info": "exception"}` to get the field names in the spec.
- `timestamp=True`, which adds a `timestamp` field in UTC ISO 8601 from `record.created`.
- `json_ensure_ascii=False`, so pt-BR text such as "maçã" is not escaped.
- A subclass re-applies `level`, `logger`, `message`, `timestamp` and `exception` after the library merges `extra`, so extras cannot replace them.
- Its default encoder covers `datetime`, `Decimal` and similar; the tests check the spec's "non-serializable value" scenario, and a `json_default=str` fallback is added only if one fails.

Alternative: a hand-written `logging.Formatter` (about 40 lines). Rejected by the maintainer: the library is mature and covers edge cases (reserved attributes, exception and stack info, encoders) we would otherwise have to write and test ourselves. Phase 2 ships logs through OpenTelemetry's `LoggingHandler` over OTLP, so the stdout formatter does not constrain the OTel field mapping.

### `configure_logging(log_settings)` via `dictConfig`
One `StreamHandler` on `sys.stdout` with `JsonFormatter`, attached to the root logger at `LOG__LEVEL`, with `disable_existing_loggers=False` so library loggers (uvicorn, httpx) keep working and propagate to root. `dictConfig` replaces root handlers on each call, which makes setup idempotent. `fornada_api.main()` calls `configure_logging(get_settings().log)` first and logs a startup line with provider and model name (never the key).

## Risks / Trade-offs

- [The OS has no IANA database (slim image, CI runner)] → `ZoneInfo` falls back to the `tzdata` package; add `tzdata` as a dependency if the tests fail on CI.
- [No `env_prefix` could clash with a future tool that reads `LOG__LEVEL`] → Unlikely; adding a prefix later is a mechanical rename of `.env` and `.env.example`.
- [Running from a subdirectory does not find the root `.env`] → Documented convention: run from the repo root, as with every `uv run --package` command.
- [Extra keys that clash with standard `LogRecord` attributes (`message`, `name`) raise `KeyError` in the stdlib] → That is stdlib behavior at the call site, before any formatter runs.
- [An extra key named `level`, `logger`, `timestamp` or `exception` could collide with a renamed field] → The library lets the extra win, so `FornadaJsonFormatter` (a small `JsonFormatter` subclass) writes the standard values back after the merge; a test covers it.
- [The library changes field handling in a major release] → Version is locked in `uv.lock`; Dependabot bumps run the logging tests.
- [Uvicorn installs its own logging config when started] → When FastAPI arrives, start uvicorn with `log_config=None` so our root config stays in charge. Noted for that change.
