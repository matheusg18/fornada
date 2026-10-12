"""Tracing wired into the app. The global tracer provider can be set only once
per process, so these tests never let the lifespan enable real tracing: they
either spy on the setup or register one in-memory provider for the session."""

import logging
import sys
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from fornada_api.core.config import TelemetrySettings, get_settings
from fornada_api.dependencies import get_attendant
from fornada_api.infrastructure.engine import get_engine, get_sessionmaker
from fornada_api.main import app

# Not `from fornada_api import main`: the package also defines a `main()`
# entrypoint function, which that import can return instead of the module.
main_module = sys.modules["fornada_api.main"]

ROUTE = "/conversations/{conversation_id}/messages"


class StubAttendant:
    async def reply(self, conversation_id: UUID, text: str) -> list[str]:
        return ["Olá!"]


def clear_caches() -> None:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


@pytest.fixture
def app_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Settings for the app with an unreachable database and tracing off."""
    monkeypatch.setenv("DB__URL", "postgresql://x:pw@127.0.0.1:1/x")
    monkeypatch.setenv("LLM__PROVIDER", "anthropic")
    monkeypatch.setenv("LLM__ANTHROPIC__API_KEY", "sk-ant-test")
    monkeypatch.setenv("TELEMETRY__ENABLED", "false")
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    clear_caches()
    yield
    clear_caches()
    app.dependency_overrides.clear()
    root.handlers[:], root.level = handlers, level


@pytest.fixture
def client(app_env: None) -> Iterator[TestClient]:
    with TestClient(app) as client:
        app.dependency_overrides[get_attendant] = StubAttendant
        yield client


def post(client: TestClient, conversation_id: UUID) -> int:
    response = client.post(f"/conversations/{conversation_id}/messages", json={"text": "Oi"})
    return response.status_code


def server_spans(exporter: InMemorySpanExporter) -> list[Any]:
    return [s for s in exporter.get_finished_spans() if s.kind is SpanKind.SERVER]


# --- lifespan ------------------------------------------------------------------


def test_lifespan_sets_up_and_shuts_down_tracing(
    app_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, object]] = []
    provider = object()

    def fake_setup(settings: TelemetrySettings) -> object:
        calls.append(("setup", settings))
        return provider

    def fake_shutdown(p: object) -> None:
        calls.append(("shutdown", p))

    monkeypatch.setattr(main_module, "setup_tracing", fake_setup)
    monkeypatch.setattr(main_module, "shutdown_tracing", fake_shutdown)

    with TestClient(app):
        assert calls == [("setup", get_settings().telemetry)]
    assert calls[-1] == ("shutdown", provider)


def test_disabled_tracing_leaves_the_global_provider(app_env: None) -> None:
    before = trace.get_tracer_provider()
    with TestClient(app):
        pass
    assert trace.get_tracer_provider() is before


# --- server span -----------------------------------------------------------------


def test_customer_message_yields_one_server_span(
    client: TestClient, spans: InMemorySpanExporter
) -> None:
    assert post(client, uuid4()) == 200

    (span,) = server_spans(spans)
    assert span.attributes is not None
    assert span.attributes["http.request.method"] == "POST"
    assert span.attributes["http.route"] == ROUTE
    assert span.attributes["http.response.status_code"] == 200


def test_route_template_not_the_raw_path(client: TestClient, spans: InMemorySpanExporter) -> None:
    ids = [uuid4(), uuid4()]
    for conversation_id in ids:
        post(client, conversation_id)

    found = server_spans(spans)
    assert len(found) == 2
    assert {s.attributes["http.route"] for s in found if s.attributes} == {ROUTE}
    names = " ".join(s.name for s in spans.get_finished_spans())
    assert not any(str(i) in names for i in ids)
