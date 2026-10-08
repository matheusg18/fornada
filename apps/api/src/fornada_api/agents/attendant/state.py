"""The attendant graph's state: what a turn receives, keeps and returns.

Three schemas, so callers see only the edges of the graph and nodes can add
internal channels later without changing the contract. See `attendant-agent`.
"""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class InputState(TypedDict):
    """What a turn receives: the new customer message. History comes from memory."""

    messages: Annotated[list[AnyMessage], add_messages]


class OutputState(TypedDict):
    """What a turn returns: the conversation messages and the prompt version used."""

    messages: Annotated[list[AnyMessage], add_messages]
    prompt_version: str


class AttendantState(InputState, OutputState):
    """Everything the nodes read and write."""
