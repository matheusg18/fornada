# Spec Delta

## MODIFIED Requirements

### Requirement: Tracing switch setting
`TELEMETRY__ENABLED` SHALL turn tracing, log export and metric export on or off together. It SHALL accept boolean values and default to off, so the API needs no Collector unless telemetry is turned on.

#### Scenario: Default off
- **WHEN** `TELEMETRY__ENABLED` is not set
- **THEN** tracing, log export and metric export are disabled

#### Scenario: Turned on
- **WHEN** `TELEMETRY__ENABLED=true`
- **THEN** tracing, log export and metric export are enabled

#### Scenario: Not a boolean
- **WHEN** `TELEMETRY__ENABLED=maybe`
- **THEN** settings loading fails with an error that names `TELEMETRY__ENABLED`

## ADDED Requirements

### Requirement: Token price settings
Each provider SHALL have an input and an output token price in US dollars per million tokens, under `LLM__<PROVIDER>__INPUT_USD_PER_MTOK` and `LLM__<PROVIDER>__OUTPUT_USD_PER_MTOK`. Each SHALL default to the provider's published price for that provider's default model. A negative price SHALL make settings loading fail.

#### Scenario: Price override
- **WHEN** `LLM__ANTHROPIC__INPUT_USD_PER_MTOK=3` is set
- **THEN** the Anthropic input price is US$ 3.00 per million tokens

#### Scenario: Price default
- **WHEN** no price variable is set
- **THEN** each provider's prices are the documented defaults for its default model

#### Scenario: Negative price
- **WHEN** `LLM__OPENAI__OUTPUT_USD_PER_MTOK=-1` is set
- **THEN** settings loading fails with an error that names `LLM__OPENAI__OUTPUT_USD_PER_MTOK`

#### Scenario: Model changed without prices
- **WHEN** `LLM__ANTHROPIC__MODEL` is set to a model other than the default and no price variable is set
- **THEN** settings load, and the API logs a WARNING at startup that the cost metric uses the default model's prices
