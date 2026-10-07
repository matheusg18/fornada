# Tasks

## 1. Workspace on Python 3.13

- [x] 1.1 Set `.python-version` to `3.13`, `requires-python = ">=3.13"` in both apps, `fornada-api` ruff `target-version = "py313"` and pyright `pythonVersion = "3.13"`; rewrite `except SQLAlchemyError, OSError:` in `apps/api/src/fornada_api/health.py` as `except (SQLAlchemyError, OSError):`; add `from __future__ import annotations` to the `catalog`, `orders` and `customers` models (their forward references relied on 3.14's deferred annotations); run `uv sync` at the root and verify `uv run python --version` reports 3.13 and `uv run task check` in `apps/api` passes

## 2. Chat app scaffolding

- [x] 2.1 Add `chainlit` and `httpx` with `uv add --package fornada-chat`, and the dev group (`ruff`, `pyright`, `pytest`, `taskipy`) with `uv add --package fornada-chat --dev`; verify `uv sync` resolves and `uv run --package fornada-chat chainlit --version` prints 2.12.x
- [x] 2.2 Configure ruff, pyright and pytest in `apps/chat/pyproject.toml` like `apps/api` (py313, `--import-mode=importlib`), add taskipy tasks `dev` (`chainlit run src/fornada_chat/app.py -w --headless --port 8001`), `test`, `lint`, `lint:fix`, `format`, `format:check`, `typecheck`, `check`; drop the `fornada-chat` script and the placeholder `main()`; verify `uv run task --list` in `apps/chat` shows them

## 3. API client (`chat-ui`: messages, replies, failures, config, no text in logs)

- [x] 3.1 Add `fornada_chat/client.py` with `load_api_url(environ)` (default `http://localhost:8000`, from `CHAT__API_URL`), `API_URL`, `ERROR_MESSAGE` (Brazilian Portuguese), `ApiError` and `send_message(http, conversation_id, text) -> list[str]` (POST `{"text": text}` to `/conversations/{id}/messages`; `ApiError` on connect error, timeout, non-200 or a body without `replies[].text`; one `WARNING` log with `conversation_id` and the failure kind, never the text)
- [x] 3.2 Add `apps/chat/tests/unit/test_client.py` with `httpx.MockTransport` and `pytest.mark.anyio`: path and body sent, two replies returned in order, `load_api_url` default and `CHAT__API_URL` override, and `ApiError` for connect error, timeout, HTTP 500 and a malformed body; a test sending `Meu telefone é 81987654321` through a failing transport asserts no captured log record contains `81987654321`; verify `uv run task test` in `apps/chat` passes

## 4. Chainlit layer (`chat-ui`: session id, text-only input, launch)

- [x] 4.1 Add `fornada_chat/app.py` following Chainlit's getting started: `@cl.on_chat_start` stores a `uuid4()` with `cl.user_session.set`; `@cl.on_message async def main(message: cl.Message)` reads it with `cl.user_session.get` and calls `send_message` with `message.content` with `httpx.AsyncClient(base_url=API_URL, timeout=60)` and sends each reply with `await cl.Message(content=...).send()`, or `ERROR_MESSAGE` on `ApiError`; verify `uv run task typecheck` and `uv run task lint` in `apps/chat` pass
- [x] 4.2 Run `uv run chainlit init` in `apps/chat` to generate `.chainlit/config.toml` (and `chainlit.md`, running `uv run task dev` once if `init` does not create it); set `[UI] name = "Fornada"`, `edit_message = false` and `[features.spontaneous_file_upload] enabled = false`; replace `chainlit.md` with one line; add `apps/chat/.files/` and `apps/chat/.chainlit/translations/` to `.gitignore`; verify `git status` shows only `config.toml` and `chainlit.md` as new Chainlit files
- [x] 4.3 Document the chat in `apps/chat/README.md` (what it does, `uv run task dev` on port 8001 next to the API on 8000, `CHAT__API_URL`, text-only, nothing stored, the 3.13 pin and why) and add `CHAT__API_URL` commented out under a "Chat" section in the root `.env.example`; verify the documented command starts the chat

## 5. Integration check

- [x] 5.1 Run `uv run task check` in both `apps/api` and `apps/chat` and verify both pass
- [x] 5.2 With the API on `uv run task dev` (port 8000) and the chat on `uv run task dev` (port 8001), drive `http://localhost:8001` with the Playwright MCP: verify there is no attach-file control, a message gets the API's fixed reply, there is no edit control on the sent message, the API's `conversation turn` log shows the same `conversation_id` for two messages in one session and a different one after "New chat"; stop the API and verify the error message appears; restart it and verify the next message in the same session gets the reply under the same id

## Workflow follow-up

- Archive the change with `/opsx:archive` after review, syncing `chat-ui` into `openspec/specs/`.
