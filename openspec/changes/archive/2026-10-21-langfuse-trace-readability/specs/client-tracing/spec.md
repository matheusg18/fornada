# Spec Delta

## ADDED Requirements

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

## REMOVED Requirements

### Requirement: Client spans carry no conversation content
**Reason**: Replaced by "Client spans carry no conversation content while capture is off" and "Client spans carry the turn's message and replies when capture is on". The trace root must carry the turn's conversation for Langfuse to show it as the trace's input and output.
**Migration**: Leave `TELEMETRY__CAPTURE_CONTENT` unset to keep client spans free of content. Elasticsearch never receives the content, through the Collector's redaction.
