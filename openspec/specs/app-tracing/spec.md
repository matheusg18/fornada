# app-tracing Specification

## Purpose

Defines how the Fornada API produces traces and exports them to the OpenTelemetry Collector: what identifies the service, which work is traced automatically, and how tracing starts and stops with the app.

## Requirements

### Requirement: Tracing follows the telemetry switch
When tracing is enabled in settings, the API SHALL export traces from startup on. When it is disabled, the API SHALL export no spans and SHALL NOT open any connection to a Collector.

#### Scenario: Tracing enabled
- **WHEN** the API starts with tracing enabled and serves a request
- **THEN** the spans for that request are exported to the configured OTLP endpoint

#### Scenario: Tracing disabled
- **WHEN** the API starts with tracing disabled and serves a request
- **THEN** no span is exported and no connection to an OTLP endpoint is attempted

### Requirement: Spans identify the service
Every span the API exports SHALL carry the resource attribute `service.name` with the value `fornada-api`.

#### Scenario: Service name on exported spans
- **WHEN** the API exports any span
- **THEN** the span's resource has `service.name` = `fornada-api`

### Requirement: Spans are exported over OTLP to the Collector
The API SHALL export spans over OTLP/HTTP to the endpoint set in settings. It SHALL send them in batches, off the request path, so a slow or unreachable Collector does not delay or fail a request.

#### Scenario: Span reaches the Collector
- **WHEN** tracing is enabled with the dev Collector's endpoint and the API serves a request
- **THEN** the Collector's log shows the request's spans

#### Scenario: Collector unreachable
- **WHEN** tracing is enabled, the endpoint is unreachable and a customer posts a message
- **THEN** the request completes with the same response it would have without tracing

### Requirement: Only the configured exporter sends spans
The API SHALL export spans only through the pipeline built from its own settings. Standard `OTEL_*` environment variables SHALL NOT add a second exporter.

#### Scenario: OTEL endpoint variable present
- **WHEN** tracing is enabled and `OTEL_EXPORTER_OTLP_ENDPOINT` is also set in the environment
- **THEN** each span is exported once, to the endpoint from the API's settings

### Requirement: Incoming HTTP requests produce a server span
With tracing enabled, each HTTP request the API serves SHALL produce exactly one span of kind SERVER. It SHALL carry the HTTP method, the route template and the response status code.

#### Scenario: Customer message
- **WHEN** tracing is enabled and a client posts to `/conversations/{conversation_id}/messages`
- **THEN** one SERVER span is exported with method `POST`, route `/conversations/{conversation_id}/messages` and the response status code

#### Scenario: Route template, not the raw path
- **WHEN** two requests post to the messages endpoint with different conversation ids
- **THEN** both SERVER spans carry the same route template, and no span name contains a conversation id

### Requirement: Outgoing HTTP calls are traced in the request's trace
With tracing enabled, each outgoing HTTP request the API makes while serving a request, including the calls to the LLM provider, SHALL produce a span of kind CLIENT in the same trace, under that request's SERVER span.

#### Scenario: LLM call inside a conversation turn
- **WHEN** tracing is enabled and a posted customer message makes the agent call the LLM provider
- **THEN** the exported trace has a CLIENT span for that HTTP call, with the SERVER span of the message request as its ancestor

### Requirement: Buffered spans are flushed at shutdown
When the API shuts down, it SHALL export the spans still buffered before the process exits, and then stop the tracing pipeline.

#### Scenario: Request right before shutdown
- **WHEN** tracing is enabled, the API serves a request and is stopped right after
- **THEN** that request's spans reach the Collector

### Requirement: Requests continue the caller's trace
When an incoming request carries a valid W3C `traceparent` header, the API SHALL make its SERVER span a child of the span named in it, in the same trace, and SHALL record the request's spans when that parent is sampled. A request without the header SHALL start a new trace.

#### Scenario: Client sends traceparent
- **WHEN** a client posts a message with `traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`
- **THEN** the SERVER span has trace id `4bf92f3577b34da6a3ce929d0e0e4736` and parent span id `00f067aa0ba902b7`, and the agent spans of that turn share the trace id

#### Scenario: No traceparent
- **WHEN** a client posts a message without a `traceparent` header
- **THEN** the SERVER span is the root of a new trace

### Requirement: Tool database statements are traced
With tracing enabled, each SQL statement a tool runs SHALL produce one span of kind CLIENT in the turn's trace, under that tool's span. The span SHALL name the database system and the database, and SHALL carry the statement text.

#### Scenario: Catalog lookup inside a turn
- **WHEN** tracing is enabled and a posted customer message makes the agent call `search_catalog`
- **THEN** the exported trace has a CLIENT span for each statement the tool ran, with the `execute_tool search_catalog` span as its ancestor, `db.system.name` = `postgresql`, `db.namespace` = `fornada` and the statement in `db.query.text`

### Requirement: Conversation-state statements are traced
With tracing enabled, each SQL statement the API runs to load or save a conversation's state SHALL produce one span of kind CLIENT in the trace of the turn that needed it.

#### Scenario: Checkpoint read and write during a turn
- **WHEN** tracing is enabled and a customer posts a message to an existing conversation
- **THEN** the turn's trace has CLIENT spans for the statements that read the conversation's saved state and for those that save the new state, under the turn's SERVER span

### Requirement: Each database statement is traced once
A SQL statement SHALL produce exactly one database CLIENT span, whichever database path ran it.

#### Scenario: Tool statement not duplicated
- **WHEN** tracing is enabled and a tool runs one statement
- **THEN** the trace has one CLIENT span with that statement's text, not two

### Requirement: Database spans carry no bound values
Database spans SHALL carry the SQL text with its placeholders, and SHALL NOT carry the values bound to them, in any attribute.

#### Scenario: Order created with a customer's details
- **WHEN** tracing is enabled and `create_order` inserts a customer's name, phone and address
- **THEN** the INSERT's span shows placeholders where the values go, and no attribute of any database span contains that name, phone or address

### Requirement: Failed tool statements are marked without the server's detail
With tracing enabled, a tool statement that fails SHALL end its span with error status. The status description SHALL NOT contain the `DETAIL:` line PostgreSQL adds to the error, which holds the offending row values.

#### Scenario: Unique violation on insert
- **WHEN** tracing is enabled and a tool's INSERT fails with a unique violation
- **THEN** the statement's span has status ERROR, and its status description has no `DETAIL:` line and none of the inserted values

### Requirement: No database instrumentation when tracing is off
When tracing is disabled, the API SHALL NOT instrument either database path, and database statements SHALL run as they would without telemetry.

#### Scenario: Tracing disabled
- **WHEN** the API starts with tracing disabled and a customer posts a message that makes a tool query the database
- **THEN** no database span is created and the turn's response is the same as with tracing enabled
