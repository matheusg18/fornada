"""OpenTelemetry for the API: build the trace and log pipelines, register
tracing for the process and tear both down at shutdown.

`build_tracer_provider` has no global side effects, so tests can inject an
in-memory exporter and read spans back. `setup_tracing` is what the lifespan
calls: it registers the provider globally, where FastAPI's native telemetry
looks it up on every request, and instruments `httpx2`, the HTTP client under
the Anthropic and OpenAI SDKs (plain `httpx` carries no request on a
conversation turn, so it is not instrumented) and the SQLAlchemy engine the
tools use.

`build_meter_provider` is registered globally by `setup_metrics`, like the
tracer provider: the agent's instruments come from `metrics.get_meter`, a proxy
until then and a no-op when telemetry is off.

`build_logger_provider` is not registered globally: `configure_logging` hands
it to the OTLP log handler directly, so no other code can pick it up and tests
need no process-wide state.
"""

import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPX2ClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, LogRecordExporter
from opentelemetry.sdk.metrics import (
    Counter,
    Histogram,
    MeterProvider,
    ObservableCounter,
    ObservableGauge,
    ObservableUpDownCounter,
    UpDownCounter,
)
from opentelemetry.sdk.metrics.export import AggregationTemporality, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased
from sqlalchemy.ext.asyncio import AsyncEngine

from fornada_api.core.config import TelemetrySettings

SERVICE_NAME = "fornada-api"

# Stable HTTP and database attribute names. Tests set the same value before any
# instrumentor runs (`tests/conftest.py`).
SEMCONV_OPT_IN = "http,database"


def traces_url(settings: TelemetrySettings) -> str:
    # The exporter's `endpoint=` takes the full signal URL, unlike
    # OTEL_EXPORTER_OTLP_ENDPOINT, which is a base URL the SDK extends.
    return f"{settings.otlp_endpoint}/v1/traces"


def logs_url(settings: TelemetrySettings) -> str:
    return f"{settings.otlp_endpoint}/v1/logs"


def metrics_url(settings: TelemetrySettings) -> str:
    return f"{settings.otlp_endpoint}/v1/metrics"


def build_resource() -> Resource:
    # `service.name` only. The package version (0.1.0) does not change per
    # commit, so `service.version` would not tell `v0` from later versions;
    # the prompt version comes later as a span attribute. Attributes passed
    # here win over OTEL_SERVICE_NAME and OTEL_RESOURCE_ATTRIBUTES. Traces and
    # logs share it, so Kibana joins them by service.
    return Resource.create({"service.name": SERVICE_NAME})


def build_tracer_provider(
    settings: TelemetrySettings, exporter: SpanExporter | None = None
) -> TracerProvider:
    """Build the trace pipeline without registering it. `exporter` replaces the
    OTLP exporter in tests."""
    if exporter is None:
        exporter = OTLPSpanExporter(endpoint=traces_url(settings))

    resource = build_resource()

    # Keep every span: phase 3 error analysis needs every conversation.
    # ParentBased still honors a caller's `traceparent` that dropped its trace.
    # Batch defaults: export every 5 s or 512 spans, off the request path;
    # `provider.shutdown()` drains the queue.
    provider = TracerProvider(resource=resource, sampler=ParentBased(ALWAYS_ON))
    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


def build_logger_provider(
    settings: TelemetrySettings, exporter: LogRecordExporter | None = None
) -> LoggerProvider:
    """Build the log pipeline without registering it. `exporter` replaces the
    OTLP exporter in tests."""
    if exporter is None:
        # An explicit `endpoint=` wins over OTEL_EXPORTER_OTLP_*, so no OTEL
        # variable redirects the logs or adds a second exporter.
        exporter = OTLPLogExporter(endpoint=logs_url(settings))

    # Batch defaults: export every 1 s or 512 records, off the request path;
    # `provider.shutdown()` drains the queue.
    provider = LoggerProvider(resource=build_resource())
    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    return provider


