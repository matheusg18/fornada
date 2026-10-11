# Tasks

## 1. Collector service (`telemetry-collector`: runs with the dev environment, OTLP endpoints)

- [x] 1.1 Confirm that `elastic-otel-collector:9.5.5` and `telemetrygen:v0.162.0` are still the latest tags, and check how the slim image's `docker-entrypoint` handles `--config` (Elastic docs or the `elastic-agent` repo). Record the outcome in the compose comment. Verify by naming the doc or source line in the step summary.
- [x] 1.2 Create `.devcontainer/otel-collector/config.yaml` as a skeleton: a header comment, the `service.telemetry` block exposing internal metrics on `0.0.0.0:8888`, and `TODO(human)` markers for `receivers` (OTLP gRPC and HTTP on `0.0.0.0`), `exporters` (`debug`, `verbosity: detailed`) and `service.pipelines` (one `traces` pipeline). Verify the file parses as YAML.
- [x] 1.3 TODO(human): the maintainer writes the `receivers`, `exporters` and `service.pipelines` sections (core work, AGENTS.md phase 2). The agent then reviews the file only for mistakes that would stop the Collector from starting.
- [x] 1.4 Add the `edot-collector` service to `.devcontainer/compose.yaml`: pinned image, `restart: unless-stopped`, config mounted read-only, `command: ["--config", …]`, no `ports:`, and a short comment in the file's style. Verify with `python -c 'import yaml…'` that the compose file parses and the service has no `ports` key.

## 2. Smoke-test generator (`telemetry-collector`: synthetic-span smoke test)

- [x] 2.1 Add the `telemetrygen` service to `.devcontainer/compose.yaml`: pinned image, `profiles: [smoke-test]`, `depends_on: edot-collector`, and the command `traces --otlp-endpoint edot-collector:4317 --otlp-insecure --traces 5`. Verify that the compose file parses and the service has the profile.
- [ ] 2.2 Document the smoke test in AGENTS.md ("Dev environment" → services list): the new `edot-collector` service, its in-network endpoints, and the host commands (`docker compose ls` to find the project, `docker compose -p <project> -f .devcontainer/compose.yaml --profile smoke-test run --rm telemetrygen`, `docker compose -p <project> logs edot-collector`). Also document the in-container check `curl -s edot-collector:8888/metrics | grep accepted_spans`. Verify the commands match the compose file.

## 3. End-to-end check (all `telemetry-collector` requirements)

- [ ] 3.1 Maintainer, on the host: rebuild or reopen the dev container and confirm `edot-collector` is running (`docker compose -p <project> ps`) with no host port.
- [ ] 3.2 Maintainer, on the host: run the telemetrygen command. It exits 0, and `docker compose logs edot-collector` shows the 10 synthetic spans (5 traces, each a root and one child span) with name and attributes. This is the "Pronto quando" for the change.
- [ ] 3.3 Agent, in the dev container: `curl -s edot-collector:8888/metrics` reports `otelcol_receiver_accepted_spans` ≥ 10 for the `otlp` receiver and matching `otelcol_exporter_sent_spans` for `debug`. Paste the lines in the step summary.

## Workflow follow-up

- One commit per step (`chore:` for compose and config, `docs:` for AGENTS.md), with maintainer approval before each.
- Archive the change after 3.2 passes, and sync `telemetry-collector` into `openspec/specs/`.
