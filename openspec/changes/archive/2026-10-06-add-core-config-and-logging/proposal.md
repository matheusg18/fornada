# Proposal

## Why

`fornada-api` is still a "hello world" package. Every piece that comes next in phase 1 (LangGraph agent, tools, FastAPI, seed) needs one typed place to read settings from the environment, a way to switch the LLM provider without touching code, a single time zone for date rules such as the 48h lead time, and logs that machines can parse. Setting these up first keeps later changes from reading `os.environ` ad hoc or using `print`.

This change belongs to **phase 1 (naive foundation)**. It is periphery plumbing, not a defense: it adds no tool, feature or guardrail and stays within the frozen scope.

## What Changes

- New `core` package in `apps/api/src/fornada_api/core/`.
- `core/config.py`: application settings built on `pydantic-settings`, read from the environment and the root `.env`, grouped into namespaces with the `__` nested delimiter:
  - `LLM__PROVIDER` selects the active provider (`anthropic` or `openai`).
  - `LLM__ANTHROPIC__API_KEY` / `LLM__ANTHROPIC__MODEL` and `LLM__OPENAI__API_KEY` / `LLM__OPENAI__MODEL` hold the connection settings LangChain will use for each provider.
  - `APP__TIMEZONE` sets the application clock's time zone (default `America/Sao_Paulo`).
  - `LOG__LEVEL` sets the log level.
  - Startup fails fast with a clear error when the active provider has no API key or a value is invalid.
- `core/logging.py`: setup for the standard library `logging` module that writes one JSON object per line to stdout, using `python-json-logger` as the formatter.
- Root `.env.example`, the template for the application's own settings (AGENTS.md says it arrives with the first app setting).
- `pydantic-settings` and `python-json-logger` as runtime dependencies and `pytest` as a dev dependency of `fornada-api`, plus unit tests for both modules.

Not in this change: building LangChain chat model objects (that comes with the agent), OpenTelemetry trace/span ids in log records (phase 2), and a frozen or injectable clock for tests (phase 4, if a failure calls for it).

## Capabilities

### New Capabilities
- `app-config`: how the API loads, groups and validates its runtime settings (LLM provider selection and credentials, application time zone, log level).
- `structured-logging`: the log output format and setup for the API process.

### Modified Capabilities

None. `openspec/specs/` is empty.

## Impact

- **Code:** new `apps/api/src/fornada_api/core/` (`__init__.py`, `config.py`, `logging.py`); `fornada_api.main()` configures logging at startup. New `apps/api/tests/`.
- **Dependencies:** `pydantic-settings` and `python-json-logger` (runtime), `pytest` (dev) for `fornada-api`, added with `uv add`.
- **Files:** new root `.env.example`. The root `.env` is already gitignored.
- **Dev environment:** none. `.devcontainer/.env` and `compose.yaml` stay unchanged; application settings live only in the root `.env`.
