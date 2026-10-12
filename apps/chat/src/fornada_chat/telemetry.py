"""OpenTelemetry tracing for the chat: settings, the trace pipeline, and its
start and stop with the Chainlit app.

Mirrors the simulator's `telemetry.py` with one difference: the provider is
private, never registered globally. Chainlit's server is a FastAPI app, and
FastAPI traces every request through the global provider: registering ours
would turn the chat's websocket into a span open for the whole tab, with every
message inside it (design decision 11). `client.py` gets its tracer from this
provider at startup instead.

The chat has no settings class: like `CHAT__API_URL`, the `TELEMETRY__*`
variables are read from `os.environ`. Chainlit loads `apps/chat/.env`, not the
root one, so set them in the shell or in that file.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased

SERVICE_NAME = "fornada-chat"
DEFAULT_OTLP_ENDPOINT = "http://edot-collector:4318"
TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class TelemetrySettings:
    # Off by default so tests and CI never try to reach a Collector.
    enabled: bool = False
    # Base URL of the Collector's OTLP/HTTP receiver.
    otlp_endpoint: str = DEFAULT_OTLP_ENDPOINT


def load_telemetry_settings(environ: Mapping[str, str]) -> TelemetrySettings:
    """`TELEMETRY__ENABLED` and `TELEMETRY__OTLP_ENDPOINT`, as the API reads them."""
    enabled = environ.get("TELEMETRY__ENABLED", "").strip().lower() in TRUE_VALUES
    url = environ.get("TELEMETRY__OTLP_ENDPOINT") or DEFAULT_OTLP_ENDPOINT
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("TELEMETRY__OTLP_ENDPOINT: must be an http(s) URL (http://host:4318)")
    return TelemetrySettings(enabled=enabled, otlp_endpoint=url.rstrip("/"))


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

    resource = Resource.create({"service.name": SERVICE_NAME})
    # The client span is the trace root, so this decision travels in
    # `traceparent` and the API's ParentBased follows it: keep every turn.
    # Batched, off the turn path; shutdown drains it when Chainlit stops.
    provider = TracerProvider(resource=resource, sampler=ParentBased(ALWAYS_ON))
    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


_provider: TracerProvider | None = None


def setup_tracing(settings: TelemetrySettings) -> TracerProvider | None:
    """Build the chat's provider once per process, without registering it.
    Returns it, or None when tracing is disabled.

    Idempotent: Chainlit's reload (`-w`) can run the startup hook again.
    """
    global _provider
    if not settings.enabled:
        return None
    if _provider is None:
        _provider = build_tracer_provider(settings)
    return _provider


def shutdown_tracing() -> None:
    """Export what is still buffered, then stop the pipeline, if one was built."""
    global _provider
    if _provider is not None:
        _provider.shutdown()
        _provider = None
