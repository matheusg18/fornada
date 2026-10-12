# fornada-chat

Minimal [Chainlit](https://docs.chainlit.io) chat UI. It talks to `fornada-api`
over HTTP and stores nothing: the API owns the conversation.

## Running the chat

Start the API first (see `apps/api/README.md`), then, from `apps/chat`:

```bash
uv run task dev      # http://localhost:8001, auto-reload, no browser opened
```

That is Chainlit's `chainlit run app.py -w` with `--headless` (no browser in
the dev container) and `--port 8001` (the API uses 8000, Chainlit's default).
Run it from `apps/chat`: Chainlit reads `.chainlit/config.toml` and `.env` from
the folder it starts in.

| Variable | Default | Meaning |
|---|---|---|
| `CHAT__API_URL` | `http://localhost:8000` | Base URL of `fornada-api` |
| `TELEMETRY__ENABLED` | `false` | Send traces to the Collector |
| `TELEMETRY__OTLP_ENDPOINT` | `http://edot-collector:4318` | Collector's OTLP/HTTP base URL |

Chainlit loads `.env` from `apps/chat`, not the root one, so set the
`TELEMETRY__*` variables in the shell or in `apps/chat/.env`.

## How it works

- Each chat session gets a UUID4 conversation id (`cl.user_session`). Reloading
  the page or starting a new chat starts a new conversation.
- Each message is posted to `POST /conversations/{id}/messages`; every item in
  `replies` is shown as its own bot message, in order.
- If the API is down, too slow (60 s), answers with an error status or returns
  an unexpected body, the chat shows a fixed Portuguese error message and the
  session keeps its conversation id, so the next message works once the API is
  back.
- Text only: file upload and editing a sent message are off in
  `.chainlit/config.toml`, because the API takes text and cannot rewind a
  conversation.
- Message and reply text are never logged.

Code layout: `fornada_chat/app.py` holds the Chainlit callbacks;
`fornada_chat/client.py` is the plain HTTP client (the part with unit tests).
`.chainlit/config.toml` and `chainlit.md` are versioned; Chainlit regenerates
`.chainlit/translations/` and `.files/` on start (both git-ignored).

## Tracing

With `TELEMETRY__ENABLED=true`, each message the chat posts is one span of kind
CLIENT, `POST /conversations/{conversation_id}/messages`, from the service
`fornada-chat`. It is the root of that turn's trace: the request carries its
context in a W3C `traceparent` header, so the API's spans join the same trace.
The span carries the conversation id as `session.id` and
`gen_ai.conversation.id`, so all turns of a chat are one Langfuse session. It
also carries the HTTP method, URL template, server address and port, and the
response status code. A failed post sets the status to ERROR with an
`error.type` (the status code, `connect`, `timeout` or `bad_body`). No message
or reply text goes into a span.

The chat's tracer provider is private: it is never registered as the global
OpenTelemetry provider. Chainlit's server is a FastAPI app, and FastAPI traces
every request through the global provider. Registering it would turn the
websocket into one span open for the whole tab, with every message inside it.
So the chat exports only its own client spans. `fornada_chat/telemetry.py`
builds the provider, and the `on_app_startup` and `on_app_shutdown` hooks in
`app.py` start it and drain it.

Do not set `LITERAL_API_KEY`. It turns on Chainlit's Literal AI data layer,
which starts Traceloop with its own global provider.

## Python 3.13

The workspace runs on Python 3.13, not 3.14, because Chainlit (2.12.0 at the
time of writing) requires Python below 3.14. Move back to 3.14 once Chainlit
supports it.

## Checks

From `apps/chat`: `uv run task check` runs lint, format check, type check and
the tests; `uv run task --list` shows the narrower tasks.
