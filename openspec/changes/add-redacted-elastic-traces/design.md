# Design

## Context

- The API emits `invoke_agent`, `chat` and `execute_tool` spans by hand (`agents/attendant/attendant.py`, `nodes.py`), with attribute names in `agents/attendant/tracing.py`. None of them carries content today. The `execute_tool` wrapper in `nodes.py` already has the tool call (name, id, args) and the `ToolMessage` it returns.
- v0 has no "session phone". A phone exists only as a tool argument chosen by the LLM (`create_order`, `get_order`, `cancel_order`, `send_message`, and `escalate_to_human` when given), always under the argument name `phone`. `services/phones.normalize_phone` turns it into E.164 or raises `InvalidPhone`.
- The Collector (EDOT 9.5.5, Collector core v0.161.0) has one traces pipeline, `otlp → otlphttp/langfuse`, with no processors. Elasticsearch and Kibana 9.5.5 are running, with security on over plain HTTP. `elasticsearch-setup` is a one-shot service that calls the security API as `elastic`.
- The EDOT docs say that Kibana APM needs both the `elasticapm` processor, which enriches spans, and the `elasticapm` connector, which builds the pre-aggregated APM metrics. Both ship with EDOT, not with upstream contrib. The `elasticsearch` exporter's `otel` mapping mode is the default and keeps OTel attribute names.
- Langfuse's documented OTel mapping lists `langfuse.observation.input/output`, `gen_ai.prompt/completion`, `input.value/output.value`, and `gen_ai.tool.call.arguments/result` as a fallback. It does not list `gen_ai.input.messages`. Whether Langfuse v4 renders that attribute as input has to be checked (decision 6).
- Core and periphery: "the pipelines in the Collector config" are core in phase 2. The OTTL statements and the pipeline wiring are left as `TODO(human)` with a commented sketch. The app attributes are fixed by the spec delta, which the maintainer reviews, and the agent writes them. The Elasticsearch user, secrets and compose changes are periphery.

## Goals / Non-Goals

**Goals:**
- One set of spans from the app, and two views produced by the Collector: full content in Langfuse, redacted content in Elasticsearch.
- Phones stay joinable in Kibana (same phone, same hash) without being recoverable by brute force.
- The redaction can be checked with a repeatable test that does not depend on an LLM.

**Non-Goals:**
- Detecting PII inside free text (Presidio, phase 6). This change uses a denylist of attributes, not content scanning.
- Redacting span events (`exception.message`); see Open Questions.
- Logs and metrics signals from the app.

## Decisions

### 1. Content attributes follow the GenAI semconv JSON format

`gen_ai.input.messages`, `gen_ai.output.messages` and `gen_ai.system_instructions` hold JSON strings in the convention's message shape:
- messages look like `{"role": ..., "parts": [...]}`;
- parts are `text`, `tool_call` (`id`, `name`, `arguments`) and `tool_call_response` (`id`, `response`);
- output messages also carry `finish_reason`.

The serializer lives in one function next to `tracing.py`. It converts LangChain `BaseMessage`s and nothing else.

- On `chat` spans, the input is everything sent to the model except the system message, which goes to `gen_ai.system_instructions`. This repeats the history on every call: a 10-turn conversation sends its first message 10+ times. That is accepted, because it matches what the model actually saw, and that is what phase 3 annotates.
- On `invoke_agent` spans, the input is only the turn's customer message and the output is the turn's replies. This is the readable summary of a turn.
- On `execute_tool` spans, `gen_ai.tool.call.arguments` is `json.dumps(args)` and `gen_ai.tool.call.result` is the `ToolMessage` content string. That string is already JSON from `run()`.
- *Alternative: `langfuse.observation.input/output` in app code.* Rejected. AGENTS.md forbids vendor attributes in the app, and Elasticsearch would see a Langfuse-specific name.
- *Alternative: span events (the older `gen_ai.content.prompt` events).* Rejected. The current convention moved content to attributes, and events would need their own redaction path in the Collector.
- `gen_ai.tool.definitions` stays off. It is large, it does not change within a prompt version, and `fornada.prompt.version` already identifies it.

### 2. Capture switch: `TELEMETRY__CAPTURE_CONTENT`, off by default

The setting is a bool in `TelemetrySettings`. The graph receives it when it is built, as it already receives the provider and the model, and the nodes check it before serializing anything. Off by default keeps tests and CI from building JSON for nothing. It also follows the semconv rule that content capture is opt-in, and it gives phase 7's LGPD map a single switch to point at. The root `.env.example` documents it, and the dev `.env` turns it on.

- *Alternative: `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`.* Rejected. `app-tracing` already says that `OTEL_*` variables do not configure the pipeline. All settings go through `Settings`.

### 3. The phone attribute is set in the `execute_tool` wrapper

When capture is on and the tool call's args contain `phone`, the wrapper calls `normalize_phone` and, if it succeeds, sets `fornada.customer.phone`. If it raises `InvalidPhone`, the attribute is left out. The raw argument is still in `gen_ai.tool.call.arguments`, which the Elasticsearch pipeline deletes.

