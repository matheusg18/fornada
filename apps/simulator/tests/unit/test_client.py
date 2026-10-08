import json
import logging
from uuid import uuid4

import httpx
import pytest

from fornada_simulator.client import ApiError, send_message

pytestmark = pytest.mark.anyio


def make_client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="http://api", transport=handler)


async def test_posts_text_to_the_conversation_path_and_returns_replies_in_order() -> None:
    conversation_id = uuid4()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"replies": [{"text": "um"}, {"text": "dois"}]})

    async with make_client(httpx.MockTransport(handler)) as http:
        replies = await send_message(http, conversation_id, "Oi, quero um bolo")

    assert replies == ["um", "dois"]
    assert seen[0].url.path == f"/conversations/{conversation_id}/messages"
    assert json.loads(seen[0].content) == {"text": "Oi, quero um bolo"}


@pytest.mark.parametrize(
    ("handler", "kind"),
    [
        (lambda r: (_ for _ in ()).throw(httpx.ConnectError("down")), "connect"),
        (lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow")), "timeout"),
        (lambda r: httpx.Response(500), "status"),
        (lambda r: httpx.Response(200, json={"nope": 1}), "bad_body"),
        (lambda r: httpx.Response(200, json={"replies": []}), "bad_body"),
        (lambda r: httpx.Response(200, content=b"not json"), "bad_body"),
    ],
)
async def test_failures_raise_api_error_with_a_kind(handler, kind: str) -> None:
    async with make_client(httpx.MockTransport(handler)) as http:
        with pytest.raises(ApiError) as info:
            await send_message(http, uuid4(), "oi")
    assert info.value.kind == kind


async def test_failure_logs_never_contain_the_message(caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    caplog.set_level(logging.DEBUG)
    async with make_client(httpx.MockTransport(handler)) as http:
        with pytest.raises(ApiError):
            await send_message(http, uuid4(), "Meu telefone é 81987654321")
    assert "81987654321" not in caplog.text
