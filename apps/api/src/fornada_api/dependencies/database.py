"""Database session for FastAPI path operations."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from fornada_api.infrastructure.engine import get_sessionmaker


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """One session per request, closed when the request ends.

    Never commits: closing rolls back whatever the handler did not commit.
    """
    async with get_sessionmaker()() as session:
        yield session


DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
