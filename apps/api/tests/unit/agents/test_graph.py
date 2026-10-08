from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import ToolException, tool
from langgraph.checkpoint.memory import InMemorySaver

from fornada_api.agents.attendant.graph import build_graph
from fornada_api.agents.attendant.prompt import load_system_prompt
from fornada_api.agents.attendant.state import InputState
from tests.unit.agents.fakes import ScriptedChatModel, tool_call

pytestmark = pytest.mark.anyio

PROMPT = load_system_prompt("Prompt A")


@pytest.fixture
def runs() -> list[str]:
    return []


@pytest.fixture
def tools(runs: list[str]) -> list[Any]:
    @tool
    async def search_catalog() -> str:
        """Lists the cakes."""
        runs.append("search_catalog")
        return "bolo-chocolate"

    @tool
    async def check_capacity(date: str) -> str:
        """Free kg on a date."""
        runs.append("check_capacity")
        return "5 kg"

    @tool
    async def calculate_quote(weight_kg: float) -> str:
        """Prices a cake."""
        runs.append("calculate_quote")
        if weight_kg % 0.5:
            raise ToolException("weight must be in steps of 0.5 kg")
        return "224.75"

    calculate_quote.handle_tool_error = True
    return [search_catalog, check_capacity, calculate_quote]


def config(thread: str = "t1") -> Any:
    return {"configurable": {"thread_id": thread}}


def compile_graph(model: ScriptedChatModel, tools: list[Any], saver=None, prompt=PROMPT):
    return build_graph(model, tools, prompt).compile(checkpointer=saver or InMemorySaver())


def say(text: str) -> InputState:
    return {"messages": [HumanMessage(text)]}


async def test_answer_without_tools(tools: list[Any], runs: list[str]) -> None:
    model = ScriptedChatModel(answers=[AIMessage("Olá! Como posso ajudar?")])
    output = await compile_graph(model, tools).ainvoke(say("oi"), config())
    assert len(model.calls) == 1
    assert runs == []
    assert output["messages"][-1].content == "Olá! Como posso ajudar?"


async def test_one_tool_round(tools: list[Any], runs: list[str]) -> None:
    model = ScriptedChatModel(
        answers=[tool_call("search_catalog", {}, "c1"), AIMessage("Temos bolo")]
    )
    await compile_graph(model, tools).ainvoke(say("catálogo"), config())
    assert runs == ["search_catalog"]
    assert len(model.calls) == 2
    result = model.calls[1][-1]
    assert isinstance(result, ToolMessage)
    assert result.content == "bolo-chocolate"


async def test_several_tool_calls_in_one_answer(tools: list[Any], runs: list[str]) -> None:
    both = AIMessage(
        content="",
        tool_calls=[
            {"name": "check_capacity", "args": {"date": "2026-10-20"}, "id": "c1"},
            {"name": "calculate_quote", "args": {"weight_kg": 2.5}, "id": "c2"},
        ],
    )
    model = ScriptedChatModel(answers=[both, AIMessage("ok")])
    await compile_graph(model, tools).ainvoke(say("quanto?"), config())
    assert sorted(runs) == ["calculate_quote", "check_capacity"]
    results = {m.tool_call_id: m.content for m in model.calls[1] if isinstance(m, ToolMessage)}
    assert results == {"c1": "5 kg", "c2": "224.75"}


async def test_tool_error_reaches_the_next_model_call(tools: list[Any]) -> None:
    model = ScriptedChatModel(
        answers=[tool_call("calculate_quote", {"weight_kg": 2.3}, "c1"), AIMessage("use 2,5 kg")]
    )
    output = await compile_graph(model, tools).ainvoke(say("2,3 kg"), config())
    result = model.calls[1][-1]
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "0.5" in result.content
    assert output["messages"][-1].content == "use 2,5 kg"


async def test_second_turn_sees_the_first(tools: list[Any]) -> None:
    model = ScriptedChatModel(answers=[AIMessage("um"), AIMessage("dois")])
    graph = compile_graph(model, tools)
    await graph.ainvoke(say("primeira"), config())
    await graph.ainvoke(say("segunda"), config())
    texts = [m.content for m in model.calls[1] if not isinstance(m, SystemMessage)]
    assert texts == ["primeira", "um", "segunda"]


async def test_threads_are_isolated(tools: list[Any]) -> None:
    model = ScriptedChatModel(answers=[AIMessage("a"), AIMessage("b")])
    graph = compile_graph(model, tools)
    await graph.ainvoke(say("meu nome é Ana"), config("A"))
    await graph.ainvoke(say("qual é o meu nome?"), config("B"))
    seen = [m.content for m in model.calls[1]]
    assert "meu nome é Ana" not in seen


async def test_output_keys(tools: list[Any]) -> None:
    model = ScriptedChatModel(answers=[AIMessage("oi")])
    output = await compile_graph(model, tools).ainvoke(say("oi"), config())
    assert set(output) == {"messages", "prompt_version"}
    assert output["prompt_version"] == PROMPT.version


async def test_history_has_no_system_message_and_every_answer_has_the_version(
    tools: list[Any],
) -> None:
    model = ScriptedChatModel(answers=[tool_call("search_catalog", {}, "c1"), AIMessage("ok")])
    graph = compile_graph(model, tools)
    await graph.ainvoke(say("oi"), config())
    stored = (await graph.aget_state(config())).values["messages"]
    assert not [m for m in stored if isinstance(m, SystemMessage)]
    answers = [m for m in stored if isinstance(m, AIMessage)]
    assert len(answers) == 2
    assert all(m.response_metadata["prompt_version"] == PROMPT.version for m in answers)


async def test_prompt_change_between_turns(tools: list[Any]) -> None:
    saver = InMemorySaver()
    model = ScriptedChatModel(answers=[AIMessage("velho"), AIMessage("novo")])
    prompt_b = load_system_prompt("Prompt B")
    await compile_graph(model, tools, saver).ainvoke(say("um"), config())
    graph_b = compile_graph(model, tools, saver, prompt_b)
    await graph_b.ainvoke(say("dois"), config())
    assert model.calls[1][0] == SystemMessage("Prompt B")
    stored = (await graph_b.aget_state(config())).values["messages"]
    versions = [m.response_metadata["prompt_version"] for m in stored if isinstance(m, AIMessage)]
    assert versions == [PROMPT.version, prompt_b.version]
    assert PROMPT.version != prompt_b.version
