"""Fixtures for unit and integration tests. The global tracer and meter
providers can be set only once per process, so span tests share one in-memory
exporter and metric tests one in-memory reader for the session."""

import os

import pytest
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import Counter, Histogram, MeterProvider
from opentelemetry.sdk.metrics.export import AggregationTemporality, InMemoryMetricReader
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


@pytest.fixture(scope="session")
def session_metric_reader() -> InMemoryMetricReader:
    """One in-memory reader on the process-wide meter provider, registered once.
    Delta, like the app's exporter, so each collect holds only what was
    recorded since the previous one."""
    delta = {kind: AggregationTemporality.DELTA for kind in (Counter, Histogram)}
    reader = InMemoryMetricReader(preferred_temporality=delta)
    metrics.set_meter_provider(MeterProvider(metric_readers=[reader]))
    return reader


@pytest.fixture
def metric_reader(session_metric_reader: InMemoryMetricReader) -> InMemoryMetricReader:
    """The session reader, drained of what earlier tests recorded."""
    session_metric_reader.get_metrics_data()
    return session_metric_reader
