"""Database spans on the engine path (`app-tracing` spec, database requirements)."""

from collections.abc import AsyncIterator

import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from fornada_api.core.telemetry import instrument_engine, uninstrument_engine

pytestmark = pytest.mark.anyio

PHONE = "+5581999991234"
NAME = "Maria Teste"
ADDRESS = "Rua das Flores, 123, Boa Viagem"


@pytest.fixture
async def exporter(app_engine: AsyncEngine) -> AsyncIterator[InMemorySpanExporter]:
    """The app engine instrumented with an in-memory provider."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    instrument_engine(app_engine, provider)
    yield exporter
    uninstrument_engine()


def statement_spans(exporter: InMemorySpanExporter) -> list[ReadableSpan]:
    return [s for s in exporter.get_finished_spans() if "db.query.text" in (s.attributes or {})]


def statement(span: ReadableSpan) -> str:
    return str((span.attributes or {})["db.query.text"])


async def test_select_is_a_client_span_with_its_statement(
    app_engine: AsyncEngine, exporter: InMemorySpanExporter
) -> None:
    async with app_engine.connect() as connection:
        await connection.execute(text("SELECT count(*) FROM products"))

    (span,) = statement_spans(exporter)
    assert span.kind is SpanKind.CLIENT
    assert span.attributes is not None
    assert span.attributes["db.system.name"] == "postgresql"
    assert span.attributes["db.namespace"] == app_engine.url.database
    assert span.attributes["db.query.text"] == "SELECT count(*) FROM products"


async def test_spans_carry_no_bound_values(
    app_engine: AsyncEngine, exporter: InMemorySpanExporter
) -> None:
    async with app_engine.connect() as connection:
        transaction = await connection.begin()
        await connection.execute(
            text("INSERT INTO customers (name, phone) VALUES (:name, :phone)"),
            {"name": NAME, "phone": PHONE},
        )
        await connection.execute(text("SELECT CAST(:address AS text)"), {"address": ADDRESS})
        await transaction.rollback()

    spans = statement_spans(exporter)
    assert any("INSERT INTO customers" in statement(s) for s in spans)
    everything = repr([(s.name, dict(s.attributes or {}), s.status.description) for s in spans])
    for value in ("5581999991234", NAME, ADDRESS):
        assert value not in everything


async def test_failed_statement_is_an_error_without_server_detail(
    app_engine: AsyncEngine, exporter: InMemorySpanExporter
) -> None:
    async with app_engine.connect() as connection:
        existing = await connection.scalar(text("SELECT phone FROM customers LIMIT 1"))
        with pytest.raises(IntegrityError):
            await connection.execute(
                text("INSERT INTO customers (name, phone) VALUES (:name, :phone)"),
                {"name": NAME, "phone": existing},
            )

    (failed,) = [s for s in statement_spans(exporter) if "INSERT INTO customers" in statement(s)]
    assert failed.status.status_code is StatusCode.ERROR
    description = failed.status.description or ""
    assert "DETAIL:" not in description
    assert str(existing) not in description
    assert NAME not in description
