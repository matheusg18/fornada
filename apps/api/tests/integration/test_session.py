import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from fornada_api.dependencies import get_db_session
from fornada_api.models import SentMessage

pytestmark = pytest.mark.anyio


async def test_uncommitted_insert_is_discarded(
    app_engine: AsyncEngine, session: AsyncSession
) -> None:
    marker = f"test-{uuid.uuid4()}"
    dependency = get_db_session()
    db = await anext(dependency)
    db.add(SentMessage(to_phone="+5581999999999", body=marker))
    await db.flush()  # the row reaches the database inside the open transaction
    await dependency.aclose()  # request ends without a commit

    count = await session.scalar(
        select(func.count()).select_from(SentMessage).where(SentMessage.body == marker)
    )
    assert count == 0


async def test_session_closed_after_failing_request(app_engine: AsyncEngine) -> None:
    dependency = get_db_session()
    db = await anext(dependency)
    await db.scalar(select(1))  # checks a connection out of the pool
    assert app_engine.pool.checkedout() == 1

    # FastAPI throws the handler's exception into the dependency.
    with pytest.raises(RuntimeError):
        await dependency.athrow(RuntimeError("handler failed"))
    assert app_engine.pool.checkedout() == 0
