"""LangGraph's PostgreSQL checkpointer: the conversations' memory.

The pool opens without connecting, so the app starts with the database down.
The library's own tables are created on the first turn, once.
"""

import asyncio
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


class Checkpointer:
    def __init__(self, url: str) -> None:
        # The settings `autocommit`, `prepare_threshold` and `row_factory` are
        # what AsyncPostgresSaver requires of its connections.
        self._pool: AsyncConnectionPool[Any] = AsyncConnectionPool(
            url,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
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
