# app-config Specification

## Purpose

Defines how the Fornada API loads, groups and validates its runtime settings from the environment, so every component reads one typed source of configuration.

## Requirements

### Requirement: Settings load from environment and root .env file
The API SHALL read its settings from process environment variables and from a `.env` file at the repository root. When both define the same key, the process environment SHALL win. A missing `.env` file SHALL NOT be an error.

#### Scenario: Value from .env file
- **WHEN** the root `.env` contains `LOG__LEVEL=DEBUG` and the environment does not define it
- **THEN** the loaded log level is `DEBUG`

#### Scenario: Environment overrides .env file
- **WHEN** the root `.env` contains `LOG__LEVEL=DEBUG` and the environment defines `LOG__LEVEL=WARNING`
- **THEN** the loaded log level is `WARNING`

#### Scenario: No .env file
- **WHEN** no root `.env` exists and every required value comes from the environment
- **THEN** settings load without error

### Requirement: Settings are grouped into namespaces
Settings SHALL be grouped into the namespaces `LLM`, `APP`, `LOG` and `DB`. A nested setting SHALL be addressed in the environment by joining namespace and field names with a double underscore (`__`), case-insensitively.

#### Scenario: Nested provider key
- **WHEN** the environment defines `LLM__ANTHROPIC__API_KEY=sk-ant-test`
- **THEN** the Anthropic API key in the `LLM` namespace is `sk-ant-test`

#### Scenario: Lowercase variable name
- **WHEN** the environment defines `app__timezone=UTC`
- **THEN** the application time zone is `UTC`

### Requirement: Active LLM provider is selectable
`LLM__PROVIDER` SHALL select the active LLM provider. Accepted values SHALL be `anthropic` and `openai`; the default SHALL be `anthropic`. Any other value SHALL make settings loading fail.

#### Scenario: Default provider
- **WHEN** `LLM__PROVIDER` is not set and an Anthropic API key is set
- **THEN** the active provider is `anthropic`

#### Scenario: Switch to OpenAI
- **WHEN** `LLM__PROVIDER=openai` and `LLM__OPENAI__API_KEY` is set
- **THEN** the active provider is `openai`

#### Scenario: Unknown provider
- **WHEN** `LLM__PROVIDER=gemini`
- **THEN** settings loading fails with an error that names `LLM__PROVIDER`

### Requirement: Per-provider connection settings
Each provider (`anthropic`, `openai`) SHALL have its own API key and model name under `LLM__<PROVIDER>__API_KEY` and `LLM__<PROVIDER>__MODEL`. Each model name SHALL have a default, so only the API key is needed to run.

#### Scenario: Model override
- **WHEN** `LLM__ANTHROPIC__MODEL=claude-sonnet-5-5` is set
- **THEN** the Anthropic model name is `claude-sonnet-5-5`

#### Scenario: Model default
- **WHEN** `LLM__OPENAI__MODEL` is not set
- **THEN** the OpenAI model name is the documented default

### Requirement: Active provider must have an API key
Settings loading SHALL fail when the active provider has no API key or an empty one. The inactive provider's API key SHALL be optional.

#### Scenario: Active provider without key
- **WHEN** `LLM__PROVIDER=anthropic` and `LLM__ANTHROPIC__API_KEY` is not set
- **THEN** settings loading fails with an error that names `LLM__ANTHROPIC__API_KEY`

#### Scenario: Inactive provider without key
- **WHEN** `LLM__PROVIDER=anthropic`, `LLM__ANTHROPIC__API_KEY` is set and no OpenAI key is set
- **THEN** settings load without error

### Requirement: API keys are never exposed in output
API keys and the database URL SHALL be held as secret values. Their text representation (string conversion, repr, settings dump, log lines) SHALL mask the value.

#### Scenario: Printing settings
- **WHEN** the loaded settings object is converted to a string or logged
- **THEN** the output does not contain the API key value

#### Scenario: Database password not printed
- **WHEN** `DB__URL` contains a password and the loaded settings object is converted to a string or logged
- **THEN** the output does not contain the password

### Requirement: Application time zone
`APP__TIMEZONE` SHALL set the time zone the application uses for "now" and for calendar dates. It SHALL accept an IANA time zone name and default to `America/Sao_Paulo`. An unknown name SHALL make settings loading fail.

#### Scenario: Default time zone
- **WHEN** `APP__TIMEZONE` is not set
- **THEN** the application time zone is `America/Sao_Paulo`

#### Scenario: Invalid time zone
- **WHEN** `APP__TIMEZONE=Mars/Olympus`
- **THEN** settings loading fails with an error that names `APP__TIMEZONE`

### Requirement: Log level setting
`LOG__LEVEL` SHALL set the minimum log level. It SHALL accept `DEBUG`, `INFO`, `WARNING`, `ERROR` and `CRITICAL`, case-insensitively, and default to `INFO`. Any other value SHALL make settings loading fail.

#### Scenario: Default log level
- **WHEN** `LOG__LEVEL` is not set
- **THEN** the log level is `INFO`

#### Scenario: Lowercase level
- **WHEN** `LOG__LEVEL=debug`
- **THEN** the log level is `DEBUG`

### Requirement: Database URL is required
`DB__URL` SHALL set the PostgreSQL connection URL the API uses. It SHALL be required; settings loading SHALL fail with an error that names `DB__URL` when it is missing, empty or not a PostgreSQL URL.

#### Scenario: Missing database URL
- **WHEN** `DB__URL` is not set
- **THEN** settings loading fails with an error that names `DB__URL`

#### Scenario: Not a PostgreSQL URL
- **WHEN** `DB__URL=mysql://user:pass@host/db`
- **THEN** settings loading fails with an error that names `DB__URL`

#### Scenario: Plain PostgreSQL URL
- **WHEN** `DB__URL=postgresql://fornada:secret@postgres:5432/fornada`
- **THEN** settings load without error

### Requirement: Settings template is committed
The repository SHALL contain a root `.env.example` that lists every setting with a placeholder or its default value and no real secret.

#### Scenario: Template covers every setting
- **WHEN** a setting is added to the application
- **THEN** `.env.example` lists it in the same change

### Requirement: Default daily capacity setting
`APP__DAILY_CAPACITY_KG` SHALL set the oven capacity in kg for dates without a capacity override. It SHALL accept a decimal number greater than zero and default to `15`. A value that is not a positive number SHALL make settings loading fail with an error that names `APP__DAILY_CAPACITY_KG`.

#### Scenario: Default capacity
- **WHEN** `APP__DAILY_CAPACITY_KG` is not set
- **THEN** the default daily capacity is exactly 15 kg

#### Scenario: Override
- **WHEN** `APP__DAILY_CAPACITY_KG=20.5`
- **THEN** the default daily capacity is exactly 20.5 kg

#### Scenario: Invalid capacity
- **WHEN** `APP__DAILY_CAPACITY_KG=0`
- **THEN** settings loading fails with an error that names `APP__DAILY_CAPACITY_KG`
