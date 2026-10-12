"""The attendant's spans (`agent-tracing` spec), read back from the session's
in-memory exporter. The scripted model never touches the network."""

import uuid
from typing import Any

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.tools import ToolException, tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import NoOpTracer, SpanKind, StatusCode
from pydantic import SecretStr

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


@tool
async def check_capacity(date: str) -> str:
    """Free kg on a date."""
    return "5 kg"


@tool
async def calculate_quote(weight_kg: float) -> str:
    """Prices a cake."""
    if weight_kg % 0.5:
        raise ToolException("weight must be in steps of 0.5 kg")
    return "224.75"


calculate_quote.handle_tool_error = True


@tool
async def get_order(order_id: int, phone: str) -> str:
    """An order's status; echoes the phone, as the real tool returns customer data."""
    return f"pedido {order_id} do telefone {phone}: confirmado"


TOOLS = [search_catalog, check_capacity, calculate_quote, get_order]


def build(model: ScriptedChatModel) -> tuple[GraphAttendant, Any]:
    graph = build_graph(model, TOOLS, PROMPT).compile(checkpointer=InMemorySaver())
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


# --- chat spans --------------------------------------------------------------

CHAT_SPAN = "chat claude-haiku-4-5"


def chat_spans(exporter: InMemorySpanExporter) -> list[ReadableSpan]:
    return [s for s in exporter.get_finished_spans() if s.name == CHAT_SPAN]


def answer(text: str, **fields: Any) -> AIMessage:
    """A model answer as `ChatAnthropic` returns it, with usage and metadata."""
    return AIMessage(text, **fields)


async def test_one_chat_span_per_model_call(spans: InMemorySpanExporter) -> None:
    model = ScriptedChatModel(answers=[tool_call("search_catalog", {}, "c1"), AIMessage("ok")])
    agent, _ = build(model)
    await agent.reply(uuid.uuid4(), "catálogo")

    (turn,) = turn_spans(spans)
    chats = chat_spans(spans)
    assert turn.context is not None
    assert len(chats) == 2
    for chat in chats:
        assert chat.kind is SpanKind.CLIENT
        assert chat.parent is not None
        assert chat.parent.span_id == turn.context.span_id


async def test_chat_span_names_the_provider_and_model(spans: InMemorySpanExporter) -> None:
    agent, _ = build(ScriptedChatModel(answers=[AIMessage("Olá!")]))
    await agent.reply(uuid.uuid4(), "oi")

    (chat,) = chat_spans(spans)
    assert attrs(chat)[tracing.GEN_AI_OPERATION_NAME] == "chat"
    assert attrs(chat)[tracing.GEN_AI_PROVIDER_NAME] == "anthropic"
    assert attrs(chat)[tracing.GEN_AI_REQUEST_MODEL] == "claude-haiku-4-5"


async def test_chat_span_carries_prompt_version_and_session(spans: InMemorySpanExporter) -> None:
    agent, _ = build(ScriptedChatModel(answers=[AIMessage("Olá!")]))
    conversation = uuid.uuid4()
    await agent.reply(conversation, "oi")

    (chat,) = chat_spans(spans)
    assert attrs(chat)[tracing.FORNADA_PROMPT_VERSION] == PROMPT.version
    assert attrs(chat)[tracing.GEN_AI_CONVERSATION_ID] == str(conversation)
    assert attrs(chat)[tracing.SESSION_ID] == str(conversation)


async def test_chat_span_carries_usage_and_response(spans: InMemorySpanExporter) -> None:
    reply = answer(
        "Olá!",
        usage_metadata={"input_tokens": 1200, "output_tokens": 85, "total_tokens": 1285},
        # Keys `langchain-anthropic` 1.7.5 puts in `response_metadata`.
        response_metadata={
            "id": "msg_01",
            "model_name": "claude-haiku-4-5-20251001",
            "stop_reason": "end_turn",
        },
    )
    agent, _ = build(ScriptedChatModel(answers=[reply]))
    await agent.reply(uuid.uuid4(), "oi")

    (chat,) = chat_spans(spans)
    assert attrs(chat)[tracing.GEN_AI_USAGE_INPUT_TOKENS] == 1200
    assert attrs(chat)[tracing.GEN_AI_USAGE_OUTPUT_TOKENS] == 85
    assert attrs(chat)[tracing.GEN_AI_RESPONSE_MODEL] == "claude-haiku-4-5-20251001"
    assert attrs(chat)[tracing.GEN_AI_RESPONSE_ID] == "msg_01"
    assert attrs(chat)[tracing.GEN_AI_RESPONSE_FINISH_REASONS] == ("end_turn",)


