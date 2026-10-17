"""OpenTelemetry for the API: build the trace and log pipelines, register
tracing for the process and tear both down at shutdown.

`build_tracer_provider` has no global side effects, so tests can inject an
in-memory exporter and read spans back. `setup_tracing` is what the lifespan
calls: it registers the provider globally, where FastAPI's native telemetry
looks it up on every request, and instruments `httpx2`, the HTTP client under
the Anthropic and OpenAI SDKs (plain `httpx` carries no request on a
conversation turn, so it is not instrumented) and the SQLAlchemy engine the
tools use.

`build_logger_provider` is not registered globally: `configure_logging` hands
it to the OTLP log handler directly, so no other code can pick it up and tests
need no process-wide state.
"""

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPX2ClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor, LogRecordExporter
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
