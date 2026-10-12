"""The attendant's entry point: one customer message in, the bot's replies out.

The HTTP layer depends only on `Attendant`. `GraphAttendant` runs one turn of
the LangGraph graph on the conversation's thread.
"""

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol
from uuid import UUID

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph
from opentelemetry.trace import SpanKind, StatusCode

from fornada_api.agents.attendant import tracing

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
        conversation = str(conversation_id)
        # The turn span. Nodes run inside it, so `chat` and `execute_tool`
        # spans become its children. Attributes known up front go in at
        # creation, where samplers can see them.
        with tracing.tracer.start_as_current_span(
            f"{tracing.OP_INVOKE_AGENT} {tracing.AGENT_NAME}",
            kind=SpanKind.INTERNAL,
            attributes={
                tracing.GEN_AI_OPERATION_NAME: tracing.OP_INVOKE_AGENT,
                tracing.GEN_AI_AGENT_NAME: tracing.AGENT_NAME,
                tracing.GEN_AI_CONVERSATION_ID: conversation,
                tracing.SESSION_ID: conversation,
            },
            # The default status description is "Type: message", and a message
            # can carry customer data. The status is set below, without one.
            set_status_on_exception=False,
        ) as span:
            try:
                output = await self._graph.ainvoke({"messages": [HumanMessage(text)]}, config)
            except Exception as error:
                span.set_status(StatusCode.ERROR)
                span.set_attribute(tracing.ERROR_TYPE, type(error).__name__)
                # Re-raised: leaving the `with` records the exception event once.
                raise
            # Known only after the graph ran: the version the model calls used.
            span.set_attribute(tracing.FORNADA_PROMPT_VERSION, output["prompt_version"])
        return turn_replies(output["messages"]) or [FALLBACK_REPLY]