def build_meter_provider(settings: TelemetrySettings) -> MeterProvider:
    """Build the metric pipeline without registering it."""
    # Delta for every instrument kind: Elasticsearch drops cumulative
    # histograms, and one rule for all kinds keeps a future instrument from
    # being dropped silently. Explicit endpoint, so no OTEL_* variable
    # redirects it. Exported every 10 s (default 60 s) so a simulator batch of
    # a few minutes gives the p95 panel enough points.
    DELTA = {kind: AggregationTemporality.DELTA for kind in (Counter, Histogram, ...)}
    #
    #    Weigh: UpDownCounter and the gauges model a level, not a change; delta
    #    makes their points meaningless alone. We have none today. Map them to
    #    DELTA anyway (one rule) or leave them CUMULATIVE (correct if one appears)?
    #
    # 2. Exporter. Same rules as the other two signals: an explicit endpoint, so
    #    no OTEL_* variable redirects it.
    #
    #    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    #    (a module-level import: the tests replace `telemetry.OTLPMetricExporter`)
    #    exporter = OTLPMetricExporter(endpoint=metrics_url(settings), preferred_temporality=DELTA)
    #
    # 3. Reader and interval. A PeriodicExportingMetricReader collects every
    #    instrument on a background thread and exports. Default 60 s; a simulator
    #    batch lasts minutes, so 10 s gives the p95 panel enough points.
    #
    #    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    #    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=10_000)
    #    return MeterProvider(resource=build_resource(), metric_readers=[reader])
    DELTA = {
        kind: AggregationTemporality.DELTA
        for kind in (
            Counter,
            Histogram,
            ObservableCounter,
            ObservableGauge,
            ObservableUpDownCounter,
            UpDownCounter,
        )
    }

    exporter = OTLPMetricExporter(endpoint=metrics_url(settings), preferred_temporality=DELTA)
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=10_000)
    return MeterProvider(resource=build_resource(), metric_readers=[reader])


def setup_metrics(settings: TelemetrySettings) -> MeterProvider | None:
    """Register metrics for the process. Returns the provider to shut down, or
    None when telemetry is disabled."""
    if not settings.enabled:
        return None

    provider = build_meter_provider(settings)
    # Global so the instruments' proxy meter resolves to it. Set once per
    # process; a second call is ignored with a warning.
    metrics.set_meter_provider(provider)
    return provider


def shutdown_metrics(provider: MeterProvider) -> None:
    """Collect and export what was recorded since the last export, then stop."""
    provider.shutdown()


def instrument_engine(engine: AsyncEngine, provider: TracerProvider) -> None:
    """One CLIENT span per statement the engine runs. Spans carry the SQL with
    its placeholders (parameters are never captured). The instrumentor's error
    listener is registered after `drop_server_detail`, so a failed statement's
    span gets the message without the server's `DETAIL:` line.

    `skip_dep_check`: the instrumentor (0.66b1) declares `sqlalchemy < 2.1.0`
    and instruments nothing outside it, but the project uses 2.1. The engine
    tests would fail if 2.1 broke it; if they do, pin `sqlalchemy<2.1`."""
    SQLAlchemyInstrumentor().instrument(
        engine=engine.sync_engine, tracer_provider=provider, skip_dep_check=True
    )


def uninstrument_engine() -> None:
    SQLAlchemyInstrumentor().uninstrument()


def setup_tracing(settings: TelemetrySettings, engine: AsyncEngine) -> TracerProvider | None:
    """Register tracing for the process and instrument `engine`. Returns the
    provider to shut down, or None when tracing is disabled."""
    if not settings.enabled:
        return None

    provider = build_tracer_provider(settings)

    # Global so FastAPI's native telemetry finds it on every request. It can
    # be set only once per process; a second call is ignored with a warning.
    trace.set_tracer_provider(provider)
    # Stable HTTP attribute names on the httpx2 CLIENT spans, matching FastAPI's
    # SERVER span, and stable database names on the database spans. Read from
    # os.environ (not `.env`, which only reaches Settings) once per process,
    # when the first instrumentor initializes, so it must come before
    # `instrument()`. `setdefault` lets the real environment override it, e.g.
    # to add `gen_ai_latest_experimental`.
    os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", SEMCONV_OPT_IN)
    HTTPX2ClientInstrumentor().instrument(tracer_provider=provider)
    instrument_engine(engine, provider)
    return provider


def shutdown_tracing(provider: TracerProvider) -> None:
    """Stop creating spans, then export what is still buffered."""
    HTTPX2ClientInstrumentor().uninstrument()
    uninstrument_engine()
    provider.shutdown()


def shutdown_logging(provider: LoggerProvider) -> None:
    """Export the log records still buffered, then stop the log pipeline."""
    provider.shutdown()
