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

### Requirement: Traces are written to the Collector log only
The Collector SHALL run one traces pipeline from the OTLP receiver to a debug exporter that writes received spans to the Collector's standard output, with enough detail to see each span's name and attributes. The Collector SHALL NOT export to any backend.

#### Scenario: Span reaches the log
- **WHEN** the Collector receives a span over OTLP
- **THEN** the Collector log shows that span's name and attributes

#### Scenario: No backend
- **WHEN** the Collector receives spans
- **THEN** it sends nothing to Langfuse, Elasticsearch or any other network destination

### Requirement: Synthetic-span smoke test
The dev environment SHALL provide an on-demand synthetic telemetry generator that sends a fixed, small number of spans to the Collector over OTLP and then exits. It SHALL NOT start with the dev environment.

#### Scenario: Smoke test run
- **WHEN** the maintainer runs the generator from the host
- **THEN** it exits successfully and the Collector log shows the generated spans

#### Scenario: Not started by default
- **WHEN** the dev container starts
- **THEN** the generator does not run

### Requirement: Reception is observable from the dev container
The Collector SHALL expose its internal metrics, including the count of accepted spans, on a port reachable from the `dev` container by service name, so reception can be checked without Docker access.

#### Scenario: Accepted spans counted
- **WHEN** the generator has sent N spans
- **THEN** the Collector's internal metrics, read from the `dev` container, report at least N accepted spans for the OTLP receiver
