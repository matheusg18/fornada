"""The graph's model node. The tool node is LangGraph's prebuilt `ToolNode`."""

from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool

from fornada_api.agents.attendant.prompt import SystemPrompt
from fornada_api.agents.attendant.state import AttendantState

PROMPT_VERSION_KEY = "prompt_version"


def make_call_model(model: BaseChatModel, tools: Sequence[BaseTool], prompt: SystemPrompt):
    """The model node, with `tools` bound to `model` once, when the graph is built.

    The system prompt goes first in every call and is never returned, so it is
    not saved in the conversation. The answer records the prompt version.
    """
    model_with_tools = model.bind_tools(list(tools))

    async def call_model(state: AttendantState) -> dict[str, Any]:
        answer = await model_with_tools.ainvoke([SystemMessage(prompt.text), *state["messages"]])
        answer.response_metadata = {**answer.response_metadata, PROMPT_VERSION_KEY: prompt.version}
        return {"messages": [answer], PROMPT_VERSION_KEY: prompt.version}

    return call_model
