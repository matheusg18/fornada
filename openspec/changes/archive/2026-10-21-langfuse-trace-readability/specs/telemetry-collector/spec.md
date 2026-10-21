# Spec Delta

## ADDED Requirements

### Requirement: Langfuse shows infrastructure spans at DEBUG level
Before export to Langfuse, the Collector SHALL set Langfuse's observation level to `DEBUG` on every span that has a parent, has no `gen_ai.operation.name` and does not have status ERROR. Other spans SHALL keep the level Langfuse assigns them (`DEFAULT`, or `ERROR` for a span with status ERROR). Spans exported to Elasticsearch SHALL NOT carry the level attribute.

#### Scenario: SQL span hidden by default
- **WHEN** a traced turn runs a tool that queries the database
- **THEN** in Langfuse the SQL span's level is `DEBUG`, and the tool span's level is `DEFAULT`

#### Scenario: Agent visible under the root
- **WHEN** a turn is traced from the chat through the API
- **THEN** Langfuse's trace tree at its default level shows the `invoke_agent` observation directly under the root, with the HTTP and FastAPI spans between them hidden

#### Scenario: Root kept visible
- **WHEN** a request posted with no `traceparent` starts its trace at the API's SERVER span
- **THEN** that root span keeps the `DEFAULT` level in Langfuse

#### Scenario: Failed infrastructure span stays visible
- **WHEN** a tool's SQL statement fails and its span has status ERROR
- **THEN** that span is not marked `DEBUG`: Langfuse shows it at `ERROR` level, in the default tree

#### Scenario: Elasticsearch unchanged
- **WHEN** the same trace is read in Elasticsearch
- **THEN** none of its spans carries the Langfuse level attribute

### Requirement: Langfuse names a turn's root span `turn`
Before export to Langfuse, the Collector SHALL rename to `turn` every root span whose URL template is `/conversations/{conversation_id}/messages`. Other spans and the spans exported to Elasticsearch SHALL keep their names.

#### Scenario: Chat turn in the trace list
- **WHEN** the chat posts a message with tracing on
- **THEN** Langfuse lists the trace with the name `turn`, and Elasticsearch stores the same root span as `POST /conversations/{conversation_id}/messages`

#### Scenario: Other traces keep their names
- **WHEN** the smoke test sends its synthetic traces
- **THEN** Langfuse shows their root spans with the names `telemetrygen` sent

## MODIFIED Requirements

### Requirement: Langfuse keeps the content
Redaction for Elasticsearch SHALL NOT change the spans exported to Langfuse. Langfuse SHALL receive the content attributes and `fornada.customer.phone` exactly as the app sent them. The Langfuse pipeline SHALL change only the observation level and the root span name, as its own requirements state.

#### Scenario: Same trace, two views
- **WHEN** content capture is on and a customer gives their phone in a turn that calls `get_order`
- **THEN** in Langfuse the trace's spans show the message text, the tool arguments and the phone in clear, and in Elasticsearch the same spans show neither the text nor the phone

#### Scenario: Root content reaches Langfuse only
- **WHEN** content capture is on in the simulator and it posts a message
- **THEN** in Langfuse the `turn` observation shows the message as input and the replies as output, and in Elasticsearch the same span has neither attribute
