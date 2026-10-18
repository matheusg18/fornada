# app-metrics Specification

## Purpose

Defines the API's metrics: when they are exported, which instruments exist with their units and buckets, which dimensions they may carry, how model spend is priced, and how the persona reaches them, so Kibana can show cost per conversation, latency percentiles and tool error rates.

## Requirements

### Requirement: Metrics follow the telemetry switch
The API SHALL export metrics only when `TELEMETRY__ENABLED` is true, to `{TELEMETRY__OTLP_ENDPOINT}/v1/metrics`. With it off, the API SHALL record nothing that is exported and SHALL open no connection to a Collector.

#### Scenario: Telemetry off
- **WHEN** the API serves a turn with `TELEMETRY__ENABLED` unset
- **THEN** no metric is exported and no OTLP connection is attempted

#### Scenario: Telemetry on
- **WHEN** the API serves a turn with `TELEMETRY__ENABLED=true`
- **THEN** its metrics are exported to `{TELEMETRY__OTLP_ENDPOINT}/v1/metrics` within one export interval

### Requirement: Metrics identify the service
Every metric the API exports SHALL carry the resource attribute `service.name` = `fornada-api`, the same resource as its traces and logs.

#### Scenario: Metric resource
- **WHEN** the API exports a metric
- **THEN** its resource has `service.name` = `fornada-api`

### Requirement: Only the configured exporter sends metrics
The API SHALL export metrics only through the exporter built from `TELEMETRY__OTLP_ENDPOINT`. `OTEL_EXPORTER_OTLP_*` variables SHALL NOT redirect them or add a second exporter.

#### Scenario: OTEL variables ignored
- **WHEN** `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://elsewhere:4318/v1/metrics` is set
- **THEN** metrics still go to `{TELEMETRY__OTLP_ENDPOINT}/v1/metrics` and nowhere else

### Requirement: Metrics are exported with delta temporality
Every counter and histogram the API exports SHALL use delta aggregation temporality, so Elasticsearch stores the histograms instead of dropping them.

#### Scenario: Delta histogram
- **WHEN** the API exports `gen_ai.invoke_agent.duration`
- **THEN** its data points have delta aggregation temporality

#### Scenario: Delta counter
- **WHEN** the API exports `fornada.tool.calls`
- **THEN** its data points have delta aggregation temporality

### Requirement: Buffered metrics are flushed at shutdown
When the API stops, it SHALL export the measurements recorded since the last export before the process exits.

#### Scenario: Turn just before shutdown
- **WHEN** a turn completes and the API is stopped before the next export interval
- **THEN** that turn's measurements are exported before the process exits

### Requirement: Model call duration
Each model call SHALL record its duration in seconds in the histogram `gen_ai.client.inference.duration`, including failed calls, with the semconv bucket boundaries `[0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92]`.

#### Scenario: Successful call
- **WHEN** the agent calls the model once in a turn
- **THEN** `gen_ai.client.inference.duration` gets one measurement, equal to that `chat` span's duration within 10 ms, with `gen_ai.operation.name` = `chat`, `gen_ai.provider.name` and `gen_ai.request.model`

#### Scenario: Failed call
- **WHEN** the model call raises `APITimeoutError`
- **THEN** `gen_ai.client.inference.duration` gets one measurement with `error.type` = `APITimeoutError`

### Requirement: Model call token usage
Each model call that returns usage SHALL record its input tokens in the histogram `gen_ai.client.inference.operation.input_tokens` and its output tokens in `gen_ai.client.inference.operation.output_tokens`, with the semconv bucket boundaries `[1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864]`. A failed call SHALL record 0 on both.

#### Scenario: Usage recorded
- **WHEN** a model call returns 1200 input tokens and 80 output tokens
- **THEN** the input histogram gets 1200 and the output histogram gets 80, each with `gen_ai.operation.name`, `gen_ai.provider.name` and `gen_ai.request.model`

#### Scenario: Failed call
- **WHEN** a model call fails before a response arrives
- **THEN** both token histograms get 0, with `error.type` set

### Requirement: Turn duration
Each turn SHALL record its end-to-end duration in seconds in the histogram `gen_ai.invoke_agent.duration`, including failed turns, with the same bucket boundaries as the model call duration.

#### Scenario: Turn recorded
- **WHEN** the API answers one customer message
- **THEN** `gen_ai.invoke_agent.duration` gets one measurement, equal to the `invoke_agent` span's duration within 10 ms, with `gen_ai.operation.name` = `invoke_agent`, `gen_ai.agent.name` = `fornada-attendant` and `gen_ai.request.model`

#### Scenario: Failed turn
- **WHEN** a turn fails with `GraphRecursionError`
- **THEN** `gen_ai.invoke_agent.duration` gets one measurement with `error.type` = `GraphRecursionError`

### Requirement: Tool call duration
Each tool call SHALL record its duration in seconds in the histogram `gen_ai.execute_tool.duration`, with the same bucket boundaries as the model call duration, `gen_ai.tool.name`, `gen_ai.tool.type` and `gen_ai.agent.name`, and `error.type` when the call failed.

