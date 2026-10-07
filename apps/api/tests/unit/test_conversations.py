import json
import logging
import uuid
from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from fornada_api.core.config import LogSettings, get_settings
from fornada_api.core.logging import configure_logging
from fornada_api.dependencies import get_attendant
from fornada_api.infrastructure.engine import get_engine, get_sessionmaker
from fornada_api.main import app

REPLY = "Olá! Aqui é a Fornada."


class StubAttendant:
    async def reply(self, conversation_id: UUID, text: str) -> list[str]:
        return [REPLY]


def clear_caches() -> None:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The app with an unreachable database: the endpoint must not need it."""
    monkeypatch.setenv("DB__URL", "postgresql://x:pw@127.0.0.1:1/x")
    monkeypatch.setenv("LLM__PROVIDER", "anthropic")
    monkeypatch.setenv("LLM__ANTHROPIC__API_KEY", "sk-ant-test")
    monkeypatch.setenv("LOG__LEVEL", "INFO")
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    clear_caches()
    with TestClient(app) as client:
        app.dependency_overrides[get_attendant] = StubAttendant
        yield client
    clear_caches()
    app.dependency_overrides.clear()
    root.handlers[:], root.level = handlers, level


def post(client: TestClient, conversation_id: UUID | str, body: object):
    return client.post(f"/conversations/{conversation_id}/messages", json=body)


def test_customer_sends_a_message(client: TestClient) -> None:
    conversation_id = UUID("3f1c2a4e-8d0b-4c55-9a7e-2b6f0e1d9c11")
    response = post(client, conversation_id, {"text": "Oi, quero um bolo de chocolate"})
    assert response.status_code == 200
    assert response.json() == {
        "conversation_id": str(conversation_id),
        "replies": [{"text": REPLY}],
    }


def test_first_message_to_a_new_id(client: TestClient) -> None:
    assert post(client, uuid.uuid4(), {"text": "oi"}).status_code == 200


def test_id_is_not_a_uuid(client: TestClient) -> None:
    assert post(client, "482", {"text": "oi"}).status_code == 422


@pytest.mark.parametrize("body", [{}, {"text": "   "}, {"text": ""}, {"text": 42}, ["oi"]])
def test_invalid_body(client: TestClient, body: object) -> None:
    assert post(client, uuid.uuid4(), body).status_code == 422


class TwoReplies:
    async def reply(self, conversation_id: UUID, text: str) -> list[str]:
        return ["primeira", "segunda"]


def test_every_reply_is_returned_in_order(client: TestClient) -> None:
    app.dependency_overrides[get_attendant] = TwoReplies
    response = post(client, uuid.uuid4(), {"text": "oi"})
    assert response.json()["replies"] == [{"text": "primeira"}, {"text": "segunda"}]


def test_turn_is_logged_without_the_text(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    # The app bound logging to the stdout of fixture setup; rebind it to capsys.
    configure_logging(LogSettings(level="INFO"))
    conversation_id = uuid.uuid4()
    post(client, conversation_id, {"text": "Meu telefone é 81987654321"})
    lines = capsys.readouterr().out.splitlines()
    turns = [r for r in map(json.loads, lines) if r["message"] == "conversation turn"]
    assert len(turns) == 1
    assert turns[0]["conversation_id"] == str(conversation_id)
    assert turns[0]["text_length"] == 26
    assert not [line for line in lines if "81987654321" in line]