async def test_chat_span_reads_the_openai_finish_reason(spans: InMemorySpanExporter) -> None:
    # `langchain-openai` 1.6.7 names it `finish_reason`, not `stop_reason`.
    reply = answer("Olá!", response_metadata={"id": "chatcmpl-1", "finish_reason": "stop"})
    agent, _ = build(ScriptedChatModel(answers=[reply]))
    await agent.reply(uuid.uuid4(), "oi")

    (chat,) = chat_spans(spans)
    assert attrs(chat)[tracing.GEN_AI_RESPONSE_FINISH_REASONS] == ("stop",)


async def test_chat_span_without_usage_has_no_token_attributes(
    spans: InMemorySpanExporter,
) -> None:
    agent, _ = build(ScriptedChatModel(answers=[AIMessage("Olá!")]))
    await agent.reply(uuid.uuid4(), "oi")

    (chat,) = chat_spans(spans)
    assert not [k for k in attrs(chat) if k.startswith("gen_ai.usage.")]
    assert tracing.GEN_AI_RESPONSE_FINISH_REASONS not in attrs(chat)


async def test_failed_model_call_marks_the_chat_span_as_error(
    spans: InMemorySpanExporter,
) -> None:
    agent, _ = build(FailingChatModel(answers=[AIMessage("nunca")]))
    with pytest.raises(ProviderDown):
        await agent.reply(uuid.uuid4(), "oi")

    (chat,) = chat_spans(spans)
    assert chat.status.status_code is StatusCode.ERROR
    assert attrs(chat)[tracing.ERROR_TYPE] == "ProviderDown"
    assert [e.name for e in chat.events] == ["exception"]
    # The status carries no exception message: messages can hold customer data.
    assert not chat.status.description


async def test_chat_span_carries_no_conversation_text(spans: InMemorySpanExporter) -> None:
    secret = "Meu telefone é 11 98765-4321"
    agent, _ = build(ScriptedChatModel(answers=[AIMessage("Anotado, 11 98765-4321")]))
    await agent.reply(uuid.uuid4(), secret)

    (chat,) = chat_spans(spans)
    values = " ".join(str(v) for v in attrs(chat).values())
    assert "98765-4321" not in values
    assert PROMPT.text not in values


def test_langchain_models_report_provider_and_model() -> None:
    """The real chat classes give the values `chat` spans read, so a LangChain
    change to `_get_ls_params()` breaks here, not silently in Langfuse."""
    anthropic = ChatAnthropic(
        model_name="claude-haiku-4-5", api_key=SecretStr("sk-ant-test"), timeout=None, stop=None
    )
    openai = ChatOpenAI(model="gpt-5-mini", api_key=SecretStr("sk-test"))

    for model, provider, name in [
        (anthropic, "anthropic", "claude-haiku-4-5"),
        (openai, "openai", "gpt-5-mini"),
    ]:
        params = model._get_ls_params()
        assert (params.get("ls_provider"), params.get("ls_model_name")) == (provider, name)


# --- tool spans ----------------------------------------------------------------


def tool_spans(exporter: InMemorySpanExporter) -> list[ReadableSpan]:
    return [s for s in exporter.get_finished_spans() if s.name.startswith("execute_tool ")]


def calls(*pairs: tuple[str, dict[str, Any], str]) -> AIMessage:
    """One model answer that requests several tools at once."""
    return AIMessage(content="", tool_calls=[{"name": n, "args": a, "id": i} for n, a, i in pairs])


async def test_one_internal_tool_span_per_call(spans: InMemorySpanExporter) -> None:
    model = ScriptedChatModel(
        answers=[tool_call("search_catalog", {}, "toolu_01"), AIMessage("ok")]
    )
    agent, _ = build(model)
    conversation = uuid.uuid4()
    await agent.reply(conversation, "catálogo")

    (turn,) = turn_spans(spans)
    (span,) = tool_spans(spans)
    assert turn.context is not None and span.parent is not None
    assert span.name == "execute_tool search_catalog"
    assert span.kind is SpanKind.INTERNAL
    assert span.parent.span_id == turn.context.span_id
    assert attrs(span) == {
        tracing.GEN_AI_OPERATION_NAME: "execute_tool",
        tracing.GEN_AI_TOOL_NAME: "search_catalog",
        tracing.GEN_AI_TOOL_CALL_ID: "toolu_01",
        tracing.GEN_AI_TOOL_TYPE: "function",
        tracing.GEN_AI_CONVERSATION_ID: str(conversation),
        tracing.SESSION_ID: str(conversation),
    }
    assert span.status.status_code is StatusCode.UNSET


