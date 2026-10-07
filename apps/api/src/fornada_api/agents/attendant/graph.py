"""Builds the attendant's ReAct graph.

START -> call_model -> (tools -> call_model)* -> END. Compile it with a
checkpointer so each conversation keeps its messages.
"""

from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph import START, StateGraph

from fornada_api.agents.attendant.edges import route_after_model
from fornada_api.agents.attendant.nodes import make_call_model, make_tool_node
from fornada_api.agents.attendant.prompt import SystemPrompt
from fornada_api.agents.attendant.state import AttendantState, InputState, OutputState


def build_graph(
    model: BaseChatModel, tools: Sequence[BaseTool], prompt: SystemPrompt
) -> StateGraph[AttendantState, Any, InputState, OutputState]:
    builder = StateGraph(AttendantState, input_schema=InputState, output_schema=OutputState)
    builder.add_node("call_model", make_call_model(model.bind_tools(list(tools)), prompt))
    builder.add_node("tools", make_tool_node(tools))
    builder.add_edge(START, "call_model")
    builder.add_conditional_edges("call_model", route_after_model)
    builder.add_edge("tools", "call_model")
    return builder
