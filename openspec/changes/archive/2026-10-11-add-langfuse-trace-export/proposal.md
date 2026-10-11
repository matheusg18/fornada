# Proposal

## Why

The API now emits a SERVER span per conversation turn (`add-app-tracing`), but the Collector only prints it to its own log. Phase 2 step A says traces go to Langfuse, the LLM view where conversations become sessions and, from phase 3 on, the place where traces are read and annotated. This change connects the Collector to the self-hosted Langfuse that already runs in the dev environment, so the span from the previous step shows up there.

This is **phase 2 (instrumentation), step A**. It stays within the frozen scope: no tool, feature or app code changes, only the dev environment's Collector pipeline and the credentials it needs.

## What Changes

- The Collector's traces pipeline gets an `otlphttp/langfuse` exporter that sends spans to Langfuse's OTLP endpoint (`http://langfuse-web:3000/api/public/otel`) over the compose network, authenticated with the Langfuse project's API keys (HTTP Basic) and with the `x-langfuse-ingestion-version: 4` header so spans appear in real time.
- The Basic auth string is a dev environment secret: it lives in `.devcontainer/.env`, is derived from the existing `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`, and reaches only the `edot-collector` service. The committed Collector config references it by environment variable, never by value.
- `.devcontainer/init-env.sh` generates the auth string for new environments and adds it to an existing `.devcontainer/.env` that lacks it, so a rebuild picks it up without manual edits.
- The Collector stops being "log only": the existing requirement that forbids any backend is replaced. Whether the `debug` exporter stays in the pipeline next to Langfuse is a maintainer decision (design.md).
- Docs: `apps/api/README.md` ("Tracing") and the comments in the Collector config describe the new destination and how to check it.

Out of scope: Elasticsearch fan-out, redaction processors, logs and metrics pipelines (step B); `gen_ai.*` spans, session ids and per-turn/LLM/tool spans (later step A changes); any Langfuse SDK in app code.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `telemetry-collector`: the Collector exports traces to Langfuse with authentication, instead of writing them only to its log. The "Traces are written to the Collector log only" requirement is replaced, and the smoke test's expected outcome moves accordingly.

## Impact

- `.devcontainer/otel-collector/config.yaml`: new exporter, traces pipeline change (core: the maintainer writes the pipeline).
- `.devcontainer/compose.yaml`: `edot-collector` receives the Langfuse auth variable.
- `.devcontainer/init-env.sh` and `.devcontainer/.env.example`: new `LANGFUSE_OTLP_AUTH` secret.
- `apps/api/README.md`, AGENTS.md (dev environment notes) where they say the Collector only logs.
- No app code, dependency or image version changes. Langfuse 4.53.0 and EDOT 9.5.5 already support this (OTLP/HTTP ingestion; `otlphttp` exporter is in EDOT core).
