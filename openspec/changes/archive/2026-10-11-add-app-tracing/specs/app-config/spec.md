# Spec Delta

## MODIFIED Requirements

### Requirement: Settings are grouped into namespaces
Settings SHALL be grouped into the namespaces `LLM`, `APP`, `LOG`, `DB` and `TELEMETRY`. A nested setting SHALL be addressed in the environment by joining namespace and field names with a double underscore (`__`), case-insensitively.

#### Scenario: Nested provider key
- **WHEN** the environment defines `LLM__ANTHROPIC__API_KEY=sk-ant-test`
- **THEN** the Anthropic API key in the `LLM` namespace is `sk-ant-test`

#### Scenario: Lowercase variable name
- **WHEN** the environment defines `app__timezone=UTC`
- **THEN** the application time zone is `UTC`

#### Scenario: Telemetry namespace
- **WHEN** the environment defines `TELEMETRY__ENABLED=true`
- **THEN** tracing is enabled in the `TELEMETRY` namespace

## ADDED Requirements

### Requirement: Tracing switch setting
`TELEMETRY__ENABLED` SHALL turn tracing on or off. It SHALL accept boolean values and default to off, so the API needs no Collector unless tracing is turned on.

#### Scenario: Default off
- **WHEN** `TELEMETRY__ENABLED` is not set
- **THEN** tracing is disabled

#### Scenario: Turned on
- **WHEN** `TELEMETRY__ENABLED=true`
- **THEN** tracing is enabled

#### Scenario: Not a boolean
- **WHEN** `TELEMETRY__ENABLED=maybe`
- **THEN** settings loading fails with an error that names `TELEMETRY__ENABLED`

### Requirement: OTLP endpoint setting
`TELEMETRY__OTLP_ENDPOINT` SHALL set the base URL of the Collector's OTLP/HTTP receiver. The signal path is added by the API. It SHALL default to the dev Collector, `http://edot-collector:4318`. A value that is not an `http` or `https` URL SHALL make settings loading fail.

#### Scenario: Default endpoint
- **WHEN** `TELEMETRY__OTLP_ENDPOINT` is not set
- **THEN** the OTLP endpoint is `http://edot-collector:4318`

#### Scenario: Override
- **WHEN** `TELEMETRY__OTLP_ENDPOINT=http://localhost:4318`
- **THEN** the OTLP endpoint is `http://localhost:4318`

#### Scenario: Invalid endpoint
- **WHEN** `TELEMETRY__OTLP_ENDPOINT=edot-collector:4317`
- **THEN** settings loading fails with an error that names `TELEMETRY__OTLP_ENDPOINT`
