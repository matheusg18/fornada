"""Integration tests run against the dev container's seeded database.

They are skipped when `DATABASE_URI` is not set (outside the dev container).
"""

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

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


@pytest.fixture(autouse=True)
def db_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the app at the seeded database, with a placeholder LLM key."""
    from fornada_api.core.config import get_settings

    if DATABASE_URI:
        monkeypatch.setenv("DB__URL", DATABASE_URI)
    monkeypatch.setenv("LLM__PROVIDER", "anthropic")
    monkeypatch.setenv("LLM__ANTHROPIC__API_KEY", "sk-ant-test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """A test-owned engine, independent of the app's cached one."""
    assert DATABASE_URI
    url = make_url(DATABASE_URI).set(drivername="postgresql+psycopg")
    engine = create_async_engine(url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(engine) as session:
        yield session
