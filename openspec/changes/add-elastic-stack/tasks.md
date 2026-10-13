# Tasks

All of this is periphery (AGENTS.md, phase 2: "Elastic and Langfuse compose, credentials"), so the agent does it without `TODO(human)` markers. The dev container has no Docker socket: every step that starts, restarts or inspects containers is run by the maintainer on the host, and the agent checks what it can from `dev`.

## 0. Baseline

- [x] 0.1 Before any change, with the current stack up, record available memory from `dev` (`free -h`) and ask the maintainer for `docker stats --no-stream` from the host. Paste both in the step summary; task 4 compares against them.

## 1. Secrets (`elastic-stack`: secrets stay out of the repo and the workspace)

- [x] 1.1 Update `.devcontainer/init-env.sh` (design.md, decision 6): the new-file branch writes `ELASTIC_PASSWORD`, `KIBANA_SYSTEM_PASSWORD` and `KIBANA_ENCRYPTION_KEY`; an `ensure_secret` helper appends each one to an existing file that lacks it, with no other line changed. Verify against copies in the scratchpad (no file, a file from before `LANGFUSE_OTLP_AUTH`, a current file, a file already updated): `diff` shows only appended lines, a second run changes nothing, and `KIBANA_ENCRYPTION_KEY` is at least 32 characters.
- [x] 1.2 Add the three variables with one comment each to `.devcontainer/.env.example`. Verify every variable `init-env.sh` writes appears in the template.

## 2. Services (`elastic-stack`: run with the dev environment, reachability, authentication, `kibana_system`, persistence, memory budget)

- [x] 2.1 Add `elasticsearch` to `.devcontainer/compose.yaml` (decisions 1, 2 and 4): image `docker.elastic.co/elasticsearch/elasticsearch:9.5.5`, single-node and security settings, `ES_JAVA_OPTS`, `xpack.ml.enabled=false`, `mem_limit`/`memswap_limit` 1536m (raised from 1g after an OOM kill, design.md decision 2), health check, `elasticsearch_data` volume, no `ports`, `restart: unless-stopped`, secrets with `${VAR:?}`. Comment the memory numbers and why swap is off.
- [x] 2.2 Add `elasticsearch-setup` (decision 3): one-shot, depends on `elasticsearch` healthy, sets the `kibana_system` password, `restart: "no"`.
- [x] 2.3 Add `kibana` (decisions 2, 4 and 5): image `docker.elastic.co/kibana/kibana:9.5.5`, connection as `kibana_system`, encryption keys, `TELEMETRY_OPTIN=false`, no `STATUS_ALLOWANONYMOUS` (design.md decision 4), `NODE_OPTIONS`, `mem_limit`/`memswap_limit` 1g, health check on `/api/status`, `127.0.0.1:5601:5601`, depends on `elasticsearch-setup` completed successfully.
- [x] 2.4 Update the compose header comment (services list, Elastic tags kept equal to the EDOT Collector's) and add 5601 to `forwardPorts`/`portsAttributes` ("Kibana") in `.devcontainer/devcontainer.json`. Verify with `grep` that the Elastic secrets are referenced only by the three Elastic services, that the three Elastic tags match, and that `python3 -c 'import yaml,sys; yaml.safe_load(open(sys.argv[1]))'` parses the compose file.
- [x] 2.5 Update AGENTS.md "Dev environment": the new services, Kibana URL and login (`elastic`, password in `.devcontainer/.env`), the memory limits and where to see OOM kills, and that Elasticsearch has no host port. Verify no remaining text says Elastic is still to come in the dev environment (`grep -n -i "elastic" AGENTS.md`).
- [x] 2.6 Maintainer rebuilds the dev container. Agent checks from `dev`: `curl -s -o /dev/null -w '%{http_code}\n' elasticsearch:9200` prints `401` and `curl -s kibana:5601/api/status` reports `available`. Maintainer confirms on the host that `docker compose -p fornada_devcontainer ps` shows `elasticsearch-setup` exited 0 and no Elastic service restarting, and `docker compose -p fornada_devcontainer port elasticsearch 9200` prints nothing.

## 3. Behavior checks (`elastic-stack` scenarios)

- [ ] 3.1 Maintainer opens http://localhost:5601 on the host, logs in as `elastic` and reaches the Kibana home page. This is the first half of the "Pronto quando".
- [x] 3.2 Limits: maintainer runs `docker inspect -f '{{.HostConfig.Memory}} {{.HostConfig.MemorySwap}}'` for `elasticsearch` and `kibana` (expect `1610612736 1610612736` and `1073741824 1073741824`) and, in Kibana Dev Tools, `GET _nodes/stats/jvm?filter_path=**.heap_max_in_bytes` (expect 536870912). Record the outputs.
- [x] 3.3 Persistence: in Kibana Dev Tools, index one test document; maintainer restarts the dev environment; the document is still returned by a search and Kibana logs in again without any manual step. Delete the test index afterwards.
- [x] 3.4 Secret hygiene: `git grep` finds none of the three secret values (maintainer provides them or runs the grep on the host), and `env | grep -i -E 'elastic|kibana'` in `dev` prints nothing. Record the result.

## 4. Memory with everything up (`elastic-stack`: fixed memory budget, machine stays usable)

- [ ] 4.1 With every service up and idle for a few minutes and Kibana open in the browser (including one visit to Observability, the heaviest app it will open in step B), maintainer runs `docker stats --no-stream` on the host; agent runs `free -h` in `dev`. Write a before/after table (per service, total, available host memory) against the 0.1 baseline in the step summary. Pass: Elasticsearch under 1.5 GiB and Kibana under 1 GiB, `RestartCount` 0 and no `Killed process` in `journalctl -k`, and the maintainer confirms the editor and browser stay responsive. That is the second half of the "Pronto quando".
- [ ] 4.2 If Kibana is OOM-killed or Elasticsearch fails at 4.1, apply the fallback in design.md (Risks) in this change, update the numbers in the spec, design and AGENTS.md together, and repeat 4.1. If available memory is too low, record which existing service uses the most and propose the follow-up change; do not limit it here.

## Workflow follow-up

- One commit per group, with maintainer approval before each: `chore:` for 1, `feat:` for 2, `docs:` if 4.2 changes any number.
- Open the PR, then `/opsx:archive` after merge.
