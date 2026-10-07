"""The attendant's entry point: one customer message in, the bot's replies out.

The HTTP layer depends only on `Attendant`. `GraphAttendant` runs one turn of
the LangGraph graph on the conversation's thread.
"""

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol
from uuid import UUID

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph

FALLBACK_REPLY = "Desculpe, não consegui responder agora. Pode repetir?"
# About 12 model-tool rounds. Protects the token budget from a runaway tool
# loop; it does not limit what the agent may do.
RECURSION_LIMIT = 25


class Attendant(Protocol):
    async def reply(self, conversation_id: UUID, text: str) -> list[str]:
        """Answer one customer message with one or more bot messages."""
        ...


def turn_replies(messages: Sequence[AnyMessage]) -> list[str]:
    """The non-empty model texts after the last customer message, in order."""
    start = 0
    for index, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            start = index + 1
    texts = [m.text for m in messages[start:] if isinstance(m, AIMessage)]
    return [text for text in texts if text.strip()]


class GraphAttendant:
    """Runs the compiled graph; the conversation id is the LangGraph thread id."""

    def __init__(
        self,
        graph: CompiledStateGraph[Any, Any, Any, Any],
        before_turn: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._graph = graph
        # Runs before every turn, for one-time setup such as the checkpointer tables.
        self._before_turn = before_turn

    async def reply(self, conversation_id: UUID, text: str) -> list[str]:
        if self._before_turn:
            await self._before_turn()
        config: Any = {
            "configurable": {"thread_id": str(conversation_id)},
            "recursion_limit": RECURSION_LIMIT,
        }
        output = await self._graph.ainvoke({"messages": [HumanMessage(text)]}, config)
        return turn_replies(output["messages"]) or [FALLBACK_REPLY]
