import pytest
from langchain_core.messages import AIMessage, HumanMessage

from tests.unit.agents.fakes import ScriptedChatModel

pytestmark = pytest.mark.anyio


async def test_answers_come_back_in_order_and_calls_are_recorded() -> None:
    model = ScriptedChatModel(answers=[AIMessage("um"), AIMessage("dois")])
    first = await model.ainvoke([HumanMessage("a")])
    second = await model.ainvoke([HumanMessage("b")])
    assert (first.content, second.content) == ("um", "dois")
    assert [call[0].content for call in model.calls] == ["a", "b"]
