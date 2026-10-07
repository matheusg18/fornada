import uuid
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.prebuilt import ToolRuntime

from fornada_api.agents.attendant.attendant import FALLBACK_REPLY, GraphAttendant
from fornada_api.agents.attendant.graph import build_graph
from fornada_api.agents.attendant.prompt import load_system_prompt
from tests.unit.agents.fakes import ScriptedChatModel, tool_call

pytestmark = pytest.mark.anyio

seen_thread_ids: list[Any] = []


@tool
async def search_catalog(runtime: ToolRuntime) -> str:
    """Lists the cakes and records the run's thread id."""
    seen_thread_ids.append((runtime.config.get("configurable") or {})["thread_id"])
    return "bolo-chocolate"


def attendant(model: ScriptedChatModel) -> GraphAttendant:
    graph = build_graph(model, [search_catalog], load_system_prompt("Prompt"))
    return GraphAttendant(graph.compile(checkpointer=InMemorySaver()))


async def test_text_before_a_tool_call_is_a_reply() -> None:
    first = AIMessage(
        content="Vou verificar a agenda",
        tool_calls=[{"name": "search_catalog", "args": {}, "id": "c1"}],
    )
    model = ScriptedChatModel(answers=[first, AIMessage("Temos 5 kg livres no dia 20")])
    replies = await attendant(model).reply(uuid.uuid4(), "tem vaga?")
    assert replies == ["Vou verificar a agenda", "Temos 5 kg livres no dia 20"]


async def test_only_the_current_turn_is_returned() -> None:
    model = ScriptedChatModel(answers=[AIMessage("um"), AIMessage("dois"), AIMessage("três")])
    agent = attendant(model)
    conversation = uuid.uuid4()
    await agent.reply(conversation, "a")
    await agent.reply(conversation, "b")
    assert await agent.reply(conversation, "c") == ["três"]


async def test_empty_model_text_falls_back() -> None:
    model = ScriptedChatModel(answers=[AIMessage("")])
    assert await attendant(model).reply(uuid.uuid4(), "oi") == [FALLBACK_REPLY]


async def test_thread_id_is_the_conversation_id() -> None:
    seen_thread_ids.clear()
    model = ScriptedChatModel(answers=[tool_call("search_catalog", {}, "c1"), AIMessage("ok")])
    conversation = uuid.uuid4()
    await attendant(model).reply(conversation, "catálogo")
    assert seen_thread_ids == [str(conversation)]


async def test_a_looping_model_hits_the_step_limit() -> None:
    model = ScriptedChatModel(answers=[tool_call("search_catalog", {}, "c1")])
    with pytest.raises(GraphRecursionError):
        await attendant(model).reply(uuid.uuid4(), "catálogo")


async def test_before_turn_runs_before_each_turn() -> None:
    calls: list[str] = []

    async def before_turn() -> None:
        calls.append("setup")

    graph = build_graph(
        ScriptedChatModel(answers=[AIMessage("oi")]), [search_catalog], load_system_prompt("P")
    )
    agent = GraphAttendant(graph.compile(checkpointer=InMemorySaver()), before_turn)
    await agent.reply(uuid.uuid4(), "a")
    await agent.reply(uuid.uuid4(), "b")
    assert calls == ["setup", "setup"]
