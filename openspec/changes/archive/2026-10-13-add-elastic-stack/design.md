# Design

## Context

- `.devcontainer/compose.yaml` runs `dev`, `postgres`, the Langfuse v4 stack (`langfuse-web`, `langfuse-worker`, `clickhouse`, `valkey`, `minio`), `edot-collector` (EDOT 9.5.5) and the on-demand `telemetrygen`. No service has a memory limit. Images are pinned exactly and Dependabot bumps them.
- The latest Elastic release is 9.5.5 for both `elasticsearch` and `kibana` (Docker Hub, 2026-10-13), the same version as the EDOT Collector.
- The maintainer's machine has ~15 GiB of RAM and 8 GiB of swap. With the current stack up, about 6.7 GiB is available (`free -h` in the dev container, which sees host memory).
- `init-env.sh` runs on the host before every start. It creates `.devcontainer/.env` once; afterwards it only derives `LANGFUSE_OTLP_AUTH` when it is missing. It has no general "add a new random secret" path yet.
- The `dev` container has no Docker socket, so `docker stats`, `docker compose exec` and restarts are run by the maintainer on the host.
- AGENTS.md puts "Elastic and Langfuse compose, credentials" in the periphery for phase 2, so this change has no `TODO(human)` markers.
- Memory choices (1 GiB each, auth on without TLS) were made by the maintainer when the change was proposed. Elasticsearch was raised to 1.5 GiB during implementation, also by the maintainer, after it was OOM-killed at 1 GiB (decision 2).

## Goals / Non-Goals

**Goals:**
- Elasticsearch and Kibana start with the dev environment, without manual steps, also on a machine whose `.devcontainer/.env` predates this change.
- A measured memory picture of the whole stack with Elastic up, recorded before and after, so "the machine stays usable" is a number and not an impression.

**Non-Goals:**
- Index templates, ILM, data streams, APM integration setup in Kibana: they come with the Collector's Elasticsearch exporter, which creates what it needs.
- Production hardening (TLS, multiple nodes, snapshots).

## Decisions

### 1. Single node, security on, plain HTTP

Elasticsearch settings, as environment variables on the service:

- `discovery.type=single-node`: one node, no cluster formation. It also means the bootstrap checks (for example `vm.max_map_count`) are not enforced, so a host with defaults still starts.
- `xpack.security.enabled=true`, `xpack.security.http.ssl.enabled=false`, `xpack.security.transport.ssl.enabled=false`, `xpack.security.enrollment.enabled=false`, with `ELASTIC_PASSWORD` set. Setting security explicitly turns off the image's auto-configuration (generated certificates and enrollment tokens printed to the log), which does not fit a headless start.
- `xpack.license.self_generated.type=basic`.
- *Alternative: security off.* Rejected by the maintainer: Kibana would open without a login, and from step B the indices hold trace data whose redaction is exactly what phase 2 and 6 measure.
- *Alternative: TLS too.* Rejected by the maintainer: it needs a certificate setup service and CA wiring in Kibana and the Collector, for traffic that never leaves the compose network.

### 2. Memory: hard limits, no swap, explicit heaps

| Service | `mem_limit` | `memswap_limit` | Runtime cap |
|---|---|---|---|
| `elasticsearch` | 1536m | 1536m | `ES_JAVA_OPTS=-Xms512m -Xmx512m` |
| `kibana` | 1g | 1g | `NODE_OPTIONS=--max-old-space-size=768` |

- Heap at 512 MiB, a third of the container limit. Elastic's guidance is at most half; the rest is for off-heap memory, Lucene's file cache and the JVM itself. Writing the heap down makes the spec checkable and stops a future limit change from silently changing it.
- *Planned: 1 GiB for Elasticsearch, heap at half.* Measured on 9.5.5 with an empty cluster on the 12-CPU host: 512 MiB heap (pre-touched) + ~290 MiB non-heap (metaspace, code cache) + stacks for 189 threads and malloc arenas reached 1023 MiB of anonymous memory, and the kernel OOM-killed it about 2.5 minutes after start. With `node.processors=2` (85 threads) it still climbed from 929 to 961 MiB in 4 minutes and hit the cgroup limit, leaving no room for step B indexing. Raised to 1.5 GiB, heap unchanged, by the maintainer's choice.
- *Alternative: stay at 1 GiB with a 384 MiB heap and `node.processors=2`.* Rejected: the heap gets tight once step B indexes traces, logs and metrics, and the non-heap part keeps growing.
- `memswap_limit` equal to `mem_limit` disables swap for the container. Without it, Docker allows as much swap as RAM, and a swapping JVM gets slow without failing, which is the "machine becomes unusable" failure this change is about. With no swap, an overrun is an OOM kill of that container only, visible in `docker compose ps` and restarted by the policy.
- Kibana's Node heap is capped below the container limit so V8 collects garbage before the kernel kills the process.
- `xpack.ml.enabled=false`: machine learning starts a native process with its own off-heap memory, which does not fit the limit and is not used by any phase.
- *Alternative: `deploy.resources.limits.memory`.* Same effect in Compose v2, but `mem_limit`/`memswap_limit` sit next to each other at service level and the swap limit has no `deploy` equivalent.
- *Alternative: limit every service now.* Deferred: the proposal keeps this change to the new services. Task 4 measures the rest so a follow-up can be argued from numbers.

### 3. `kibana_system` password set by a one-shot service

`elasticsearch-setup` uses the Elasticsearch image (for its `curl`), waits for `elasticsearch` to be healthy (`depends_on: condition: service_healthy`), then calls `POST /_security/user/kibana_system/_password` as `elastic`, and exits 0. `kibana` depends on it with `condition: service_completed_successfully`. It has `restart: "no"`.

