# Tasks

Tasks marked `TODO(human)` are core (AGENTS.md, phase 2: "the pipelines in the Collector config"). The agent leaves the marker and a short "Learn by Doing" note, then stops and waits for the maintainer. Credentials and compose are periphery. The dev container has no Docker socket, so every Collector restart is run by the maintainer on the host.

## 1. Credential (`telemetry-collector`: authenticated with the project keys)

- [x] 1.1 Update `.devcontainer/init-env.sh` (design.md, decision 2): new files get `LANGFUSE_OTLP_AUTH`; an existing file without it gets the value derived from its `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` appended, with no other line changed; a file that already has it is left untouched. Verify by running the script against copies in the scratchpad (missing file, old file, current file): `diff` shows only the appended line for the old file, and `echo "$LANGFUSE_OTLP_AUTH" | base64 -d` gives `pk:sk`.
- [x] 1.2 Add `LANGFUSE_OTLP_AUTH=` with a one-line comment (how it is derived, never edit by hand) to `.devcontainer/.env.example`. Verify every variable `init-env.sh` writes appears in the template.
- [x] 1.3 Pass `LANGFUSE_OTLP_AUTH: ${LANGFUSE_OTLP_AUTH:?}` to `edot-collector` only in `.devcontainer/compose.yaml`, with a comment. Verify with `grep` that no other service, and in particular `dev`, references it.

## 2. Collector pipeline (`telemetry-collector`: exported to Langfuse, outage does not affect reception)

- [x] 2.1 Agent prepares `.devcontainer/otel-collector/config.yaml`: update the header comment (no longer "no backend"), and leave `TODO(human)` markers with a "Learn by Doing" note for 2.2–2.4, referencing design.md decision 4. Verify the file is still valid YAML (`python3 -c 'import yaml,sys; yaml.safe_load(open(sys.argv[1]))' …`).
- [x] 2.2 TODO(human): write the `otlphttp/langfuse` exporter: endpoint on the compose network and the `Authorization` and `x-langfuse-ingestion-version` headers, with the credential read from the environment (decision 4.1).
- [x] 2.3 TODO(human): decide whether `debug` stays in the traces pipeline and at which verbosity, and add `otlphttp/langfuse` to the pipeline's exporters (decision 4.2).
- [x] 2.4 TODO(human): decide on processors for this step (none, or `memory_limiter`/`batch`), with a one-line comment for the choice (decision 4.3).
- [x] 2.5 Agent reviews 2.2–2.4 only for mistakes that stop the Collector from starting or authenticating, and asks questions instead of fixing. Maintainer rebuilds the dev container (so `init-env.sh` and compose apply) or, if `.devcontainer/.env` already has the value, recreates `edot-collector` from the host. Verify `curl -s edot-collector:8888/metrics` answers from the `dev` container and the host's `docker compose -p fornada_devcontainer logs edot-collector` shows no config or auth error.

## 3. Docs

- [x] 3.1 Update `apps/api/README.md` ("Tracing": traces go to Langfuse, where to look, the per-exporter counters) and the AGENTS.md dev environment notes (smoke test now ends in Langfuse; counters per exporter). Verify no remaining text says the Collector only logs or has no backend (`grep -rn -i "only prints\|no backend\|log only" apps/api/README.md AGENTS.md .devcontainer/`).

## 4. End-to-end check (all `telemetry-collector` deltas)

- [x] 4.1 Maintainer predicts in one sentence what the Langfuse trace for one customer message will look like (how many observations, which is the root, what the name is). Then, with `TELEMETRY__ENABLED=true`, `uv run task dev` and a POST to `/conversations/<uuid>/messages`: Langfuse (http://localhost:3000, project Fornada → Tracing) shows the trace with the SERVER span as root and its children. This is the "Pronto quando". Compare with the prediction.
- [x] 4.2 Agent, in the dev container: before and after 4.1, `curl -s edot-collector:8888/metrics | grep -E '^otelcol_exporter_(sent|send_failed)_spans'` shows `sent_spans` for `otlphttp/langfuse` going up by the request's span count and `send_failed_spans` unchanged. Paste both readings in the step summary.
- [x] 4.3 Secret hygiene: `git grep` finds neither the secret key nor the encoded value, and `env | grep -i langfuse` in the `dev` container prints nothing. Record the result.
- [x] 4.4 Outage: maintainer stops `langfuse-web` on the host, agent posts a message. The reply is normal and `otelcol_receiver_accepted_spans` still grows. Restart `langfuse-web` and record what happened to the spans sent while it was down (retried and delivered, or dropped).
- [x] 4.5 Maintainer runs the `telemetrygen` smoke test from the host; its traces appear in Langfuse with `service.name=telemetrygen`.

## Workflow follow-up

- One commit per group, with maintainer approval before each: `chore:` for 1, `feat:` for 2, `docs:` for 3.
- Open the PR, then `/opsx:archive` after merge.
