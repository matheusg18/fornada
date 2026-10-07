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

## Python 3.13

The workspace runs on Python 3.13, not 3.14, because Chainlit (2.12.0 at the
time of writing) requires Python below 3.14. Move back to 3.14 once Chainlit
supports it.

## Checks

From `apps/chat`: `uv run task check` runs lint, format check, type check and
the tests; `uv run task --list` shows the narrower tasks.
