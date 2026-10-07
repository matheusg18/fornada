"""The chat channel: clients send a customer message and read the bot's replies.

The client picks the conversation id (a UUID); the first message to an unseen id
starts the conversation. Message text is never logged, only its length.
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, StringConstraints

from fornada_api.dependencies import AttendantDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


class MessageIn(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Reply(BaseModel):
    text: str


class TurnOut(BaseModel):
    conversation_id: UUID
    replies: list[Reply]


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: UUID, message: MessageIn, attendant: AttendantDep
) -> TurnOut:
    """Send one customer message and get the bot's replies for this turn."""
    logger.info(
        "conversation turn",
        extra={"conversation_id": str(conversation_id), "text_length": len(message.text)},
    )
    try:
        replies = await attendant.reply(conversation_id, message.text)
    except Exception:
        # Provider and driver errors can carry hosts, ids or keys: log, never return.
        logger.exception("turn failed", extra={"conversation_id": str(conversation_id)})
        raise HTTPException(status_code=503, detail="attendant unavailable") from None
    return TurnOut(
        conversation_id=conversation_id,
        replies=[Reply(text=reply) for reply in replies],
    )
