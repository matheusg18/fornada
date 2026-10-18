"""Tracing wired into the app. The global tracer provider can be set only once
per process, so these tests never let the lifespan enable real tracing: they
either spy on the setup or register one in-memory provider for the session."""

import json
import logging
import sys
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import anthropic
import httpcore2
import httpx2
import pytest
from fastapi.testclient import TestClient
from langchain_anthropic import ChatAnthropic, chat_models
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from opentelemetry import trace
from opentelemetry.instrumentation.httpx import HTTPX2ClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind
from pydantic import SecretStr

from fornada_api.agents.attendant.attendant import GraphAttendant
from fornada_api.agents.attendant.graph import build_graph
from fornada_api.agents.attendant.prompt import load_system_prompt
from fornada_api.core.config import TelemetrySettings, get_settings
from fornada_api.core.telemetry import (
    build_tracer_provider,
    instrument_engine,
    shutdown_tracing,
)
from fornada_api.dependencies import get_attendant
from fornada_api.infrastructure.checkpointer import Checkpointer
from fornada_api.infrastructure.engine import get_engine, get_sessionmaker
from fornada_api.main import app
from tests.unit.agents.fakes import ScriptedChatModel
from tests.unit.agents.test_agent_metrics import Collected, attrs

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


def spy_checkpointer(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Record the tracer provider the lifespan hands the `Checkpointer`."""
    seen: list[object] = []

    def build(url: str, tracer_provider: Any = None) -> Checkpointer:
        seen.append(tracer_provider)
        return Checkpointer(url, tracer_provider)

    monkeypatch.setattr(main_module, "Checkpointer", build)
    return seen


def test_tracing_off_instruments_no_database_path(
    app_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = spy_checkpointer(monkeypatch)
    with TestClient(app):
        assert not SQLAlchemyInstrumentor().is_instrumented_by_opentelemetry
    assert seen == [None]


def test_tracing_on_instruments_the_engine_and_traces_the_checkpointer(
    app_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = spy_checkpointer(monkeypatch)
    provider = object()
    engines: list[object] = []

    def fake_setup(settings: TelemetrySettings, engine: object) -> object:
        engines.append(engine)
        return provider

    monkeypatch.setattr(main_module, "setup_tracing", fake_setup)
    monkeypatch.setattr(main_module, "shutdown_tracing", lambda p: None)

    with TestClient(app):
        assert engines == [get_engine()]
    assert seen == [provider]


def test_shutdown_uninstruments_the_engine(app_env: None) -> None:
    provider = build_tracer_provider(TelemetrySettings(enabled=True), InMemorySpanExporter())
    instrument_engine(get_engine(), provider)
    assert SQLAlchemyInstrumentor().is_instrumented_by_opentelemetry

    shutdown_tracing(provider)

    assert not SQLAlchemyInstrumentor().is_instrumented_by_opentelemetry


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


# --- persona baggage (`app-metrics` spec) ----------------------------------------

PERSONA = "fornada.simulator.persona.id"
BAGGAGE = {"baggage": f"{PERSONA}=apressada"}

# The Messages API body for a one-text answer.
ANTHROPIC_ANSWER = {
    "id": "msg_test",
    "type": "message",
    "role": "assistant",
    "model": "claude-haiku-4-5",
    "content": [{"type": "text", "text": "Olá!"}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 10, "output_tokens": 2},
}


class FakePool:
    """Answers under a real `AsyncHTTPTransport`. The instrumentor wraps that
    class's `handle_async_request`, which a `MockTransport` would bypass, so
    the headers seen here are the ones the instrumentor injected."""

    def __init__(self) -> None:
        self.requests: list[httpcore2.Request] = []

    async def handle_async_request(self, request: httpcore2.Request) -> httpcore2.Response:
        self.requests.append(request)
        return httpcore2.Response(
            200,
            headers=[(b"content-type", b"application/json")],
            content=json.dumps(ANTHROPIC_ANSWER).encode(),
        )

    def headers(self) -> list[dict[str, str]]:
        return [
            {k.decode().lower(): v.decode() for k, v in request.headers}
            for request in self.requests
        ]


@pytest.fixture
def provider_pool(
    spans: InMemorySpanExporter, monkeypatch: pytest.MonkeyPatch
) -> Iterator[FakePool]:
    """`ChatAnthropic` on an instrumented HTTP client that never leaves the process."""
    pool = FakePool()
    transport = httpx2.AsyncHTTPTransport()
    # Duck-typed: the transport only calls `handle_async_request` on it.
    transport._pool = pool  # pyright: ignore[reportAttributeAccessIssue]

    def http_client(**kwargs: Any) -> anthropic.DefaultAsyncHttpxClient:
        return anthropic.DefaultAsyncHttpxClient(base_url=kwargs["base_url"], transport=transport)

    monkeypatch.setattr(chat_models, "_get_default_async_httpx_client", http_client)
    HTTPX2ClientInstrumentor().instrument(tracer_provider=trace.get_tracer_provider())
    yield pool
    HTTPX2ClientInstrumentor().uninstrument()


def anthropic_attendant() -> GraphAttendant:
    model = ChatAnthropic(
        model_name="claude-haiku-4-5", api_key=SecretStr("sk-ant-test"), timeout=None, stop=None
    )
    graph = build_graph(model, [], load_system_prompt("Prompt de teste"))
    return GraphAttendant(graph.compile(checkpointer=InMemorySaver()))


def test_baggage_persona_reaches_the_turns_measurements(
    client: TestClient, spans: InMemorySpanExporter, metric_reader: InMemoryMetricReader
) -> None:
    # `spans` registers an SDK tracer provider: FastAPI extracts the request's
    # context (baggage included) only when tracing is on, as in the app.
    attendant = scripted_attendant()
    app.dependency_overrides[get_attendant] = lambda: attendant
    response = client.post(
        f"/conversations/{uuid4()}/messages", json={"text": "Oi"}, headers=BAGGAGE
    )
    assert response.status_code == 200

    collected = Collected(metric_reader)
    for name in ("gen_ai.invoke_agent.duration", "gen_ai.client.inference.duration"):
        points = collected.points(name)
        assert points, name
        assert {attrs(p)[PERSONA] for p in points} == {"apressada"}, name


def test_baggage_is_not_forwarded_to_the_model_provider(
    client: TestClient, provider_pool: FakePool
) -> None:
    attendant = anthropic_attendant()
    app.dependency_overrides[get_attendant] = lambda: attendant
    response = client.post(
        f"/conversations/{uuid4()}/messages", json={"text": "Oi"}, headers=BAGGAGE
    )
    assert response.status_code == 200

    (sent,) = provider_pool.headers()
    # The propagator ran: the provider call still continues the trace.
    assert "traceparent" in sent
    assert "baggage" not in sent


def test_persona_is_on_no_span(client: TestClient, spans: InMemorySpanExporter) -> None:
    attendant = scripted_attendant()
    app.dependency_overrides[get_attendant] = lambda: attendant
    client.post(f"/conversations/{uuid4()}/messages", json={"text": "Oi"}, headers=BAGGAGE)

    found = spans.get_finished_spans()
    assert found
    assert not [s.name for s in found if PERSONA in (s.attributes or {})]
