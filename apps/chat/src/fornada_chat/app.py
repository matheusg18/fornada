"""Chainlit entry point: a thin layer over `client.send_message`."""

from uuid import UUID, uuid4

import chainlit as cl
import httpx

from fornada_chat.client import API_URL, ERROR_MESSAGE, ApiError, send_message

# A real agent turn can chain several LLM and tool calls, so wait longer than
# httpx's 5 s default.
REQUEST_TIMEOUT_SECONDS = 60

CONVERSATION_ID_KEY = "conversation_id"


@cl.on_chat_start
async def start() -> None:
    cl.user_session.set(CONVERSATION_ID_KEY, uuid4())


@cl.on_message
async def main(message: cl.Message) -> None:
    conversation_id = cl.user_session.get(CONVERSATION_ID_KEY)
    if not isinstance(conversation_id, UUID):
        raise RuntimeError("chat session has no conversation id; on_chat_start did not run")
    try:
        async with httpx.AsyncClient(base_url=API_URL, timeout=REQUEST_TIMEOUT_SECONDS) as http:
            replies = await send_message(http, conversation_id, message.content)
    except ApiError:
        await cl.Message(content=ERROR_MESSAGE).send()
        return
    for reply in replies:
        await cl.Message(content=reply).send()
