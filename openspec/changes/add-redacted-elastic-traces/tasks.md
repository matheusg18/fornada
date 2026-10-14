# Tasks

Tasks marked `TODO(human)` are core (AGENTS.md, phase 2: "the pipelines in the Collector config"). The agent leaves the marker with a commented sketch from design.md, then stops and waits for the maintainer. The app attributes repeat the pattern of the spans the maintainer already wrote, so the agent writes them, mirroring that code. Run `uv run task check` from `apps/api` at the end of each app group.

## 1. Check how Langfuse renders the content attributes

- [x] 1.1 Send one synthetic trace from `dev` to the Collector, using a short Python script in the scratchpad with the OTLP/HTTP exporter. It has one span with `gen_ai.operation.name=chat`, `gen_ai.input.messages`, `gen_ai.output.messages` and `gen_ai.system_instructions` in semconv JSON, and one span with `gen_ai.tool.call.arguments` and `gen_ai.tool.call.result`. Ask the maintainer to open it in Langfuse and record whether the input and output render on each observation (design.md, decision 6). Verify with the maintainer's answer, written into design.md decision 6 as "observed".

## 2. Content capture setting

- [x] 2.1 Write failing tests in the settings test module for `TELEMETRY__CAPTURE_CONTENT`: default off, `true` turns it on, and `maybe` fails with an error naming the variable (`app-config` delta). Verify they fail.
- [x] 2.2 Add `capture_content: bool = False` to `TelemetrySettings` and document it in the root `.env.example` (design.md, decision 2). Passing it to the graph and the attendant moves to 3.3, where it is used and tested. Verify the 2.1 tests pass and `uv run task check` passes.

## 3. Content attributes on agent spans

- [x] 3.1 Add the attribute names to `agents/attendant/tracing.py`: `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result` and `fornada.customer.phone`. Also add a serializer from LangChain messages to semconv message JSON (text, `tool_call` and `tool_call_response` parts, and `finish_reason` on output; design.md, decision 1). Add unit tests for the serializer covering a user message, an AI message with text, an AI message with two tool calls and a tool message. Verify the tests pass.
- [x] 3.2 Write failing tests in `tests/unit/agents/test_agent_tracing.py` for the `agent-tracing` delta:
  - `chat` input, output and system instructions with capture on, including the tool-call answer and the provider error case;
  - `invoke_agent` input and output with one message and two replies;
  - `execute_tool` arguments and result, including the error result;
  - `fornada.customer.phone` for `(81) 99999-1234`, the invalid phone, a tool with no phone, and capture off;
  - no content attribute and no phone with capture off;
  - no tool definitions on any span;
  - the same replies and stored messages with capture on and off.

  Verify they fail.
- [x] 3.3 Pass `capture_content` from the settings to `build_graph` and `GraphAttendant`, then set the attributes in `attendant.py` (turn span), in `nodes.py` (`call_model` and the `execute_tool` wrapper; the phone goes through `normalize_phone`, design.md decision 3), all behind the switch. Mirror the existing span code. Verify the 3.2 tests pass and `uv run task check` passes.

## 4. Elasticsearch user and secrets

- [x] 4.1 Add `ELASTIC_OTEL_PASSWORD` (`hex 24`) and `PHONE_HASH_SALT` (`hex 32`) to `.devcontainer/init-env.sh`, both in the new-file branch and through `ensure_secret`, and to `.devcontainer/.env.example` with one comment each (design.md, decision 7). Verify by running the script logic against a copy of an old `.env` in the scratchpad: the two lines are appended and every other line is unchanged.
- [x] 4.2 Extend `elasticsearch-setup` in `.devcontainer/compose.yaml`: idempotent `PUT` of role `otel_writer` (index privileges `auto_configure` and `create_doc` on `traces-*-*`, `metrics-*-*` and `logs-*-*`; no cluster privilege, per the EDOT `elasticsearch` exporter docs) and of user `otel_collector`, before the `kibana_system` call. Pass `ELASTIC_OTEL_PASSWORD` to it. Verify with `docker compose config` on the host (maintainer) or by reviewing the rendered YAML, and that `git grep` finds no secret values.
- [x] 4.3 Give `edot-collector` the environment variables `ELASTIC_OTEL_PASSWORD` and `PHONE_HASH_SALT`, and `depends_on: elasticsearch-setup: service_completed_successfully`. Verify that `env` in `dev` shows neither variable.

## 5. Collector fan-out and redaction

