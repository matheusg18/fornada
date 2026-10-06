# structured-logging Specification

## Purpose

Defines the log output of the Fornada API process: one structured JSON object per line, built on the standard logging facility, so logs can be parsed and later correlated with traces.

## Requirements

### Requirement: Logs are JSON lines on stdout
Once logging is configured, every log record emitted through the standard logging facility, by application code or by libraries, SHALL be written to standard output as exactly one line holding one JSON object.

#### Scenario: Application log line
- **WHEN** application code logs `"pedido criado"` at INFO
- **THEN** stdout receives one line that parses as a JSON object

#### Scenario: Library log line
- **WHEN** a third-party library logs through the standard logging facility
- **THEN** its record is also written as one JSON line on stdout

### Requirement: Standard fields in every record
Every JSON log record SHALL contain `timestamp` (ISO 8601 in UTC with offset), `level` (level name), `logger` (logger name) and `message` (the formatted message). Non-ASCII text SHALL be kept as is, not escaped.

#### Scenario: Fields present
- **WHEN** logger `fornada_api.tools` logs `"bolo de maçã"` at WARNING
- **THEN** the record has `level` = `WARNING`, `logger` = `fornada_api.tools`, `message` = `"bolo de maçã"` and a UTC `timestamp`

### Requirement: Extra context becomes top-level fields
Values passed as extra context on a log call SHALL appear as top-level fields of the JSON record. Values that are not JSON-serializable SHALL be written as their string form instead of failing the log call. Extra keys SHALL NOT replace the standard fields.

#### Scenario: Extra field
- **WHEN** code logs `"quote"` with extra `{"order_id": 482, "total": "120.00"}`
- **THEN** the record has `order_id` = `482` and `total` = `"120.00"`

#### Scenario: Non-serializable value
- **WHEN** an extra value is a `datetime` or `Decimal`
- **THEN** the record holds its string form and the log call does not raise

### Requirement: Exceptions are serialized
A record logged with exception information SHALL include an `exception` field with the formatted traceback as a single JSON string.

#### Scenario: Logging an exception
- **WHEN** code calls the exception-logging method inside an `except` block
- **THEN** the record has an `exception` field with the traceback, and the output is still one line

### Requirement: Level comes from settings
Logging setup SHALL use the log level from application settings (`LOG__LEVEL`). Records below that level SHALL NOT be written.

#### Scenario: Records below level
- **WHEN** the level is `WARNING` and code logs at INFO
- **THEN** nothing is written

### Requirement: Setup is idempotent
Configuring logging more than once in the same process SHALL NOT duplicate output.

#### Scenario: Configured twice
- **WHEN** logging setup runs twice and code logs one message
- **THEN** stdout receives exactly one line
