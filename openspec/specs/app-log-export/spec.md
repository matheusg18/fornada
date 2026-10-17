# app-log-export Specification

## Purpose
Defines how the Fornada API exports its log records to the OpenTelemetry Collector, alongside its traces, so that any log written during a request can be joined with the trace of that request.

## Requirements

### Requirement: Log export follows the telemetry switch
When telemetry is enabled in settings, the API SHALL export its log records over OTLP from startup on. When it is disabled, the API SHALL export no log record and SHALL NOT open any connection to a Collector. In both cases the stdout JSON output SHALL be unchanged.

#### Scenario: Telemetry enabled
- **WHEN** the API starts with telemetry enabled and code logs `"turn failed"` at ERROR
- **THEN** that record is exported to the configured OTLP endpoint and is also written to stdout as one JSON line

#### Scenario: Telemetry disabled
- **WHEN** the API starts with telemetry disabled and code logs a record
- **THEN** the record is written to stdout only, and no connection to an OTLP endpoint is attempted

### Requirement: Exported records keep level, logger and context
Each exported record SHALL carry the formatted message as its body, its severity, the logger name, and the extra context passed on the log call as attributes. A record logged with exception information SHALL carry the exception type, message and stack trace.

#### Scenario: Extra context
- **WHEN** logger `fornada_api.conversations` logs `"turn failed"` at ERROR with extra `{"conversation_id": "c0ffee00-0000-4000-8000-000000000000"}` inside an `except` block
- **THEN** the exported record has body `turn failed`, severity ERROR, logger name `fornada_api.conversations`, attribute `conversation_id` with that value, and the exception type and stack trace

### Requirement: Exported records are filtered by the configured level
The API SHALL export only records at or above the log level from settings (`LOG__LEVEL`), the same records it writes to stdout.

#### Scenario: Below level
- **WHEN** the level is `WARNING`, telemetry is enabled and code logs at INFO
- **THEN** nothing is exported and nothing is written to stdout

### Requirement: Records identify the service
Every log record the API exports SHALL carry the resource attribute `service.name` with the value `fornada-api`, the same value as its spans.

#### Scenario: Service name on exported records
- **WHEN** the API exports any log record
- **THEN** the record's resource has `service.name` = `fornada-api`

### Requirement: Records written inside a span carry its trace context
A record logged while a span is active SHALL carry that span's trace id and span id. A record logged with no active span SHALL carry no trace id.

#### Scenario: Tool failure inside a turn
- **WHEN** telemetry is enabled, a customer message is posted and a tool fails and logs `"tool failed"`
- **THEN** the exported record's trace id equals the trace id of that request's SERVER span, and its span id is the id of a span in that trace

#### Scenario: Caller's trace
- **WHEN** a client posts a message with a valid `traceparent` and the turn fails
- **THEN** the exported `"turn failed"` record carries the trace id from the `traceparent`

#### Scenario: Startup log
- **WHEN** the API logs `"fornada-api starting"` during startup, outside any request
- **THEN** the exported record has no trace id

### Requirement: Log export runs off the request path
The API SHALL export log records in batches, off the request path, so a slow or unreachable Collector does not delay or fail a request.

#### Scenario: Collector unreachable
- **WHEN** telemetry is enabled, the endpoint is unreachable and a customer posts a message
- **THEN** the request completes with the same response it would have without telemetry

### Requirement: Telemetry SDK records stay local
Records from the telemetry SDK's own loggers SHALL be written to stdout and SHALL NOT be exported, so a failing export cannot produce more records to export.

#### Scenario: Export failure while the Collector is down
- **WHEN** telemetry is enabled, the Collector is unreachable and the SDK logs that an export failed
- **THEN** that record appears on stdout and is not queued for export

### Requirement: Only the configured exporter sends logs
The API SHALL export log records only through the pipeline built from its own settings. Standard `OTEL_*` environment variables SHALL NOT add a second log exporter or handler.

#### Scenario: OTEL logs variables present
- **WHEN** telemetry is enabled and `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` are set in the environment
- **THEN** each record is exported once, to the endpoint from the API's settings

### Requirement: Logging setup stays idempotent with export on
Configuring logging more than once in the same process with telemetry enabled SHALL NOT duplicate stdout lines or exported records.

#### Scenario: Configured twice
- **WHEN** logging setup runs twice with log export on and code logs one message
- **THEN** stdout receives exactly one line and exactly one record is exported

### Requirement: Buffered records are flushed at shutdown
When the API shuts down, it SHALL export the log records still buffered, including those written while shutting down, before the process exits, and then stop the log pipeline.

#### Scenario: Error right before shutdown
- **WHEN** telemetry is enabled, a turn fails and the API is stopped right after
- **THEN** the `"turn failed"` record reaches the Collector
