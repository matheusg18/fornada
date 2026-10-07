"""Async SQLAlchemy engine and session factory, built once from settings.

Cached like `get_settings()`. Tests that point at another database clear the
caches. The LangGraph tools, which run outside a request, can use
`get_sessionmaker()` directly.
"""

from functools import cache

from sqlalchemy import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fornada_api.core.config import get_settings

APPLICATION_NAME = "fornada-api"


def to_async_url(url: str) -> URL:
    """`postgresql://…` (as in `DATABASE_URI`) -> the async psycopg 3 driver."""
    return make_url(url).set(drivername="postgresql+psycopg")


@cache
def get_engine() -> AsyncEngine:
    # Creating the engine does not connect; the pool connects on first use.
    return create_async_engine(
        to_async_url(get_settings().db.url.get_secret_value()),
        pool_pre_ping=True,
        connect_args={"application_name": APPLICATION_NAME},
    )


@cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: reading an expired attribute would need IO,
    # which async sessions cannot do implicitly.
    return async_sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)
