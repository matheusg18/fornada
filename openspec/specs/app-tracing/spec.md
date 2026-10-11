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
