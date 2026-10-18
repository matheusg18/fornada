"""The attendant's metrics (`app-metrics` spec), read back from the session's
in-memory reader. Delta temporality: each collect holds only this test's
measurements. The scripted model never touches the network."""

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

import pytest
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from opentelemetry import baggage, context
from opentelemetry.sdk.metrics.export import (
    HistogramDataPoint,
    InMemoryMetricReader,
    NumberDataPoint,
)
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from fornada_api.agents.attendant.attendant import GraphAttendant, is_first_completed_turn
from fornada_api.agents.attendant.graph import build_graph
from fornada_api.agents.attendant.metrics import TokenPrices
from tests.unit.agents.fakes import ScriptedChatModel, tool_call
from tests.unit.agents.test_agent_tracing import (
    PROMPT,
    TOOLS,
    FailingChatModel,
    ProviderDown,
    always_failing_capacity,
    build_with_real_tools,
    catalog_and_capacity,
)

pytestmark = pytest.mark.anyio

MODEL = "claude-haiku-4-5"
PRICES = TokenPrices(input_usd_per_mtok=Decimal("1.00"), output_usd_per_mtok=Decimal("5.00"))
PERSONA = "fornada.simulator.persona.id"

DURATION_BUCKETS = (
    0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92,
)  # fmt: skip
TOKEN_BUCKETS = (
    1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864,
)  # fmt: skip

ALLOWED_ATTRIBUTES = {
    "gen_ai.operation.name",
    "gen_ai.provider.name",
    "gen_ai.request.model",
    "gen_ai.response.model",
    "gen_ai.agent.name",
    "gen_ai.tool.name",
    "gen_ai.tool.type",
    "error.type",
    PERSONA,
}


def build(model: ScriptedChatModel, *, capture_content: bool = False) -> tuple[GraphAttendant, Any]:
    graph = build_graph(model, TOOLS, PROMPT, capture_content=capture_content, prices=PRICES)
    compiled = graph.compile(checkpointer=InMemorySaver())
    attendant = GraphAttendant(compiled, capture_content=capture_content, request_model=MODEL)
    return attendant, compiled


class Collected:
    """One collect of the reader, indexed by metric name."""

    def __init__(self, reader: InMemoryMetricReader) -> None:
        self.by_name: dict[str, list[Any]] = {}
        self.units: dict[str, str] = {}
        data = reader.get_metrics_data()
        if data is None:
            return
        for resource_metrics in data.resource_metrics:
            for scope_metrics in resource_metrics.scope_metrics:
                for metric in scope_metrics.metrics:
                    self.by_name.setdefault(metric.name, []).extend(metric.data.data_points)
                    self.units[metric.name] = metric.unit or ""

    def points(self, name: str) -> list[Any]:
        return self.by_name.get(name, [])

    def histogram(self, name: str) -> HistogramDataPoint:
        (point,) = self.points(name)
        assert isinstance(point, HistogramDataPoint)
        return point

    def total(self, name: str, **attributes: str) -> float:
        """Sum of a counter's points whose attributes include `attributes`."""
        return sum(
            p.value
            for p in self.points(name)
            if isinstance(p, NumberDataPoint)
            and all(attrs(p).get(k) == v for k, v in attributes.items())
        )


def attrs(point: Any) -> dict[str, Any]:
    return dict(point.attributes or {})


def duration_s(span: ReadableSpan) -> float:
    return ((span.end_time or 0) - (span.start_time or 0)) / 1e9


@contextmanager
def persona(value: str) -> Generator[None]:
    """The request context FastAPI extracts from a `baggage` header."""
    token = context.attach(baggage.set_baggage(PERSONA, value))
    try:
        yield
    finally:
        context.detach(token)


def usage(input_tokens: int, output_tokens: int, text: str = "Olá!") -> AIMessage:
    return AIMessage(
        text,
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
        response_metadata={"model_name": "claude-haiku-4-5-20251001"},
    )


# --- model calls -----------------------------------------------------------------


