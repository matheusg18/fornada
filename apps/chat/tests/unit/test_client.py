import json
import logging
from uuid import uuid4

import httpx
import pytest

from fornada_chat.client import (
    DEFAULT_API_URL,
    ApiError,
    load_api_url,
    send_message,
)

pytestmark = pytest.mark.anyio

CONVERSATION_ID = uuid4()


def make_client(handler: httpx.MockTransport | None = None, **kwargs) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=kwargs.pop("base_url", "http://api.test"), transport=handler, **kwargs
    )


def replying(status: int = 200, body: object | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


def raising(exc: Exception) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return httpx.MockTransport(handler)


async def test_posts_text_to_the_conversation_path() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"replies": [{"text": "Olá!"}]})

    async with make_client(httpx.MockTransport(handler)) as http:
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
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"replies": [{"text": "ok"}]})

    async with make_client(httpx.MockTransport(handler), base_url="http://api.local:9000") as http:
        await send_message(http, CONVERSATION_ID, "oi")

    assert str(seen[0].url) == f"http://api.local:9000/conversations/{CONVERSATION_ID}/messages"


@pytest.mark.parametrize(
    ("transport", "kind"),
    [
        (raising(httpx.ConnectError("refused")), "connect"),
        (raising(httpx.ReadTimeout("slow")), "timeout"),
        (replying(500, {"detail": "boom"}), "status"),
        (replying(422, {"detail": "bad"}), "status"),
        (replying(200, {"nope": []}), "bad_body"),
        (replying(200, {"replies": []}), "bad_body"),
        (replying(200, {"replies": [{"text": 1}]}), "bad_body"),
        (replying(200, {"replies": ["texto"]}), "bad_body"),
        (replying(200, ["not", "an", "object"]), "bad_body"),
    ],
)
async def test_failures_raise_api_error(transport: httpx.MockTransport, kind: str) -> None:
    async with make_client(transport) as http:
        with pytest.raises(ApiError) as excinfo:
            await send_message(http, CONVERSATION_ID, "oi")
    assert excinfo.value.kind == kind


async def test_non_json_body_is_a_bad_body() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"<html>"))
    async with make_client(transport) as http:
        with pytest.raises(ApiError) as excinfo:
            await send_message(http, CONVERSATION_ID, "oi")
    assert excinfo.value.kind == "bad_body"


async def test_failure_logs_the_conversation_id_but_never_the_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "81987654321"
    with caplog.at_level(logging.DEBUG):
        async with make_client(raising(httpx.ConnectError("refused"))) as http:
            with pytest.raises(ApiError):
                await send_message(http, CONVERSATION_ID, f"Meu telefone é {secret}")

    records = [r for r in caplog.records if r.name == "fornada_chat.client"]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert records[0].__dict__["conversation_id"] == str(CONVERSATION_ID)
    assert records[0].__dict__["kind"] == "connect"
    assert all(secret not in r.getMessage() for r in caplog.records)
    assert all(secret not in str(r.__dict__) for r in caplog.records)
