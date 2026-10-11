# Design

## Context

The dev environment is one compose project (`.devcontainer/compose.yaml`) started by the host's dev container tooling. The `dev` container has no Docker socket on purpose (AGENTS.md, "Dev environment"). So from inside it an agent cannot run `docker compose`, start one-shot containers or read another container's logs. Compose changes take effect only when the maintainer rebuilds or reopens the container on the host. Images are pinned to exact tags so the existing `docker-compose` Dependabot entry can bump them.

Versions checked on 2026-10-11:

- EDOT Collector: `docker.elastic.co/elastic-agent/elastic-otel-collector:9.5.5`, the same release as `elastic/elastic-agent:9.5.5`, which Elastic's self-managed Docker quickstart uses.
- telemetrygen: `ghcr.io/open-telemetry/opentelemetry-collector-contrib/telemetrygen:v0.162.0`, the same as the latest contrib release.

## Goals / Non-Goals

**Goals:**
- Prove that OTLP in → Collector → debug log works, with no app code and no backend.
- Leave the Collector at the address the app will use in step A (`edot-collector:4317`/`4318`).
- Give the agent a way to check the result from inside the container, not only the maintainer from the host.

**Non-Goals:**
- Exporters to Langfuse or Elasticsearch, processors (batch, redaction, attribute normalization), logs and metrics pipelines. These come in later phase 2 steps.
- App instrumentation, `TracerProvider` or any `.env` setting for the app.
- Publishing Collector ports to the host. A host-side OTLP client is not needed yet.

## Decisions

**Slim `elastic-otel-collector` image over `elastic/elastic-agent`.** The slim image ships only the EDOT Collector. The full Elastic Agent image is larger and needs `ELASTIC_AGENT_OTEL=true` to run in Collector mode. Both run the same EDOT components. The slim image's entrypoint is `tini -- docker-entrypoint`, with no default `Cmd`. The service passes `--config <path>` as its command, as in Elastic's quickstart. If the entrypoint does not start in Collector mode with only that argument, `ELASTIC_AGENT_OTEL=true` is the fallback. Apply checks this against the image's own docs and entrypoint script.

**Config in a file under `.devcontainer/otel-collector/`, mounted read-only.** It sits next to the other infra config (`postgres/`, `db/`). Later steps add exporters and processors to the same file. Writing the pipelines is core work (AGENTS.md, phase 2), so the agent mounts an empty skeleton file and the maintainer writes `receivers`, `exporters` and `service.pipelines`. The agent then reviews the file only for mistakes that break startup.

**`debug` exporter at `verbosity: detailed`.** `basic` only logs counts. `detailed` prints each span with its name and attributes, which is what the "Pronto quando" check needs. telemetrygen sends only a few spans, so the volume is small.

**OTLP receiver bound to `0.0.0.0` inside the container, no `ports:` mapping.** The OTLP receiver listens on `localhost` by default, which other containers cannot reach. Binding to all interfaces exposes the receiver only on the compose network, because nothing is published. This fits the dev container's isolation and the Postgres setup, which also publishes no port.

**telemetrygen as a compose service behind a `smoke-test` profile.** The dev container has no Docker or Go, and the contrib releases publish telemetrygen only as an image. A profiled service can never start by accident (`stopCompose` / `up` skip profiles). It is pinned and visible to Dependabot. It reuses the compose network, so it targets `edot-collector:4317` the same way the app will. The maintainer runs it on the host with `docker compose --profile smoke-test run --rm telemetrygen` against the dev container's compose project, and reads the result with `docker compose logs edot-collector`. Its command is fixed: `traces --otlp-endpoint edot-collector:4317 --otlp-insecure --traces 5`. Alternatives: installing telemetrygen in the dev container image, which means a bigger image and a build-time download for one smoke test, or `curl` with a hand-written OTLP/HTTP JSON payload, which is not what the maintainer asked for. The `curl` payload stays useful as a manual check from inside the container.

**Agent-side check through the Collector's internal metrics.** The Collector serves Prometheus metrics on `:8888`. The service config sets the internal telemetry endpoint to `0.0.0.0:8888`, so `curl edot-collector:8888/metrics` from the `dev` container shows `otelcol_receiver_accepted_spans` and `otelcol_exporter_sent_spans` for the debug exporter. This proves reception without Docker access. The log check stays the maintainer's "Pronto quando".

## Risks / Trade-offs

- [The slim image's entrypoint behaves differently from the full agent image, so the service exits or ignores `--config`] → Check the entrypoint before the maintainer rebuilds. Fall back to `ELASTIC_AGENT_OTEL=true`, or to `elastic/elastic-agent:9.5.5`, and record which one in the compose comment.
- [The compose project name on the host is not obvious, so `docker compose run` creates a second project and a separate network where `edot-collector` does not resolve] → Document the exact host command with `-p <project>`, found with `docker compose ls`.
- [The internal telemetry config keys changed between Collector versions (`service.telemetry.metrics.address` vs. `readers`)] → Use the form documented for the Collector core version EDOT 9.5.5 is built on, and check that the service starts.
- [A config error leaves the Collector in a restart loop that the agent cannot see] → The agent-side `curl` fails fast, and the maintainer checks `docker compose logs edot-collector` first.

## Migration Plan

Add the services, then the maintainer rebuilds the dev container on the host. Rollback means removing the two services and the config file. No data or volume is involved.
