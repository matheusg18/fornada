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