- *Alternative: each tool sets the attribute on the current span, as `check_capacity` does with `free_kg`.* Rejected. Five tools would repeat the same lines, and a new tool with a phone could easily forget them. The wrapper handles every tool in one place, and the argument name is shared across tools (`PhoneArg`).
- *Alternative: the raw value when it does not normalize.* Rejected. The raw value could be any text the LLM produced (an injection payload, a CPF), and the Collector would hash it as if it were a phone.
- The name is `fornada.customer.phone`, not `user.id`. Langfuse would turn `user.id` into its "user" entity, but one v0 conversation can touch several phones (the exfiltration case), so the phone does not identify the user.

### 4. Collector: two pipelines on one receiver, redaction only on the Elasticsearch side

Sketch (core: the maintainer writes the final version):

```
traces/langfuse:  otlp → (none)                                   → otlphttp/langfuse
traces/elastic:   otlp → transform/redact → elasticapm (processor) → elasticsearch/otel, elasticapm (connector)
metrics/apm:      elasticapm (connector) → elasticsearch/otel
```

- Fan-out comes from the receiver feeding two pipelines. The Collector's fan-out consumer gives a separate copy to each pipeline whose processors mutate data (`transform` declares that it does), so redaction in `traces/elastic` cannot change what reaches Langfuse. The spec's "Langfuse keeps the content" scenario checks this, so it does not depend on trusting the implementation.
- Redaction runs before `elasticapm`. If it ran after, the processor and the connector would see the content and could copy it into derived fields or metrics.
- The old `traces` pipeline is renamed `traces/langfuse`, with the same components. This is a config detail, not a behavior change.
- *Alternative: one pipeline with `routing`, or a `transform` running before both exporters.* Rejected. Either one strips content from Langfuse, or it needs per-exporter logic that the Collector does not have.
- *Alternative: redact in the app, with two exporters in the SDK.* Rejected. It is a second pipeline in every process (API, chat, simulator), and the stack's design puts PII handling in the Collector.

### 5. Redaction statements: denylist delete, salted SHA-256 for the phone

The intent, as OTTL in the `span` context (sketch for the `TODO(human)`):

```
delete_matching_keys(attributes, "^gen_ai\\.(input\\.messages|output\\.messages|system_instructions|tool\\.call\\.(arguments|result))$")
set(attributes["fornada.customer.phone"], SHA256(Concat(["${env:PHONE_HASH_SALT}", attributes["fornada.customer.phone"]], ""))) where attributes["fornada.customer.phone"] != nil
```

- Salted, because Brazilian mobile numbers are a space of about 10^10. An unsalted SHA-256 of every number can be computed in minutes, and that would turn the hash back into the phone. The salt is a dev secret (`hex 32`), so the same phone gets the same hash, as the spec requires.
- *Alternative: HMAC.* OTTL has no HMAC function. With a fixed-length secret prefix and an input that is never extended, `SHA256(salt ‖ phone)` is enough for pseudonymization. It is not a MAC.
- *Alternative: an allowlist (`keep_matching_keys` with the known attributes).* It is safer against new content attributes, but it would drop the HTTP, `service.*` and `elasticapm` attributes unless they were all listed, and that list breaks on every semconv bump. The denylist is kept, and Risks covers what it misses.
- *Alternative: `redaction` processor (contrib).* It masks values that match patterns but cannot hash with a salt, and it is not certain to be in the EDOT 9.5.5 component list. `transform` is in EDOT.
- The statements apply to spans from every service, not only `fornada-api`. The clients emit no content today, so this costs nothing and still covers a future client that does.

### 6. Langfuse rendering is checked first, with a Collector-side fallback

The first implementation task sends one span with `gen_ai.input.messages` to Langfuse and checks whether the observation shows input and output.
- If it does, nothing more is needed.
- If it does not, `traces/langfuse` gets its own `transform/langfuse` that copies `gen_ai.input.messages` to `langfuse.observation.input` and `gen_ai.output.messages` to `langfuse.observation.output`, on `invoke_agent` and `chat` spans. Tool spans already map through Langfuse's documented `gen_ai.tool.call.*` fallback.

This keeps `langfuse.*` attributes out of app code, as `add-agent-spans` decided. Copying adds attributes and leaves the original content untouched, so the spec's "exactly as the app sent them" still holds.

**Observed (task 1.1, Langfuse v4.53, 2026-10-13):** a synthetic trace with the semconv attributes (`b9a0f9cda2cdb0685b6b9f2c4ac8198f`) rendered fully with no Collector mapping, so the fallback is not needed:
- `invoke_agent`: `gen_ai.input.messages` and `gen_ai.output.messages` appear as User and Assistant.
- `chat`: `gen_ai.system_instructions` appears as System, the input as User, and a `tool_call` output part as an Assistant tool call, with name, call id and arguments.
- `execute_tool`: `gen_ai.tool.call.arguments` and `gen_ai.tool.call.result` appear as Input and Output, parsed as JSON. The observation is shown under the tool name (`get_order`).

### 7. Elasticsearch user for the Collector

