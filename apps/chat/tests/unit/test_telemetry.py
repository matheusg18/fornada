"""The chat's trace pipeline (`client-tracing` spec)."""

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import TraceFlags

from fornada_chat import telemetry
from fornada_chat.telemetry import (
    TelemetrySettings,
    build_tracer_provider,
    load_telemetry_settings,
    setup_tracing,
    shutdown_tracing,
    traces_url,
)

ENABLED = TelemetrySettings(enabled=True, otlp_endpoint="http://collector:4318")


def test_tracing_is_off_by_default() -> None:
    assert load_telemetry_settings({}) == TelemetrySettings(
        enabled=False, otlp_endpoint="http://edot-collector:4318"
    )


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "on"])
def test_enabled_values(value: str) -> None:
    assert load_telemetry_settings({"TELEMETRY__ENABLED": value}).enabled is True


@pytest.mark.parametrize("value", ["false", "0", "", "no"])
def test_disabled_values(value: str) -> None:
    assert load_telemetry_settings({"TELEMETRY__ENABLED": value}).enabled is False


def test_endpoint_comes_from_the_environment() -> None:
    settings = load_telemetry_settings({"TELEMETRY__OTLP_ENDPOINT": "http://collector:4318/"})
    assert settings.otlp_endpoint == "http://collector:4318"
    assert traces_url(settings) == "http://collector:4318/v1/traces"


def test_invalid_endpoint_names_the_variable() -> None:
    with pytest.raises(ValueError, match="TELEMETRY__OTLP_ENDPOINT: must be an http"):
        load_telemetry_settings({"TELEMETRY__OTLP_ENDPOINT": "edot-collector:4318"})


def test_spans_identify_the_chat() -> None:
    exporter = InMemorySpanExporter()
    provider = build_tracer_provider(ENABLED, exporter=exporter)
    span = provider.get_tracer("test").start_span("turn")
    assert span.get_span_context().trace_flags & TraceFlags.SAMPLED
    span.end()
    provider.force_flush()

    (exported,) = exporter.get_finished_spans()
    assert exported.resource.attributes["service.name"] == "fornada-chat"


def test_disabled_tracing_builds_nothing() -> None:
    assert setup_tracing(TelemetrySettings(enabled=False)) is None


def test_setup_builds_one_private_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(telemetry, "_provider", None)
    monkeypatch.setattr(telemetry, "build_tracer_provider", lambda settings: TracerProvider())
    before = trace.get_tracer_provider()

    first = setup_tracing(ENABLED)
    assert first is not None
    assert setup_tracing(ENABLED) is first
    # Never global: Chainlit's FastAPI would trace its websocket with it.
    assert trace.get_tracer_provider() is before

    shutdown_tracing()
    assert telemetry._provider is None
