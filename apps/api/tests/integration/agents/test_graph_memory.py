"""Conversation memory in the real PostgreSQL checkpointer, with a scripted model."""

import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from fornada_api.agents.attendant.attendant import GraphAttendant
from fornada_api.agents.attendant.graph import build_graph
from fornada_api.agents.attendant.prompt import load_system_prompt
from fornada_api.infrastructure.checkpointer import Checkpointer
from tests.unit.agents.fakes import ScriptedChatModel

pytestmark = pytest.mark.anyio

PROMPT = load_system_prompt("Prompt de teste")
CHECKPOINT_TABLES = {
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
}
APP_TABLES_SQL = text(
    "SELECT table_name, column_name FROM information_schema.columns"
    " WHERE table_schema = 'public' AND table_name <> ALL(:checkpoint_tables)"
    " ORDER BY table_name, ordinal_position"
)


def config(conversation: uuid.UUID) -> Any:
    return {"configurable": {"thread_id": str(conversation)}}


async def open_checkpointer() -> Checkpointer:
    checkpointer = Checkpointer(os.environ["DATABASE_URI"])
    await checkpointer.open()
    await checkpointer.ensure_setup()
    return checkpointer


def attendant(checkpointer: Checkpointer, model: ScriptedChatModel) -> GraphAttendant:
    graph = build_graph(model, [], PROMPT).compile(checkpointer=checkpointer.saver)
    return GraphAttendant(graph, before_turn=checkpointer.ensure_setup)


@pytest.fixture
async def checkpointer() -> AsyncIterator[Checkpointer]:
    checkpointer = await open_checkpointer()
    yield checkpointer
    await checkpointer.close()


@pytest.fixture
def conversations() -> list[uuid.UUID]:
    return []


@pytest.fixture(autouse=True)
async def cleanup(
    checkpointer: Checkpointer, conversations: list[uuid.UUID]
) -> AsyncIterator[None]:
    yield
    for conversation in conversations:
        await checkpointer.saver.adelete_thread(str(conversation))


def new_conversation(conversations: list[uuid.UUID]) -> uuid.UUID:
    conversation = uuid.uuid4()
    conversations.append(conversation)
    return conversation


async def test_checkpointer_tables_exist_and_app_tables_are_unchanged(
    checkpointer: Checkpointer, app_engine: AsyncEngine, conversations: list[uuid.UUID]
) -> None:
    params = {"checkpoint_tables": sorted(CHECKPOINT_TABLES)}
    async with app_engine.connect() as connection:
        before = (await connection.execute(APP_TABLES_SQL, params)).all()
    model = ScriptedChatModel(answers=[AIMessage("oi")])
    await attendant(checkpointer, model).reply(new_conversation(conversations), "oi")
    async with app_engine.connect() as connection:
        after = (await connection.execute(APP_TABLES_SQL, params)).all()
        tables = {
            row[0]
            for row in await connection.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
        }
    assert tables >= CHECKPOINT_TABLES
    assert before == after
    assert len({table for table, _ in after}) == 11


async def test_second_turn_sees_the_first(
    checkpointer: Checkpointer, conversations: list[uuid.UUID]
) -> None:
    model = ScriptedChatModel(answers=[AIMessage("um"), AIMessage("dois")])
    agent = attendant(checkpointer, model)
    conversation = new_conversation(conversations)
    await agent.reply(conversation, "primeira")
    await agent.reply(conversation, "segunda")
    assert [m.content for m in model.calls[1][1:]] == ["primeira", "um", "segunda"]


async def test_conversations_are_isolated(
    checkpointer: Checkpointer, conversations: list[uuid.UUID]
) -> None:
    model = ScriptedChatModel(answers=[AIMessage("a"), AIMessage("b")])
    agent = attendant(checkpointer, model)
    await agent.reply(new_conversation(conversations), "meu nome é Ana")
    await agent.reply(new_conversation(conversations), "qual é o meu nome?")
    assert "meu nome é Ana" not in [m.content for m in model.calls[1]]


async def test_memory_survives_a_restart(conversations: list[uuid.UUID]) -> None:
    conversation = new_conversation(conversations)
    first = await open_checkpointer()
    await attendant(first, ScriptedChatModel(answers=[AIMessage("um")])).reply(
        conversation, "primeira"
    )
    await first.close()

    second = await open_checkpointer()
    model = ScriptedChatModel(answers=[AIMessage("dois")])
    await attendant(second, model).reply(conversation, "segunda")
    await second.close()
    assert [m.content for m in model.calls[0][1:]] == ["primeira", "um", "segunda"]


async def test_stored_answer_keeps_its_prompt_version(
    checkpointer: Checkpointer, conversations: list[uuid.UUID]
) -> None:
    conversation = new_conversation(conversations)
    model = ScriptedChatModel(answers=[AIMessage("oi")])
    agent = attendant(checkpointer, model)
    await agent.reply(conversation, "oi")
    graph = build_graph(model, [], PROMPT).compile(checkpointer=checkpointer.saver)
    stored = (await graph.aget_state(config(conversation))).values["messages"]
    answers = [m for m in stored if isinstance(m, AIMessage)]
    assert [m.response_metadata["prompt_version"] for m in answers] == [PROMPT.version]
