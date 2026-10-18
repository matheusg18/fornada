"""Log and metric export wired into the app. Like `test_tracing.py`, these
tests never let the lifespan register real tracing or metrics: they spy on the
setup and build the logger provider on an in-memory exporter."""

import logging
import sys
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from fornada_api.core.config import TelemetrySettings, get_settings
from fornada_api.core.telemetry import build_logger_provider
from fornada_api.dependencies import get_attendant
from fornada_api.infrastructure.engine import get_engine, get_sessionmaker
from fornada_api.main import app

main_module = sys.modules["fornada_api.main"]

TRACE_ID = 0x4BF92F3577B34DA6A3CE929D0E0E4736
TRACEPARENT = f"00-{TRACE_ID:032x}-00f067aa0ba902b7-01"


class FailingAttendant:
    async def reply(self, conversation_id: UUID, text: str) -> list[str]:
        raise RuntimeError("provider down")


def clear_caches() -> None:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


def configure_env(monkeypatch: pytest.MonkeyPatch, *, telemetry: bool) -> None:
    monkeypatch.setenv("DB__URL", "postgresql://x:pw@127.0.0.1:1/x")
    monkeypatch.setenv("LLM__PROVIDER", "anthropic")
    monkeypatch.setenv("LLM__ANTHROPIC__API_KEY", "sk-ant-test")
    monkeypatch.setenv("TELEMETRY__ENABLED", "true" if telemetry else "false")
    clear_caches()


@pytest.fixture
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    clear_caches()
    app.dependency_overrides.clear()
    root.handlers[:], root.level = handlers, level


class Spies:
    def __init__(self) -> None:
        self.exporter = InMemoryLogRecordExporter()
        self.provider: LoggerProvider | None = None
        self.events: list[tuple[str, list[str]]] = []

    def handler_names(self) -> list[str]:
        return [type(h).__name__ for h in logging.getLogger().handlers]

    def exported(self) -> list[Any]:
        assert self.provider is not None
        self.provider.force_flush()
        return list(self.exporter.get_finished_logs())


@pytest.fixture
def telemetry_on(
    monkeypatch: pytest.MonkeyPatch, restore_logging: None, spans: InMemorySpanExporter
) -> Spies:
    configure_env(monkeypatch, telemetry=True)
    spies = Spies()

    def fake_build(settings: TelemetrySettings) -> LoggerProvider:
        spies.provider = build_logger_provider(settings, spies.exporter)
        return spies.provider

    def fake_shutdown_logging(provider: LoggerProvider) -> None:
        spies.events.append(("shutdown_logging", spies.handler_names()))
        provider.shutdown()

    monkeypatch.setattr(main_module, "build_logger_provider", fake_build)
    monkeypatch.setattr(main_module, "shutdown_logging", fake_shutdown_logging)
    monkeypatch.setattr(main_module, "setup_tracing", lambda settings, engine: object())
    # Never a real meter provider: it would register globally and export over OTLP.
    monkeypatch.setattr(main_module, "setup_metrics", lambda settings: object())
    monkeypatch.setattr(
        main_module,
        "shutdown_metrics",
        lambda provider: spies.events.append(("shutdown_metrics", spies.handler_names())),
    )
    monkeypatch.setattr(
        main_module,
        "shutdown_tracing",
        lambda provider: spies.events.append(("shutdown_tracing", spies.handler_names())),
    )
    return spies


def post_failing_turn(client: TestClient, headers: dict[str, str] | None = None) -> None:
    app.dependency_overrides[get_attendant] = FailingAttendant
    response = client.post(
        f"/conversations/{uuid4()}/messages", json={"text": "Oi"}, headers=headers
    )
    assert response.status_code == 503


def test_telemetry_off_builds_no_logger_provider(
    monkeypatch: pytest.MonkeyPatch, restore_logging: None
) -> None:
    configure_env(monkeypatch, telemetry=False)
    built: list[object] = []
    monkeypatch.setattr(main_module, "build_logger_provider", lambda s: built.append(s))

    with TestClient(app):
        assert [type(h).__name__ for h in logging.getLogger().handlers] == ["StreamHandler"]
    assert built == []


