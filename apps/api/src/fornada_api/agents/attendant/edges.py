"""The graph's routing: after the model answers, run tools or end the turn."""

from typing import Literal

from langchain_core.messages import AIMessage

from fornada_api.agents.attendant.state import AttendantState


def route_after_model(state: AttendantState) -> Literal["tools", "__end__"]:
    """`tools` when the last answer asks for tool calls, else the turn ends."""
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return "__end__"  # langgraph.graph.END, typed as a literal for the router
