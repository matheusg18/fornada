# telemetry-collector Specification

## Purpose

Defines the local OpenTelemetry Collector that every Fornada telemetry signal passes through in the dev environment: the OTLP endpoints it accepts, the pipelines it runs and how its pipeline is smoke-tested without an instrumented app.

## Requirements

### Requirement: Collector runs with the dev environment
The dev environment SHALL run an EDOT Collector service that starts with the other dev services and restarts unless stopped. Its image SHALL be pinned to an exact version.

#### Scenario: Dev environment starts
- **WHEN** the dev container is started or rebuilt
- **THEN** the Collector service is running alongside `postgres` and Langfuse

### Requirement: OTLP endpoints reachable inside the dev network
The Collector SHALL accept OTLP over gRPC on port 4317 and over HTTP on port 4318, reachable from the `dev` container by the Collector's service name. These ports SHALL NOT be published to the host.

#### Scenario: Endpoint from the dev container
- **WHEN** a client in the `dev` container sends OTLP traces to the Collector's service name on port 4317 or 4318
- **THEN** the Collector accepts them

#### Scenario: Not exposed on the host
- **WHEN** the dev environment is running
- **THEN** no Collector port is bound on the host

### Requirement: Traces are exported to Langfuse
The Collector's traces pipeline SHALL export every span it receives over OTLP to the dev environment's Langfuse project, through Langfuse's OTLP/HTTP endpoint on the compose network. Spans SHALL be ingested in real time, without the delay Langfuse applies to OTLP data that does not declare the v4 ingestion version.

#### Scenario: App span reaches Langfuse
- **WHEN** tracing is enabled in the API and a customer message is posted to `/conversations/{conversation_id}/messages`
- **THEN** within a few seconds of the batch export, the Langfuse project shows a trace whose root observation is the request's SERVER span, with `service.name` `fornada-api` and its CLIENT children in the same trace

#### Scenario: Export does not leave the dev network
- **WHEN** the Collector exports spans to Langfuse
- **THEN** it sends them to the Langfuse service on the compose network, not through a host port or any external address

### Requirement: Langfuse export is authenticated with the project keys
The Collector SHALL authenticate to Langfuse with the dev Langfuse project's API keys. The credential SHALL be a dev environment secret provided to the Collector service only: it SHALL NOT appear in any committed file and SHALL NOT be passed to the `dev` container.

#### Scenario: Accepted with the project keys
- **WHEN** the dev environment starts with the generated secrets
- **THEN** Langfuse accepts the Collector's exports without an authentication error

#### Scenario: Secret kept out of the repo and the workspace
- **WHEN** the committed Collector config, compose file and templates are inspected, and the `dev` container's environment is listed
- **THEN** none of them contains the Langfuse secret key or the encoded credential

#### Scenario: Existing environment gets the credential
- **WHEN** the dev container is started on a machine whose dev environment secrets file was created before this change
- **THEN** the credential is derived from the existing Langfuse keys and added, without regenerating any other secret

### Requirement: Langfuse outage does not affect reception
While Langfuse is unavailable or rejects exports, the Collector SHALL keep accepting OTLP from clients, and the API SHALL keep answering normally. The Collector MAY drop spans it cannot deliver after its retries.

#### Scenario: Langfuse down
- **WHEN** Langfuse is stopped and the API sends spans
- **THEN** the Collector still counts the spans as accepted and the customer gets a normal reply

### Requirement: Synthetic-span smoke test
The dev environment SHALL provide an on-demand synthetic telemetry generator that sends a fixed, small number of spans to the Collector over OTLP and then exits. It SHALL NOT start with the dev environment.

#### Scenario: Smoke test run
- **WHEN** the maintainer runs the generator from the host
- **THEN** it exits successfully and the generated traces appear in the Langfuse project

#### Scenario: Not started by default
- **WHEN** the dev container starts
- **THEN** the generator does not run

### Requirement: Reception is observable from the dev container
The Collector SHALL expose its internal metrics, including the count of accepted spans and, per exporter, the count of spans sent and of spans that failed to send, on a port reachable from the `dev` container by service name, so reception and delivery can be checked without Docker access.

#### Scenario: Accepted spans counted
- **WHEN** the generator has sent N spans
- **THEN** the Collector's internal metrics, read from the `dev` container, report at least N accepted spans for the OTLP receiver

#### Scenario: Delivery to Langfuse counted
- **WHEN** the Collector has exported N spans to Langfuse successfully
- **THEN** its internal metrics report at least N sent spans for the Langfuse exporter and no new failed spans

### Requirement: Traces are also exported to Elasticsearch
The Collector SHALL export every span it receives over OTLP to the dev environment's Elasticsearch as well as to Langfuse, over the compose network, in a form Kibana APM shows as services, transactions and traces.

#### Scenario: Same trace in both backends
- **WHEN** tracing is enabled in the API and a customer message is posted
- **THEN** the trace, under the same trace id, is shown in Langfuse and in Kibana APM under the service `fornada-api`

#### Scenario: Client root in Kibana
- **WHEN** the simulator posts a message with tracing enabled end to end
- **THEN** Kibana APM shows the trace starting at the `fornada-simulator` span, with `fornada-api` as a downstream service

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

### Requirement: Delivery to Elasticsearch is observable from the dev container
The Collector's internal metrics SHALL report spans sent and spans that failed to send for the Elasticsearch exporter, alongside the Langfuse exporter's counts.

#### Scenario: Delivery counted
- **WHEN** the Collector has exported N spans to Elasticsearch successfully
- **THEN** its internal metrics, read from the `dev` container, report at least N sent spans for the Elasticsearch exporter and no new failed spans

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
