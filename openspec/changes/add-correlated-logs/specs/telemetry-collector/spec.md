# Spec Delta

## ADDED Requirements

### Requirement: Logs are exported to Elasticsearch
The Collector SHALL export every log record it receives over OTLP to the dev environment's Elasticsearch, over the compose network, keeping the record's trace id and span id. Log records SHALL NOT be exported to Langfuse.

#### Scenario: Error log next to its trace
- **WHEN** telemetry is enabled in the API and a turn fails with `"turn failed"`
- **THEN** Elasticsearch stores the record under the service `fornada-api` with severity ERROR and the trace id of that request, and Kibana APM shows a trace with that id

#### Scenario: From the log to the trace
- **WHEN** the maintainer opens that ERROR record in Kibana
- **THEN** its trace id leads to the same trace in Kibana APM, and to the same trace id in Langfuse

### Requirement: Log delivery is observable from the dev container
The Collector's internal metrics SHALL report log records accepted by the OTLP receiver, and log records sent and failed for the Elasticsearch exporter.

#### Scenario: Log delivery counted
- **WHEN** the API has exported N log records and the Collector has delivered them
- **THEN** its internal metrics, read from the `dev` container, report at least N accepted log records and at least N sent log records for the Elasticsearch exporter, with no new failed ones

## MODIFIED Requirements

### Requirement: Elasticsearch receives no conversation content
Before export to Elasticsearch, the Collector SHALL delete `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `gen_ai.tool.call.arguments` and `gen_ai.tool.call.result` from every span and from every log record, whatever service sent it. All other attributes SHALL reach Elasticsearch unchanged, except the phone.

#### Scenario: Content stripped
- **WHEN** content capture is on in the API and a turn with a tool call is traced
- **THEN** no span of that trace in Elasticsearch has any of the five content attributes, and its `gen_ai.usage.*`, `gen_ai.tool.name` and `fornada.prompt.version` attributes are present

#### Scenario: Synthetic span with content
- **WHEN** a span from any service carries `gen_ai.input.messages` with a customer message
- **THEN** the document Elasticsearch stores for that span does not contain the message text

#### Scenario: Synthetic log record with content
- **WHEN** a log record from any service carries `gen_ai.input.messages` with a customer message as an attribute
- **THEN** the document Elasticsearch stores for that record does not contain the message text, and its body, severity and trace id are present

### Requirement: Elasticsearch receives the phone only as a salted hash
Before export to Elasticsearch, the Collector SHALL replace the value of `fornada.customer.phone` on spans and on log records with the lowercase hex SHA-256 of a secret salt joined with the phone. The same phone SHALL always give the same hash, on spans and logs alike, and the hash SHALL NOT be computable without the salt.

#### Scenario: Phone hashed
- **WHEN** a span with `fornada.customer.phone` = `+5581999991234` is exported
- **THEN** the span in Elasticsearch has `fornada.customer.phone` as a 64-character hex string, and no stored field contains `5581999991234`

#### Scenario: Stable across conversations
- **WHEN** two conversations call `get_order` with the same phone
- **THEN** their tool spans in Elasticsearch carry the same hash

#### Scenario: Plain hash does not match
- **WHEN** the unsalted SHA-256 of `+5581999991234` is computed
- **THEN** it differs from the value stored in Elasticsearch

#### Scenario: Phone on a log record
- **WHEN** a log record with attribute `fornada.customer.phone` = `+5581999991234` is exported
- **THEN** the record in Elasticsearch carries the same hash as a span with that phone, and no stored field of the record contains `5581999991234`

### Requirement: One backend's outage does not affect the other
While Elasticsearch is unavailable or rejects exports, the Collector SHALL keep accepting OTLP, for spans and log records, and SHALL keep exporting spans to Langfuse, and the reverse. The Collector MAY drop spans or log records it cannot deliver to the failing backend after its retries.

#### Scenario: Elasticsearch down
- **WHEN** Elasticsearch is stopped and the API sends spans
- **THEN** the spans still reach Langfuse, and the customer gets a normal reply

#### Scenario: Langfuse down
- **WHEN** Langfuse is stopped and the API sends spans
- **THEN** the spans still reach Elasticsearch

#### Scenario: Langfuse down, logs unaffected
- **WHEN** Langfuse is stopped and the API sends log records
- **THEN** the log records still reach Elasticsearch
