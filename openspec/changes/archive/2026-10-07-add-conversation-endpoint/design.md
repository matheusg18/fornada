# Design

## Context

`fornada-api` has one router today (`health.py`, mounted in `main.py`), a per-request database session dependency (`dependencies/database.py`), and the nine tools in `agents/attendant/tools.py`. There is no graph yet: its nodes, state and prompt are core work the maintainer designs in a later change. The lifespan loads settings and builds the engine without connecting, so the app can serve requests that never touch the database even when PostgreSQL is down.

The contract decisions (client-chosen UUID, text-only body, synchronous JSON, stateless fixed reply) were made with the maintainer before this change; see `proposal.md` and `specs/conversation-api/spec.md`.

## Goals / Non-Goals

**Goals:**
- Freeze the HTTP shape that the simulator, Chainlit, evals and promptfoo will target, so wiring the graph later changes only what sits behind the endpoint.
- Leave one obvious place where the graph plugs in, swappable in tests.

**Non-Goals:**
- Any graph, LLM call, prompt or state design. The seam takes a message and returns replies; it does not decide what the graph's state looks like.
- Persistence, history, conversation listing or `GET` endpoints.
- The Chainlit client, the simulator, telemetry spans.

## Decisions

### 1. Route and resource shape

`POST /conversations/{conversation_id}/messages`, status 200, body `{"text": ...}`, response `{"conversation_id", "replies": [{"text"}]}`.

- **200, not 201.** The call is a turn exchange: the useful result is the replies, not a created resource with a `Location`. No message id is returned because nothing is stored yet.
- **`replies` is a list of objects**, not a single string. One agent turn may emit several messages (a quote, then a payment link), and an object leaves room for later per-reply fields without breaking clients. Fields are added only when a change needs them (no `role`, no `id`, no `status` now).
- **Alternative rejected:** `POST /chat` with the id in the body. The path form makes the conversation the resource, matches the LangGraph `thread_id` one to one and reads well in traces and access logs.

### 2. Client-generated UUID

The path parameter is typed `uuid.UUID`, so FastAPI returns 422 for anything else. Clients generate a UUID4 per conversation. This doubles as the future LangGraph `thread_id` and the phase 2 session id (`session.id` in Langfuse), with no lookup table.

Accepted trade-off: anyone who knows or guesses an id can post into that conversation. With UUID4 guessing is impractical, and v0 has no auth anyway. Binding a conversation to the customer's phone is phase 6 work.

### 3. The `Attendant` seam

```python
# agents/attendant/attendant.py (sketch)
class Attendant(Protocol):
    async def reply(self, conversation_id: UUID, text: str) -> list[str]: ...

class FixedAttendant:
    async def reply(self, conversation_id: UUID, text: str) -> list[str]:
        return [FIXED_REPLY]
```

- Lives in `agents/attendant/` because it is the attendant's entry point; the graph-backed implementation will sit next to it.
- Async because the real one awaits the graph (`ainvoke`) and the tools are async.
- Plain types (`UUID`, `str`, `list[str]`) instead of the HTTP schemas, so the agent package does not import the web layer and the graph's state stays the maintainer's decision.
- Exposed through `dependencies/attendant.py` as `AttendantDep = Annotated[Attendant, Depends(get_attendant)]`, like `DbSessionDep`. Tests and later the graph swap it with `app.dependency_overrides` or by changing `get_attendant`.
- **Alternative rejected:** putting the fixed text straight in the route. It would work today, but the next change would have to restructure the route instead of replacing one dependency.

### 4. Request and response models

`conversations.py` holds the router plus Pydantic models: `MessageIn` (`text: str` with whitespace stripping and `min_length=1`), `Reply` (`text: str`) and `TurnOut` (`conversation_id: UUID`, `replies: list[Reply]`). Stripping is only for validation of blank input; the attendant receives the text as validated. No `max_length` in v0 (see Risks).

### 5. Turn log

The route logs one INFO record, `"conversation turn"`, with `extra={"conversation_id": str(id), "text_length": len(text)}`. Never the text: customer messages carry names, phones and addresses, and the LGPD and Presidio work (phase 6) starts from "the text is not in logs" instead of having to remove it. Phase 2 moves the same fields onto the turn span.

### 6. Fixed reply text

One Portuguese constant, for example: "Olá! Aqui é a Fornada. Ainda estou aprendendo a anotar pedidos, mas logo vou poder te ajudar com o seu bolo." The exact wording is not part of the contract; tests compare against the constant, not a literal.

## Risks / Trade-offs

- [No message size cap or rate limit] → Deliberate for v0, so phase 5 can measure denial-of-service and cost attacks against it. With a fixed reply there is no token cost yet.
- [Two concurrent posts to the same conversation] → Harmless while stateless. When the checkpointer arrives, concurrent turns on one `thread_id` can race; that change must decide (lock per conversation or reject with 409).
- [Contract churn when the graph lands] → The shape was chosen to absorb it: the graph changes the `Attendant` implementation, and new fields are additive.
- [Clients assume `replies` has exactly one item] → The spec says "one or more"; the simulator and Chainlit must iterate.

## Migration Plan

Additive endpoint; nothing to migrate. Rollback is removing the router include.
