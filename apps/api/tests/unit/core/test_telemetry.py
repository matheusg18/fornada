"""Tracing setup. These tests never register a global provider: they build one
with an in-memory exporter, so they need no Collector and leave the process
untouched for other tests."""

from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from fornada_api.core.config import TelemetrySettings
from fornada_api.core.telemetry import (
    build_tracer_provider,
    setup_tracing,
    shutdown_tracing,
    traces_url,
)

ENABLED = TelemetrySettings(enabled=True)


def test_spans_identify_the_service() -> None:
    exporter = InMemorySpanExporter()
    provider = build_tracer_provider(ENABLED, exporter)
    provider.get_tracer(__name__).start_span("turn").end()
    provider.shutdown()

    (span,) = exporter.get_finished_spans()
    assert span.resource.attributes["service.name"] == "fornada-api"


def test_buffered_spans_are_exported_at_shutdown() -> None:
    exporter = InMemorySpanExporter()
    provider = build_tracer_provider(ENABLED, exporter)
    tracer = provider.get_tracer(__name__)
    for name in ("a", "b", "c"):
        tracer.start_span(name).end()

    shutdown_tracing(provider)

    assert sorted(s.name for s in exporter.get_finished_spans()) == ["a", "b", "c"]


def test_disabled_tracing_registers_nothing() -> None:
    before = trace.get_tracer_provider()
    assert setup_tracing(TelemetrySettings(enabled=False)) is None
    assert trace.get_tracer_provider() is before


def test_traces_go_to_the_signal_path_of_the_endpoint() -> None:
    settings = TelemetrySettings(otlp_endpoint="http://edot-collector:4318")
    assert traces_url(settings) == "http://edot-collector:4318/v1/traces"
