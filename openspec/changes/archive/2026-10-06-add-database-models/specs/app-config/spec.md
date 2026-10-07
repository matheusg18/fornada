# Spec Delta

## MODIFIED Requirements

### Requirement: Settings are grouped into namespaces
Settings SHALL be grouped into the namespaces `LLM`, `APP`, `LOG` and `DB`. A nested setting SHALL be addressed in the environment by joining namespace and field names with a double underscore (`__`), case-insensitively.

#### Scenario: Nested provider key
- **WHEN** the environment defines `LLM__ANTHROPIC__API_KEY=sk-ant-test`
- **THEN** the Anthropic API key in the `LLM` namespace is `sk-ant-test`

#### Scenario: Lowercase variable name
- **WHEN** the environment defines `app__timezone=UTC`
- **THEN** the application time zone is `UTC`

### Requirement: API keys are never exposed in output
API keys and the database URL SHALL be held as secret values. Their text representation (string conversion, repr, settings dump, log lines) SHALL mask the value.

#### Scenario: Printing settings
- **WHEN** the loaded settings object is converted to a string or logged
- **THEN** the output does not contain the API key value

#### Scenario: Database password not printed
- **WHEN** `DB__URL` contains a password and the loaded settings object is converted to a string or logged
- **THEN** the output does not contain the password

## ADDED Requirements

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