async def test_model_call_duration(
    metric_reader: InMemoryMetricReader, spans: InMemorySpanExporter
) -> None:
    agent, _ = build(ScriptedChatModel(answers=[usage(1200, 80)]))
    await agent.reply(uuid.uuid4(), "oi")

    collected = Collected(metric_reader)
    point = collected.histogram("gen_ai.client.inference.duration")
    assert collected.units["gen_ai.client.inference.duration"] == "s"
    assert point.count == 1
    assert point.explicit_bounds == DURATION_BUCKETS
    assert attrs(point) == {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "anthropic",
        "gen_ai.request.model": MODEL,
        "gen_ai.response.model": "claude-haiku-4-5-20251001",
        PERSONA: "none",
    }
    (chat,) = [s for s in spans.get_finished_spans() if s.name == f"chat {MODEL}"]
    assert point.sum == pytest.approx(duration_s(chat), abs=0.01)


async def test_model_call_tokens(metric_reader: InMemoryMetricReader) -> None:
    agent, _ = build(ScriptedChatModel(answers=[usage(1200, 80)]))
    await agent.reply(uuid.uuid4(), "oi")

    collected = Collected(metric_reader)
    tokens_in = collected.histogram("gen_ai.client.inference.operation.input_tokens")
    tokens_out = collected.histogram("gen_ai.client.inference.operation.output_tokens")
    assert (tokens_in.sum, tokens_out.sum) == (1200, 80)
    assert tokens_in.explicit_bounds == TOKEN_BUCKETS
    assert tokens_out.explicit_bounds == TOKEN_BUCKETS
    assert collected.units["gen_ai.client.inference.operation.input_tokens"] == "{token}"
    assert attrs(tokens_in)["gen_ai.operation.name"] == "chat"
    assert attrs(tokens_in)["gen_ai.provider.name"] == "anthropic"
    assert attrs(tokens_in)["gen_ai.request.model"] == MODEL


async def test_model_call_cost(metric_reader: InMemoryMetricReader) -> None:
    agent, _ = build(ScriptedChatModel(answers=[usage(1200, 80)]))
    await agent.reply(uuid.uuid4(), "oi")

    collected = Collected(metric_reader)
    # 1200 * 1.00 / 1e6 + 80 * 5.00 / 1e6
    assert collected.total("fornada.gen_ai.cost") == pytest.approx(0.0016)
    (point,) = collected.points("fornada.gen_ai.cost")
    assert collected.units["fornada.gen_ai.cost"] == "USD"
    assert attrs(point) == {
        "gen_ai.provider.name": "anthropic",
        "gen_ai.request.model": MODEL,
        PERSONA: "none",
    }


async def test_model_call_without_usage_records_no_cost(
    metric_reader: InMemoryMetricReader,
) -> None:
    agent, _ = build(ScriptedChatModel(answers=[AIMessage("Olá!")]))
    await agent.reply(uuid.uuid4(), "oi")

    assert Collected(metric_reader).points("fornada.gen_ai.cost") == []


async def test_failed_model_call(metric_reader: InMemoryMetricReader) -> None:
    agent, _ = build(FailingChatModel(answers=[AIMessage("nunca")]))
    with pytest.raises(ProviderDown):
        await agent.reply(uuid.uuid4(), "oi")

    collected = Collected(metric_reader)
    duration = collected.histogram("gen_ai.client.inference.duration")
    assert attrs(duration)["error.type"] == "ProviderDown"
    for name in (
        "gen_ai.client.inference.operation.input_tokens",
        "gen_ai.client.inference.operation.output_tokens",
    ):
        point = collected.histogram(name)
        assert (point.count, point.sum) == (1, 0)
        assert attrs(point)["error.type"] == "ProviderDown"
    assert collected.points("fornada.gen_ai.cost") == []


# --- turns -----------------------------------------------------------------------


async def test_turn_duration(
    metric_reader: InMemoryMetricReader, spans: InMemorySpanExporter
) -> None:
    agent, _ = build(ScriptedChatModel(answers=[AIMessage("Olá!")]))
    await agent.reply(uuid.uuid4(), "oi")

    point = Collected(metric_reader).histogram("gen_ai.invoke_agent.duration")
    assert point.explicit_bounds == DURATION_BUCKETS
    assert attrs(point) == {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.name": "fornada-attendant",
        "gen_ai.request.model": MODEL,
        PERSONA: "none",
    }
    (turn,) = [s for s in spans.get_finished_spans() if s.name.startswith("invoke_agent")]
    assert point.sum == pytest.approx(duration_s(turn), abs=0.01)


