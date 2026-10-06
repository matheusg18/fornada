# Tasks

## 1. Setup

- [x] 1.1 Run `uv add --package fornada-api pydantic-settings python-json-logger` and `uv add --package fornada-api --dev pytest` from the repo root; verify `uv sync` succeeds and `uv.lock` lists all three
- [x] 1.2 Add `[tool.pytest.ini_options]` (`testpaths = ["apps/api/tests"]`) where pytest picks it up from the repo root, create `apps/api/src/fornada_api/core/__init__.py` and `apps/api/tests/core/`; verify `uv run --package fornada-api pytest` runs and collects zero tests without error

## 2. Settings (`app-config`)

- [x] 2.1 Implement `core/config.py`: `ProviderSettings`, `LlmSettings` (provider literal, per-provider key/model, `active` property, active-key validator), `AppSettings` (`timezone: ZoneInfo`), `LogSettings` (level, case-insensitive), root `Settings` with `__` delimiter, root `.env`, `extra="ignore"`, and cached `get_settings()`; verify `python -c` import works
- [x] 2.2 Set the model defaults to `claude-haiku-4-5` (Anthropic) and `gpt-5-mini` (OpenAI); verify a test asserts both defaults
- [x] 2.3 Write `tests/core/test_config.py` covering every `app-config` scenario (env vs `.env` precedence with a temp file, missing `.env`, nested and lowercase names, default and unknown provider, missing active key, missing inactive key, model override and default, masked secrets in `str`/`repr`/`model_dump`, default and invalid time zone, default and lowercase log level, invalid level); verify all pass
- [x] 2.4 Create the root `.env.example` with every setting (placeholder keys, default values, short comments); verify a test loads it as `_env_file` with placeholder keys and gets no validation error

## 3. Logging (`structured-logging`)

- [x] 3.1 Implement `core/logging.py`: `configure_logging(log_settings)` via `dictConfig` on the root logger to stdout, with `pythonjsonlogger.json.JsonFormatter` (`timestamp=True`, `rename_fields` to `level`/`logger`/`exception`, `json_ensure_ascii=False`); verify a manual log call prints one JSON line with those field names
- [x] 3.2 Write `tests/core/test_logging.py` covering every `structured-logging` scenario (one JSON line, library logger, standard fields with non-ASCII text, extras, extras that try to overwrite a standard field, `datetime`/`Decimal` extras, exception on one line, level filtering, idempotent setup) using `capsys`; verify all pass

## 4. Wiring

- [x] 4.1 Update `fornada_api.main()` to call `configure_logging(get_settings().log)` and log a startup line with provider and model; verify `uv run --package fornada-api fornada-api` with a placeholder key prints one JSON line without the key, and fails with a clear message naming `LLM__ANTHROPIC__API_KEY` when no key is set
- [x] 4.2 Add a short "Configuration" section to `apps/api/README.md` (where settings come from, the `__` namespaces, run from repo root, JSON logs); verify its commands run as written

## Workflow follow-up

- Commit with a Conventional Commits message (`feat: add core settings and JSON logging`).
- Archive the change with `/opsx:archive` after review.
