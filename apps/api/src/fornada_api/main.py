"""FastAPI application. Serve it with `fastapi dev` (see the README)."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fornada_api import conversations, health
from fornada_api.agents.attendant.attendant import GraphAttendant
from fornada_api.agents.attendant.graph import build_graph
from fornada_api.agents.attendant.model import build_chat_model
from fornada_api.agents.attendant.prompt import load_system_prompt
from fornada_api.agents.attendant.tools import default_tools
from fornada_api.core.config import get_settings
from fornada_api.core.logging import configure_logging
from fornada_api.core.telemetry import setup_tracing, shutdown_tracing
from fornada_api.infrastructure.checkpointer import Checkpointer
from fornada_api.infrastructure.engine import get_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # Invalid settings fail here, before any request is served.
    settings = get_settings()
    configure_logging(settings.log)
    engine = get_engine()
    prompt = load_system_prompt()
    checkpointer = Checkpointer(settings.db.url.get_secret_value())
    tracer_provider = None
    try:
        # Global before the first request: FastAPI looks the provider up per
        # request. None when tracing is off.
        tracer_provider = setup_tracing(settings.telemetry)
        await checkpointer.open()
        # Content only matters when spans are exported; with tracing off, skip
        # building it.
        capture = settings.telemetry.enabled and settings.telemetry.capture_content
        graph = build_graph(
            build_chat_model(settings.llm), default_tools(), prompt, capture_content=capture
        )
        app.state.attendant = GraphAttendant(
            graph.compile(checkpointer=checkpointer.saver),
            before_turn=checkpointer.ensure_setup,
            capture_content=capture,
        )
        logger.info(
            "fornada-api starting",
            extra={
                "llm_provider": settings.llm.provider,
                "llm_model": settings.llm.active.model,
                "prompt_version": prompt.version,
            },
        )
        yield
    finally:
        await checkpointer.close()
        await engine.dispose()
        # Last, so spans emitted while closing still get exported. Drains the
        # span queue; with the Collector down it retries for a few seconds.
        if tracer_provider is not None:
            shutdown_tracing(tracer_provider)


# FastAPI's native OpenTelemetry emits the SERVER span per request through the
# global provider (core/telemetry.py). `tracing` and `operation_spans` keep
# their defaults (True): the dependencies/endpoint/serialization child spans
# show where request time goes.
app = FastAPI(
    title="Fornada API",
    lifespan=lifespan,
    telemetry={
        # core/telemetry.py owns the only exporter; True would add a second
        # one from OTEL_* variables and send every span twice. An explicit
        # value wins over FASTAPI_OTEL_AUTO_CONFIGURE.
        "auto_configure": False,
        # Off until step B adds meter and logger providers. `logs` records
        # exception messages and stack traces, which can carry customer text.
        "metrics": False,
        "logs": False,
    },
)
app.include_router(health.router)
app.include_router(conversations.router)
