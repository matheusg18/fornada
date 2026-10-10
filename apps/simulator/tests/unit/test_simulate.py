import json
import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from fornada_simulator.personas import PERSONAS
from fornada_simulator.settings import SimulatorSettings
from fornada_simulator.simulate import END_MARKER, plan_jobs, run_batch, run_conversation
from fornada_simulator.transcript import read_jsonl

pytestmark = pytest.mark.anyio

PERSONA = PERSONAS[0]
GOAL = PERSONA.goals[0]


class ScriptedModel:
    """Returns the scripted customer messages in order; an Exception item is raised."""

    def __init__(self, script: Sequence[str | Exception], *, repeat_last: bool = False) -> None:
        self.script = list(script)
        self.repeat_last = repeat_last
        self.calls: list[list[BaseMessage]] = []

    async def ainvoke(self, input: list[BaseMessage], /) -> BaseMessage:
        self.calls.append(list(input))
        index = (
            min(len(self.calls) - 1, len(self.script) - 1)
            if self.repeat_last
            else len(self.calls) - 1
        )
        item = self.script[index]
        if isinstance(item, Exception):
            raise item
        return AIMessage(item)


def api(
    handler: Callable[[httpx.Request], httpx.Response] | None = None,
) -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def default(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"replies": [{"text": "Oi!"}]})

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return (handler or default)(request)

    client = httpx.AsyncClient(base_url="http://api", transport=httpx.MockTransport(respond))
    return client, seen


async def test_first_message_is_posted_under_a_new_uuid4() -> None:
    http, seen = api()
    async with http:
        transcript = await run_conversation(
            PERSONA,
            GOAL,
            http,
            ScriptedModel(["bolo amanhã", f"valeu {END_MARKER}"]),
            max_turns=5,
            run_id="r",
        )
    assert json.loads(seen[0].content) == {"text": "bolo amanhã"}
    assert seen[0].url.path == f"/conversations/{transcript.conversation_id}/messages"
    assert UUID(str(transcript.conversation_id)).version == 4


async def test_both_replies_reach_the_persona_in_order() -> None:
    http, _ = api(
        lambda r: httpx.Response(200, json={"replies": [{"text": "primeiro"}, {"text": "segundo"}]})
    )
    model = ScriptedModel(["oi", END_MARKER])
    async with http:
        transcript = await run_conversation(PERSONA, GOAL, http, model, max_turns=5, run_id="r")
    last_input = model.calls[1][-1]
    assert isinstance(last_input, HumanMessage)
    assert last_input.content.index("primeiro") < last_input.content.index("segundo")
    attendant = [m for m in transcript.messages if m.role == "attendant"]
    assert [(m.text, m.reply_index) for m in attendant] == [("primeiro", 0), ("segundo", 1)]


async def test_marker_ends_the_conversation_and_is_never_posted() -> None:
    http, seen = api()
    async with http:
        transcript = await run_conversation(
            PERSONA,
            GOAL,
            http,
            ScriptedModel(["oi", f"obrigada! {END_MARKER}"]),
            max_turns=5,
            run_id="r",
        )
    assert transcript.outcome == "completed"
    assert [json.loads(r.content)["text"] for r in seen] == ["oi", "obrigada!"]
    assert all(END_MARKER not in m.text for m in transcript.messages)


async def test_a_message_that_is_only_the_marker_posts_nothing() -> None:
    http, seen = api()
    async with http:
        transcript = await run_conversation(
            PERSONA, GOAL, http, ScriptedModel(["oi", END_MARKER]), max_turns=5, run_id="r"
        )
    assert transcript.outcome == "completed"
    assert len(seen) == 1
    assert transcript.turns == 1


async def test_a_persona_that_never_ends_stops_at_the_cap() -> None:
    http, seen = api()
    async with http:
        transcript = await run_conversation(
            PERSONA,
            GOAL,
            http,
            ScriptedModel(["mais um"], repeat_last=True),
            max_turns=12,
            run_id="r",
        )
    assert transcript.outcome == "max_turns"
    assert transcript.turns == 12
    assert len(seen) == 12


async def test_api_failure_on_turn_three_keeps_two_turns() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if len(seen) == 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"replies": [{"text": "ok"}]})

    http, seen = api(handler)
    async with http:
        transcript = await run_conversation(
            PERSONA, GOAL, http, ScriptedModel(["a", "b", "c", "d"]), max_turns=10, run_id="r"
        )
    assert transcript.outcome == "api_error"
    attendant_replies = [m for m in transcript.messages if m.role == "attendant"]
    assert len(attendant_replies) == 2


async def test_persona_model_failure_keeps_the_first_turn() -> None:
    http, _ = api()
    model = ScriptedModel(["oi", RuntimeError("boom with secret-detail")])
    async with http:
        transcript = await run_conversation(PERSONA, GOAL, http, model, max_turns=5, run_id="r")
    assert transcript.outcome == "simulator_error"
    assert transcript.turns == 1
    assert len(transcript.messages) == 2


async def test_logs_never_contain_message_text(caplog: pytest.LogCaptureFixture) -> None:
    http, _ = api(
        lambda r: httpx.Response(200, json={"replies": [{"text": "resposta-secreta-do-bot"}]})
    )
    caplog.set_level(logging.DEBUG)
    async with http:
        await run_conversation(
            PERSONA,
            GOAL,
            http,
            ScriptedModel(["mensagem-secreta-do-cliente", f"tchau {END_MARKER}"]),
            max_turns=5,
            run_id="r",
        )
    assert "secreta" not in caplog.text


def test_plan_is_even_and_goals_differ_per_persona() -> None:
    jobs = plan_jobs(4)
    assert len(jobs) == 20
    for persona in PERSONAS:
        goals = [goal for p, goal in jobs if p.id == persona.id]
        assert len(goals) == 4
        assert len(set(goals)) == 4


def settings(**overrides: object) -> SimulatorSettings:
    return SimulatorSettings.model_validate({"anthropic": {"api_key": "k"}, **overrides})


async def test_a_failing_conversation_never_stops_the_batch(tmp_path: Path) -> None:
    posts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal posts
        posts += 1
        # Every fifth call fails: those conversations end with api_error.
        if posts % 5 == 0:
            return httpx.Response(503)
        return httpx.Response(200, json={"replies": [{"text": "ok"}]})

    class EndingModel:
        async def ainvoke(self, input: list[BaseMessage], /) -> BaseMessage:
            return AIMessage(f"oi {END_MARKER}")

    transcripts = await run_batch(
        settings(),
        EndingModel(),
        runs_dir=tmp_path,
        run_id="batch",
        transport=httpx.MockTransport(handler),
    )
    assert len(transcripts) == 20
    assert "api_error" in {t.outcome for t in transcripts}
    assert len(read_jsonl(tmp_path / "batch.jsonl")) == 20
