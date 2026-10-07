# Tasks

## 1. Attendant seam

- [x] 1.1 Add `agents/attendant/attendant.py` with the `Attendant` protocol (`async reply(conversation_id: UUID, text: str) -> list[str]`), `FIXED_REPLY` (Brazilian Portuguese) and `FixedAttendant`; add `dependencies/attendant.py` with `get_attendant` and `AttendantDep`, exported from `dependencies/__init__.py`; add a unit test that `FixedAttendant().reply(...)` returns `[FIXED_REPLY]` for two different ids and texts; verify `uv run task test:unit` and `uv run task typecheck` pass

## 2. Endpoint (`conversation-api`)

- [ ] 2.1 Add `conversations.py` with `MessageIn` (stripped, non-empty `text`), `Reply`, `TurnOut` and `POST /conversations/{conversation_id}/messages` (UUID path param, calls `AttendantDep`, logs `"conversation turn"` with `conversation_id` and `text_length`, returns 200); include the router in `main.py`; verify `/docs` lists the route when running `uv run task dev`
- [ ] 2.2 Add unit tests in `tests/unit/test_conversations.py` using `TestClient(app)` with env pointing `DB__URL` at an unreachable `postgresql://x:pw@127.0.0.1:1/x` and a placeholder LLM key: happy path (200, echoed `conversation_id`, one reply equal to `FIXED_REPLY`), new UUID accepted, `/conversations/482/messages` → 422, `{}` → 422, `{"text": "   "}` → 422, two conversations get the same reply, and a dependency override of `get_attendant` returning two replies yields both in order; verify `uv run task test:unit` passes
- [ ] 2.3 Add a unit test that posts `{"text": "Meu telefone é 81987654321"}`, reads the JSON lines from captured stdout (logging replaces root handlers, so use `capsys`, not `caplog`), finds one `"conversation turn"` record with the conversation id and `text_length` 26, and asserts no line contains `81987654321`; verify it passes
- [ ] 2.4 Document the endpoint in `apps/api/README.md` (request, response, 422 cases, fixed reply for now, text never logged) and add a `curl` example; verify the example works against `uv run task dev`

## 3. Integration check

- [ ] 3.1 Run `uv run task check` in `apps/api` and verify it passes; start `uv run task dev` and `curl -X POST localhost:8000/conversations/$(python3 -c 'import uuid; print(uuid.uuid4())')/messages -H 'content-type: application/json' -d '{"text":"oi"}'`, verifying a 200 with the fixed reply and a `conversation turn` JSON log line without the text

## Workflow follow-up

- Archive the change with `/opsx:archive` after review, syncing `conversation-api` into `openspec/specs/`.