- The call is idempotent, so it runs on every start. That also repairs a volume where the password was set from an older secret.
- *Alternative: Kibana as `elastic`.* Kibana 8+ refuses to start with the `elastic` superuser.
- *Alternative: a service account token for Kibana.* Needs `elasticsearch-service-tokens` inside the Elasticsearch container and a file shared through a volume; more moving parts than one HTTP call.
- *Alternative: set it in `post-create.sh`.* That runs in `dev`, which must not hold the `elastic` password.

### 4. Health checks and reachability

- `elasticsearch`: `curl -s -u elastic:$ELASTIC_PASSWORD 'http://localhost:9200/_cluster/health?wait_for_status=yellow&timeout=1s'` succeeds. A single node with replicas stays yellow forever, so yellow counts as healthy.
- `kibana`: `/api/status` reports `available`. With `status.allowAnonymous` left at its default (`false`), an unauthenticated caller gets a redacted response with only the overall level, which is enough for the check and for the agent from `dev` at `kibana:5601`. Setting it to `true` returns the full status (versions, build, host memory, every plugin) without login, so it stays off. (Planned as `true`; Kibana 9.5's status route returns the full response whenever anonymous access is allowed.) Port published as `127.0.0.1:5601:5601`, added to `forwardPorts` in `devcontainer.json` with the label "Kibana".
- Elasticsearch publishes no host port, like the Collector. The maintainer uses Kibana's Dev Tools; the `dev` container reaches `elasticsearch:9200` but has no credentials, which is enough to check it answers 401.
- `dev` keeps depending on `postgres` only, so the editor does not wait for Kibana's slow first start (1–2 minutes).

### 5. Kibana settings

`ELASTICSEARCH_HOSTS=http://elasticsearch:9200`, `ELASTICSEARCH_USERNAME=kibana_system`, `ELASTICSEARCH_PASSWORD`, and one generated key used for `XPACK_SECURITY_ENCRYPTIONKEY`, `XPACK_ENCRYPTEDSAVEDOBJECTS_ENCRYPTIONKEY` and `XPACK_REPORTING_ENCRYPTIONKEY` (the pattern in Elastic's own compose example). The saved-objects key matters for step B: APM and alerting store encrypted saved objects, and without a stable key they break on every restart. `TELEMETRY_OPTIN=false`, like Langfuse's `TELEMETRY_ENABLED=false`.

### 6. Secrets in `.devcontainer/.env`, appended when missing

New variables: `ELASTIC_PASSWORD` (`hex 24`), `KIBANA_SYSTEM_PASSWORD` (`hex 24`), `KIBANA_ENCRYPTION_KEY` (`hex 32`, 64 chars; Kibana needs at least 32).

- `init-env.sh` writes them in the new-file branch. For existing files it gets a small `ensure_secret NAME VALUE` helper: if `NAME` has no value, append `NAME=VALUE` (keeping the last line intact), print one line, and touch nothing else. The `LANGFUSE_OTLP_AUTH` branch stays as is.
- Compose passes them with `${VAR:?}` only to `elasticsearch`, `elasticsearch-setup` and `kibana`. `dev` gets nothing new.
- `.env.example` gets the three names with one comment each.

### 7. Verification split

- Agent, from `dev`: `curl -s -o /dev/null -w '%{http_code}' elasticsearch:9200` gives 401; `curl -s kibana:5601/api/status` shows `available`; `free -h` before and after; `git grep` and `env` for secret hygiene.
- Maintainer, on the host: `docker stats --no-stream` with everything up, heap and limits via `docker compose exec`, the Kibana login, and a restart that keeps a test document. Kibana opening with the machine still responsive is the "Pronto quando".

## Risks / Trade-offs

- [Kibana 9 needs more than 1 GiB at startup or when APM opens, and gets OOM-killed in a loop] → `docker inspect` shows a growing `RestartCount` and `journalctl -k` on the host shows `Memory cgroup out of memory: Killed process`; `.State.OOMKilled` only describes the current run and is false again after the restart. Raise Kibana to 1.5 GiB (and its Node heap to 1 GiB) in this change and record why; the spec's number is updated with it.
- [512 MiB heap is too small once step B indexes traces, logs and metrics] → circuit-breaker errors in the Collector's export counters and in Kibana. Revisit the limit then, with the measured index size; not a problem with an empty cluster.
- [Low `vm.max_map_count` on the host] → not enforced in single-node mode; at worst a startup warning. If Elasticsearch fails on mmap, set `node.store.allow_mmap=false`.
- [Disk watermarks: at 90% disk use Elasticsearch makes indices read-only] → the host is at 22% today; left at defaults so a full disk is visible rather than hidden.
- [Up to 2.5 GiB more RAM with everything up] → that is the point of the limits: the cost is bounded and measured in task 4. If available memory drops too low, the follow-up limits the existing services (ClickHouse is the likely first one).
- [Anonymous callers see Kibana's overall status level] → loopback only, overall level only; `status.allowAnonymous` stays off so details need a login.
- [The `elastic` password is a superuser credential] → it lives only in the gitignored `.devcontainer/.env` and the two services that need it.

## Migration Plan

1. Pull, then rebuild or restart the dev container: `init-env.sh` appends the three secrets, and compose creates the new services and the `elasticsearch_data` volume.
2. First start takes a few minutes (image pulls, Kibana's first boot). Kibana at http://localhost:5601, user `elastic`, password from `.devcontainer/.env`.
3. Rollback: revert the commit and restart. The extra lines in `.devcontainer/.env` are harmless; remove the volume with `docker volume rm fornada_devcontainer_elasticsearch_data` if wanted.
