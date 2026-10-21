"""Integration tests run against the test-only database, seeded for a fixed day.

At the start of each session the app tables are recreated and the seed is
loaded with `fornada.seed_day` pinned to `SEED_DAY`, so results depend neither
on the calendar nor on the dev database. They are skipped when
`TEST_DATABASE_URI` is not set (outside the dev container); there is no
fallback to `DATABASE_URI`.
"""

import datetime as dt
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import LiteralString, cast

import psycopg
import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fornada_api.core.config import get_settings
from fornada_api.infrastructure.engine import get_engine, get_sessionmaker, to_async_url

TEST_DATABASE_URI = os.environ.get("TEST_DATABASE_URI")

# A Monday; the seed fills day +3 (15 kg) and +4, and leaves 2 kg on day +5.
SEED_DAY = dt.date(2026, 3, 9)

DB_DIR = Path(__file__).parents[4] / ".devcontainer" / "db"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.path.is_relative_to(os.path.dirname(__file__)):
            item.add_marker(pytest.mark.integration)
            if not TEST_DATABASE_URI:
                item.add_marker(pytest.mark.skip(reason="TEST_DATABASE_URI is not set"))


@pytest.fixture(scope="session", autouse=True)
def seeded_database() -> None:
    """Recreate the app tables and load the seed for `SEED_DAY`, once per session."""
    if not TEST_DATABASE_URI:
        return
    with psycopg.connect(TEST_DATABASE_URI, autocommit=True) as conn:
        conn.execute("SELECT set_config('fornada.seed_day', %s, false)", (SEED_DAY.isoformat(),))
        for name in ("schema.sql", "seed.sql"):
            # Committed files from the repo, so trusted SQL; psycopg types it as LiteralString.
            conn.execute(cast(LiteralString, (DB_DIR / name).read_text()))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def clear_caches() -> None:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


@pytest.fixture(autouse=True)
def db_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the app at the test database, with a placeholder LLM key."""
    if TEST_DATABASE_URI:
        monkeypatch.setenv("DB__URL", TEST_DATABASE_URI)
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
    assert TEST_DATABASE_URI
    engine = create_async_engine(to_async_url(TEST_DATABASE_URI))
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
def full_day() -> dt.date:
    """The seeded day whose non-cancelled orders fill the default 15 kg."""
    return SEED_DAY + dt.timedelta(days=3)
