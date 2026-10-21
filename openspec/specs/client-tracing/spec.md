# client-tracing Specification

## Purpose

Defines how the clients that call the conversation API (the chat UI and the persona simulator) trace each posted message, so every turn's trace starts at the client and every conversation is one session of whole traces.

## Requirements

### Requirement: Client tracing follows the telemetry switch
The chat and the simulator SHALL export traces only when `TELEMETRY__ENABLED` is true, to the OTLP/HTTP base URL in `TELEMETRY__OTLP_ENDPOINT`. Tracing SHALL be off by default. When it is off, a client SHALL export no spans, open no connection to a Collector and send no `traceparent` header.

#### Scenario: Tracing disabled
- **WHEN** the simulator runs a conversation with `TELEMETRY__ENABLED` unset
- **THEN** no span is exported, no OTLP connection is attempted and the API receives no `traceparent` header

#### Scenario: Tracing enabled
- **WHEN** the chat runs with `TELEMETRY__ENABLED=true` and a person sends a message
- **THEN** the message's client span is exported to `{TELEMETRY__OTLP_ENDPOINT}/v1/traces`

### Requirement: Client spans identify their service
Every span the chat exports SHALL carry the resource attribute `service.name` = `fornada-chat`. Every span the simulator exports SHALL carry `service.name` = `fornada-simulator`.

#### Scenario: Simulator resource
- **WHEN** the simulator exports a span
- **THEN** its resource has `service.name` = `fornada-simulator`

#### Scenario: Chat resource
- **WHEN** the chat exports a span
- **THEN** its resource has `service.name` = `fornada-chat`

### Requirement: One client span per posted message
With tracing enabled, each customer message the chat or the simulator posts SHALL produce exactly one span of kind CLIENT. It SHALL have no parent and SHALL be named `POST /conversations/{conversation_id}/messages`, with the template and not the id. It SHALL carry the HTTP method and, when a response arrives, its status code.

#### Scenario: One message, one root
- **WHEN** the simulator posts one customer message
- **THEN** one CLIENT span named `POST /conversations/{conversation_id}/messages` is exported with no parent, method `POST` and status code 200

#### Scenario: Turns are separate traces
- **WHEN** a simulated conversation posts three messages
- **THEN** three client spans are exported, each with a different trace id

#### Scenario: Root even inside another span
- **WHEN** a client posts a message while another span is current in its process
- **THEN** the client span still has no parent and starts a new trace

### Requirement: The chat traces only its posts
With tracing enabled, the chat SHALL export only its client spans. Chainlit's own server work, such as the websocket connection and HTTP requests for the UI, SHALL NOT produce spans.

#### Scenario: Chat tab open
- **WHEN** a person opens the chat, sends two messages and closes the tab
- **THEN** the chat exports exactly two spans, both client spans, in two different traces

### Requirement: Clients propagate trace context to the API
With tracing enabled, each posted message SHALL carry a W3C `traceparent` header for its client span, so the API's spans for that turn join the client's trace.

#### Scenario: API joins the client's trace
- **WHEN** tracing is enabled in the simulator and in the API and the simulator posts a message
- **THEN** the API's SERVER span for that request has the client span as its parent, in the same trace

### Requirement: Client spans carry the conversation as a session
Each client span SHALL carry the conversation id as `session.id` and as `gen_ai.conversation.id`, so the trace's root belongs to the same Langfuse session as the agent's spans.

#### Scenario: Session on the root
- **WHEN** the chat posts a message in conversation `3f1c2a4e-8d0b-4c55-9a7e-2b6f0e1d9c11`
- **THEN** the client span has `session.id` and `gen_ai.conversation.id` equal to that id

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

### Requirement: Failed posts mark the client span as an error
When a post fails on connection or timeout, the API answers with a non-200 status, or a 200 body cannot be read as replies, the client span SHALL have status ERROR and `error.type` set to the failure kind, with no status description. A successful post SHALL leave the status UNSET.