async def test_failed_turn_duration(metric_reader: InMemoryMetricReader) -> None:
    # The model asks for a tool forever, until LangGraph's recursion limit.
    looping = ScriptedChatModel(answers=[tool_call("search_catalog", {}, "c1")])
    agent, _ = build(looping)
    with pytest.raises(GraphRecursionError):
        await agent.reply(uuid.uuid4(), "oi")

    point = Collected(metric_reader).histogram("gen_ai.invoke_agent.duration")
    assert attrs(point)["error.type"] == "GraphRecursionError"


# --- tools -----------------------------------------------------------------------


async def test_tool_call_duration_and_count(
    metric_reader: InMemoryMetricReader, spans: InMemorySpanExporter
) -> None:
    model = ScriptedChatModel(
        answers=[tool_call("check_capacity", {"date": "2026-10-20"}, "c1"), AIMessage("ok")]
    )
    agent, _ = build(model)
    await agent.reply(uuid.uuid4(), "tem vaga?")

    collected = Collected(metric_reader)
    point = collected.histogram("gen_ai.execute_tool.duration")
    assert point.explicit_bounds == DURATION_BUCKETS
    assert attrs(point) == {
        "gen_ai.tool.name": "check_capacity",
        "gen_ai.tool.type": "function",
        "gen_ai.agent.name": "fornada-attendant",
        PERSONA: "none",
    }
    (tool,) = [s for s in spans.get_finished_spans() if s.name.startswith("execute_tool")]
    assert point.sum == pytest.approx(duration_s(tool), abs=0.01)

    (calls,) = collected.points("fornada.tool.calls")
    assert calls.value == 1
    assert collected.units["fornada.tool.calls"] == "{call}"
    # A successful call carries no `error.type`.
    assert attrs(calls) == {"gen_ai.tool.name": "check_capacity", PERSONA: "none"}


async def test_tool_error_is_counted(metric_reader: InMemoryMetricReader) -> None:
    agent = build_with_real_tools(catalog_and_capacity(), always_failing_capacity())
    await agent.reply(uuid.uuid4(), "tem bolo para dia 20?")

    collected = Collected(metric_reader)
    capacity = [
        p
        for p in collected.points("fornada.tool.calls")
        if attrs(p)["gen_ai.tool.name"] == "check_capacity"
    ]
    (point,) = capacity
    assert point.value == 1
    assert attrs(point)["error.type"] == "tool_error"


async def test_error_rate_per_tool(metric_reader: InMemoryMetricReader) -> None:
    # One successful call to `check_capacity`, one failing `calculate_quote` (weight
    # not in 0.5 kg steps): the rate per tool comes from the same counter.
    model = ScriptedChatModel(
        answers=[
            tool_call("check_capacity", {"date": "2026-10-20"}, "c1"),
            tool_call("calculate_quote", {"weight_kg": 2.3}, "c2"),
            AIMessage("ok"),
        ]
    )
    agent, _ = build(model)
    await agent.reply(uuid.uuid4(), "orçamento")

    collected = Collected(metric_reader)
    quote_all = collected.total("fornada.tool.calls", **{"gen_ai.tool.name": "calculate_quote"})
    quote_failed = collected.total(
        "fornada.tool.calls", **{"gen_ai.tool.name": "calculate_quote", "error.type": "tool_error"}
    )
    capacity_failed = [
        p
        for p in collected.points("fornada.tool.calls")
        if attrs(p)["gen_ai.tool.name"] == "check_capacity" and "error.type" in attrs(p)
    ]
    assert quote_failed / quote_all == 1.0
    assert capacity_failed == []


# --- conversations ---------------------------------------------------------------


async def test_three_turns_count_one_conversation(metric_reader: InMemoryMetricReader) -> None:
    agent, _ = build(ScriptedChatModel(answers=[AIMessage("um"), AIMessage("dois")]))
    conversation = uuid.uuid4()
    for text in ("a", "b", "c"):
        await agent.reply(conversation, text)

    collected = Collected(metric_reader)
    assert collected.total("fornada.conversations") == 1
    (point,) = collected.points("fornada.conversations")
    assert collected.units["fornada.conversations"] == "{conversation}"
    assert attrs(point) == {"gen_ai.agent.name": "fornada-attendant", PERSONA: "none"}


