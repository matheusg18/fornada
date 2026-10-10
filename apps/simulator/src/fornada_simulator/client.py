"""HTTP client for the Fornada conversation API.

Every failure surfaces as one `ApiError` whose `kind` says how the turn failed.
Message and reply text is never logged, only ids and failure kinds.
"""

import logging
from typing import Literal
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

ApiErrorKind = Literal["timeout", "connect", "status", "bad_body"]


class ApiError(Exception):
    """The API call for one turn failed; `kind` says how."""

    def __init__(self, kind: ApiErrorKind) -> None:
        super().__init__(kind)
        self.kind: ApiErrorKind = kind


def _fail(conversation_id: UUID, kind: ApiErrorKind, **extra: object) -> ApiError:
    logger.warning(
        "api call failed", extra={"conversation_id": str(conversation_id), "kind": kind, **extra}
    )
    return ApiError(kind)


async def send_message(http: httpx.AsyncClient, conversation_id: UUID, text: str) -> list[str]:
    """Post one customer message; return the attendant's reply texts, in order."""
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
