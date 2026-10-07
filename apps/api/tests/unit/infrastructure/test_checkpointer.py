import pytest

from fornada_api.infrastructure.checkpointer import Checkpointer

pytestmark = pytest.mark.anyio


async def test_opening_against_an_unreachable_database_does_not_raise() -> None:
    checkpointer = Checkpointer("postgresql://x:pw@127.0.0.1:1/x")
    await checkpointer.open()
    await checkpointer.close()
