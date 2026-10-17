"""Tracing setup. These tests never register a global provider: they build one
with an in-memory exporter, so they need no Collector and leave the process
untouched for other tests."""

import pytest
from opentelemetry import trace
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from fornada_api.core import telemetry
from fornada_api.core.config import TelemetrySettings
from fornada_api.core.telemetry import (
    build_logger_provider,
    build_tracer_provider,
    logs_url,
    setup_tracing,
    shutdown_logging,
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


def test_logs_go_to_the_signal_path_of_the_endpoint() -> None:
    settings = TelemetrySettings(otlp_endpoint="http://edot-collector:4318")
    assert logs_url(settings) == "http://edot-collector:4318/v1/logs"


def test_log_records_identify_the_service() -> None:
    exporter = InMemoryLogRecordExporter()
    provider = build_logger_provider(ENABLED, exporter)
    provider.get_logger(__name__).emit(body="oi")
    shutdown_logging(provider)

    (record,) = exporter.get_finished_logs()
    assert record.resource.attributes["service.name"] == "fornada-api"


def test_buffered_log_records_are_exported_at_shutdown() -> None:
    exporter = InMemoryLogRecordExporter()
    provider = build_logger_provider(ENABLED, exporter)
    logger = provider.get_logger(__name__)
    for body in ("a", "b", "c"):
        logger.emit(body=body)

    shutdown_logging(provider)

    assert sorted(str(r.log_record.body) for r in exporter.get_finished_logs()) == ["a", "b", "c"]


def test_otel_environment_does_not_redirect_log_export(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://elsewhere:4318")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", "http://elsewhere:4318/v1/logs")
    endpoints: list[str | None] = []

    class SpyExporter(InMemoryLogRecordExporter):
        def __init__(self, endpoint: str | None = None) -> None:
            super().__init__()
            endpoints.append(endpoint)

    monkeypatch.setattr(telemetry, "OTLPLogExporter", SpyExporter)
    shutdown_logging(build_logger_provider(TelemetrySettings(enabled=True)))

    assert endpoints == ["http://edot-collector:4318/v1/logs"]
