# Proposal

## Why

Phase 2 step B fans traces out to Elasticsearch and adds logs and metrics, all viewed in Kibana. Today the dev environment has no Elasticsearch or Kibana, so the Collector has nowhere to send them. Elasticsearch and Kibana are also the heaviest services in the stack: on a ~15 GiB machine that already runs Langfuse, ClickHouse, Postgres and the dev container, an unbounded JVM can make the machine unusable. This change brings them up first, with fixed memory limits, so the exporters and pipelines that follow land on a stack that is known to fit.

This is **phase 2 (instrumentation), step B, first change**. It stays within the frozen scope: no tool, feature or app code changes, only dev environment services and their secrets.

## What Changes

- Two new services in `.devcontainer/compose.yaml`, pinned to the same Elastic version as the EDOT Collector (9.5.5):
  - `elasticsearch`: single node, security on (login required) over plain HTTP inside the compose network, data in a named volume, no host port.
  - `kibana`: connects to Elasticsearch as `kibana_system`, published on `127.0.0.1:5601` and forwarded by the dev container.
- A one-shot `elasticsearch-setup` service sets the `kibana_system` password once Elasticsearch is healthy, then exits. Kibana waits for it.
- Memory limits: Elasticsearch is capped at 1.5 GiB and Kibana at 1 GiB of RAM, both with no swap, and Elasticsearch's JVM heap is fixed at 512 MiB. (Planned at 1 GiB each; Elasticsearch was OOM-killed at 1 GiB, see design.md.)
- New dev environment secrets in `.devcontainer/.env`: the `elastic` superuser password, the `kibana_system` password and Kibana's encryption key. `init-env.sh` generates them for new files and appends them to existing files without touching other secrets. They reach only the Elastic services, never the `dev` container.
- Docs: AGENTS.md dev environment notes (services, Kibana URL and login, memory limits) and the compose header comment.

Out of scope: any Collector change (Elasticsearch exporter, logs and metrics pipelines, redaction processors) and any app code (`LoggerProvider`, `MeterProvider`); those are the next step B changes. Memory limits on the existing services (Langfuse, ClickHouse, Postgres, MinIO, Valkey) are not added here; this change measures their usage with everything up and leaves limits there to a follow-up if the measurement calls for it. No TLS.

## Capabilities

### New Capabilities

- `elastic-stack`: the dev environment's Elasticsearch and Kibana services: how they start, authenticate, persist data, where they are reachable, and the memory budget they must stay within.

### Modified Capabilities

None. `telemetry-collector` does not change until the Collector exports to Elasticsearch.

## Impact

- `.devcontainer/compose.yaml`: `elasticsearch`, `elasticsearch-setup` and `kibana` services, `elasticsearch_data` volume.
- `.devcontainer/devcontainer.json`: forward port 5601.
- `.devcontainer/init-env.sh` and `.devcontainer/.env.example`: three new secrets; the script learns to append missing random secrets to an existing file.
- `AGENTS.md`: dev environment section.
- Dependabot already watches compose images, so the new tags are bumped with the rest. No Python dependency changes.
- Resource cost: up to 2.5 GiB more RAM (about 2 GiB measured idle) and one more volume on disk.
