"""The endpoint end to end: real tools, real checkpointer, scripted model."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sqlalchemy import create_engine, text

from fornada_api.infrastructure.engine import to_async_url
from fornada_api.main import app
from tests.integration.conftest import DATABASE_URI
from tests.unit.agents.fakes import ScriptedChatModel, tool_call


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    model = ScriptedChatModel(
        answers=[
            tool_call("escalate_to_human", {"reason": "cliente pediu atendente"}, "c1"),
            AIMessage("Avisei a dona da confeitaria."),
        ]
    )
    monkeypatch.setattr("fornada_api.main.build_chat_model", lambda llm: model)
    with TestClient(app) as client:
        yield client


def test_escalation_records_the_conversation_id_from_the_url(client: TestClient) -> None:
    assert DATABASE_URI
    conversation_id = uuid.uuid4()
    # Sync engine (psycopg) just for the check and the cleanup.
    engine = create_engine(to_async_url(DATABASE_URI).set(drivername="postgresql+psycopg"))
    try:
        response = client.post(
            f"/conversations/{conversation_id}/messages", json={"text": "quero falar com a dona"}
        )
        assert response.status_code == 200
        assert response.json()["replies"] == [{"text": "Avisei a dona da confeitaria."}]
        with engine.begin() as connection:
            rows = connection.execute(
                text("SELECT reason FROM escalations WHERE thread_id = :id"),
                {"id": str(conversation_id)},
            ).all()
            assert [row[0] for row in rows] == ["cliente pediu atendente"]
    finally:
        with engine.begin() as connection:
            params = {"id": str(conversation_id)}
            connection.execute(text("DELETE FROM escalations WHERE thread_id = :id"), params)
            for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                connection.execute(text(f"DELETE FROM {table} WHERE thread_id = :id"), params)
        engine.dispose()
