"""The attendant's entry point: one customer message in, the bot's replies out.

The HTTP layer depends only on `Attendant`. `GraphAttendant` runs one turn of
the LangGraph graph on the conversation's thread.
"""

import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol
from uuid import UUID

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph
from opentelemetry import baggage, context
from opentelemetry.trace import SpanKind, StatusCode

from fornada_api.agents.attendant import metrics, span_content, tracing

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


def is_first_completed_turn(messages: Sequence[AnyMessage]) -> bool:
    """True when no turn before this one ended with a reply.

    A turn ends with a model answer that asks for no tool. A failed turn never
    gets there, but its customer message (and any tool round it finished) is
    already in the checkpoint, so counting customer messages would miss a
    conversation whose first message failed and was sent again."""
    last_customer = max(
        (i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=0
    )
    return not any(isinstance(m, AIMessage) and not m.tool_calls for m in messages[:last_customer])


class GraphAttendant:
    """Runs the compiled graph; the conversation id is the LangGraph thread id."""

    def __init__(
        self,
        graph: CompiledStateGraph[Any, Any, Any, Any],
        before_turn: Callable[[], Awaitable[None]] | None = None,
        *,
        capture_content: bool = False,
        chaos_enabled: bool = False,
        request_model: str | None = None,
    ) -> None:
        self._graph = graph
        # Runs before every turn, for one-time setup such as the checkpointer tables.
        self._before_turn = before_turn
        # Puts the customer message and the replies on the turn span.
        self._capture_content = capture_content
        # Marks every turn span of a chaos-mode run, so its traces can be filtered.
        self._chaos_enabled = chaos_enabled
        # The configured model, a dimension of the turn duration.
        self._request_model = request_model

    async def reply(self, conversation_id: UUID, text: str) -> list[str]:
        # Read once per turn, before the graph runs; the nodes' tasks copy it.
        persona = metrics.persona_from_baggage()
        token = metrics.current_persona.set(persona)
        # Then the client's baggage goes: the model provider's HTTP client
        # injects the current context's baggage, and baggage is untrusted input
        # of any size. Spans and the persona stay; the nodes' tasks copy both.
        otel_token = context.attach(baggage.clear())
        try:
            return await self._reply(conversation_id, text, persona)
        finally:
            context.detach(otel_token)
            metrics.current_persona.reset(token)

    async def _reply(self, conversation_id: UUID, text: str, persona: str) -> list[str]:
        if self._before_turn:
            await self._before_turn()
        config: Any = {
            "configurable": {"thread_id": str(conversation_id)},
            "recursion_limit": RECURSION_LIMIT,
        }
        conversation = str(conversation_id)
        attributes: dict[str, str | bool] = {
            tracing.GEN_AI_OPERATION_NAME: tracing.OP_INVOKE_AGENT,
            tracing.GEN_AI_AGENT_NAME: tracing.AGENT_NAME,
            tracing.GEN_AI_CONVERSATION_ID: conversation,
            tracing.SESSION_ID: conversation,
        }
        if self._chaos_enabled:
            # Absent, not false, with chaos off.
            attributes[tracing.FORNADA_CHAOS_ENABLED] = True
        if self._capture_content:
            attributes[tracing.GEN_AI_INPUT_MESSAGES] = span_content.text_messages("user", [text])
        # The turn span. Nodes run inside it, so `chat` and `execute_tool`
        # spans become its children. Attributes known up front go in at
        # creation, where samplers can see them.
        with tracing.tracer.start_as_current_span(
            f"{tracing.OP_INVOKE_AGENT} {tracing.AGENT_NAME}",
            kind=SpanKind.INTERNAL,
            attributes=attributes,
            # The default status description is "Type: message", and a message
            # can carry customer data. The status is set below, without one.
            set_status_on_exception=False,
        ) as span:
            measured = {
                tracing.GEN_AI_OPERATION_NAME: tracing.OP_INVOKE_AGENT,
                tracing.GEN_AI_AGENT_NAME: tracing.AGENT_NAME,
                metrics.FORNADA_SIMULATOR_PERSONA_ID: persona,
            }
            if self._request_model is not None:
                measured[tracing.GEN_AI_REQUEST_MODEL] = self._request_model
            start = time.perf_counter()
            try:
                output = await self._graph.ainvoke({"messages": [HumanMessage(text)]}, config)
            except Exception as error:
                span.set_status(StatusCode.ERROR)
                span.set_attribute(tracing.ERROR_TYPE, type(error).__name__)
                metrics.invoke_agent_duration.record(
                    time.perf_counter() - start,
                    {**measured, tracing.ERROR_TYPE: type(error).__name__},
                )
                # Re-raised: leaving the `with` records the exception event once.
                raise
            metrics.invoke_agent_duration.record(time.perf_counter() - start, measured)
            if is_first_completed_turn(output["messages"]):
                metrics.conversations.add(
                    1,
                    {
                        tracing.GEN_AI_AGENT_NAME: tracing.AGENT_NAME,
                        metrics.FORNADA_SIMULATOR_PERSONA_ID: persona,
                    },
                )
            # Known only after the graph ran: the version the model calls used.
            span.set_attribute(tracing.FORNADA_PROMPT_VERSION, output["prompt_version"])
            replies = turn_replies(output["messages"]) or [FALLBACK_REPLY]
            if self._capture_content:
                span.set_attribute(
                    tracing.GEN_AI_OUTPUT_MESSAGES,
                    span_content.text_messages("assistant", replies),
                )
        return replies
