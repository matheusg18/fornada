# Proposal

## Why

Each turn's trace starts today at the API's SERVER span. The clients that drive conversations, the Chainlit chat and the persona simulator, leave no trace. So a trace cannot show how long the customer waited, nor which persona and batch produced a conversation. Phase 3 reads 100–150 simulated conversations. Before that, every simulated conversation must show up in Langfuse as one session of whole traces, each tagged with the persona that played it. Step B adds the Elasticsearch fan-out. With client roots already in place, Kibana APM gets the client → API service map and the latency the client saw, next to the server's latency, without another change to the clients.

Phase 2 (instrumentation), step A: traces only, to Langfuse. The change stays within the frozen scope. It adds no tool and no agent behavior, and touches the two existing clients only to trace their calls.

## What Changes

- The chat and the simulator each set up their own OpenTelemetry tracer provider, with their own `service.name` (`fornada-chat`, `fornada-simulator`). Each exports over OTLP/HTTP to the Collector, behind the same `TELEMETRY__*` switch the API uses, which is off by default.
- Each customer message the chat or the simulator posts produces one span of kind CLIENT. It is the root of that turn's trace, and the client sends its context to the API in a W3C `traceparent` header. One trace per turn; the conversation is the session.
- The client span carries the conversation id as `session.id` and `gen_ai.conversation.id`, so the root observation belongs to the same Langfuse session as the agent's spans.
- Simulator client spans also carry the persona id and the batch run id. These stay on the client span. The API reads nothing from the client except `traceparent`.
- The persona's own LLM calls are not traced, so a session's cost in Langfuse is the agent's cost only.
- The simulator flushes its spans when a batch ends and shuts its provider down when the process exits. The notebook flushes after each run. A run that ends right away still exports every root span, so no trace reaches Langfuse with its root missing.
- The chat shuts its provider down when Chainlit stops.
- The notebook switches from `httpx` to `httpx2`, the client the simulator package uses.

## Capabilities

### New Capabilities
- `client-tracing`: how the clients that call the conversation API (chat UI and persona simulator) trace each posted message: their resource, the CLIENT span per message, context propagation to the API, session and persona attributes, the telemetry switch, and flushing before exit.

### Modified Capabilities
- `app-tracing`: the API continues the caller's trace when a request carries a valid `traceparent`, and its SERVER span becomes the child of the client span instead of a trace root.

## Impact

- `apps/chat`: new telemetry module, `client.send_message` wraps the POST in a span and injects headers, and `app.py` sets tracing up on startup and shuts it down on shutdown. New dependencies: `opentelemetry-sdk` and `opentelemetry-exporter-otlp-proto-http`.
- `apps/simulator`: new telemetry module and `TelemetrySettings` under `TELEMETRY__*`. `client.send_message` wraps the POST in a span, `run_conversation` passes persona and run ids, and `__main__` flushes and shuts down. The notebook moves to `httpx2` and flushes. Same new dependencies.
- `apps/api`: no code change. FastAPI's telemetry already extracts `traceparent` with the global propagator, and the sampler is `ParentBased(ALWAYS_ON)`. Covered by a new test.
- `.env.example`: notes that the `TELEMETRY__*` settings now also apply to the chat and the simulator.
- Langfuse: traces now have a client root observation. Session cost is unchanged, because client spans are not generations.
