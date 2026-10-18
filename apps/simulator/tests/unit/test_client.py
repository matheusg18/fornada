import json
import logging
from typing import Any
from uuid import uuid4

import httpx2
import pytest
from opentelemetry import baggage, context, trace
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import NoOpTracer, SpanKind, StatusCode

from fornada_simulator import client
from fornada_simulator.client import ApiError, send_message

pytestmark = pytest.mark.anyio


def make_client(handler: httpx2.MockTransport) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(base_url="http://api", transport=handler)


async def test_posts_text_to_the_conversation_path_and_returns_replies_in_order() -> None:
    conversation_id = uuid4()
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"replies": [{"text": "um"}, {"text": "dois"}]})

    async with make_client(httpx2.MockTransport(handler)) as http:
        replies = await send_message(http, conversation_id, "Oi, quero um bolo")

    assert replies == ["um", "dois"]
    assert seen[0].url.path == f"/conversations/{conversation_id}/messages"
    assert json.loads(seen[0].content) == {"text": "Oi, quero um bolo"}


@pytest.mark.parametrize(
    ("handler", "kind"),
    [
        (lambda r: (_ for _ in ()).throw(httpx2.ConnectError("down")), "connect"),
        (lambda r: (_ for _ in ()).throw(httpx2.ReadTimeout("slow")), "timeout"),
        (lambda r: httpx2.Response(500), "status"),
        (lambda r: httpx2.Response(200, json={"nope": 1}), "bad_body"),
        (lambda r: httpx2.Response(200, json={"replies": []}), "bad_body"),
        (lambda r: httpx2.Response(200, content=b"not json"), "bad_body"),
    ],
)
async def test_failures_raise_api_error_with_a_kind(handler, kind: str) -> None:
    async with make_client(httpx2.MockTransport(handler)) as http:
        with pytest.raises(ApiError) as info:
            await send_message(http, uuid4(), "oi")
    assert info.value.kind == kind


async def test_failure_logs_never_contain_the_message(caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(503)

    caplog.set_level(logging.DEBUG)
    async with make_client(httpx2.MockTransport(handler)) as http:
        with pytest.raises(ApiError):
            await send_message(http, uuid4(), "Meu telefone é 81987654321")
    assert "81987654321" not in caplog.text


# --- client span (`client-tracing` spec) -----------------------------------------


def ok(request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(200, json={"replies": [{"text": "Olá!"}]})


def client_spans(exporter: InMemorySpanExporter) -> list[ReadableSpan]:
    return [s for s in exporter.get_finished_spans() if s.kind is SpanKind.CLIENT]


def attrs(span: ReadableSpan) -> dict[str, Any]:
    return dict(span.attributes or {})


async def test_one_root_client_span_per_post(spans: InMemorySpanExporter) -> None:
    async with make_client(httpx2.MockTransport(ok)) as http:
        await send_message(http, uuid4(), "oi")

    (span,) = client_spans(spans)
    assert span.name == "POST /conversations/{conversation_id}/messages"
    assert span.parent is None
    assert attrs(span)["http.request.method"] == "POST"
    assert attrs(span)["url.template"] == "/conversations/{conversation_id}/messages"
    assert attrs(span)["server.address"] == "api"
    assert attrs(span)["http.response.status_code"] == 200
    assert span.status.status_code is StatusCode.UNSET


async def test_each_post_is_its_own_trace(spans: InMemorySpanExporter) -> None:
    conversation_id = uuid4()
    async with make_client(httpx2.MockTransport(ok)) as http:
        for text in ("um", "dois", "três"):
            await send_message(http, conversation_id, text)

    found = client_spans(spans)
    assert len({s.context.trace_id for s in found if s.context}) == 3


async def test_traceparent_names_the_client_span(spans: InMemorySpanExporter) -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return ok(request)

    async with make_client(httpx2.MockTransport(handler)) as http:
        await send_message(http, uuid4(), "oi")

    (span,) = client_spans(spans)
    assert span.context is not None
    version, trace_id, span_id, flags = seen[0].headers["traceparent"].split("-")
    assert version == "00"
    # Sampled bit set; the SDK may add others (W3C level 2 sets `random`, 0x02).
    assert int(flags, 16) & 0x01
    assert int(trace_id, 16) == span.context.trace_id
    assert int(span_id, 16) == span.context.span_id


async def test_span_carries_session_persona_and_run(spans: InMemorySpanExporter) -> None:
    conversation_id = uuid4()
    async with make_client(httpx2.MockTransport(ok)) as http:
        await send_message(
            http, conversation_id, "oi", persona_id="apressada", run_id="20261012T120000-ab12"
        )

    (span,) = client_spans(spans)
    assert attrs(span)["session.id"] == str(conversation_id)
    assert attrs(span)["gen_ai.conversation.id"] == str(conversation_id)
    assert attrs(span)["fornada.simulator.persona.id"] == "apressada"
    assert attrs(span)["fornada.simulator.run.id"] == "20261012T120000-ab12"


async def test_span_without_persona_has_no_persona_attributes(
    spans: InMemorySpanExporter,
) -> None:
    async with make_client(httpx2.MockTransport(ok)) as http:
        await send_message(http, uuid4(), "oi")

    (span,) = client_spans(spans)
    assert "fornada.simulator.persona.id" not in attrs(span)
    assert "fornada.simulator.run.id" not in attrs(span)


async def test_span_carries_no_message_text(spans: InMemorySpanExporter) -> None:
    async with make_client(httpx2.MockTransport(ok)) as http:
        await send_message(http, uuid4(), "Meu telefone é 81987654321", persona_id="apressada")

    (span,) = client_spans(spans)
    values = " ".join(str(v) for v in attrs(span).values())
    assert "81987654321" not in values
    assert "Olá!" not in values


async def test_500_marks_the_span_as_an_error(spans: InMemorySpanExporter) -> None:
    async with make_client(httpx2.MockTransport(lambda r: httpx2.Response(500))) as http:
        with pytest.raises(ApiError):
            await send_message(http, uuid4(), "oi")

    (span,) = client_spans(spans)
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description is None
    assert attrs(span)["http.response.status_code"] == 500
    assert attrs(span)["error.type"] == "500"


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: (_ for _ in ()).throw(httpx2.ConnectError("down")),
        lambda r: (_ for _ in ()).throw(httpx2.ReadTimeout("slow")),
        lambda r: httpx2.Response(200, json={"nope": 1}),
    ],
    ids=["connect", "timeout", "bad_body"],
)
async def test_other_failures_mark_the_span_as_an_error(
    handler, spans: InMemorySpanExporter
) -> None:
    async with make_client(httpx2.MockTransport(handler)) as http:
        with pytest.raises(ApiError):
            await send_message(http, uuid4(), "oi")

    (span,) = client_spans(spans)
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description is None
    assert attrs(span)["error.type"]


