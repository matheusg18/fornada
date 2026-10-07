import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fornada_api.models import SentMessage

pytestmark = pytest.mark.anyio


async def test_commit_stays_inside_the_test(
    rollback_sessionmaker: async_sessionmaker[AsyncSession], session: AsyncSession
) -> None:
    marker = f"test-{uuid.uuid4()}"
    async with rollback_sessionmaker() as db, db.begin():
        db.add(SentMessage(to_phone="+5581999999999", body=marker))
    # A later session of the same test sees the committed row...
    async with rollback_sessionmaker() as db:
        assert await db.scalar(select(SentMessage.id).where(SentMessage.body == marker))
    # ...but no other connection does: it is never committed for real.
    count = await session.scalar(
        select(func.count()).select_from(SentMessage).where(SentMessage.body == marker)
    )
    assert count == 0