async def test_two_tools_in_one_answer_are_siblings(spans: InMemorySpanExporter) -> None:
    both = calls(
        ("check_capacity", {"date": "2026-10-20"}, "c1"),
        ("calculate_quote", {"weight_kg": 2.0}, "c2"),
    )
    agent, _ = build(ScriptedChatModel(answers=[both, AIMessage("ok")]))
    await agent.reply(uuid.uuid4(), "orçamento")

    (turn,) = turn_spans(spans)
    found = {s.name: s for s in tool_spans(spans)}
    assert set(found) == {"execute_tool check_capacity", "execute_tool calculate_quote"}
    assert attrs(found["execute_tool check_capacity"])[tracing.GEN_AI_TOOL_CALL_ID] == "c1"
    assert attrs(found["execute_tool calculate_quote"])[tracing.GEN_AI_TOOL_CALL_ID] == "c2"
    assert turn.context is not None
    for span in found.values():
        assert span.parent is not None
        assert span.parent.span_id == turn.context.span_id


async def test_waterfall_follows_the_graph(spans: InMemorySpanExporter) -> None:
    model = ScriptedChatModel(
        answers=[
            tool_call("check_capacity", {"date": "2026-10-20"}, "c1"),
            tool_call("calculate_quote", {"weight_kg": 2.0}, "c2"),
            AIMessage("Fica R$ 224,75"),
        ]
    )
    agent, _ = build(model)
    await agent.reply(uuid.uuid4(), "quanto fica?")

    (turn,) = turn_spans(spans)
    assert turn.context is not None
    children = sorted(
        (
            s
            for s in spans.get_finished_spans()
            if s.parent is not None and s.parent.span_id == turn.context.span_id
        ),
        key=lambda s: s.start_time or 0,
    )
    assert [s.name for s in children] == [
        CHAT_SPAN,
        "execute_tool check_capacity",
        CHAT_SPAN,
        "execute_tool calculate_quote",
        CHAT_SPAN,
    ]
    # Each tool starts after the model call that requested it has ended.
    for chat, tool_span in [(children[0], children[1]), (children[2], children[3])]:
        assert (chat.end_time or 0) <= (tool_span.start_time or 0)


async def test_tool_error_result_marks_only_the_tool_span(spans: InMemorySpanExporter) -> None:
    model = ScriptedChatModel(
        answers=[tool_call("calculate_quote", {"weight_kg": 2.3}, "c1"), AIMessage("Use 2,5 kg")]
    )
    agent, _ = build(model)
    await agent.reply(uuid.uuid4(), "2,3 kg")

    (span,) = tool_spans(spans)
    assert span.status.status_code is StatusCode.ERROR
    assert attrs(span)[tracing.ERROR_TYPE] == "tool_error"
    # The status says nothing of the tool's message, which can hold customer data.
    assert not span.status.description
    (turn,) = turn_spans(spans)
    assert turn.status.status_code is StatusCode.UNSET


async def test_invalid_tool_arguments_mark_the_tool_span(spans: InMemorySpanExporter) -> None:
    model = ScriptedChatModel(
        answers=[tool_call("calculate_quote", {"weight_kg": "dois"}, "c1"), AIMessage("ok")]
    )
    agent, _ = build(model)
    await agent.reply(uuid.uuid4(), "orçamento")

    (span,) = tool_spans(spans)
    assert span.status.status_code is StatusCode.ERROR
    assert attrs(span)[tracing.ERROR_TYPE] == "tool_error"


async def test_tool_spans_carry_no_arguments_or_results(spans: InMemorySpanExporter) -> None:
    model = ScriptedChatModel(
        answers=[
            tool_call("get_order", {"order_id": 482, "phone": "11 98765-4321"}, "c1"),
            AIMessage("ok"),
        ]
    )
    agent, _ = build(model)
    await agent.reply(uuid.uuid4(), "meu pedido 482, telefone 11 98765-4321")

    for span in spans.get_finished_spans():
        values = " ".join(str(v) for v in attrs(span).values())
        assert "98765-4321" not in values, span.name
        assert "confirmado" not in values, span.name
