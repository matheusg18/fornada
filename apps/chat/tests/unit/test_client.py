import json
import logging
from typing import Any
from uuid import uuid4

import httpx2
import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import NoOpTracer, SpanKind, StatusCode

from fornada_chat import client
from fornada_chat.client import (
    DEFAULT_API_URL,
    ApiError,
    load_api_url,
    send_message,
)

pytestmark = pytest.mark.anyio

CONVERSATION_ID = uuid4()


def make_client(handler: httpx2.MockTransport | None = None, **kwargs) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        base_url=kwargs.pop("base_url", "http://api.test"), transport=handler, **kwargs
    )


def replying(status: int = 200, body: object | None = None) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status, json=body)

    return httpx2.MockTransport(handler)


def raising(exc: Exception) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise exc

    return httpx2.MockTransport(handler)


async def test_posts_text_to_the_conversation_path() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"replies": [{"text": "Olá!"}]})

    async with make_client(httpx2.MockTransport(handler)) as http:
        await send_message(http, CONVERSATION_ID, "Oi, quero um bolo de chocolate")

    (request,) = seen
    assert request.method == "POST"
    assert request.url.path == f"/conversations/{CONVERSATION_ID}/messages"
    assert json.loads(request.content) == {"text": "Oi, quero um bolo de chocolate"}


async def test_returns_every_reply_in_order() -> None:
    body = {"replies": [{"text": "Orçamento: R$ 180,00"}, {"text": "Link de pagamento: …"}]}
    async with make_client(replying(body=body)) as http:
        replies = await send_message(http, CONVERSATION_ID, "oi")
    assert replies == ["Orçamento: R$ 180,00", "Link de pagamento: …"]


def test_api_url_defaults_to_localhost() -> None:
    assert load_api_url({}) == DEFAULT_API_URL == "http://localhost:8000"


def test_api_url_comes_from_the_environment() -> None:
    assert load_api_url({"CHAT__API_URL": "http://api.local:9000"}) == "http://api.local:9000"


def test_blank_api_url_falls_back_to_the_default() -> None:
    assert load_api_url({"CHAT__API_URL": ""}) == DEFAULT_API_URL


async def test_custom_base_url_is_used() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"replies": [{"text": "ok"}]})

    async with make_client(httpx2.MockTransport(handler), base_url="http://api.local:9000") as http:
        await send_message(http, CONVERSATION_ID, "oi")

    assert str(seen[0].url) == f"http://api.local:9000/conversations/{CONVERSATION_ID}/messages"


@pytest.mark.parametrize(
    ("transport", "kind"),
    [
        (raising(httpx2.ConnectError("refused")), "connect"),
        (raising(httpx2.ReadTimeout("slow")), "timeout"),
        (replying(500, {"detail": "boom"}), "status"),
        (replying(422, {"detail": "bad"}), "status"),
        (replying(200, {"nope": []}), "bad_body"),
        (replying(200, {"replies": []}), "bad_body"),
        (replying(200, {"replies": [{"text": 1}]}), "bad_body"),
        (replying(200, {"replies": ["texto"]}), "bad_body"),
        (replying(200, ["not", "an", "object"]), "bad_body"),
    ],
)
async def test_failures_raise_api_error(transport: httpx2.MockTransport, kind: str) -> None:
    async with make_client(transport) as http:
        with pytest.raises(ApiError) as excinfo:
            await send_message(http, CONVERSATION_ID, "oi")
    assert excinfo.value.kind == kind


async def test_non_json_body_is_a_bad_body() -> None:
    transport = httpx2.MockTransport(lambda request: httpx2.Response(200, content=b"<html>"))
    async with make_client(transport) as http:
        with pytest.raises(ApiError) as excinfo:
            await send_message(http, CONVERSATION_ID, "oi")
    assert excinfo.value.kind == "bad_body"


async def test_failure_logs_the_conversation_id_but_never_the_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "81987654321"
    with caplog.at_level(logging.DEBUG):
        async with make_client(raising(httpx2.ConnectError("refused"))) as http:
            with pytest.raises(ApiError):
                await send_message(http, CONVERSATION_ID, f"Meu telefone é {secret}")

    records = [r for r in caplog.records if r.name == "fornada_chat.client"]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert records[0].__dict__["conversation_id"] == str(CONVERSATION_ID)
    assert records[0].__dict__["kind"] == "connect"
    assert all(secret not in r.getMessage() for r in caplog.records)
    assert all(secret not in str(r.__dict__) for r in caplog.records)


# --- client span (`client-tracing` spec) -----------------------------------------


def ok() -> httpx2.MockTransport:
    return replying(body={"replies": [{"text": "Olá!"}]})


def client_spans(exporter: InMemorySpanExporter) -> list[ReadableSpan]:
    return [s for s in exporter.get_finished_spans() if s.kind is SpanKind.CLIENT]


def attrs(span: ReadableSpan) -> dict[str, Any]:
    return dict(span.attributes or {})


async def test_one_root_client_span_per_post(spans: InMemorySpanExporter) -> None:
    async with make_client(ok()) as http:
        await send_message(http, CONVERSATION_ID, "oi")

    (span,) = client_spans(spans)
    assert span.name == "POST /conversations/{conversation_id}/messages"
    assert span.parent is None
    assert attrs(span)["http.request.method"] == "POST"
    assert attrs(span)["url.template"] == "/conversations/{conversation_id}/messages"
    assert attrs(span)["server.address"] == "api.test"
    assert attrs(span)["server.port"] == 80
    assert attrs(span)["http.response.status_code"] == 200
    assert attrs(span)["session.id"] == str(CONVERSATION_ID)
    assert attrs(span)["gen_ai.conversation.id"] == str(CONVERSATION_ID)
    assert not any(key.startswith("fornada.simulator.") for key in attrs(span))
    assert span.status.status_code is StatusCode.UNSET


