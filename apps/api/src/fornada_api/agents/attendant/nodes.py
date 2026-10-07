"""The graph's nodes: the model call and the tool runner."""

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode

from fornada_api.agents.attendant.prompt import SystemPrompt
from fornada_api.agents.attendant.state import AttendantState

PROMPT_VERSION_KEY = "prompt_version"


def make_call_model(
    model: BaseChatModel | Any, prompt: SystemPrompt
) -> Callable[[AttendantState], Awaitable[dict[str, Any]]]:
    """The model node. `model` must already have the tools bound.

    The system prompt goes first in every call and is never returned, so it is
    not saved in the conversation. The answer records the prompt version.
    """

    async def call_model(state: AttendantState) -> dict[str, Any]:
        answer = await model.ainvoke([SystemMessage(prompt.text), *state["messages"]])
        answer.response_metadata = {**answer.response_metadata, PROMPT_VERSION_KEY: prompt.version}
        return {"messages": [answer], PROMPT_VERSION_KEY: prompt.version}

    return call_model


def make_tool_node(tools: Sequence[BaseTool]) -> ToolNode:
    return ToolNode(list(tools))
