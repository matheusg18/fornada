"""FastAPI application. Serve it with `fastapi dev` (see the README)."""

import logging
from collections.abc import AsyncIterator
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
from fornada_api.infrastructure.checkpointer import Checkpointer
from fornada_api.infrastructure.engine import get_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Invalid settings fail here, before any request is served.
    settings = get_settings()
    configure_logging(settings.log)
    engine = get_engine()
    prompt = load_system_prompt()
    checkpointer = Checkpointer(settings.db.url.get_secret_value())
    try:
        await checkpointer.open()
        graph = build_graph(build_chat_model(settings.llm), default_tools(), prompt)
        app.state.attendant = GraphAttendant(
            graph.compile(checkpointer=checkpointer.saver), before_turn=checkpointer.ensure_setup
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


app = FastAPI(title="Fornada API", lifespan=lifespan)
app.include_router(health.router)
app.include_router(conversations.router)
