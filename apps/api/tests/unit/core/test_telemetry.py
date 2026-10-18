"""Tracing setup. These tests never register a global provider: they build one
with an in-memory exporter, so they need no Collector and leave the process
untouched for other tests."""

from collections.abc import Sequence
from typing import Any, ClassVar

import pytest
from opentelemetry import metrics, trace
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    Histogram,
    HistogramDataPoint,
    MetricExporter,
    MetricExportResult,
    MetricsData,
    NumberDataPoint,
    PeriodicExportingMetricReader,
    Sum,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy.ext.asyncio import create_async_engine

from fornada_api.core import telemetry
from fornada_api.core.config import TelemetrySettings
from fornada_api.core.telemetry import (
    build_logger_provider,
    build_meter_provider,
    build_tracer_provider,
    logs_url,
    metrics_url,
    setup_metrics,
    setup_tracing,
    shutdown_logging,
    shutdown_metrics,
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
    engine = create_async_engine("postgresql+psycopg://x@127.0.0.1:1/x")
    assert setup_tracing(TelemetrySettings(enabled=False), engine) is None
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


# --- metrics -----------------------------------------------------------------


class SpyMetricExporter(MetricExporter):
    """Stands in for `OTLPMetricExporter`: records how it was built and what it
    was asked to export, so the tests exercise the real provider setup."""

    built: ClassVar[list["SpyMetricExporter"]] = []

    def __init__(self, endpoint: str | None = None, **kwargs: Any) -> None:
        super().__init__(preferred_temporality=kwargs.get("preferred_temporality"))
        self.endpoint = endpoint
        self.kwargs = kwargs
        self.exported: list[MetricsData] = []
        SpyMetricExporter.built.append(self)

    def export(self, metrics_data: MetricsData, timeout_millis: float = 10_000, **kwargs: Any):
        self.exported.append(metrics_data)
        return MetricExportResult.SUCCESS

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True

    def shutdown(self, timeout_millis: float = 30_000, **kwargs: Any) -> None:
        pass


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> type[SpyMetricExporter]:
    SpyMetricExporter.built = []
    monkeypatch.setattr(telemetry, "OTLPMetricExporter", SpyMetricExporter)
    return SpyMetricExporter


def points(exporter: SpyMetricExporter, name: str) -> Sequence[Any]:
    """Every data point exported for metric `name`, in export order."""
    return [
        point
        for batch in exporter.exported
        for resource_metrics in batch.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
        if metric.name == name
        for point in metric.data.data_points
    ]


def test_metrics_go_to_the_signal_path_of_the_endpoint() -> None:
    settings = TelemetrySettings(otlp_endpoint="http://edot-collector:4318")
    assert metrics_url(settings) == "http://edot-collector:4318/v1/metrics"


def test_otel_environment_does_not_redirect_metric_export(
    monkeypatch: pytest.MonkeyPatch, spy: type[SpyMetricExporter]
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://elsewhere:4318")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "http://elsewhere:4318/v1/metrics")
    shutdown_metrics(build_meter_provider(ENABLED))

    assert [e.endpoint for e in spy.built] == ["http://edot-collector:4318/v1/metrics"]


def test_metrics_identify_the_service(spy: type[SpyMetricExporter]) -> None:
    provider = build_meter_provider(ENABLED)
    provider.get_meter(__name__).create_counter("turns").add(1)
    shutdown_metrics(provider)

    (exporter,) = spy.built
    (batch, *_) = exporter.exported
    assert batch.resource_metrics[0].resource.attributes["service.name"] == "fornada-api"


def test_counters_are_exported_as_deltas(spy: type[SpyMetricExporter]) -> None:
    provider = build_meter_provider(ENABLED)
    counter = provider.get_meter(__name__).create_counter("turns")
    counter.add(1)
    provider.force_flush()
    counter.add(1)
    shutdown_metrics(provider)

    first, second = points(spy.built[0], "turns")
    assert isinstance(second, NumberDataPoint)
    # Cumulative would report 2 here: the total since the start.
    assert (first.value, second.value) == (1, 1)
    data = spy.built[0].exported[0].resource_metrics[0].scope_metrics[0].metrics[0].data
    assert isinstance(data, Sum)
    assert data.aggregation_temporality == AggregationTemporality.DELTA


def test_histograms_are_exported_as_deltas(spy: type[SpyMetricExporter]) -> None:
    provider = build_meter_provider(ENABLED)
    histogram = provider.get_meter(__name__).create_histogram("turn.duration", unit="s")
    histogram.record(1.0)
    provider.force_flush()
    histogram.record(3.0)
    shutdown_metrics(provider)

    first, second = points(spy.built[0], "turn.duration")
    assert isinstance(second, HistogramDataPoint)
    assert (first.count, second.count) == (1, 1)
    assert second.sum == 3.0
    data = spy.built[0].exported[0].resource_metrics[0].scope_metrics[0].metrics[0].data
    assert isinstance(data, Histogram)
    assert data.aggregation_temporality == AggregationTemporality.DELTA


def test_metrics_are_exported_every_10_seconds(
    monkeypatch: pytest.MonkeyPatch, spy: type[SpyMetricExporter]
) -> None:
    intervals: list[float | None] = []

    class SpyReader(PeriodicExportingMetricReader):
        def __init__(self, exporter: MetricExporter, **kwargs: Any) -> None:
            intervals.append(kwargs.get("export_interval_millis"))
            super().__init__(exporter, **kwargs)

    monkeypatch.setattr(telemetry, "PeriodicExportingMetricReader", SpyReader)
    shutdown_metrics(build_meter_provider(ENABLED))

    assert intervals == [10_000]


def test_buffered_measurements_are_exported_at_shutdown(spy: type[SpyMetricExporter]) -> None:
    provider = build_meter_provider(ENABLED)
    provider.get_meter(__name__).create_counter("turns").add(3)

    shutdown_metrics(provider)

    (point,) = points(spy.built[0], "turns")
    assert point.value == 3


@pytest.mark.parametrize(
    "scope",
    [
        "opentelemetry.instrumentation.httpx",
        "opentelemetry.instrumentation.psycopg",
        "opentelemetry.instrumentation.sqlalchemy",
    ],
)
def test_instrumentation_metrics_are_dropped(scope: str, spy: type[SpyMetricExporter]) -> None:
    provider = build_meter_provider(ENABLED)
    provider.get_meter(scope).create_histogram("db.client.operation.duration").record(0.1)
    provider.get_meter(__name__).create_counter("turns").add(1)
    shutdown_metrics(provider)

    assert not points(spy.built[0], "db.client.operation.duration")
    assert points(spy.built[0], "turns")


def test_disabled_metrics_register_nothing() -> None:
    before = metrics.get_meter_provider()
    assert setup_metrics(TelemetrySettings(enabled=False)) is None
    assert metrics.get_meter_provider() is before
