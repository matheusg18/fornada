# Design

## Context

`apps/chat` is a placeholder member of the uv workspace (`fornada_chat/__init__.py` prints a greeting; no dependencies, no tooling). `apps/api` serves `POST /conversations/{id}/messages` on port 8000 (see `openspec/specs/conversation-api/spec.md`): text in, `replies` list out, fixed reply for now. The workspace has one `.python-version` (3.14), one `uv.lock` and one root `.venv`.

Chainlit 2.12.0 (latest) declares `requires-python >=3.10,<3.14`, and so does its `main` branch; upstream issues about 3.14 (event-loop errors under `nest_asyncio`/`anyio`) are closed without lifting the cap. Chainlit 2.x no longer ships usage telemetry, so there is nothing to turn off there. Chainlit reads its config from `<app root>/.chainlit/config.toml`, where the app root is the working directory of `chainlit run` (or `CHAINLIT_APP_ROOT`), and creates `.chainlit/`, `chainlit.md` and `.files/` there on first run.

## Goals / Non-Goals

**Goals:**
- A person can chat with the API from a browser, with the same contract the simulator, evals and promptfoo use.
- The chat stays a thin, testable HTTP client: everything worth testing lives outside Chainlit callbacks.

**Non-Goals:**
- Chat history across reloads, login, Chainlit data layer, streaming, any styling (frozen UI).
- Sending the customer's phone (phase 6 changes the contract first).
- A Docker image or compose service for the chat; it runs in the dev container like the API.

## Decisions

### 1. Move the workspace to Python 3.13

`.python-version` → `3.13`; both apps `requires-python = ">=3.13"`; `fornada-api` ruff `target-version = "py313"` and pyright `pythonVersion = "3.13"`. The only 3.14-only code is `except SQLAlchemyError, OSError:` in `health.py` (PEP 758), which becomes `except (SQLAlchemyError, OSError):`. The models in `catalog.py`, `orders.py` and `customers.py` also relied on 3.14's deferred annotations (unquoted forward references to classes in other files or later in the file), so they get `from __future__ import annotations`, the standard SQLAlchemy idiom. `uv sync` then re-resolves `uv.lock` and recreates the root `.venv` on 3.13.

- **Alternatives rejected** (chosen with the maintainer): taking `apps/chat` out of the workspace (its own lock and `.venv`, against the AGENTS.md layout rule), or a plain HTML page instead of Chainlit.
- Reverting is the same edit in the other direction once Chainlit allows 3.14.

### 2. Module layout: thin Chainlit layer over a plain client

```
apps/chat/src/fornada_chat/
├─ __init__.py
├─ app.py      # Chainlit callbacks only (on_chat_start, on_message)
└─ client.py   # API_URL, ERROR_MESSAGE, ApiError, send_message()
```

```python
# client.py (sketch)
async def send_message(
    http: httpx.AsyncClient, conversation_id: UUID, text: str
) -> list[str]:
    """POST one message; return reply texts in order, or raise ApiError."""
```

- `send_message` takes the `httpx.AsyncClient` as an argument, so tests pass one built on `httpx.MockTransport` with no server and no Chainlit runtime.
- It raises one `ApiError` for every failure the spec groups together (connect error, timeout, non-200, a body without the expected shape); `app.py` catches only that and sends `ERROR_MESSAGE`. Anything else is a bug and surfaces as Chainlit's own error.
- `app.py` follows Chainlit's getting started ("Pure Python") and its chat life cycle and user session pages: `@cl.on_chat_start` stores `uuid4()` with `cl.user_session.set`; `@cl.on_message async def main(message: cl.Message)` reads it with `cl.user_session.get`, calls `send_message` with `message.content` and a client built from `API_URL`, and sends each reply with `await cl.Message(content=...).send()`. No module-level state besides constants, as the user session page warns. `cl.chat_context` is not used: the API owns the conversation history.
- Adapted from the getting started: `app.py` sits in the package (`src/fornada_chat/app.py`) instead of the project folder, to keep the `src/` layout of `apps/api`.
- **Alternative rejected:** putting the HTTP call inside `on_message`. It would need Chainlit's session context in every test.

### 3. HTTP client details

- `httpx` (async), a new `AsyncClient(base_url=API_URL, timeout=60s)` per message via `async with`. One person at a time does not need a pooled client, and this avoids lifecycle hooks. 60 s instead of httpx's 5 s default because a real agent turn (several LLM and tool calls) can take tens of seconds.
- The response body is checked by hand: `replies` must be a list of objects with a string `text`, otherwise `ApiError`. A Pydantic model for one field is not worth it.
- **Alternative rejected:** importing `TurnOut` from `fornada-api`. The chat would depend on the API package and its settings; the contract is HTTP, so the client mirrors it.

