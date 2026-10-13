"""Builds the attendant's ReAct graph.

START -> call_model -> (tools -> call_model)* -> END. Compile it with a
checkpointer so each conversation keeps its messages.
"""

from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from fornada_api.agents.attendant.nodes import make_call_model, make_wrap_tool_call
from fornada_api.agents.attendant.prompt import SystemPrompt
from fornada_api.agents.attendant.state import AttendantState, InputState, OutputState


def build_graph(
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    prompt: SystemPrompt,
    *,
    capture_content: bool = False,
) -> StateGraph[AttendantState, Any, InputState, OutputState]:
    """`capture_content` puts conversation content and phones on the spans."""
    builder = StateGraph(AttendantState, input_schema=InputState, output_schema=OutputState)
    builder.add_node("call_model", make_call_model(model, tools, prompt, capture_content))
    tool_node = ToolNode(list(tools), awrap_tool_call=make_wrap_tool_call(capture_content))
    builder.add_node("tools", tool_node)
    builder.add_edge(START, "call_model")
    builder.add_conditional_edges("call_model", tools_condition)
    builder.add_edge("tools", "call_model")
    return builder
