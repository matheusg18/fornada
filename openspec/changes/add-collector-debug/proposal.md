# Proposal

## Why

Phase 2 sends every signal through the EDOT Collector before it reaches Langfuse or Elasticsearch. If the first instrumented app run shows nothing in Langfuse, the fault could be the SDK setup, the network, the Collector or the backend. Bringing the Collector up alone first, with only a `debug` exporter and synthetic spans from `telemetrygen`, proves the receiver end of the pipeline works before any app code or backend exists. Later steps then only have to debug one new piece at a time.

**Phase:** 2 (instrumentation), the first step before step A. The compose wiring and the `telemetrygen` setup are periphery work. The Collector pipeline config is core (AGENTS.md: "the pipelines in the Collector config"), so the maintainer writes it and the tasks mark it `TODO(human)`.

**Scope:** stays within the frozen scope. It adds no tool or agent feature, no defense and no app code. The app is not instrumented yet.

## What Changes

- New `edot-collector` service in `.devcontainer/compose.yaml`, running the EDOT Collector image pinned to an exact version, started with the dev environment.
- New Collector config file mounted into that service. It has an `otlp` receiver (gRPC and HTTP) and a `debug` exporter, joined by one `traces` pipeline. It has no backend exporter yet.
- New `telemetrygen` service in the same compose file, behind a compose profile so it does not start with the dev environment. When run on demand, it sends a small, fixed number of synthetic spans to the Collector over OTLP.
- The dev container can reach the Collector by service name (`edot-collector:4317`/`4318`), which is where the app will send its telemetry in step A. No port is published to the host.
- AGENTS.md gets the new service and the smoke-test command in its "Dev environment" section.

## Capabilities

### New Capabilities
- `telemetry-collector`: the local OpenTelemetry Collector in the dev environment: which OTLP endpoints it exposes, which pipelines and exporters it runs, and how its pipeline is smoke-tested with synthetic telemetry. Later phase 2 steps extend it with the Langfuse and Elasticsearch exporters and the redaction processors.

### Modified Capabilities
None.

## Impact

- **Files:** `.devcontainer/compose.yaml`, a new Collector config file under `.devcontainer/`, `AGENTS.md`.
- **Images:** `docker.elastic.co/elastic-agent/elastic-otel-collector` and `ghcr.io/open-telemetry/opentelemetry-collector-contrib/telemetrygen`, both pinned to exact tags. The existing `docker-compose` Dependabot entry picks them up.
- **Dev environment:** the dev container must be rebuilt or reopened on the host to start the new service. The dev container has no Docker socket, so running `telemetrygen` and reading Collector logs happen on the host with `docker compose`. From inside the container, the Collector's internal metrics confirm spans were received.
- **Secrets:** none. The Collector has no credentials at this step.
- **App code:** none.
