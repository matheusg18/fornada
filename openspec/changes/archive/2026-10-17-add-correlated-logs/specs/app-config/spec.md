# Spec Delta

## MODIFIED Requirements

### Requirement: Tracing switch setting
`TELEMETRY__ENABLED` SHALL turn tracing and log export on or off together. It SHALL accept boolean values and default to off, so the API needs no Collector unless telemetry is turned on.

#### Scenario: Default off
- **WHEN** `TELEMETRY__ENABLED` is not set
- **THEN** tracing and log export are disabled

#### Scenario: Turned on
- **WHEN** `TELEMETRY__ENABLED=true`
- **THEN** tracing and log export are enabled

#### Scenario: Not a boolean
- **WHEN** `TELEMETRY__ENABLED=maybe`
- **THEN** settings loading fails with an error that names `TELEMETRY__ENABLED`
