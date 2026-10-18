# Spec Delta

## ADDED Requirements

### Requirement: Metrics are exported to Elasticsearch
The Collector SHALL export every metric it receives over OTLP to the dev environment's Elasticsearch, over the compose network, keeping delta histograms as histograms Kibana can compute percentiles on. Metrics SHALL NOT be exported to Langfuse.

#### Scenario: App metrics in Elasticsearch
- **WHEN** telemetry is enabled in the API and a customer message is posted
- **THEN** within one export interval Elasticsearch stores `gen_ai.invoke_agent.duration` and `fornada.tool.calls` data points under the service `fornada-api`

#### Scenario: Histogram kept
- **WHEN** the API exports a delta `gen_ai.invoke_agent.duration` histogram
- **THEN** the Collector log has no "dropping cumulative temporality histogram" warning, and Kibana computes its 95th percentile

### Requirement: Metric data points carry only allowed attributes in Elasticsearch
Before export to Elasticsearch, the Collector SHALL delete every metric data point attribute other than `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.agent.name`, `gen_ai.tool.name`, `gen_ai.tool.type`, `error.type` and `fornada.simulator.persona.id`, whatever service sent it. Resource attributes SHALL be kept.

#### Scenario: High-cardinality attribute dropped
- **WHEN** a metric data point arrives with `gen_ai.conversation.id`, `fornada.customer.phone` and `gen_ai.tool.name` attributes
- **THEN** the document Elasticsearch stores for it has `gen_ai.tool.name` and neither the conversation id nor the phone

#### Scenario: App metrics unchanged
- **WHEN** the API exports its metrics
- **THEN** every data point reaches Elasticsearch with the same attributes it was sent with, and `service.name` = `fornada-api`

### Requirement: Metric delivery is observable from the dev container
The Collector's internal metrics SHALL report metric points accepted by the OTLP receiver, and metric points sent and failed for the Elasticsearch exporter.

#### Scenario: Metric delivery counted
- **WHEN** the API has exported N metric points and the Collector has delivered them
- **THEN** its internal metrics, read from the `dev` container, report at least N accepted metric points and at least N sent metric points for the Elasticsearch exporter, with no new failed ones

## MODIFIED Requirements

### Requirement: One backend's outage does not affect the other
While Elasticsearch is unavailable or rejects exports, the Collector SHALL keep accepting OTLP, for spans, log records and metrics, and SHALL keep exporting spans to Langfuse, and the reverse. The Collector MAY drop spans, log records or metric points it cannot deliver to the failing backend after its retries.

#### Scenario: Elasticsearch down
- **WHEN** Elasticsearch is stopped and the API sends spans
- **THEN** the spans still reach Langfuse, and the customer gets a normal reply

#### Scenario: Langfuse down
- **WHEN** Langfuse is stopped and the API sends spans
- **THEN** the spans still reach Elasticsearch

#### Scenario: Langfuse down, logs unaffected
- **WHEN** Langfuse is stopped and the API sends log records
- **THEN** the log records still reach Elasticsearch

#### Scenario: Langfuse down, metrics unaffected
- **WHEN** Langfuse is stopped and the API sends metrics
- **THEN** the metrics still reach Elasticsearch
