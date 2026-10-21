"""Database spans on the checkpointer path (`app-tracing` spec, conversation-state
statements)."""

import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from langgraph.checkpoint.base import empty_checkpoint
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from fornada_api.infrastructure.checkpointer import Checkpointer

pytestmark = pytest.mark.anyio


def build_provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


async def save_and_load(checkpointer: Checkpointer) -> None:
    thread: Any = {"configurable": {"thread_id": str(uuid.uuid4()), "checkpoint_ns": ""}}
    saved: Any = await checkpointer.saver.aput(
        thread, empty_checkpoint(), {"source": "input", "step": 0}, {}
    )
    assert await checkpointer.saver.aget_tuple(saved) is not None
    await checkpointer.saver.adelete_thread(thread["configurable"]["thread_id"])


@pytest.fixture
async def traced() -> AsyncIterator[InMemorySpanExporter]:
    provider, exporter = build_provider()
    checkpointer = Checkpointer(os.environ["TEST_DATABASE_URI"], tracer_provider=provider)
    await checkpointer.open()
    await checkpointer.ensure_setup()
    exporter.clear()
    await save_and_load(checkpointer)
    await checkpointer.close()
    yield exporter


async def test_checkpoint_statements_are_client_spans(traced: InMemorySpanExporter) -> None:
    spans = [s for s in traced.get_finished_spans() if "db.query.text" in (s.attributes or {})]
    assert spans
    assert {s.kind for s in spans} == {SpanKind.CLIENT}
    statements = " ".join(str((s.attributes or {})["db.query.text"]) for s in spans)
    assert "checkpoints" in statements
    assert all((s.attributes or {})["db.system.name"] == "postgresql" for s in spans)


async def test_without_a_provider_there_are_no_spans() -> None:
    provider, exporter = build_provider()
    # Not handed to the checkpointer, so nothing may reach it.
    checkpointer = Checkpointer(os.environ["TEST_DATABASE_URI"])
    await checkpointer.open()
    await checkpointer.ensure_setup()
    await save_and_load(checkpointer)
    await checkpointer.close()
    provider.shutdown()
    assert exporter.get_finished_spans() == ()