- [x] 5.1 Add the `elasticsearch/otel` exporter (endpoint `http://elasticsearch:9200`, user `otel_collector`, password from env, `mapping.mode: otel`), the `elasticapm` processor and the `elasticapm` connector to `.devcontainer/otel-collector/config.yaml`, with comments in the file's style. Check the key names against the EDOT 9.5.5 component docs. Rename `traces` to `traces/langfuse` with no other change. Leave the new pipelines out until 5.2. Verify the Collector starts cleanly (maintainer: `docker compose logs edot-collector`) and Langfuse still receives traces.
- [x] 5.2 TODO(human): write the `transform/redact` processor statements and the `traces/elastic` and `metrics/apm` pipelines (design.md, decisions 4 and 5). The agent leaves the marker in `config.yaml` with the sketch from design.md commented out. Verify the Collector starts cleanly and that `otelcol_exporter_sent_spans` for the Elasticsearch exporter grows after a turn (`curl -s edot-collector:8888/metrics | grep spans`).
- [x] 5.3 If task 1.1 showed that Langfuse does not render `gen_ai.input.messages`, write TODO(human) for `transform/langfuse` on `traces/langfuse`, copying it to `langfuse.observation.input` and `gen_ai.output.messages` to `langfuse.observation.output` (design.md, decision 6). Otherwise mark this task done with "not needed" and the evidence. Verify a `chat` observation shows input and output in Langfuse. *Not needed:* task 1.1 showed native rendering, and a real API turn (trace `c6bd4b8938fd8412206662280d415761`) showed User, System, history, tool arguments and result in Langfuse with no Collector mapping.
- [x] 5.4 Update AGENTS.md (Collector: fan-out, redaction, the new secrets, how to check the Elasticsearch side in Dev Tools) and the header comment in `config.yaml`. Verify the documented commands run as written.

## 6. End-to-end verification

- [x] 6.1 Deterministic smoke test: the maintainer runs `telemetrygen` on the host with `--telemetry-attributes` setting `gen_ai.input.messages` and `fornada.customer.phone` to known values. Check that Langfuse shows both in clear, and that in Kibana Dev Tools the content attribute is absent, the phone is a 64-character hex, and neither the phone digits nor the unsalted SHA-256 of the phone appear in any field (`telemetry-collector` delta). Record the queries and results in the step summary. *Done with a Python OTLP script from `dev` instead of `telemetrygen` (same fixed input, no LLM, no host step): one `execute_tool get_order` span with `gen_ai.tool.call.arguments` and `fornada.customer.phone` = `+5581999991234`, trace `f7732a8e564b611a3818154a8911191e`. Langfuse showed the arguments as Input and the phone in clear. Kibana Dev Tools showed 1 span with no content attribute, the phone as `fe618e59…ab06` (64 hex, unlike the unsalted SHA-256 of `+5581999991234` or `5581999991234`), and 0 hits for `"5581999991234"` across all fields.*
- [x] 6.2 Real turn: with `TELEMETRY__ENABLED=true` and `TELEMETRY__CAPTURE_CONTENT=true`, run a short simulator conversation that makes the model call `get_order` with a fake phone, and note one trace id. Langfuse shows the message text, tool arguments and phone. Kibana APM shows the trace from `fornada-simulator` to `fornada-api`. Dev Tools shows no content attribute, a hashed phone, and 0 hits for the phone digits and for one message word across all fields (the "Pronto quando"). Record the Elasticsearch exporter's sent and failed counts, and the size of the largest `gen_ai.input.messages`. *Done 2026-10-14:* one simulator conversation (persona `malandro`, other customer's order, 4 turns, `get_order`, `escalate_to_human` and `send_message` called), conversation `85ac37d4-633d-4c64-9d54-b364e7978919`, `get_order` turn trace `5265a0544f7e0953c965fc7d9da40866`. Langfuse: root is the `fornada-simulator` CLIENT span; `get_order` shows arguments (`81 95240-7908`), the full result (other customer's name and address: a v0 leak, input for phase 5) and `fornada.customer.phone` = `+5581952407908`. Kibana APM: services `fornada-simulator` and `fornada-api`, traces originate at `fornada-simulator`, dependency `api.anthropic.com:443` upstream of `fornada-api`. Dev Tools: 11 spans for the trace, none with a content attribute (usage, model, finish reasons and tool name kept), phone as `8250ed63…d5fb`; 0 hits for `5581952407908`, `5581988010005` or `95240-7908`, and 0 hits for `Lucca Moura`, `Alameda de Sales` or `Diego` across all fields. Collector: 350 spans sent to each exporter, no failures; 124 APM metric points to Elasticsearch. Largest `gen_ai.input.messages`: 4,989 bytes (14 messages, last model call of the 4th turn).*
- [ ] 6.3 Least privilege and outage: with the `otel_collector` credential, a `_search` and a `GET _security/user` are denied. With `elasticsearch` stopped, a turn still reaches Langfuse. With `langfuse-web` stopped, it still reaches Elasticsearch. Verify with the maintainer's observations and the Collector's metrics.

## Workflow follow-up

- Archive the change after the maintainer's review, and sync the `agent-tracing`, `telemetry-collector` and `app-config` specs.
- Remind the maintainer that the next step B change is logs and metrics (`LoggerProvider`, `MeterProvider`, their Collector pipelines). Remind them too of the open question about `exception.message` in span events, answered by the 6.2 search.
