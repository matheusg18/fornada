# Spec Delta

## ADDED Requirements

### Requirement: Traces are also exported to Elasticsearch
The Collector SHALL export every span it receives over OTLP to the dev environment's Elasticsearch as well as to Langfuse, over the compose network, in a form Kibana APM shows as services, transactions and traces.

#### Scenario: Same trace in both backends
- **WHEN** tracing is enabled in the API and a customer message is posted
- **THEN** the trace, under the same trace id, is shown in Langfuse and in Kibana APM under the service `fornada-api`

#### Scenario: Client root in Kibana
- **WHEN** the simulator posts a message with tracing enabled end to end
- **THEN** Kibana APM shows the trace starting at the `fornada-simulator` span, with `fornada-api` as a downstream service

### Requirement: Elasticsearch receives no conversation content
Before export to Elasticsearch, the Collector SHALL delete `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `gen_ai.tool.call.arguments` and `gen_ai.tool.call.result` from every span, whatever service sent it. All other attributes SHALL reach Elasticsearch unchanged, except the phone.

#### Scenario: Content stripped
- **WHEN** content capture is on in the API and a turn with a tool call is traced
- **THEN** no span of that trace in Elasticsearch has any of the five content attributes, and its `gen_ai.usage.*`, `gen_ai.tool.name` and `fornada.prompt.version` attributes are present

#### Scenario: Synthetic span with content
- **WHEN** a span from any service carries `gen_ai.input.messages` with a customer message
- **THEN** the document Elasticsearch stores for that span does not contain the message text

### Requirement: Elasticsearch receives the phone only as a salted hash
Before export to Elasticsearch, the Collector SHALL replace the value of `fornada.customer.phone` with the lowercase hex SHA-256 of a secret salt joined with the phone. The same phone SHALL always give the same hash, and the hash SHALL NOT be computable without the salt.

#### Scenario: Phone hashed
- **WHEN** a span with `fornada.customer.phone` = `+5581999991234` is exported
- **THEN** the span in Elasticsearch has `fornada.customer.phone` as a 64-character hex string, and no stored field contains `5581999991234`

#### Scenario: Stable across conversations
- **WHEN** two conversations call `get_order` with the same phone
- **THEN** their tool spans in Elasticsearch carry the same hash

#### Scenario: Plain hash does not match
- **WHEN** the unsalted SHA-256 of `+5581999991234` is computed
- **THEN** it differs from the value stored in Elasticsearch

### Requirement: Langfuse keeps the content
Redaction for Elasticsearch SHALL NOT change the spans exported to Langfuse. Langfuse SHALL receive the content attributes and `fornada.customer.phone` exactly as the app sent them.

#### Scenario: Same trace, two views
- **WHEN** content capture is on and a customer gives their phone in a turn that calls `get_order`
- **THEN** in Langfuse the trace's spans show the message text, the tool arguments and the phone in clear, and in Elasticsearch the same spans show neither the text nor the phone

### Requirement: Elasticsearch export uses a write-only user
The Collector SHALL authenticate to Elasticsearch as a dedicated user that can only write the indices the export uses. The user SHALL be created without manual steps. Its password and the hash salt SHALL be dev environment secrets passed only to the services that need them, never committed and never passed to the `dev` container.

#### Scenario: Fresh environment
- **WHEN** the dev environment starts with an empty Elasticsearch volume
- **THEN** the Collector exports to Elasticsearch without an authentication error and without the maintainer running any command

#### Scenario: Least privilege
- **WHEN** the Collector's credential is used to search an index or to read cluster security settings
- **THEN** Elasticsearch denies the request

#### Scenario: Secrets kept out
- **WHEN** the committed Collector config, compose file and templates are inspected, and the `dev` container's environment is listed
- **THEN** none of them contains the user's password or the salt

#### Scenario: Existing environment gets the new secrets
- **WHEN** the dev container starts on a machine whose dev environment secrets file was created before this change
- **THEN** the password and the salt are added without changing any other secret

### Requirement: One backend's outage does not affect the other
While Elasticsearch is unavailable or rejects exports, the Collector SHALL keep accepting OTLP and SHALL keep exporting to Langfuse, and the reverse. The Collector MAY drop spans it cannot deliver to the failing backend after its retries.

#### Scenario: Elasticsearch down
- **WHEN** Elasticsearch is stopped and the API sends spans
- **THEN** the spans still reach Langfuse, and the customer gets a normal reply

#### Scenario: Langfuse down
- **WHEN** Langfuse is stopped and the API sends spans
- **THEN** the spans still reach Elasticsearch

### Requirement: Delivery to Elasticsearch is observable from the dev container
The Collector's internal metrics SHALL report spans sent and spans that failed to send for the Elasticsearch exporter, alongside the Langfuse exporter's counts.

#### Scenario: Delivery counted
- **WHEN** the Collector has exported N spans to Elasticsearch successfully
- **THEN** its internal metrics, read from the `dev` container, report at least N sent spans for the Elasticsearch exporter and no new failed spans
