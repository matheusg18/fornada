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
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from fornada_api.agents.attendant.attendant import GraphAttendant
from fornada_api.agents.attendant.graph import build_graph
from fornada_api.agents.attendant.prompt import load_system_prompt
from fornada_api.core.config import TelemetrySettings, get_settings
from fornada_api.dependencies import get_attendant
from fornada_api.infrastructure.engine import get_engine, get_sessionmaker
from fornada_api.main import app
from tests.unit.agents.fakes import ScriptedChatModel

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

    def fake_setup(settings: TelemetrySettings, engine: object) -> object:
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


# --- caller's trace context ------------------------------------------------------

TRACE_ID = 0x4BF92F3577B34DA6A3CE929D0E0E4736
PARENT_SPAN_ID = 0x00F067AA0BA902B7
TRACEPARENT = f"00-{TRACE_ID:032x}-{PARENT_SPAN_ID:016x}-01"


def scripted_attendant() -> GraphAttendant:
    """A real graph on a scripted model, so the turn emits its agent spans."""
    model = ScriptedChatModel(answers=[AIMessage("Olá!")])
    graph = build_graph(model, [], load_system_prompt("Prompt de teste"))
    return GraphAttendant(graph.compile(checkpointer=InMemorySaver()))


def test_request_with_traceparent_continues_the_callers_trace(
    client: TestClient, spans: InMemorySpanExporter
) -> None:
    attendant = scripted_attendant()
    app.dependency_overrides[get_attendant] = lambda: attendant
    response = client.post(
        f"/conversations/{uuid4()}/messages",
        json={"text": "Oi"},
        headers={"traceparent": TRACEPARENT},
    )
    assert response.status_code == 200

    (server,) = server_spans(spans)
    assert server.context is not None
    assert server.context.trace_id == TRACE_ID
    assert server.parent is not None
    assert server.parent.span_id == PARENT_SPAN_ID
    assert server.parent.is_remote
    (turn,) = [s for s in spans.get_finished_spans() if s.name == "invoke_agent fornada-attendant"]
    assert turn.context is not None
    assert turn.context.trace_id == TRACE_ID


def test_request_without_traceparent_starts_a_trace(
    client: TestClient, spans: InMemorySpanExporter
) -> None:
    assert post(client, uuid4()) == 200

    (server,) = server_spans(spans)
    assert server.parent is None