#### Scenario: Tool call recorded
- **WHEN** the agent calls `check_capacity` once
- **THEN** `gen_ai.execute_tool.duration` gets one measurement with `gen_ai.tool.name` = `check_capacity`, equal to the `execute_tool` span's duration within 10 ms

### Requirement: Tool calls are counted with their outcome
Each tool call SHALL add 1 to the counter `fornada.tool.calls`, with `gen_ai.tool.name`. A call whose `execute_tool` span is marked as an error SHALL also carry the same `error.type` as that span; a successful call SHALL carry no `error.type`.

#### Scenario: Tool error counted
- **WHEN** chaos mode makes `check_capacity` fail
- **THEN** `fornada.tool.calls` grows by 1 with `gen_ai.tool.name` = `check_capacity` and `error.type` = `tool_error`

#### Scenario: Full day is not an error
- **WHEN** `check_capacity` answers that the date is full
- **THEN** `fornada.tool.calls` grows by 1 with `gen_ai.tool.name` = `check_capacity` and no `error.type`

#### Scenario: Error rate per tool
- **WHEN** a batch makes 20 `check_capacity` calls and 2 of them fail
- **THEN** the sum of `fornada.tool.calls` with `error.type` divided by the sum of all `fornada.tool.calls`, for `check_capacity`, is 0.1

### Requirement: Model spend is counted in US dollars
Each model call that returns usage SHALL add its cost to the counter `fornada.gen_ai.cost`, in US dollars: input tokens times the active provider's input price plus output tokens times its output price, each price per million tokens. It SHALL carry `gen_ai.provider.name` and `gen_ai.request.model`.

#### Scenario: Cost of one call
- **WHEN** input costs US$ 1.00 and output US$ 5.00 per million tokens, and a call uses 1200 input and 80 output tokens
- **THEN** `fornada.gen_ai.cost` grows by 0.0016

#### Scenario: No usage, no cost
- **WHEN** a model call fails before a response arrives
- **THEN** `fornada.gen_ai.cost` does not change

### Requirement: Started conversations are counted
The API SHALL add 1 to the counter `fornada.conversations` when a conversation's first turn completes, and never again for that conversation. Cost per conversation is `sum(fornada.gen_ai.cost) / sum(fornada.conversations)` over a time range.

#### Scenario: Three turns, one conversation
- **WHEN** a conversation completes three turns
- **THEN** `fornada.conversations` grew by exactly 1

#### Scenario: First turn failed
- **WHEN** a conversation's first message fails and the customer sends it again successfully
- **THEN** `fornada.conversations` grows by 1, on the successful turn

### Requirement: Metrics carry only low-cardinality dimensions
A metric data point SHALL carry only these attributes: `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.agent.name`, `gen_ai.tool.name`, `gen_ai.tool.type`, `error.type` and `fornada.simulator.persona.id`. It SHALL NOT carry a conversation or session id, a call or response id, a phone, a prompt or any message content.

#### Scenario: No conversation id
- **WHEN** two conversations each complete a turn with the same model and persona
- **THEN** their `gen_ai.invoke_agent.duration` measurements fall in the same series

#### Scenario: No content with capture on
- **WHEN** `TELEMETRY__CAPTURE_CONTENT=true` and a tool is called with a phone
- **THEN** no exported data point has an attribute outside the allowed list

### Requirement: Persona dimension from baggage
Every measurement the API records SHALL carry `fornada.simulator.persona.id`, read from the W3C Baggage of the request: one of `apressada`, `indecisa`, `pechincheira`, `mae_alergica` or `malandro` when the baggage holds that value, `other` for any other value, and `none` when the request has no such baggage entry.

#### Scenario: Known persona
- **WHEN** the simulator posts a message for persona `pechincheira`
- **THEN** that turn's measurements carry `fornada.simulator.persona.id` = `pechincheira`

#### Scenario: Unknown value
- **WHEN** a request carries the baggage entry `fornada.simulator.persona.id=x7f3a9`
- **THEN** that turn's measurements carry `fornada.simulator.persona.id` = `other`

#### Scenario: Chat traffic
- **WHEN** the chat posts a message, with no baggage
- **THEN** that turn's measurements carry `fornada.simulator.persona.id` = `none`

### Requirement: Baggage stops at the API
The API SHALL NOT forward the baggage it receives on any outgoing request, including calls to the model provider, and SHALL NOT copy baggage entries onto its spans or logs.

#### Scenario: Provider call without baggage
- **WHEN** a request with baggage `fornada.simulator.persona.id=apressada` makes the agent call the model
- **THEN** the HTTP request to the model provider has no `baggage` header

#### Scenario: Span without persona
- **WHEN** the simulator posts a message for persona `apressada`
- **THEN** no span exported by the API carries `fornada.simulator.persona.id`

### Requirement: Metrics do not change the turn
Recording metrics SHALL NOT change the replies, the tool calls or the saved conversation. A failure to record or export a metric SHALL NOT fail the turn.

#### Scenario: Collector down
- **WHEN** telemetry is on, the Collector is unreachable, and a customer sends a message
- **THEN** the API answers with the same replies as with telemetry off
