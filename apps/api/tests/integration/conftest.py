"""Integration tests run against the dev container's seeded database.

They are skipped when `DATABASE_URI` is not set (outside the dev container).
"""

import datetime as dt
import os
from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fornada_api.core.config import get_settings
from fornada_api.infrastructure.engine import get_engine, get_sessionmaker, to_async_url

DATABASE_URI = os.environ.get("DATABASE_URI")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.path.is_relative_to(os.path.dirname(__file__)):
            item.add_marker(pytest.mark.integration)
            if not DATABASE_URI:
                item.add_marker(pytest.mark.skip(reason="DATABASE_URI is not set"))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def clear_caches() -> None:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


@pytest.fixture(autouse=True)
def db_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the app at the seeded database, with a placeholder LLM key."""
    if DATABASE_URI:
        monkeypatch.setenv("DB__URL", DATABASE_URI)
    monkeypatch.setenv("LLM__PROVIDER", "anthropic")
    monkeypatch.setenv("LLM__ANTHROPIC__API_KEY", "sk-ant-test")
    clear_caches()
    yield
    clear_caches()


@pytest.fixture
async def app_engine() -> AsyncIterator[AsyncEngine]:
    """The app's cached engine, disposed after the test so no connection leaks."""
    engine = get_engine()
    yield engine
    await engine.dispose()


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """A test-owned engine, independent of the app's cached one."""
    assert DATABASE_URI
    engine = create_async_engine(to_async_url(DATABASE_URI))
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(engine) as session:
        yield session


@pytest.fixture
async def rollback_sessionmaker(
    engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Sessions whose commits never reach the database.

    Every session joins one outer transaction on a single connection; a
    session's commit only releases a savepoint. The outer transaction is
    rolled back when the test ends, so tests that create orders leave the
    seed untouched.
    """
    async with engine.connect() as connection:
        outer = await connection.begin()
        yield async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )
        await outer.rollback()


@pytest.fixture
async def full_day(session: AsyncSession) -> dt.date:
    """The first future date whose non-cancelled orders fill the default 15 kg.

    The seed creates one at run day + 3, relative to the day it was applied,
    so the offset from today changes as the dev database ages.
    """
    day = await session.scalar(
        text(
            "SELECT delivery_date FROM orders"
            " WHERE status <> 'cancelled'"
            "   AND delivery_date > (now() AT TIME ZONE 'America/Sao_Paulo')::date"
            " GROUP BY delivery_date HAVING sum(weight_kg) = 15"
            " ORDER BY delivery_date LIMIT 1"
        )
    )
    if day is None:
        pytest.skip("no full day left in the seed; reset the database")
    return day
