# Proposal

## Why

The nine tools exist, but nothing outside the process can talk to the attendant. The simulator, the Chainlit UI, the eval suite and `promptfoo redteam` all need one HTTP contract to send a customer message and read the bot's reply. Fixing that contract now, behind a fixed reply, lets those clients be built against it while the LangGraph graph (core work) is designed separately, and the graph later plugs in without changing the contract.

**Phase:** 1 (naive foundation). The endpoint has no defenses: no authentication, no rate limit, no message size cap, no input classifier. Phases 5 and 6 measure and add those.

**Scope:** stays within the frozen scope. It adds no tool and no feature beyond the chat channel the agent already needs. The reply is a fixed text; no LLM is called.

## What Changes

- New endpoint `POST /conversations/{conversation_id}/messages`:
  - The client chooses the conversation id (a UUID). The first message to an unseen id starts the conversation; there is no "create conversation" call.
  - Request body: `{"text": "<customer message>"}`.
  - Response: HTTP 200 with `{"conversation_id": "<uuid>", "replies": [{"text": "<bot message>"}]}`. `replies` is a list because one turn of the agent may send more than one message.
  - For now the reply is one fixed Portuguese text. Nothing is stored and no LLM is called.
- A small seam between the HTTP layer and the agent (an `Attendant` with one async `reply` method), injected as a FastAPI dependency. This change ships a fixed implementation; the graph replaces it later, and tests can override it.
- One log line per turn with the conversation id and the message length, never the message text.
- Deferred on purpose, each to the change that needs it: the customer's phone bound to the session (phase 6 guardrails), conversation history (the LangGraph checkpointer), streaming (SSE, only if the UI needs it), and conversation end or escalation status.

## Capabilities

### New Capabilities
- `conversation-api`: the HTTP contract clients use to talk to the attendant: conversation ids, the message request and reply shapes, validation errors, the current fixed reply and what each turn logs.

### Modified Capabilities
None. `api-service` keeps the app lifecycle and health endpoint; its requirements do not change.

## Impact

- **Code:** new router `apps/api/src/fornada_api/conversations.py`, the `Attendant` seam and its fixed implementation in `agents/attendant/`, a dependency in `dependencies/`, and `main.py` includes the router. No change to models, schema, tools or settings.
- **Dependencies:** none.
- **Database:** none. The endpoint does not read or write the database yet.
- **Tests:** unit tests through FastAPI's `TestClient` with no database needed.
- **Clients:** the simulator (phase 1), Chainlit, the eval suite (phase 4) and the promptfoo HTTP provider (phase 5) target this contract.
- **Later phases:** phase 2 opens the per-turn span here and uses the conversation id as the session id; phase 6 adds the session phone to this contract.