async def test_client_span_is_a_root_inside_another_span(spans: InMemorySpanExporter) -> None:
    with trace.get_tracer("test").start_as_current_span("outer"):
        async with make_client(httpx2.MockTransport(ok)) as http:
            await send_message(http, uuid4(), "oi")

    (span,) = client_spans(spans)
    assert span.parent is None


async def test_no_traceparent_when_tracing_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "tracer", NoOpTracer())
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return ok(request)

    async with make_client(httpx2.MockTransport(handler)) as http:
        await send_message(http, uuid4(), "oi")

    assert "traceparent" not in seen[0].headers


@pytest.mark.parametrize(
    ("base_url", "port"),
    [("http://api", 80), ("https://api", 443), ("http://api:8000", 8000)],
)
async def test_server_port_follows_the_scheme_default(
    base_url: str, port: int, spans: InMemorySpanExporter
) -> None:
    async with httpx2.AsyncClient(base_url=base_url, transport=httpx2.MockTransport(ok)) as http:
        await send_message(http, uuid4(), "oi")

    (span,) = client_spans(spans)
    assert attrs(span)["server.port"] == port


# --- persona baggage (`client-tracing` spec) -------------------------------------


def capture(seen: list[httpx2.Request]) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return ok(request)

    return httpx2.MockTransport(handler)


async def test_baggage_carries_only_the_persona(spans: InMemorySpanExporter) -> None:
    seen: list[httpx2.Request] = []
    async with make_client(capture(seen)) as http:
        await send_message(http, uuid4(), "oi", persona_id="apressada", run_id="run-1")

    assert seen[0].headers["baggage"] == "fornada.simulator.persona.id=apressada"


async def test_ambient_baggage_is_not_sent(spans: InMemorySpanExporter) -> None:
    seen: list[httpx2.Request] = []
    token = context.attach(baggage.set_baggage("user.id", "42"))
    try:
        async with make_client(capture(seen)) as http:
            await send_message(http, uuid4(), "oi", persona_id="apressada")
    finally:
        context.detach(token)

    assert seen[0].headers["baggage"] == "fornada.simulator.persona.id=apressada"


async def test_no_baggage_without_a_persona(spans: InMemorySpanExporter) -> None:
    seen: list[httpx2.Request] = []
    async with make_client(capture(seen)) as http:
        await send_message(http, uuid4(), "oi")

    assert "baggage" not in seen[0].headers


async def test_no_baggage_when_tracing_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client, "tracer", NoOpTracer())
    seen: list[httpx2.Request] = []
    async with make_client(capture(seen)) as http:
        await send_message(http, uuid4(), "oi", persona_id="apressada")

    assert "baggage" not in seen[0].headers
