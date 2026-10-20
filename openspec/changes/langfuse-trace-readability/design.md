# Design

## Context

- The Collector fans traces out to two pipelines. `traces/langfuse` has no processors and exports spans as the app sent them; `traces/elastic` runs `transform/redact` (which deletes `gen_ai.input.messages` and `gen_ai.output.messages` from every service's spans) and `elasticapm`. The Collector gives each pipeline whose processors change data its own copy, so a processor in one pipeline never changes what the other exports.
- Langfuse runs v4.53 in `events_only` mode. A trace has no input or output of its own: the trace list and the session page show the root observation's. Every observation has a level (`DEBUG`, `DEFAULT`, `WARNING`, `ERROR`), and the trace tree's "Min Level" filter defaults to `DEFAULT`.
- Every turn's root is a CLIENT span from the chat or the simulator (`client-tracing`), named after the HTTP route. Under it come the API's SERVER span, `fastapi.endpoint`, then `invoke_agent`, which already carries the turn's messages when the API captures content (`agent-tracing`).
- Manual probes on 2026-10-20 (synthetic traces sent straight to Langfuse, `service.name` `level-probe`):
  1. Five spans with `langfuse.observation.level=DEBUG`, three of them between the root and `invoke_agent`: the default tree showed `turn` → `invoke_agent` → `chat` / `calculate_quote` / `chat`, with the note "5 hidden observations below DEFAULT level. Show all". Langfuse hangs the children of a hidden span on its nearest visible ancestor.
  2. `gen_ai.input.messages` and `gen_ai.output.messages` on a root SPAN with only HTTP attributes: Langfuse showed them as the root's input and output, and kept the observation type SPAN.

## Goals / Non-Goals

**Goals:**
- A turn reads in Langfuse as root → agent → model calls and tools, with the turn's conversation on the root.
- No `langfuse.*` attribute in app code, and nothing new reaches Elasticsearch.

**Non-Goals:**
- Rewriting traces already in Langfuse.
- Spans per LangGraph node, as LangSmith shows. The graph is the model ↔ tools loop, which the `chat` and tool spans already show.
- Changing which spans exist or what the API sends.

## Decisions

### 1. Hide infrastructure spans with the `DEBUG` level, in the Collector

A `transform/langfuse_view` processor in `traces/langfuse` sets `span.attributes["langfuse.observation.level"] = "DEBUG"` where the span has a parent, has no `gen_ai.operation.name` and its status is not ERROR. Sketch (check the OTTL paths against EDOT 9.5.5's transform processor docs when implementing):

```yaml
transform/langfuse_view:
  error_mode: ignore
  trace_statements:
    - set(span.attributes["langfuse.observation.level"], "DEBUG") where span.parent_span_id.string != "0000000000000000" and span.attributes["gen_ai.operation.name"] == nil and span.status.code != STATUS_CODE_ERROR
```

- **Root test:** OTTL's `span.parent_span_id.string` hex-encodes the 8-byte id, so a root reads `"0000000000000000"`, never `""` (checked in the v0.161.0 source and with an `otelcol-contrib` 0.161.0 run). The string is compared because OTTL has no comparison rule for `SpanID` values.
- **Why the Collector:** what counts as noise is a property of the Langfuse view, not of the app. Kibana needs those spans at full weight, and the app stays vendor-neutral.
- **Why keep ERROR spans visible:** a failed SQL statement or model HTTP call is exactly what an error analysis looks for; hiding it behind a filter would bury the evidence.
- **Why `error_mode: ignore`:** unlike the redaction, this is presentation. A statement error should send the span to Langfuse unmarked, not drop the batch.
- *Alternative: drop the spans in the Langfuse pipeline (`filter` processor).* Rejected: `invoke_agent` would point to a parent that never arrives, and Langfuse would show it as an orphan; the SQL detail would be gone from Langfuse for good.
- *Alternative: set the level in the app.* Rejected: it would put a `langfuse.*` attribute on every instrumentor's spans, through a span processor in three apps.

### 2. Rename the turn's root to `turn`, in the Collector

The same processor runs `set(span.name, "turn")` on root spans with `url.template` == `/conversations/{conversation_id}/messages`.

- **Why the span name:** in v4 the trace name shown in the list is the root observation's name, and the tree shows it too. Renaming in the Langfuse pipeline keeps the HTTP name in Elasticsearch, where Kibana APM groups transactions by it and the HTTP semconv requires it.
- *Alternative: `langfuse.trace.name`.* Rejected: Langfuse's v4 docs ask for it on every span to be filterable, and it would not rename the root in the tree.

### 3. Root content as `gen_ai.*` attributes on the client span

With capture on, the client span gets `gen_ai.input.messages` (one `user` message with the posted text) and, once replies are read, `gen_ai.output.messages` (one `assistant` message per reply). The JSON shape is the API's (`span_content.py`: `{"role", "parts": [{"type": "text", "content"}]}`, `ensure_ascii=False`).

- **Why these names:** probe 2 shows Langfuse reads them on a plain span, and `transform/redact` already deletes them for Elasticsearch, so the redaction needs no change.
- **Trade-off:** the GenAI semconv defines these attributes for GenAI operation spans, not HTTP client spans. Here the HTTP call is the whole turn of a conversational agent, so its input and output are the turn's messages; the attributes carry the same meaning.
- *Alternative: `langfuse.observation.input` / `output`, set in the app or mapped by the Collector from a `fornada.*` attribute.* Rejected: vendor names in the app, or a mapping step plus a new entry in the redaction denylist for no gain.
- *Alternative: have the API put the content on its SERVER span.* Rejected: with a client in front, the SERVER span is not the root, and the root is what Langfuse shows.

### 4. One switch name, read by each client

The chat and the simulator read `TELEMETRY__CAPTURE_CONTENT` the way each already reads `TELEMETRY__ENABLED`: the chat's frozen dataclass from the environment, the simulator's pydantic `TelemetrySettings`. One name means the root `.env` turns capture on or off for all three processes at once. Each app gets its own small function to build the message JSON: the workspace has no shared package, and the clients do not import the API (decision in `add-chainlit-chat`).

### 5. Reading a session

The API also puts `session.id` on its GenAI spans (`agent-tracing`), so the session page still lists `invoke_agent` and the `chat` observations under each turn. The readable view is the session page filtered to **Is Root Observation = true**: one block per turn with the customer's message and the bot's replies. `AGENTS.md` documents it, together with the trace page's "Min Level". `session.id` stays on every span, as Langfuse's v4 docs recommend for filtering observations by session.

## Risks / Trade-offs

- [Langfuse may change how it renders hidden `DEBUG` spans] → The probe is recorded above; the verification task repeats it on a real turn. If a later version hides whole subtrees, removing one processor restores today's view.
- [Conversation text in two more processes] → Only with capture on, only to the Collector, and only Langfuse receives it, which already holds the same text from the API. The LGPD map (phase 7) lists the clients as sources.
- [A span the app should show gets hidden because it lacks `gen_ai.operation.name`] → Every span the agent instrumentation creates has it today (`agent-tracing`). A new kind of span added later would land at `DEBUG` and show under "Show all"; the spec scenario on the agent's visibility catches a regression.
- [Root output missing when a turn fails] → Intended: a failed post keeps the input only, so filtering the session by "has output" would hide failed turns. `AGENTS.md` says to filter by root, not by output.

## Migration Plan

1. Merge; restart `edot-collector` on the host (`docker compose -p fornada_devcontainer restart edot-collector`), since the config is mounted read-only and read at start.
2. Set `TELEMETRY__CAPTURE_CONTENT=true` in the root `.env` for the clients (already there for the API in `.env.example`).
3. Rollback: remove `transform/langfuse_view` from `traces/langfuse` and restart the Collector; unset the switch for the clients.
