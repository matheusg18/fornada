"""The simulator's trace pipeline (`client-tracing` spec)."""

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import TraceFlags

from fornada_simulator.settings import TelemetrySettings
from fornada_simulator.telemetry import build_tracer_provider, setup_tracing, traces_url

ENABLED = TelemetrySettings(enabled=True, otlp_endpoint="http://collector:4318")


def built() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    return build_tracer_provider(ENABLED, exporter=exporter), exporter


def test_traces_url_appends_the_signal_path() -> None:
    assert traces_url(ENABLED) == "http://collector:4318/v1/traces"


def test_spans_identify_the_simulator() -> None:
    provider, exporter = built()
    provider.get_tracer("test").start_span("turn").end()
    provider.force_flush()

    (span,) = exporter.get_finished_spans()
    assert span.resource.attributes["service.name"] == "fornada-simulator"


def test_root_spans_are_sampled() -> None:
    # The client is the root: its decision travels in `traceparent` to the API.
    provider, _ = built()
    span = provider.get_tracer("test").start_span("turn")
    assert span.get_span_context().trace_flags & TraceFlags.SAMPLED


def test_spans_reach_the_exporter_only_after_a_flush() -> None:
    provider, exporter = built()
    provider.get_tracer("test").start_span("turn").end()
    # Batched: nothing exported yet, so a process that exits now loses it.
    assert exporter.get_finished_spans() == ()
    provider.force_flush()
    assert len(exporter.get_finished_spans()) == 1


def test_disabled_tracing_registers_nothing() -> None:
    before = trace.get_tracer_provider()
    assert setup_tracing(TelemetrySettings(enabled=False)) is None
    assert trace.get_tracer_provider() is before


def test_setup_reuses_the_registered_provider(session_exporter: InMemorySpanExporter) -> None:
    # `session_exporter` registered the process-wide SDK provider.
    registered = trace.get_tracer_provider()
    assert setup_tracing(ENABLED) is registered
    assert setup_tracing(ENABLED) is registered
