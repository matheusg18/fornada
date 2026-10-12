"""OpenTelemetry tracing for the simulator: build the trace pipeline, register
it for the process, flush it after a batch and shut it down at exit.

Mirrors the API's `core/telemetry.py`. `build_tracer_provider` has no global
side effects, so tests inject an in-memory exporter. Spans come from
`trace.get_tracer(...)` in `client.py`: a proxy until `setup_tracing`
registers the SDK provider, a no-op when tracing is off.
"""

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased

from fornada_simulator.settings import TelemetrySettings

SERVICE_NAME = "fornada-simulator"


def traces_url(settings: TelemetrySettings) -> str:
    # The exporter's `endpoint=` takes the full signal URL.
    return f"{settings.otlp_endpoint}/v1/traces"


def build_tracer_provider(
    settings: TelemetrySettings, exporter: SpanExporter | None = None
) -> TracerProvider:
    """Build the trace pipeline without registering it. `exporter` replaces the
    OTLP exporter in tests."""
    if exporter is None:
        exporter = OTLPSpanExporter(endpoint=traces_url(settings))

    # `service.name` only: the run id changes per batch and the notebook runs
    # several batches in one process, so it goes on the span, not here.
    resource = Resource.create({"service.name": SERVICE_NAME})
    # The client span is the trace root, so this decision travels in
    # `traceparent` and the API's ParentBased follows it: keep every turn.
    # Batched, off the turn path; `run_batch` flushes before returning.
    provider = TracerProvider(resource=resource, sampler=ParentBased(ALWAYS_ON))
    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


def setup_tracing(settings: TelemetrySettings) -> TracerProvider | None:
    """Register tracing for the process. Returns the provider to shut down, or
    None when tracing is disabled.

    Idempotent: `trace.set_tracer_provider` works once per process, and the
    notebook can run its setup cell again. A second call returns the provider
    already registered instead of building one that would never be used.
    """
    if not settings.enabled:
        return None
    current = trace.get_tracer_provider()
    if isinstance(current, TracerProvider):
        return current
    provider = build_tracer_provider(settings)
    trace.set_tracer_provider(provider)
    return provider


def flush_tracing() -> None:
    """Export the spans still buffered, if an SDK provider is registered."""
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.force_flush()


def shutdown_tracing(provider: TracerProvider) -> None:
    """Export what is still buffered, then stop the pipeline."""
    provider.shutdown()