async def test_failed_first_turn_counts_on_the_retry(metric_reader: InMemoryMetricReader) -> None:
    # One checkpointer for both: the failed turn saves nothing, so the retry is
    # the conversation's first turn.
    saver = InMemorySaver()

    def attendant(model: ScriptedChatModel) -> GraphAttendant:
        graph = build_graph(model, TOOLS, PROMPT, prices=PRICES)
        return GraphAttendant(graph.compile(checkpointer=saver), request_model=MODEL)

    conversation = uuid.uuid4()
    with pytest.raises(ProviderDown):
        await attendant(FailingChatModel(answers=[AIMessage("nunca")])).reply(conversation, "oi")
    assert Collected(metric_reader).points("fornada.conversations") == []

    agent = attendant(ScriptedChatModel(answers=[AIMessage("Olá!")]))
    await agent.reply(conversation, "oi")
    await agent.reply(conversation, "tudo bem?")

    assert Collected(metric_reader).total("fornada.conversations") == 1


# --- persona ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sent", "recorded"),
    [("pechincheira", "pechincheira"), ("mae_alergica", "mae_alergica"), ("x7f3a9", "other")],
)
async def test_persona_from_baggage(
    sent: str, recorded: str, metric_reader: InMemoryMetricReader
) -> None:
    model = ScriptedChatModel(
        answers=[tool_call("search_catalog", {}, "c1"), usage(100, 10, "Temos bolo")]
    )
    agent, _ = build(model)
    with persona(sent):
        await agent.reply(uuid.uuid4(), "oi")

    collected = Collected(metric_reader)
    for name in (
        "gen_ai.invoke_agent.duration",
        "gen_ai.client.inference.duration",
        "gen_ai.execute_tool.duration",
        "fornada.tool.calls",
        "fornada.gen_ai.cost",
        "fornada.conversations",
    ):
        points = collected.points(name)
        assert points, name
        assert {attrs(p)[PERSONA] for p in points} == {recorded}, name


async def test_no_baggage_is_none(metric_reader: InMemoryMetricReader) -> None:
    agent, _ = build(ScriptedChatModel(answers=[AIMessage("Olá!")]))
    await agent.reply(uuid.uuid4(), "oi")

    point = Collected(metric_reader).histogram("gen_ai.invoke_agent.duration")
    assert attrs(point)[PERSONA] == "none"


# --- dimensions ------------------------------------------------------------------


async def test_only_allowed_attributes_with_content_capture(
    metric_reader: InMemoryMetricReader,
) -> None:
    model = ScriptedChatModel(
        answers=[
            tool_call("get_order", {"order_id": 482, "phone": "+55 81 99999-1234"}, "c1"),
            usage(500, 20, "Seu pedido está confirmado"),
        ]
    )
    agent, _ = build(model, capture_content=True)
    with persona("malandro"):
        await agent.reply(uuid.uuid4(), "meu pedido 482")

    collected = Collected(metric_reader)
    assert collected.by_name
    for name, points in collected.by_name.items():
        for point in points:
            assert set(attrs(point)) <= ALLOWED_ATTRIBUTES, name


async def test_two_conversations_share_one_series(metric_reader: InMemoryMetricReader) -> None:
    agent, _ = build(ScriptedChatModel(answers=[AIMessage("Olá!")]))
    await agent.reply(uuid.uuid4(), "oi")
    await agent.reply(uuid.uuid4(), "oi")

    point = Collected(metric_reader).histogram("gen_ai.invoke_agent.duration")
    assert point.count == 2


@pytest.mark.parametrize(
    ("messages", "first"),
    [
        # The first turn completed.
        ([HumanMessage("oi"), AIMessage("Olá!")], True),
        # A second turn.
        ([HumanMessage("oi"), AIMessage("Olá!"), HumanMessage("e aí"), AIMessage("oi")], False),
        # The first message failed and was sent again.
        ([HumanMessage("oi"), HumanMessage("oi"), AIMessage("Olá!")], True),
        # The first turn failed after a tool round; the retry is still the first reply.
        (
            [
                HumanMessage("tem vaga?"),
                tool_call("check_capacity", {"date": "2026-10-20"}, "c1"),
                ToolMessage("5 kg", tool_call_id="c1"),
                HumanMessage("tem vaga?"),
                AIMessage("Tem sim"),
            ],
            True,
        ),
    ],
)
def test_first_completed_turn(messages: list[AnyMessage], first: bool) -> None:
    assert is_first_completed_turn(messages) is first
