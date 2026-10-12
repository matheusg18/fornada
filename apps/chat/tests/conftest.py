"""Fixtures for the chat's tests. The chat's provider is private (see
`telemetry.py`), so each span test builds its own and hands it to the client."""

from collections.abc import Iterator

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from fornada_chat import client


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> Iterator[TracerProvider]:
    """A private provider with an in-memory exporter, used by the client."""
    provider = TracerProvider()
    monkeypatch.setattr(client, "tracer", provider.get_tracer("fornada_chat.client"))
    yield provider
    provider.shutdown()


@pytest.fixture
def spans(provider: TracerProvider) -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return exporter
