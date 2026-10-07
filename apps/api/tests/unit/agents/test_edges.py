from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END

from fornada_api.agents.attendant.edges import route_after_model
from fornada_api.agents.attendant.state import AttendantState
from tests.unit.agents.fakes import tool_call


def state_with(*messages) -> AttendantState:
    return {"messages": list(messages), "prompt_version": "sha256:000000000000"}


def test_tool_calling_answer_goes_to_tools() -> None:
    state = state_with(HumanMessage("oi"), tool_call("search_catalog", {}, "c1"))
    assert route_after_model(state) == "tools"


def test_text_answer_ends_the_turn() -> None:
    assert route_after_model(state_with(HumanMessage("oi"), AIMessage("olá"))) == END


def test_text_plus_tool_calls_goes_to_tools() -> None:
    answer = AIMessage(
        content="Vou ver",
        tool_calls=[{"name": "check_capacity", "args": {}, "id": "c1"}],
    )
    assert route_after_model(state_with(HumanMessage("oi"), answer)) == "tools"
