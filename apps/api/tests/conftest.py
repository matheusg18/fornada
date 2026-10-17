"""Fixtures for unit and integration tests. The global tracer provider can be
set only once per process, so span tests share one in-memory exporter for the
session."""

import os

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from fornada_api.core.telemetry import SEMCONV_OPT_IN

# Read once per process, by the first instrumentor that initializes, so it must
# be set before any test instruments anything; the app sets the same value.
os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", SEMCONV_OPT_IN)


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
