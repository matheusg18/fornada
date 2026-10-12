"""Shared unit-test fixtures. The global tracer provider can be set only once
per process, so span tests share one in-memory exporter for the session."""

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def session_exporter() -> InMemorySpanExporter:
    """One in-memory exporter on the process-wide provider, registered once."""
    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


@pytest.fixture
def spans(session_exporter: InMemorySpanExporter) -> InMemorySpanExporter:
    session_exporter.clear()
    return session_exporter
