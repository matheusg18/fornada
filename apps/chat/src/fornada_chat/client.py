"""HTTP client for the Fornada conversation API.

The chat only talks to the API through `send_message`. Every failure the chat
treats the same way (API unreachable, too slow, error status, unexpected body)
surfaces as one `ApiError`, so the UI layer has a single thing to catch.

Each post is one CLIENT span, the root of that turn's trace. Its context goes
to the API in a `traceparent` header, so the API's spans join the trace (see
the `client-tracing` spec). Mirrors the simulator's client, minus the persona.
"""

import logging
import os
from collections.abc import Mapping
from typing import Any
from uuid import UUID

import httpx2
from opentelemetry import propagate, trace
from opentelemetry.context import Context
from opentelemetry.trace import Span, SpanKind, StatusCode, Tracer, TracerProvider

DEFAULT_API_URL = "http://localhost:8000"

# Shown to the customer when a turn fails. Brazilian Portuguese on purpose.
ERROR_MESSAGE = "Desculpe, não consegui responder agora. Tente novamente em instantes."

logger = logging.getLogger(__name__)
# A no-op until the startup hook calls `use_tracer_provider` with the chat's
# private provider (see `telemetry.py`).
tracer: Tracer = trace.NoOpTracer()

URL_TEMPLATE = "/conversations/{conversation_id}/messages"
# Semconv `{method} {url.template}`: the template, never the id.
SPAN_NAME = f"POST {URL_TEMPLATE}"

# `httpx2.URL.port` is None when the URL uses its scheme's default port.
DEFAULT_PORTS = {"http": 80, "https": 443}

# Attribute names, as plain strings like the API's `tracing.py`.
HTTP_REQUEST_METHOD = "http.request.method"
HTTP_RESPONSE_STATUS_CODE = "http.response.status_code"
URL_TEMPLATE_ATTR = "url.template"
SERVER_ADDRESS = "server.address"
SERVER_PORT = "server.port"
SESSION_ID = "session.id"
GEN_AI_CONVERSATION_ID = "gen_ai.conversation.id"
ERROR_TYPE = "error.type"


def load_api_url(environ: Mapping[str, str]) -> str:
    return environ.get("CHAT__API_URL") or DEFAULT_API_URL


API_URL = load_api_url(os.environ)


def use_tracer_provider(provider: TracerProvider) -> None:
    """Make the client's spans with `provider`."""
    global tracer
    tracer = provider.get_tracer(__name__)


class ApiError(Exception):
    """The API call for one turn failed; `kind` says how."""

    def __init__(self, kind: str, status_code: int | None = None) -> None:
        super().__init__(kind)
        self.kind = kind
        # Set when the API answered with a non-200 status.
        self.status_code = status_code


def _fail(conversation_id: UUID, kind: str, status_code: int | None = None) -> ApiError:
    # Never log the message or reply text: customers type names and phones.
    extra: dict[str, object] = {"conversation_id": str(conversation_id), "kind": kind}
    if status_code is not None:
        extra["status_code"] = status_code
    logger.warning("api call failed", extra=extra)
    return ApiError(kind, status_code)


def request_attributes(http: httpx2.AsyncClient, conversation_id: UUID) -> dict[str, Any]:
    """The client span's attributes, known before the request is sent."""
    return {
        HTTP_REQUEST_METHOD: "POST",
        URL_TEMPLATE_ATTR: URL_TEMPLATE,
        SERVER_ADDRESS: http.base_url.host,
        SERVER_PORT: http.base_url.port or DEFAULT_PORTS[http.base_url.scheme],
        SESSION_ID: str(conversation_id),
        GEN_AI_CONVERSATION_ID: str(conversation_id),
    }


def mark_failed(span: Span, error: ApiError) -> None:
    """Record a failed post on the client span. A successful one stays UNSET."""
    span.set_status(StatusCode.ERROR)  # no description: it could echo a body
    if error.status_code is not None:
        # HTTP semconv: the status code, as a string.
        span.set_attribute(ERROR_TYPE, str(error.status_code))
    else:
        # One of: "timeout", "connect", "bad_body". Low cardinality.
        span.set_attribute(ERROR_TYPE, error.kind)


async def send_message(http: httpx2.AsyncClient, conversation_id: UUID, text: str) -> list[str]:
    """Post one customer message; return the bot's reply texts, in order."""
    with tracer.start_as_current_span(
        SPAN_NAME,
        kind=SpanKind.CLIENT,
        attributes=request_attributes(http, conversation_id),
        # Always a root: one trace per turn, whatever span is current.
        context=Context(),
        # The default description is the exception message; `mark_failed`
        # sets the status without one.
        set_status_on_exception=False,
    ) as span:
        try:
            return await _post(http, conversation_id, text, span)
        except ApiError as error:
            mark_failed(span, error)
            raise


async def _post(
    http: httpx2.AsyncClient, conversation_id: UUID, text: str, span: Span
) -> list[str]:
    # The current span's context, as `traceparent`. Nothing is added when
    # tracing is off: a no-op span has no valid context.
    headers: dict[str, str] = {}
    propagate.inject(headers)
    try:
        response = await http.post(
            URL_TEMPLATE.format(conversation_id=conversation_id),
            json={"text": text},
            headers=headers,
        )
    except httpx2.TimeoutException as exc:
        raise _fail(conversation_id, "timeout") from exc
    except httpx2.TransportError as exc:
        raise _fail(conversation_id, "connect") from exc

    span.set_attribute(HTTP_RESPONSE_STATUS_CODE, response.status_code)
    if response.status_code != 200:
        raise _fail(conversation_id, "status", response.status_code)

    try:
        replies = [reply["text"] for reply in response.json()["replies"]]
    except (ValueError, KeyError, TypeError) as exc:
        raise _fail(conversation_id, "bad_body") from exc
    if not replies or not all(isinstance(reply, str) for reply in replies):
        raise _fail(conversation_id, "bad_body")
    return replies
