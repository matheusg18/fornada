import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from fornada_api.agents.attendant.nodes import make_call_model
from fornada_api.agents.attendant.prompt import load_system_prompt
from tests.unit.agents.fakes import ScriptedChatModel

pytestmark = pytest.mark.anyio

PROMPT = load_system_prompt("Você é a atendente.")


async def run_node(model: ScriptedChatModel):
    node = make_call_model(model, PROMPT)
    return await node({"messages": [HumanMessage("oi")], "prompt_version": ""})


async def test_model_sees_the_system_prompt_first() -> None:
    model = ScriptedChatModel(answers=[AIMessage("olá")])
    await run_node(model)
    first, second = model.calls[0]
    assert first == SystemMessage("Você é a atendente.")
    assert second.content == "oi"


async def test_answer_carries_the_prompt_version() -> None:
    update = await run_node(ScriptedChatModel(answers=[AIMessage("olá")]))
    assert update["messages"][0].response_metadata["prompt_version"] == PROMPT.version
    assert update["prompt_version"] == PROMPT.version


async def test_update_has_no_system_message() -> None:
    update = await run_node(ScriptedChatModel(answers=[AIMessage("olá")]))
    assert not [m for m in update["messages"] if isinstance(m, SystemMessage)]
