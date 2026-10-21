# Spec Delta

## MODIFIED Requirements

### Requirement: Simulator spans name the persona and batch
Each simulator client span SHALL carry the persona's identifier as `fornada.simulator.persona.id` and the batch run id as `fornada.simulator.run.id`. A client span of a matrix conversation SHALL also carry the cell's intent as `fornada.simulator.intent.id` and its complication as `fornada.simulator.complication.id`; a persona batch span SHALL carry neither. These attributes SHALL stay on the client span: the API SHALL put none of them on any span it exports, and SHALL NOT read the run id, the intent or the complication from the request.

#### Scenario: Persona on the client span
- **WHEN** the simulator plays persona `apressada` in run `20261012T120000-ab12`
- **THEN** every client span of that conversation has `fornada.simulator.persona.id` = `apressada` and `fornada.simulator.run.id` = `20261012T120000-ab12`

#### Scenario: Persona stays at the client
- **WHEN** the simulator posts a message for persona `apressada`
- **THEN** no span exported by the API carries `fornada.simulator.persona.id`

#### Scenario: Cell on the client span
- **WHEN** the simulator plays matrix cell (`indecisa`, `entrega`, `troca_sabor`)
- **THEN** every client span of that conversation has `fornada.simulator.intent.id` = `entrega` and `fornada.simulator.complication.id` = `troca_sabor`

#### Scenario: Cell stays at the client
- **WHEN** the simulator posts a message for a matrix cell
- **THEN** no span exported by the API carries `fornada.simulator.intent.id` or `fornada.simulator.complication.id`, and the request's `baggage` header carries only the persona
