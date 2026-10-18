"""Chaos faults injected by the tools before their work: latency and the
`check_capacity` outage. No database: the session factory is a fake that counts
calls and fails, so a call that reaches it ends as a generic internal error."""

import datetime as dt
import logging
import time
from decimal import Decimal
from typing import Any, cast

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fornada_api.agents.attendant import tracing
from fornada_api.agents.attendant.nodes import make_wrap_tool_call
from fornada_api.agents.attendant.tools import build_tools
from fornada_api.core.config import ChaosSettings
from fornada_api.infrastructure.chaos import Chaos
from fornada_api.services.clock import FixedClock

pytestmark = pytest.mark.anyio

OUTAGE_TEXT = "internal error in check_capacity; try again later or escalate to a human"


class CountingSessionmaker:
    """Stands in for `async_sessionmaker`; any use means the tool reached the database."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> Any:
        self.calls += 1
        raise RuntimeError("no database in unit tests")


def chaos(**kwargs: object) -> Chaos:
    settings = {"enabled": True, "latency_min_ms": 0, "latency_max_ms": 0, **kwargs}
    return Chaos(ChaosSettings.model_validate(settings))


async def call(
    name: str, args: dict[str, Any], *, chaos: Chaos | None
) -> tuple[ToolMessage, CountingSessionmaker]:
    maker = CountingSessionmaker()
    tools = build_tools(
        cast(async_sessionmaker[AsyncSession], maker),
        clock=FixedClock(dt.date(2026, 10, 7)),
        daily_capacity_kg=Decimal(15),
        chaos=chaos,
    )
    graph = StateGraph(MessagesState)
    graph.add_node("tools", ToolNode(tools, awrap_tool_call=make_wrap_tool_call()))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    message = AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "call-1"}])
    state = await graph.compile().ainvoke(
        {"messages": [message]}, config={"configurable": {"thread_id": "t-chaos"}}
    )
    result = state["messages"][-1]
    assert isinstance(result, ToolMessage)
    return result, maker


def tool_span(exporter: InMemorySpanExporter, name: str) -> ReadableSpan:
    (span,) = [s for s in exporter.get_finished_spans() if s.name == f"execute_tool {name}"]
    return span


def chaos_attrs(span: ReadableSpan) -> dict[str, Any]:
    return {k: v for k, v in (span.attributes or {}).items() if k.startswith("fornada.chaos.")}


QUOTE_ARGS = {"product_slug": "bolo-chocolate", "weight_kg": "2.5", "fulfillment": "pickup"}


# --- latency -----------------------------------------------------------------


async def test_without_chaos_no_delay_or_attribute(spans: InMemorySpanExporter) -> None:
    _, maker = await call("search_catalog", {}, chaos=None)
    assert maker.calls == 1
    assert chaos_attrs(tool_span(spans, "search_catalog")) == {}


async def test_delayed_call_records_its_delay(spans: InMemorySpanExporter) -> None:
    started = time.monotonic()
    await call("search_catalog", {}, chaos=chaos(latency_min_ms=50, latency_max_ms=50))
    assert time.monotonic() - started >= 0.05
    span = tool_span(spans, "search_catalog")
    assert chaos_attrs(span) == {tracing.FORNADA_CHAOS_DELAY_MS: 50}
    assert span.end_time is not None and span.start_time is not None
    assert span.end_time - span.start_time >= 50_000_000


async def test_zero_delay_is_recorded(spans: InMemorySpanExporter) -> None:
    await call("search_catalog", {}, chaos=chaos())
    assert chaos_attrs(tool_span(spans, "search_catalog")) == {tracing.FORNADA_CHAOS_DELAY_MS: 0}


# --- check_capacity outage ---------------------------------------------------


async def test_outage_returns_the_generic_error(spans: InMemorySpanExporter) -> None:
    message, maker = await call(
        "check_capacity", {"date": "2026-10-20"}, chaos=chaos(capacity_failure_rate=1.0)
    )
    assert message.status == "error"
    assert message.content == OUTAGE_TEXT
    assert maker.calls == 0


async def test_outage_marks_the_span(spans: InMemorySpanExporter) -> None:
    await call("check_capacity", {"date": "2026-10-20"}, chaos=chaos(capacity_failure_rate=1.0))
    span = tool_span(spans, "check_capacity")
    attrs = span.attributes or {}
    assert attrs[tracing.FORNADA_CHAOS_FAULT] == tracing.CHAOS_FAULT_CAPACITY_UNAVAILABLE
    assert span.status.status_code is StatusCode.ERROR
    assert attrs[tracing.ERROR_TYPE] == "tool_error"


async def test_outage_logs_one_warning_without_traceback(
    spans: InMemorySpanExporter, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="fornada_api"):
        await call("check_capacity", {"date": "2026-10-20"}, chaos=chaos(capacity_failure_rate=1.0))
    (record,) = [r for r in caplog.records if r.name.startswith("fornada_api")]
    assert record.levelno == logging.WARNING
    assert record.getMessage() == "chaos fault injected"
    assert record.__dict__["tool"] == "check_capacity"
    assert record.__dict__["fault"] == "capacity_unavailable"
    assert record.exc_info is None


async def test_rate_zero_reaches_the_database(spans: InMemorySpanExporter) -> None:
    _, maker = await call(
        "check_capacity", {"date": "2026-10-20"}, chaos=chaos(capacity_failure_rate=0.0)
    )
    assert maker.calls == 1
    assert tracing.FORNADA_CHAOS_FAULT not in chaos_attrs(tool_span(spans, "check_capacity"))


async def test_other_tools_never_fail_by_injection(spans: InMemorySpanExporter) -> None:
    _, maker = await call("calculate_quote", QUOTE_ARGS, chaos=chaos(capacity_failure_rate=1.0))
    assert maker.calls == 1
    assert tracing.FORNADA_CHAOS_FAULT not in chaos_attrs(tool_span(spans, "calculate_quote"))
