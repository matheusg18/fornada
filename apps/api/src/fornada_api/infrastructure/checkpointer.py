"""LangGraph's PostgreSQL checkpointer: the conversations' memory.

The pool opens without connecting, so the app starts with the database down.
The library's own tables are created on the first turn, once. With a tracer
provider, each pooled connection's statements become CLIENT spans.
"""

import asyncio
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


class Checkpointer:
    def __init__(self, url: str, tracer_provider: TracerProvider | None = None) -> None:
        # Instrument each pooled connection, not psycopg globally: the global
        # instrumentor also wraps the connections of the SQLAlchemy engine,
        # which it already traces, and every tool statement would get two spans.
        async def trace_connection(connection: AsyncConnection[Any]) -> None:
            PsycopgInstrumentor.instrument_connection(connection, tracer_provider=tracer_provider)

        # The settings `autocommit`, `prepare_threshold` and `row_factory` are
        # what AsyncPostgresSaver requires of its connections.
        self._pool: AsyncConnectionPool[Any] = AsyncConnectionPool(
            url,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
            configure=trace_connection if tracer_provider is not None else None,
            open=False,
        )
        self.saver = AsyncPostgresSaver(self._pool)  # pyright: ignore[reportArgumentType]
        self._setup_lock = asyncio.Lock()
        self._is_setup = False

    async def open(self) -> None:
        """Start the pool without waiting for a connection."""
        await self._pool.open(wait=False)

    async def ensure_setup(self) -> None:
        """Create or migrate the checkpointer tables, once per process."""
        async with self._setup_lock:
            if not self._is_setup:
                await self.saver.setup()
                self._is_setup = True

    async def close(self) -> None:
        await self._pool.close()
