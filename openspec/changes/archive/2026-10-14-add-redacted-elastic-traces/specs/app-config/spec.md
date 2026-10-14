# Spec Delta

## ADDED Requirements

### Requirement: Content capture setting
`TELEMETRY__CAPTURE_CONTENT` SHALL turn the capture of conversation content and customer phones on agent spans on or off. It SHALL accept boolean values and default to off. It SHALL have no effect while tracing is disabled.

#### Scenario: Default off
- **WHEN** `TELEMETRY__CAPTURE_CONTENT` is not set
- **THEN** content capture is off

#### Scenario: Turned on
- **WHEN** `TELEMETRY__ENABLED=true` and `TELEMETRY__CAPTURE_CONTENT=true`
- **THEN** content capture is on

#### Scenario: Not a boolean
- **WHEN** `TELEMETRY__CAPTURE_CONTENT=maybe`
- **THEN** settings loading fails with an error that names `TELEMETRY__CAPTURE_CONTENT`

#### Scenario: Tracing off
- **WHEN** `TELEMETRY__ENABLED=false` and `TELEMETRY__CAPTURE_CONTENT=true`
- **THEN** no span is exported