`elasticsearch-setup` gains two idempotent calls, a `PUT` for the role and a `PUT` for the user, run before the existing `kibana_system` call:
- Role `otel_writer`: index privileges `auto_configure` and `create_doc` on `traces-*`, `metrics-*` and `logs-*` (logs is included so the next change needs no new role), and cluster privilege `monitor`. The exact list is checked against the exporter's docs during implementation.
- User `otel_collector` with role `otel_writer`. Its password is `ELASTIC_OTEL_PASSWORD`.

The exporter authenticates with that user and password. `edot-collector` gets `depends_on: elasticsearch-setup: service_completed_successfully`, so the user exists before the first export.

- *Alternative: an API key.* Creating it needs the `elastic` password at runtime and leaves a generated key to store somewhere. A user with a password from `.env` follows the `kibana_system` pattern.
- *Alternative: the `elastic` superuser.* Rejected. The Collector would hold a superuser credential.
- `depends_on` delays the Collector, and with it Langfuse export, until Elasticsearch is healthy (about 30–60 s on a cold start). This is accepted: `dev` does not wait on the Collector, and the app's batch exporter retries.

New secrets: `ELASTIC_OTEL_PASSWORD` (`hex 24`) and `PHONE_HASH_SALT` (`hex 32`). They are added through `ensure_secret`, with one comment each in `.env.example`, and passed only to `edot-collector`. `elasticsearch-setup` also gets the password.

### 8. Verification split

- **Unit and integration (agent):** in-memory exporter tests for each new attribute, for both switch states and for the invalid phone. There is also a "same replies with capture on and off" test, mirroring the existing tracing-on/off test.
- **Collector redaction (agent, from `dev`):** with the API's tracing on, POST a message that makes the model call `get_order` with a known fake phone, and record the trace id from the SERVER span. Langfuse's public API (`/api/public/traces/{id}`, with the project keys the maintainer provides) shows the content. Collector metrics show the Elasticsearch exporter's sent and failed counts.
- **Elasticsearch side (maintainer, Kibana):**
  - APM shows the services and the trace.
  - In Dev Tools, run `GET traces-*/_search` for the trace id and check that none of the five content attributes appears and that `fornada.customer.phone` is a 64-character hex.
  - Search all fields for the phone digits and for a word from the message, and expect 0 hits.
  - Run the least-privilege check with the `otel_collector` credential.
- **Deterministic smoke (maintainer, host):** `telemetrygen` with `--telemetry-attributes` setting `gen_ai.input.messages` and `fornada.customer.phone`. This tests the redaction without an LLM and gives one fixed input to compare in both backends.

## Risks / Trade-offs

- [Denylist misses content in another attribute, such as `exception.message` from `record_exception`, `url.full`, or a future `gen_ai.*` content attribute] → The Elasticsearch check searches every field for the phone digits and a message word, not only the five known keys. Any hit becomes a new statement here. Phase 6 replaces this with Presidio.
- [Fan-out copy assumption is wrong and redaction leaks into Langfuse] → The spec scenario "Same trace, two views" is the check. If it fails, `traces/langfuse` is fed from a `forward` connector instead of sharing the receiver.
- [`gen_ai.input.messages` on `chat` spans grows with the history, which means big spans and slower export] → It is bounded by the conversation cost limit (phase 4 scenario of 60 turns). The verification run records the size of the largest `chat` span's `gen_ai.input.messages` in a long simulated conversation. If it is a problem, the SDK's attribute length limit is a one-line cap.
- [Elasticsearch heap (512 MiB) under first real load] → Watch the Collector's failed-span count and Elasticsearch's circuit-breaker errors during the verification batch. `add-elastic-stack` already marked this as the point to revisit the limit.
- [`elasticapm` components or `otel` mapping need a newer stack than 9.5.5] → Versions match (EDOT 9.5.5 with Elasticsearch 9.5.5), and 9.x is the documented target for `elasticapm`.
- [Salt rotation changes every hash] → Accepted in dev. Rotation is a phase 7 governance note.
- [Langfuse now holds customer text and phones] → The data is fake, the deployment is dev only, and capture is off by default. This is recorded in proposal Impact for the phase 7 LGPD map.

## Migration Plan

1. Pull and restart the dev container. `init-env.sh` appends the two secrets. `elasticsearch-setup` creates the role and the user. The Collector restarts with the new config.
2. Set `TELEMETRY__CAPTURE_CONTENT=true` in the root `.env` next to `TELEMETRY__ENABLED=true`.
3. Rollback: revert the commit and restart. The `otel_collector` user stays in Elasticsearch and can be deleted from Dev Tools. The `traces-*` data streams can be deleted the same way.

## Open Questions

- Should `exception.message` in span events also be removed for Elasticsearch? `add-agent-spans` judged provider and driver errors free of customer text. The Elasticsearch-wide search in the verification run answers this with data. If anything turns up, it is one more OTTL statement in `spanevent` context, with no change to the specs.
- Should `fornada.prompt.version` be copied to `langfuse.version` in `traces/langfuse`? This is deferred, as the proposal says. If decision 6's fallback adds `transform/langfuse` anyway, it is a one-line addition there.
