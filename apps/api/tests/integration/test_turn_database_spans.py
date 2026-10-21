"""One graph turn against the real database and checkpointer: where the database
spans sit in the trace, and that no statement is traced twice (`app-tracing` spec)."""

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from langchain_core.messages import AIMessage
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind
from sqlalchemy.ext.asyncio import AsyncEngine

from fornada_api.agents.attendant.attendant import GraphAttendant
from fornada_api.agents.attendant.graph import build_graph
from fornada_api.agents.attendant.prompt import load_system_prompt
from fornada_api.agents.attendant.tools import default_tools
from fornada_api.core.telemetry import instrument_engine, uninstrument_engine
from fornada_api.infrastructure.checkpointer import Checkpointer
from tests.unit.agents.fakes import ScriptedChatModel, tool_call

pytestmark = pytest.mark.anyio

TOOL_SPAN = "execute_tool search_catalog"


@pytest.fixture
async def turn_spans(
    spans: InMemorySpanExporter, app_engine: AsyncEngine
) -> AsyncIterator[list[ReadableSpan]]:
    """The spans of one turn that calls `search_catalog`."""
    provider = trace.get_tracer_provider()
    instrument_engine(app_engine, provider)  # pyright: ignore[reportArgumentType]
    checkpointer = Checkpointer(os.environ["TEST_DATABASE_URI"], provider)  # pyright: ignore[reportArgumentType]
    await checkpointer.open()
    await checkpointer.ensure_setup()
    spans.clear()
    model = ScriptedChatModel(
        answers=[tool_call("search_catalog", {}, "call-1"), AIMessage("Temos bolos!")]
    )
    graph = build_graph(model, default_tools(), load_system_prompt("Prompt de teste"))
    conversation = uuid.uuid4()
    await GraphAttendant(
        graph.compile(checkpointer=checkpointer.saver), before_turn=checkpointer.ensure_setup
    ).reply(conversation, "quais bolos vocês têm?")
    # Read before the cleanup below, whose statements belong to no turn.
    found = list(spans.get_finished_spans())
    await checkpointer.saver.adelete_thread(str(conversation))
    await checkpointer.close()
    uninstrument_engine()
    yield found


def statement_spans(found: list[ReadableSpan]) -> list[ReadableSpan]:
    return [s for s in found if "db.query.text" in (s.attributes or {})]


def text_of(span: ReadableSpan) -> str:
    return str((span.attributes or {})["db.query.text"])


def ancestors(span: ReadableSpan, found: list[ReadableSpan]) -> list[ReadableSpan]:
    by_id = {s.context.span_id: s for s in found if s.context}
    chain: list[ReadableSpan] = []
    parent = span.parent
    while parent is not None and parent.span_id in by_id:
        span = by_id[parent.span_id]
        chain.append(span)
        parent = span.parent
    return chain


async def test_tool_statements_are_under_the_tool_span(turn_spans: list[ReadableSpan]) -> None:
    tool_statements = [s for s in statement_spans(turn_spans) if "FROM products" in text_of(s)]
    assert tool_statements
    for statement in tool_statements:
        assert statement.kind is SpanKind.CLIENT
        assert TOOL_SPAN in [a.name for a in ancestors(statement, turn_spans)]


async def test_checkpoint_statements_are_in_the_same_trace(turn_spans: list[ReadableSpan]) -> None:
    (turn,) = [s for s in turn_spans if s.name.startswith("invoke_agent")]
    checkpoint = [s for s in statement_spans(turn_spans) if "checkpoint" in text_of(s)]
    assert checkpoint
    assert {s.context.trace_id for s in checkpoint if s.context} == {
        turn.context.trace_id  # pyright: ignore[reportOptionalMemberAccess]
    }


async def test_no_statement_is_traced_twice(turn_spans: list[ReadableSpan]) -> None:
    # A second instrumentation of the same statement is not its child (the
    # engine's span is not the current span while the statement runs): it is a
    # sibling with the same text that runs inside the first one's time span.
    # The same statement run twice in a turn runs one after the other.
    statements = statement_spans(turn_spans)
    for first in statements:
        for second in statements:
            if first is second or text_of(first) != text_of(second):
                continue
            assert not (
                (first.start_time or 0) <= (second.start_time or 0) < (first.end_time or 0)
            ), text_of(first)
