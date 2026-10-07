# Proposal

## Why

`POST /conversations/{id}/messages` exists, but the only way to talk to it is `curl`. Phase 1 needs a minimal chat a person can use: the maintainer to try the bot by hand, and the 3–4 real people in phase 3 error analysis. `apps/chat` is already a placeholder package for exactly this (a Chainlit UI that talks to the API over HTTP), and building it now against the fixed reply means it works unchanged when the LangGraph graph lands behind the same contract.

**Phase:** 1 (naive foundation). The UI has no login, no defenses and no polish (frozen UI rule).

**Scope:** stays within the frozen scope. It adds no tool and no agent feature; it is a thin client of the existing `conversation-api` contract.

## What Changes

- `fornada-chat` becomes a Chainlit app:
  - Each chat session generates a UUID4 conversation id. "New chat" starts a new id.
  - Each customer message is posted to `POST /conversations/{id}/messages` on the API; every item in `replies` is shown as its own bot message, in order.
  - When the API cannot be reached, times out or answers with a non-200 status, the chat shows one fixed Brazilian Portuguese error message and stays usable; the conversation id does not change.
  - The API base URL comes from `CHAT__API_URL`, defaulting to `http://localhost:8000`.
  - Text only: file upload and editing a sent message are turned off, since the API takes text and cannot rewind a conversation.
  - Served on port 8001 (the API keeps 8000, Chainlit's own default).
- Tooling for the chat app, mirroring `apps/api`: ruff, pyright, pytest and taskipy tasks (`dev`, `check`, …).
- **BREAKING (dev environment):** the uv workspace moves from Python 3.14 to **3.13**. Chainlit 2.12.0, the latest release, and its `main` branch declare `requires-python <3.14`, and one workspace has one lockfile and one interpreter. `fornada-api` drops its only 3.14-only syntax (an unparenthesized multi-exception `except` in `health.py`). Move back to 3.14 once Chainlit supports it.

## Capabilities

### New Capabilities
- `chat-ui`: the human-facing chat client: how a session maps to a conversation id, how messages and replies flow to and from the API, what the user sees when the API fails, and how it is configured and launched.

### Modified Capabilities
None. `conversation-api` is consumed as is; the Python version change is tooling and changes no requirement.

## Impact

- **Code:** `apps/chat/src/fornada_chat/` (Chainlit entry module and a small HTTP client), `apps/chat/.chainlit/config.toml`, `apps/chat/chainlit.md`; `apps/api/src/fornada_api/health.py` (one `except` clause).
- **Dependencies:** `chainlit` and `httpx` in `fornada-chat`; dev group with `ruff`, `pyright`, `pytest`, `taskipy`. One shared `uv.lock`, re-resolved for 3.13.
- **Tooling:** `.python-version` → `3.13`; both apps `requires-python = ">=3.13"`; `fornada-api` ruff `target-version = "py313"` and pyright `pythonVersion = "3.13"`. The root `.venv` volume is recreated by `uv sync`.
- **Config:** new optional `CHAT__API_URL` documented in the root `.env.example`.
- **API:** no change. No database access from the chat.
- **Later phases:** phase 3 uses this UI for the real-people conversations; phase 6 adds the customer's phone to the contract, and the chat will need to send it.
