"""HTTP client for the Fornada conversation API.

The chat only talks to the API through `send_message`. Every failure the chat
treats the same way (API unreachable, too slow, error status, unexpected body)
surfaces as one `ApiError`, so the UI layer has a single thing to catch.
"""

import logging
import os
from collections.abc import Mapping
from uuid import UUID

import httpx

DEFAULT_API_URL = "http://localhost:8000"

# Shown to the customer when a turn fails. Brazilian Portuguese on purpose.
ERROR_MESSAGE = "Desculpe, não consegui responder agora. Tente novamente em instantes."

logger = logging.getLogger(__name__)


def load_api_url(environ: Mapping[str, str]) -> str:
    return environ.get("CHAT__API_URL") or DEFAULT_API_URL


API_URL = load_api_url(os.environ)


class ApiError(Exception):
    """The API call for one turn failed; `kind` says how."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


def _fail(conversation_id: UUID, kind: str, **extra: object) -> ApiError:
    # Never log the message or reply text: customers type names and phones.
    logger.warning(
        "api call failed",
        extra={"conversation_id": str(conversation_id), "kind": kind, **extra},
    )
    return ApiError(kind)


async def send_message(http: httpx.AsyncClient, conversation_id: UUID, text: str) -> list[str]:
    """Post one customer message; return the bot's reply texts, in order."""
    try:
        response = await http.post(
            f"/conversations/{conversation_id}/messages", json={"text": text}
        )
    except httpx.TimeoutException as exc:
        raise _fail(conversation_id, "timeout") from exc
    except httpx.TransportError as exc:
        raise _fail(conversation_id, "connect") from exc

    if response.status_code != 200:
        raise _fail(conversation_id, "status", status_code=response.status_code)

    try:
        replies = [reply["text"] for reply in response.json()["replies"]]
    except (ValueError, KeyError, TypeError) as exc:
        raise _fail(conversation_id, "bad_body") from exc
    if not replies or not all(isinstance(reply, str) for reply in replies):
        raise _fail(conversation_id, "bad_body")
    return replies