async def test_traceparent_names_the_client_span(spans: InMemorySpanExporter) -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"replies": [{"text": "Olá!"}]})

    async with make_client(httpx2.MockTransport(handler)) as http:
        await send_message(http, CONVERSATION_ID, "oi")

    (span,) = client_spans(spans)
    assert span.context is not None
    version, trace_id, span_id, flags = seen[0].headers["traceparent"].split("-")
    assert version == "00"
    assert int(flags, 16) & 0x01
    assert int(trace_id, 16) == span.context.trace_id
    assert int(span_id, 16) == span.context.span_id


async def test_span_carries_no_message_text(spans: InMemorySpanExporter) -> None:
    async with make_client(ok()) as http:
        await send_message(http, CONVERSATION_ID, "Meu telefone é 81987654321")

    (span,) = client_spans(spans)
    values = " ".join(str(v) for v in attrs(span).values())
    assert "81987654321" not in values
    assert "Olá!" not in values
    assert "gen_ai.input.messages" not in attrs(span)
    assert "gen_ai.output.messages" not in attrs(span)


@pytest.fixture
def capturing(provider: TracerProvider, monkeypatch: pytest.MonkeyPatch) -> None:
    """Content capture on, as `use_tracer_provider` sets it at startup."""
    monkeypatch.setattr(client, "_capture_content", True)


def messages(span: ReadableSpan, key: str) -> list[dict[str, Any]]:
    return json.loads(attrs(span)[key])


@pytest.mark.usefixtures("capturing")
async def test_capture_puts_the_message_and_replies_on_the_span(
    spans: InMemorySpanExporter,
) -> None:
    body = {"replies": [{"text": "Oi! Vou ver o catálogo."}, {"text": "Temos chocolate."}]}
    async with make_client(replying(body=body)) as http:
        await send_message(http, CONVERSATION_ID, "Oi")

    (span,) = client_spans(spans)
    assert messages(span, "gen_ai.input.messages") == [
        {"role": "user", "parts": [{"type": "text", "content": "Oi"}]}
    ]
    assert messages(span, "gen_ai.output.messages") == [
        {"role": "assistant", "parts": [{"type": "text", "content": "Oi! Vou ver o catálogo."}]},
        {"role": "assistant", "parts": [{"type": "text", "content": "Temos chocolate."}]},
    ]


@pytest.mark.usefixtures("capturing")
async def test_capture_keeps_the_input_of_a_failed_post(spans: InMemorySpanExporter) -> None:
    async with make_client(raising(httpx2.ReadTimeout("slow"))) as http:
        with pytest.raises(ApiError):
            await send_message(http, CONVERSATION_ID, "Oi")

    (span,) = client_spans(spans)
    assert messages(span, "gen_ai.input.messages")[0]["parts"][0]["content"] == "Oi"
    assert "gen_ai.output.messages" not in attrs(span)


@pytest.mark.usefixtures("capturing")
async def test_capture_keeps_accents(spans: InMemorySpanExporter) -> None:
    async with make_client(ok()) as http:
        await send_message(http, CONVERSATION_ID, "Olá, é possível?")

    (span,) = client_spans(spans)
    assert "Olá, é possível?" in attrs(span)["gen_ai.input.messages"]


async def test_use_tracer_provider_sets_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "tracer", client.tracer)
    monkeypatch.setattr(client, "_capture_content", False)
    provider = TracerProvider()
    client.use_tracer_provider(provider, capture_content=True)
    assert client._capture_content is True
    provider.shutdown()


@pytest.mark.parametrize(
    ("transport", "error_type"),
    [
        (raising(httpx2.ConnectError("refused")), "connect"),
        (raising(httpx2.ReadTimeout("slow")), "timeout"),
        (replying(500, {"detail": "boom"}), "500"),
        (replying(200, {"nope": []}), "bad_body"),
    ],
)
async def test_failures_mark_the_span_as_an_error(
    transport: httpx2.MockTransport, error_type: str, spans: InMemorySpanExporter
) -> None:
    async with make_client(transport) as http:
        with pytest.raises(ApiError):
            await send_message(http, CONVERSATION_ID, "oi")

    (span,) = client_spans(spans)
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description is None
    assert attrs(span)["error.type"] == error_type


async def test_client_span_is_a_root_inside_another_span(
    provider: TracerProvider, spans: InMemorySpanExporter
) -> None:
    # Like Chainlit's websocket span, if one were ever current.
    with provider.get_tracer("test").start_as_current_span("WS /ws/socket.io/{path}"):
        async with make_client(ok()) as http:
            await send_message(http, CONVERSATION_ID, "oi")

    (span,) = client_spans(spans)
    assert span.parent is None


async def test_no_traceparent_when_tracing_is_off() -> None:
    # Before startup hands it a provider, the client's tracer is a no-op.
    assert isinstance(client.tracer, NoOpTracer)
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"replies": [{"text": "Olá!"}]})

    async with make_client(httpx2.MockTransport(handler)) as http:
        await send_message(http, CONVERSATION_ID, "oi")

    assert "traceparent" not in seen[0].headers
