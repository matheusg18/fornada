"""OpenTelemetry tracing for the API: build the trace pipeline, register it for
the process and tear it down at shutdown.

`build_tracer_provider` has no global side effects, so tests can inject an
in-memory exporter and read spans back. `setup_tracing` is what the lifespan
calls: it registers the provider globally, where FastAPI's native telemetry
looks it up on every request, and instruments `httpx2`, the HTTP client under
the Anthropic and OpenAI SDKs (plain `httpx` carries no request on a
conversation turn, so it is not instrumented).
"""

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPX2ClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased

from fornada_api.core.config import TelemetrySettings

SERVICE_NAME = "fornada-api"


def traces_url(settings: TelemetrySettings) -> str:
    # The exporter's `endpoint=` takes the full signal URL, unlike
    # OTEL_EXPORTER_OTLP_ENDPOINT, which is a base URL the SDK extends.
    return f"{settings.otlp_endpoint}/v1/traces"


def build_tracer_provider(
    settings: TelemetrySettings, exporter: SpanExporter | None = None
) -> TracerProvider:
    """Build the trace pipeline without registering it. `exporter` replaces the
    OTLP exporter in tests."""
    if exporter is None:
        exporter = OTLPSpanExporter(endpoint=traces_url(settings))

    # `service.name` only. The package version (0.1.0) does not change per
    # commit, so `service.version` would not tell `v0` from later versions;
    # the prompt version comes later as a span attribute. Attributes passed
    # here win over OTEL_SERVICE_NAME and OTEL_RESOURCE_ATTRIBUTES.
    resource = Resource.create({"service.name": SERVICE_NAME})

    # Keep every span: phase 3 error analysis needs every conversation.
    # ParentBased still honors a caller's `traceparent` that dropped its trace.
    # Batch defaults: export every 5 s or 512 spans, off the request path;
    # `provider.shutdown()` drains the queue.
    provider = TracerProvider(resource=resource, sampler=ParentBased(ALWAYS_ON))
    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


def setup_tracing(settings: TelemetrySettings) -> TracerProvider | None:
    """Register tracing for the process. Returns the provider to shut down, or
    None when tracing is disabled."""
    if not settings.enabled:
        return None

    provider = build_tracer_provider(settings)

    # Global so FastAPI's native telemetry finds it on every request. It can
    # be set only once per process; a second call is ignored with a warning.
    trace.set_tracer_provider(provider)
    # Stable HTTP attribute names on the httpx2 CLIENT spans, matching FastAPI's
    # SERVER span. Read from os.environ (not `.env`, which only reaches
    # Settings) once per process, when the first instrumentor initializes, so
    # it must come before `instrument()`. `setdefault` lets the real
    # environment override it, e.g. to add `gen_ai_latest_experimental`.
    os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "http")
    HTTPX2ClientInstrumentor().instrument(tracer_provider=provider)
    return provider


def shutdown_tracing(provider: TracerProvider) -> None:
    """Stop creating spans, then export what is still buffered."""
    HTTPX2ClientInstrumentor().uninstrument()
    provider.shutdown()
