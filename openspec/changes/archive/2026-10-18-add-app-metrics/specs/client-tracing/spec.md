# Spec Delta

## MODIFIED Requirements

### Requirement: Simulator spans name the persona and batch
Each simulator client span SHALL carry the persona's identifier as `fornada.simulator.persona.id` and the batch run id as `fornada.simulator.run.id`. These attributes SHALL stay on the client span: the API SHALL put neither on any span it exports, and SHALL NOT read the run id from the request.

#### Scenario: Persona on the client span
- **WHEN** the simulator plays persona `apressada` in run `20261012T120000-ab12`
- **THEN** every client span of that conversation has `fornada.simulator.persona.id` = `apressada` and `fornada.simulator.run.id` = `20261012T120000-ab12`

#### Scenario: Persona stays at the client
- **WHEN** the simulator posts a message for persona `apressada`
- **THEN** no span exported by the API carries `fornada.simulator.persona.id`

## ADDED Requirements

### Requirement: The simulator propagates the persona in baggage
With tracing enabled, each message the simulator posts SHALL carry a W3C `baggage` header with the entry `fornada.simulator.persona.id` set to the persona's identifier, and no other entry. The chat SHALL send no `baggage` header. With tracing disabled, no client SHALL send a `baggage` header.

#### Scenario: Persona in baggage
- **WHEN** tracing is enabled and the simulator posts a message for persona `mae_alergica`
- **THEN** the request has a `baggage` header whose only entry is `fornada.simulator.persona.id=mae_alergica`

#### Scenario: No run id in baggage
- **WHEN** the simulator posts a message in run `20261012T120000-ab12`
- **THEN** the `baggage` header does not contain the run id

#### Scenario: Chat sends no baggage
- **WHEN** tracing is enabled and the chat posts a message
- **THEN** the request has no `baggage` header

#### Scenario: Tracing off
- **WHEN** the simulator runs with `TELEMETRY__ENABLED` unset
- **THEN** the API receives no `baggage` header
