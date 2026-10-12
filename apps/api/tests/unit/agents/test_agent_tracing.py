"""The attendant's spans (`agent-tracing` spec), read back from the session's
in-memory exporter. The scripted model never touches the network."""

import uuid
from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import NoOpTracer, SpanKind, StatusCode

from fornada_api.agents.attendant import tracing
from fornada_api.agents.attendant.attendant import GraphAttendant
from fornada_api.agents.attendant.graph import build_graph
from fornada_api.agents.attendant.prompt import load_system_prompt
from tests.unit.agents.fakes import ScriptedChatModel, tool_call

pytestmark = pytest.mark.anyio

PROMPT = load_system_prompt("Prompt de teste")
TURN_SPAN = "invoke_agent fornada-attendant"


class ProviderDown(Exception):
    """Stands in for a provider error such as `APIConnectionError`."""


class FailingChatModel(ScriptedChatModel):
    def _generate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> ChatResult:
        raise ProviderDown("provider unreachable")


@tool
async def search_catalog() -> str:
    """Lists the cakes."""
    return "bolo-chocolate"


def build(model: ScriptedChatModel) -> tuple[GraphAttendant, Any]:
    graph = build_graph(model, [search_catalog], PROMPT).compile(checkpointer=InMemorySaver())
    return GraphAttendant(graph), graph


def turn_spans(exporter: InMemorySpanExporter) -> list[ReadableSpan]:
    return [s for s in exporter.get_finished_spans() if s.name == TURN_SPAN]


def attrs(span: ReadableSpan) -> dict[str, Any]:
    return dict(span.attributes or {})


# --- one span per turn -------------------------------------------------------


async def test_one_internal_turn_span_per_turn(spans: InMemorySpanExporter) -> None:
    agent, _ = build(ScriptedChatModel(answers=[AIMessage("Olá!")]))
    await agent.reply(uuid.uuid4(), "oi")

    (span,) = turn_spans(spans)
    assert span.kind is SpanKind.INTERNAL
    assert attrs(span)[tracing.GEN_AI_OPERATION_NAME] == "invoke_agent"
    assert attrs(span)[tracing.GEN_AI_AGENT_NAME] == "fornada-attendant"


async def test_turn_span_is_a_child_of_the_request_span(spans: InMemorySpanExporter) -> None:
    agent, _ = build(ScriptedChatModel(answers=[AIMessage("Olá!")]))
    with trace.get_tracer("test").start_as_current_span("POST /conversations") as request:
        await agent.reply(uuid.uuid4(), "oi")

    (span,) = turn_spans(spans)
    assert span.parent is not None
    assert span.parent.span_id == request.get_span_context().span_id


async def test_each_turn_has_its_own_span(spans: InMemorySpanExporter) -> None:
    agent, _ = build(ScriptedChatModel(answers=[AIMessage("um"), AIMessage("dois")]))
    conversation = uuid.uuid4()
    await agent.reply(conversation, "a")
    await agent.reply(conversation, "b")

    first, second = turn_spans(spans)
    assert first.context and second.context
    assert first.context.trace_id != second.context.trace_id


# --- attributes ----------------------------------------------------------------


async def test_turn_span_carries_the_conversation_as_session(
    spans: InMemorySpanExporter,
) -> None:
    agent, _ = build(ScriptedChatModel(answers=[AIMessage("Olá!")]))
    conversation = uuid.uuid4()
    await agent.reply(conversation, "oi")

    (span,) = turn_spans(spans)
    assert attrs(span)[tracing.GEN_AI_CONVERSATION_ID] == str(conversation)
    assert attrs(span)[tracing.SESSION_ID] == str(conversation)


async def test_turn_span_carries_the_prompt_version(spans: InMemorySpanExporter) -> None:
    agent, _ = build(ScriptedChatModel(answers=[AIMessage("Olá!")]))
    await agent.reply(uuid.uuid4(), "oi")

    (span,) = turn_spans(spans)
    assert attrs(span)[tracing.FORNADA_PROMPT_VERSION] == PROMPT.version


async def test_turn_span_has_no_model_or_token_attributes(spans: InMemorySpanExporter) -> None:
    model = ScriptedChatModel(
        answers=[tool_call("search_catalog", {}, "c1"), AIMessage("ok"), AIMessage("fim")]
    )
    agent, _ = build(model)
    await agent.reply(uuid.uuid4(), "catálogo")

    (span,) = turn_spans(spans)
    keys = attrs(span).keys()
    assert tracing.GEN_AI_PROVIDER_NAME not in keys
    assert tracing.GEN_AI_REQUEST_MODEL not in keys
    assert not [k for k in keys if k.startswith("gen_ai.usage.")]


# --- errors --------------------------------------------------------------------


async def test_failed_turn_marks_the_span_as_error(spans: InMemorySpanExporter) -> None:
    agent, _ = build(FailingChatModel(answers=[AIMessage("nunca")]))
    with pytest.raises(ProviderDown):
        await agent.reply(uuid.uuid4(), "oi")

    (span,) = turn_spans(spans)
    assert span.status.status_code is StatusCode.ERROR
    assert attrs(span)[tracing.ERROR_TYPE] == "ProviderDown"
    assert [e.name for e in span.events] == ["exception"]


async def test_successful_turn_is_not_an_error(spans: InMemorySpanExporter) -> None:
    agent, _ = build(ScriptedChatModel(answers=[AIMessage("Olá!")]))
    await agent.reply(uuid.uuid4(), "oi")

    (span,) = turn_spans(spans)
    assert span.status.status_code is StatusCode.UNSET
    assert tracing.ERROR_TYPE not in attrs(span)


# --- tracing does not change the turn ----------------------------------------


async def run_conversation() -> tuple[list[list[str]], list[BaseMessage]]:
    model = ScriptedChatModel(
        answers=[tool_call("search_catalog", {}, "c1"), AIMessage("Temos bolo"), AIMessage("ok")]
    )
    agent, graph = build(model)
    conversation = uuid.uuid4()
    replies = [await agent.reply(conversation, "catálogo"), await agent.reply(conversation, "ok")]
    config = {"configurable": {"thread_id": str(conversation)}}
    stored = (await graph.aget_state(config)).values["messages"]
    return replies, stored


def comparable(messages: list[BaseMessage]) -> list[tuple[str, Any]]:
    # Ids are random per run; type and content are what the turn produced.
    return [(m.type, m.content) for m in messages]


async def test_same_turn_with_and_without_tracing(
    spans: InMemorySpanExporter, monkeypatch: pytest.MonkeyPatch
) -> None:
    traced_replies, traced_stored = await run_conversation()
    assert turn_spans(spans)

    spans.clear()
    monkeypatch.setattr(tracing, "tracer", NoOpTracer())
    plain_replies, plain_stored = await run_conversation()

    assert turn_spans(spans) == []
    assert traced_replies == plain_replies == [["Temos bolo"], ["ok"]]
    assert comparable(traced_stored) == comparable(plain_stored)
