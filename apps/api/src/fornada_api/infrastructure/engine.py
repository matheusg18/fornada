"""Async SQLAlchemy engine and session factory, built once from settings.

Cached like `get_settings()`. Tests that point at another database clear the
caches. The LangGraph tools, which run outside a request, can use
`get_sessionmaker()` directly.
"""

from functools import cache

from sqlalchemy import URL, event, make_url
from sqlalchemy.engine import ExceptionContext
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


def _without_detail(error: BaseException | None) -> None:
    if error is not None and error.args and isinstance(error.args[0], str):
        kept = [ln for ln in error.args[0].splitlines() if not ln.startswith("DETAIL:")]
        error.args = ("\n".join(kept), *error.args[1:])


def drop_server_detail(context: ExceptionContext) -> None:
    """Remove PostgreSQL's `DETAIL:` lines from a driver error before it
    propagates. The server writes the offending values there ("Failing row
    contains (...)", "Key (phone)=(...) already exists"), and `hide_parameters`
    does not touch them. SQLAlchemy copies the driver's message into its own
    exception before this event runs, so both get the rewrite.
    """
    _without_detail(context.original_exception)
    _without_detail(context.sqlalchemy_exception)


@cache
def get_engine() -> AsyncEngine:
    # Creating the engine does not connect; the pool connects on first use.
    engine = create_async_engine(
        to_async_url(get_settings().db.url.get_secret_value()),
        pool_pre_ping=True,
        connect_args={"application_name": APPLICATION_NAME},
        # Errors keep the SQL text but not the bound values (customer names,
        # phones, addresses), which logs and Elasticsearch would store.
        hide_parameters=True,
    )
    event.listen(engine.sync_engine, "handle_error", drop_server_detail)
    return engine


@cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: reading an expired attribute would need IO,
    # which async sessions cannot do implicitly.
    return async_sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)