### 4. Configuration

`API_URL = os.environ.get("CHAT__API_URL", "http://localhost:8000")`, read once at import. One optional value does not justify `pydantic-settings`. The name follows the repo's `NAMESPACE__FIELD` convention and is documented, commented out, in the root `.env.example`. Chainlit loads `.env` from its app root (`apps/chat`), not the repo root, so the variable is set in the shell or that file when needed; the default works inside the dev container.

### 5. Chainlit config and launch

- Run from `apps/chat`, so the app root is `apps/chat`: `chainlit run src/fornada_chat/app.py -w --headless --port 8001`, as the taskipy `dev` task. This is the getting started's `chainlit run app.py -w` plus `--headless` (no browser in the dev container) and `--port 8001` (the API already uses Chainlit's default 8000).
- Generate `apps/chat/.chainlit/config.toml` with `chainlit init` (the CLI's documented way) and commit it, edited only for: `[UI] name = "Fornada"`, `[features.spontaneous_file_upload] enabled = false` and `edit_message = false` (the spec's text-only requirement: the API takes text and cannot rewind a conversation, so a Chainlit edit would desync the transcript from the API's state).
- `language` is left unset, so the UI follows the browser (Chainlit's default). The docs only accept locales present in `.chainlit/translations/`, which has `pt-PT` but no `pt-BR`; a pt-BR browser falls back to `pt-PT`. Writing a `pt-BR` translation would be UI polish (frozen UI).
- Commit a one-line `apps/chat/chainlit.md` so Chainlit does not generate its default welcome page.
- Ignore `apps/chat/.files/` and `apps/chat/.chainlit/translations/` (generated on start).
- Drop the placeholder `[project.scripts] fornada-chat` entry and `main()`; the `dev` task is the launch command.

### 6. Logging

The chat logs one `WARNING` per failed turn with `conversation_id` and the failure kind (`connect`, `timeout`, `status` with the code, `bad_body`), through `logging.getLogger(__name__)`. It never logs message or reply text, matching the API's rule, so phase 6 PII work does not have to clean the chat's logs. Chainlit's own logging setup is left as is.

### 7. Tests and tooling

Same tooling as `apps/api` (dev group with `ruff`, `pyright`, `pytest`, `taskipy`, installed with `uv add --package fornada-chat --dev`). Async tests use `pytestmark = pytest.mark.anyio`, like the API tests; `anyio` comes with `httpx`. Unit tests cover `send_message` only: request path and body, default and custom base URL, multiple replies in order, and each failure kind raising `ApiError` without the text in the logs. The Chainlit layer is verified by hand in the browser (Playwright MCP) against `uv run task dev` on the API: page loads on 8001, a message gets the fixed reply, stopping the API yields the error message, restarting it recovers in the same session.

## Risks / Trade-offs

- [Workspace on 3.13 for Chainlit's sake] → Cost is one `except` clause and the version lines. Recorded in the proposal and README so it is reverted once Chainlit lifts the cap.
- [Chainlit is a large dependency tree in the shared lock] → Only `fornada-chat` declares it, so `fornada-api` does not import it. Dependabot bumps arrive in the same lock.
- [A Chainlit dependency (`literalai`) installs a top-level `tests` package in the shared `.venv`, which pyright prefers over the API's namespace `tests/`] → `apps/api/tests/`, `tests/unit/` and `tests/unit/services/` get empty `__init__.py` files, so the local package is a regular one and wins. Found while running the API check in task 5.1.
- [Chainlit's default config allows any origin and has no auth] → Dev-only, local use in phase 1; same "no defenses in v0" stance as the API.
- [Same session id survives Chainlit websocket reconnects but not page reloads] → Reload starts a new conversation, which matches the API being stateless today. Revisit when the checkpointer adds history.
- [60 s timeout hides a hung agent for a minute] → Acceptable for a manual UI; phase 2 latency metrics show slow turns.

## Migration Plan

1. Switch the workspace to 3.13 and fix `health.py`; `uv sync` recreates the `.venv`; `uv run task check` in `apps/api` must pass before anything else.
2. Add the chat app. Developers re-run `uv sync` at the root after pulling.

Rollback: revert the commits; `uv sync` restores 3.14.
