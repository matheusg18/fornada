"""HTTP client for the Fornada conversation API.

Every failure surfaces as one `ApiError` whose `kind` says how the turn failed.
Message and reply text is never logged, only ids and failure kinds.

Each post is one CLIENT span, the root of that turn's trace. Its context goes
to the API in a `traceparent` header, so the API's spans join the trace (see
the `client-tracing` spec). With tracing on, a `baggage` header carries only
the persona id, a dimension of the API's metrics; the run id and the matrix
cell stay on the span.
"""

import logging
from typing import Any, Literal
from uuid import UUID

import httpx2
from opentelemetry import baggage, propagate, trace
from opentelemetry.context import Context
from opentelemetry.trace import Span, SpanKind
from opentelemetry.trace.status import StatusCode

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

ApiErrorKind = Literal["timeout", "connect", "status", "bad_body"]

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
PERSONA_ID = "fornada.simulator.persona.id"
RUN_ID = "fornada.simulator.run.id"
INTENT_ID = "fornada.simulator.intent.id"
COMPLICATION_ID = "fornada.simulator.complication.id"


class ApiError(Exception):
    """The API call for one turn failed; `kind` says how."""

    def __init__(self, kind: ApiErrorKind, status_code: int | None = None) -> None:
        super().__init__(kind)
        self.kind: ApiErrorKind = kind
        # Set when the API answered with a non-200 status.
        self.status_code = status_code


def _fail(conversation_id: UUID, kind: ApiErrorKind, status_code: int | None = None) -> ApiError:
    extra: dict[str, object] = {"conversation_id": str(conversation_id), "kind": kind}
    if status_code is not None:
        extra["status_code"] = status_code
    logger.warning("api call failed", extra=extra)
    return ApiError(kind, status_code)


def request_attributes(
    http: httpx2.AsyncClient,
    conversation_id: UUID,
    persona_id: str | None,
    run_id: str | None,
    intent_id: str | None = None,
    complication_id: str | None = None,
) -> dict[str, Any]:
    """The client span's attributes, known before the request is sent."""
    attributes = {
        HTTP_REQUEST_METHOD: "POST",
        URL_TEMPLATE_ATTR: URL_TEMPLATE,
        SERVER_ADDRESS: http.base_url.host,
        SERVER_PORT: http.base_url.port or DEFAULT_PORTS[http.base_url.scheme],
        SESSION_ID: str(conversation_id),
        GEN_AI_CONVERSATION_ID: str(conversation_id),
    }
    if persona_id is not None:
        attributes[PERSONA_ID] = persona_id
    if run_id is not None:
        attributes[RUN_ID] = run_id
    # The matrix cell; like the run id, never sent to the API.
    if intent_id is not None:
        attributes[INTENT_ID] = intent_id
    if complication_id is not None:
        attributes[COMPLICATION_ID] = complication_id
    return attributes


def mark_failed(span: Span, error: ApiError) -> None:
    """Record a failed post on the client span. A successful one stays UNSET."""
    span.set_status(StatusCode.ERROR)  # no description: it could echo a body
    if error.status_code is not None:
        # HTTP semconv: the status code, as a string.
        span.set_attribute(ERROR_TYPE, str(error.status_code))
    else:
        # One of: "timeout", "connect", "bad_body". Low cardinality.
        span.set_attribute(ERROR_TYPE, error.kind)


async def send_message(
    http: httpx2.AsyncClient,
    conversation_id: UUID,
    text: str,
    *,
    persona_id: str | None = None,
    run_id: str | None = None,
    intent_id: str | None = None,
    complication_id: str | None = None,
) -> list[str]:
    """Post one customer message; return the attendant's reply texts, in order."""
    with tracer.start_as_current_span(
        SPAN_NAME,
        kind=SpanKind.CLIENT,
        attributes=request_attributes(
            http, conversation_id, persona_id, run_id, intent_id, complication_id
        ),
        # Always a root: one trace per turn, whatever span is current.
        context=Context(),
        # The default description is the exception message; `mark_failed`
        # sets the status without one.
        set_status_on_exception=False,
    ) as span:
        try:
            return await _post(http, conversation_id, text, span, persona_id)
        except ApiError as error:
            mark_failed(span, error)
            raise


def outgoing_context(span: Span, persona_id: str | None) -> Context:
    """What the post propagates: the client span and, with tracing on, the
    persona as baggage. Built from an empty context, so no baggage set around
    the call goes out."""
    carried = trace.set_span_in_context(span, Context())
    # A no-op span (tracing off) has no valid context.
    if persona_id is not None and span.get_span_context().is_valid:
        carried = baggage.set_baggage(PERSONA_ID, persona_id, carried)
    return carried


async def _post(
    http: httpx2.AsyncClient,
    conversation_id: UUID,
    text: str,
    span: Span,
    persona_id: str | None,
) -> list[str]:
    # The span's context as `traceparent`, and the persona as `baggage`.
    # Nothing is added when tracing is off.
    headers: dict[str, str] = {}
    propagate.inject(headers, context=outgoing_context(span, persona_id))
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
