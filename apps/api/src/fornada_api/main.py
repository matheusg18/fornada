"""FastAPI application. Serve it with `fastapi dev` (see the README)."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fornada_api import health
from fornada_api.core.config import get_settings
from fornada_api.core.logging import configure_logging
from fornada_api.infrastructure.engine import get_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Invalid settings fail here, before any request is served.
    settings = get_settings()
    configure_logging(settings.log)
    engine = get_engine()
    logger.info(
        "fornada-api starting",
        extra={
            "llm_provider": settings.llm.provider,
            "llm_model": settings.llm.active.model,
        },
    )
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(title="Fornada API", lifespan=lifespan)
app.include_router(health.router)