#### Scenario: API returns 500
- **WHEN** the simulator posts a message and the API answers 500
- **THEN** the client span has status ERROR, status code 500 and `error.type` = `500`

#### Scenario: API unreachable
- **WHEN** the chat posts a message and the API cannot be reached
- **THEN** the client span has status ERROR and `error.type` names the transport failure

### Requirement: The persona's own model calls are not traced
The simulator SHALL NOT produce spans for the LLM calls that generate the persona's messages, so the cost of a session in Langfuse is the agent's cost only.

#### Scenario: Persona generation
- **WHEN** the simulator asks its model for the next customer message
- **THEN** no span is exported for that call

### Requirement: Clients flush spans before they stop
When a simulator batch ends, the simulator SHALL export all buffered spans before returning control, and at process exit it SHALL shut its tracing pipeline down. The chat SHALL shut its tracing pipeline down when it stops. No client span may be lost because the process exited first.

#### Scenario: Batch then exit
- **WHEN** the simulator command runs a batch with tracing enabled and exits right after it
- **THEN** every client span of the batch reaches the Collector

#### Scenario: Notebook run
- **WHEN** a notebook cell runs a batch and finishes
- **THEN** the batch's client spans have been exported before the cell returns

### Requirement: A batch produces one session per conversation with whole traces
With tracing enabled in the simulator, the API and the Collector, a batch of N conversations SHALL produce N Langfuse sessions, one per conversation id. Each trace in those sessions SHALL have exactly one root observation, the simulator's client span, and every other observation's parent SHALL be in the same trace.

#### Scenario: Default batch of 20
- **WHEN** a default batch (4 runs × 5 personas) runs with tracing enabled end to end
- **THEN** Langfuse has 20 sessions whose ids are the batch's conversation ids, and no trace in them has a missing root or a second root

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

### Requirement: Clients read the content-capture switch
The chat and the simulator SHALL read `TELEMETRY__CAPTURE_CONTENT`, the same switch the API reads. Capture SHALL be off by default, and it SHALL have no effect while tracing is off.

#### Scenario: Capture unset
- **WHEN** the simulator runs with `TELEMETRY__ENABLED=true` and `TELEMETRY__CAPTURE_CONTENT` unset
- **THEN** its client spans are exported without any conversation content

#### Scenario: Capture on, tracing off
- **WHEN** the chat runs with `TELEMETRY__CAPTURE_CONTENT=true` and `TELEMETRY__ENABLED` unset
- **THEN** no span is exported

### Requirement: Client spans carry no conversation content while capture is off
With content capture off, client spans SHALL NOT carry the customer's message text or the replies. Client spans SHALL NOT carry the persona's goal text, whatever the switch.

#### Scenario: Phone number in a message
- **WHEN** capture is off and the simulator posts a message containing a phone number
- **THEN** no attribute of the client span contains the message text or the phone number

#### Scenario: Persona goal never exported
- **WHEN** capture is on and the simulator posts a message for a persona with a goal
- **THEN** no attribute of the client span contains the goal text

### Requirement: Client spans carry the turn's message and replies when capture is on
With content capture on, each client span SHALL carry `gen_ai.input.messages` with the customer message it posted, as one `user` message, and, when replies arrive, `gen_ai.output.messages` with them as `assistant` messages in order. Both SHALL use the GenAI semconv JSON message shape the API's turn spans use.

#### Scenario: One message, two replies
- **WHEN** capture is on, the chat posts "Oi" and the API returns two replies
- **THEN** the client span's `gen_ai.input.messages` holds one user message "Oi", and its `gen_ai.output.messages` holds the two replies in order

#### Scenario: Failed post keeps the input only
- **WHEN** capture is on and the simulator's post times out
- **THEN** the client span carries `gen_ai.input.messages` with the message and no `gen_ai.output.messages`

#### Scenario: Accents are kept
- **WHEN** capture is on and the customer writes "Olá, é possível?"
- **THEN** `gen_ai.input.messages` holds that text as written, not as `\u` escapes