def test_failed_turn_log_carries_the_server_spans_trace_id(
    telemetry_on: Spies, spans: InMemorySpanExporter
) -> None:
    with TestClient(app) as client:
        post_failing_turn(client)

    (server,) = [s for s in spans.get_finished_spans() if s.kind is SpanKind.SERVER]
    assert server.context is not None
    (failed,) = [r for r in telemetry_on.exported() if r.log_record.body == "turn failed"]
    assert failed.log_record.severity_text == "ERROR"
    assert failed.log_record.trace_id == server.context.trace_id


def test_failed_turn_log_carries_the_callers_trace_id(telemetry_on: Spies) -> None:
    with TestClient(app) as client:
        post_failing_turn(client, {"traceparent": TRACEPARENT})

    (failed,) = [r for r in telemetry_on.exported() if r.log_record.body == "turn failed"]
    assert failed.log_record.trace_id == TRACE_ID


def test_startup_log_has_no_trace_id(telemetry_on: Spies) -> None:
    with TestClient(app):
        pass

    (starting,) = [
        r for r in telemetry_on.exported() if r.log_record.body == "fornada-api starting"
    ]
    assert not starting.log_record.trace_id


def test_shutdown_stops_tracing_and_metrics_then_detaches_the_handler_then_stops_logs(
    telemetry_on: Spies,
) -> None:
    with TestClient(app):
        assert "LoggingHandler" in telemetry_on.handler_names()

    assert [name for name, _ in telemetry_on.events] == [
        "shutdown_tracing",
        "shutdown_metrics",
        "shutdown_logging",
    ]
    # Metrics still flush while the OTLP log handler is attached, so a record
    # about a failed last export still reaches the Collector.
    assert "LoggingHandler" in telemetry_on.events[1][1]
    # The OTLP handler is gone before the provider stops, so no record is
    # handed to a provider that has already shut down.
    assert telemetry_on.events[-1][1] == ["StreamHandler"]
    assert telemetry_on.handler_names() == ["StreamHandler"]


# --- metrics -------------------------------------------------------------------


def test_telemetry_off_shuts_down_no_meter_provider(
    monkeypatch: pytest.MonkeyPatch, restore_logging: None
) -> None:
    configure_env(monkeypatch, telemetry=False)
    shutdowns: list[object] = []
    monkeypatch.setattr(main_module, "shutdown_metrics", shutdowns.append)

    with TestClient(app):
        pass

    # `setup_metrics` returns None when telemetry is off; nothing to shut down.
    assert shutdowns == []


def test_telemetry_on_sets_up_and_shuts_down_metrics(
    monkeypatch: pytest.MonkeyPatch, telemetry_on: Spies
) -> None:
    provider = object()
    calls: list[tuple[str, object]] = []

    def fake_setup(settings: TelemetrySettings) -> object:
        calls.append(("setup", settings))
        return provider

    monkeypatch.setattr(main_module, "setup_metrics", fake_setup)
    monkeypatch.setattr(main_module, "shutdown_metrics", lambda p: calls.append(("shutdown", p)))

    with TestClient(app):
        assert calls == [("setup", get_settings().telemetry)]
    assert calls[-1] == ("shutdown", provider)


# --- chaos mode ----------------------------------------------------------------


def chaos_records(spies: Spies) -> list[Any]:
    return [r for r in spies.exported() if r.log_record.body == "chaos mode enabled"]


def test_chaos_on_logs_one_startup_warning(
    telemetry_on: Spies, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHAOS__ENABLED", "true")
    monkeypatch.setenv("CHAOS__SEED", "42")
    clear_caches()
    with TestClient(app):
        pass

    (record,) = chaos_records(telemetry_on)
    assert record.log_record.severity_number is SeverityNumber.WARN
    attributes = dict(record.log_record.attributes or {})
    assert {
        key: attributes[key]
        for key in (
            "latency_min_ms",
            "latency_max_ms",
            "capacity_failure_rate",
            "price_increase_pct",
            "seeded",
        )
    } == {
        "latency_min_ms": 200,
        "latency_max_ms": 2000,
        "capacity_failure_rate": 0.1,
        "price_increase_pct": 10.0,
        "seeded": True,
    }
    assert "42" not in str(attributes)


def test_chaos_off_logs_no_chaos_record(telemetry_on: Spies) -> None:
    with TestClient(app):
        pass

    assert chaos_records(telemetry_on) == []
