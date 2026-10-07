import uuid

import pytest

from fornada_api.agents.attendant.attendant import FIXED_REPLY, FixedAttendant

pytestmark = pytest.mark.anyio


async def test_fixed_reply_for_any_message() -> None:
    attendant = FixedAttendant()
    first = await attendant.reply(uuid.uuid4(), "Oi, quero um bolo de chocolate")
    second = await attendant.reply(uuid.uuid4(), "Qual o prazo?")
    assert first == second == [FIXED_REPLY]
