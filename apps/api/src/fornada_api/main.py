"""FastAPI application. Serve it with `fastapi dev` (see the README)."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fornada_api import conversations, health
from fornada_api.agents.attendant.attendant import GraphAttendant
from fornada_api.agents.attendant.graph import build_graph
from fornada_api.agents.attendant.metrics import TokenPrices
from fornada_api.agents.attendant.model import build_chat_model
from fornada_api.agents.attendant.prompt import load_system_prompt
from fornada_api.agents.attendant.tools import default_tools
from fornada_api.core.config import get_settings
from fornada_api.core.logging import configure_logging
from fornada_api.core.telemetry import (
    build_logger_provider,
    setup_metrics,
    setup_tracing,
    shutdown_logging,
    shutdown_metrics,
    shutdown_tracing,
)
from fornada_api.infrastructure.checkpointer import Checkpointer
from fornada_api.infrastructure.engine import get_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # Invalid settings fail here, before any request is served.
    settings = get_settings()
    # Telemetry on: logs also go to the Collector, each stamped with the active
    # span's trace id. Building the provider does not connect.
    logger_provider = (
        build_logger_provider(settings.telemetry) if settings.telemetry.enabled else None
    )
    configure_logging(settings.log, logger_provider)
    engine = get_engine()
    prompt = load_system_prompt()
    tracer_provider = None
    meter_provider = None
    checkpointer = None
    try:
        # Global before the graph runs: the agent's instruments resolve through
        # it. None when telemetry is off.
        meter_provider = setup_metrics(settings.telemetry)
        # Global before the first request: FastAPI looks the provider up per
        # request. None when tracing is off. Before the checkpointer, which
        # needs the provider to trace its connections.
        tracer_provider = setup_tracing(settings.telemetry, engine)
        checkpointer = Checkpointer(settings.db.url.get_secret_value(), tracer_provider)
        await checkpointer.open()
        # Content only matters when spans are exported; with tracing off, skip
        # building it.
        capture = settings.telemetry.enabled and settings.telemetry.capture_content
        llm = settings.llm.active
        prices = TokenPrices(llm.input_usd_per_mtok, llm.output_usd_per_mtok)
        graph = build_graph(
            build_chat_model(settings.llm),
            default_tools(),
            prompt,
            capture_content=capture,
            prices=prices,
        )
        app.state.attendant = GraphAttendant(
            graph.compile(checkpointer=checkpointer.saver),
            before_turn=checkpointer.ensure_setup,
            capture_content=capture,
            chaos_enabled=settings.chaos.enabled,
            request_model=llm.model,
        )
        logger.info(
            "fornada-api starting",
            extra={
                "llm_provider": settings.llm.provider,
                "llm_model": settings.llm.active.model,
                "prompt_version": prompt.version,
            },
        )
        if not llm.prices_match_model:
            # The model changed but its prices did not: the cost metric is off.
            logger.warning(
                "token prices are the default model's",
                extra={"llm_model": llm.model, "llm_provider": settings.llm.provider},
            )
        if settings.chaos.enabled:
            chaos = settings.chaos
            # Faults are on in every conversation; say so loudly at startup.
            logger.warning(
                "chaos mode enabled",
                extra={
                    "latency_min_ms": chaos.latency_min_ms,
                    "latency_max_ms": chaos.latency_max_ms,
                    "capacity_failure_rate": chaos.capacity_failure_rate,
                    "price_increase_pct": float(chaos.price_increase_pct),
                    "seeded": chaos.seed is not None,
                },
            )
        yield
    finally:
        if checkpointer is not None:
            await checkpointer.close()
        await engine.dispose()
        # Last, so spans emitted while closing still get exported. Drains the
        # span queue; with the Collector down it retries for a few seconds.
        if tracer_provider is not None:
            shutdown_tracing(tracer_provider)
        # Exports what was recorded since the last 10 s export. Before logs, so
        # a warning about a failed final export still goes out.
        if meter_provider is not None:
            shutdown_metrics(meter_provider)
        # Logs after traces, so records written while tracing shuts down are
        # still exported. Detach the OTLP handler first (stdout stays), so no
        # record reaches a provider that has already stopped.
        if logger_provider is not None:
            configure_logging(settings.log)
            shutdown_logging(logger_provider)


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
        # `metrics` stays off: HTTP server metrics are out of scope (the agent's
        # own metrics cover turn latency); turning them on adds series per route
        # and status code. `logs` stays off on purpose: it records request
        # validation failures, whose error detail echoes the invalid input (the
        # customer's message). Unhandled errors are already logged by our own
        # code, inside the request's span.
        "metrics": False,
        "logs": False,
    },
)
app.include_router(health.router)
app.include_router(conversations.router)
