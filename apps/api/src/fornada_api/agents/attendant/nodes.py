"""The graph's model node, and the wrapper around each call of LangGraph's
prebuilt `ToolNode`."""

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command
from opentelemetry.trace import Span, SpanKind, StatusCode

from fornada_api.agents.attendant import span_content, tracing
from fornada_api.agents.attendant.prompt import SystemPrompt
from fornada_api.agents.attendant.state import AttendantState
from fornada_api.services.errors import InvalidPhone
from fornada_api.services.phones import normalize_phone

PROMPT_VERSION_KEY = "prompt_version"


def make_call_model(
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    prompt: SystemPrompt,
    capture_content: bool = False,
):
    """The model node, with `tools` bound to `model` once, when the graph is built.

    The system prompt goes first in every call and is never returned, so it is
    not saved in the conversation. The answer records the prompt version.
    With `capture_content`, the `chat` span also carries what was sent and
    what came back.
    """
    model_with_tools = model.bind_tools(list(tools))
    # Read once, when the graph is built: `ChatAnthropic` and `ChatOpenAI` give
    # fixed values, which match semconv's `gen_ai.provider.name` (design.md, decision 4).
    ls = model._get_ls_params()
    provider, request_model = ls.get("ls_provider"), ls.get("ls_model_name")

    # LangGraph passes the run config to a node that takes a `config` parameter;
    # its `thread_id` is the conversation id.
    async def call_model(state: AttendantState, config: RunnableConfig) -> dict[str, Any]:
        thread_id = (config.get("configurable") or {}).get("thread_id")
        # Known before the call, so samplers see them at span start. `None`
        # values are filtered below: OTel rejects them with a warning.
        attributes = {
            tracing.GEN_AI_OPERATION_NAME: tracing.OP_CHAT,
            tracing.GEN_AI_PROVIDER_NAME: provider,
            tracing.GEN_AI_REQUEST_MODEL: request_model,
            tracing.FORNADA_PROMPT_VERSION: prompt.version,
        }
        if thread_id is not None:
            attributes[tracing.GEN_AI_CONVERSATION_ID] = str(thread_id)
            attributes[tracing.SESSION_ID] = str(thread_id)
        # Input at span start, so a failed call still shows what was sent.
        if capture_content:
            attributes[tracing.GEN_AI_SYSTEM_INSTRUCTIONS] = span_content.system_instructions(
                prompt.text
            )
            attributes[tracing.GEN_AI_INPUT_MESSAGES] = span_content.input_messages(
                state["messages"]
            )

        # CLIENT: the model runs at the provider, outside this process. The
        # httpx2 span of the HTTP request starts inside it, as its child.
        with tracing.tracer.start_as_current_span(
            f"{tracing.OP_CHAT} {request_model}",
            kind=SpanKind.CLIENT,
            attributes={k: v for k, v in attributes.items() if v is not None},
            # Same reason as the turn span: no exception message in the status.
            set_status_on_exception=False,
        ) as span:
            try:
                answer = await model_with_tools.ainvoke(
                    [SystemMessage(prompt.text), *state["messages"]]
                )
            except Exception as error:
                span.set_status(StatusCode.ERROR)
                span.set_attribute(tracing.ERROR_TYPE, type(error).__name__)
                raise
            set_response_attributes(span, answer)
            if capture_content and isinstance(answer, AIMessage):
                span.set_attribute(
                    tracing.GEN_AI_OUTPUT_MESSAGES, span_content.output_messages(answer)
                )

        answer.response_metadata = {**answer.response_metadata, PROMPT_VERSION_KEY: prompt.version}
        return {"messages": [answer], PROMPT_VERSION_KEY: prompt.version}

    return call_model


def set_response_attributes(span: Span, answer: BaseMessage) -> None:
    """What the provider returned. Missing values are left out, never zeroed.

    Keys checked in `langchain-anthropic` 1.7.5 and `langchain-openai` 1.6.7:
    both put the provider's model and id in `response_metadata` ("model_name",
    "id"); `answer.id` is LangChain's run id, not the provider's. Only the stop
    reason has a different key per provider.
    """
    metadata = answer.response_metadata
    if response_model := metadata.get("model_name"):
        span.set_attribute(tracing.GEN_AI_RESPONSE_MODEL, response_model)
    if response_id := metadata.get("id"):
        span.set_attribute(tracing.GEN_AI_RESPONSE_ID, response_id)
    # One reason per generated choice; we ask for one choice, so a one-item list.
    if reason := metadata.get("stop_reason") or metadata.get("finish_reason"):
        span.set_attribute(tracing.GEN_AI_RESPONSE_FINISH_REASONS, [reason])

    usage = answer.usage_metadata if isinstance(answer, AIMessage) else None
    if usage is not None:
        # LangChain's input count already includes cache reads and writes, as
        # semconv asks; no cache attributes (design.md, decision 6).
        span.set_attribute(tracing.GEN_AI_USAGE_INPUT_TOKENS, usage["input_tokens"])
        span.set_attribute(tracing.GEN_AI_USAGE_OUTPUT_TOKENS, usage["output_tokens"])


ToolHandler = Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]]


# `error.type` for a tool call that came back as an error result. One value:
# the wrapper only sees `ToolMessage.status`, and telling a domain error from
# invalid arguments would mean reading the message text, which can hold
# customer data. The text stays in the conversation, for error analysis.
TOOL_ERROR = "tool_error"


def make_wrap_tool_call(capture_content: bool = False):
    """The `ToolNode` wrapper; `capture_content` adds arguments, result and phone."""

    async def wrap_tool_call(
        request: ToolCallRequest, handler: ToolHandler
    ) -> ToolMessage | Command:
        """The `execute_tool` span around each tool call `ToolNode` makes.

        It runs in that call's own task, so concurrent calls of one model answer
        get sibling spans, each a child of the turn span. Tools see this span as
        the current one, so a tool can add its own attributes to it.
        """
        call = request.tool_call
        name = call["name"]
        attributes = {
            tracing.GEN_AI_OPERATION_NAME: tracing.OP_EXECUTE_TOOL,
            tracing.GEN_AI_TOOL_NAME: name,
            tracing.GEN_AI_TOOL_TYPE: tracing.TOOL_TYPE_FUNCTION,
        }
        if call_id := call.get("id"):
            attributes[tracing.GEN_AI_TOOL_CALL_ID] = call_id
        thread_id = (request.runtime.config.get("configurable") or {}).get("thread_id")
        if thread_id is not None:
            attributes[tracing.GEN_AI_CONVERSATION_ID] = str(thread_id)
            attributes[tracing.SESSION_ID] = str(thread_id)
        if capture_content:
            attributes[tracing.GEN_AI_TOOL_CALL_ARGUMENTS] = span_content.to_json(call["args"])
            if phone := customer_phone(call["args"]):
                attributes[tracing.FORNADA_CUSTOMER_PHONE] = phone

        with tracing.tracer.start_as_current_span(
            f"{tracing.OP_EXECUTE_TOOL} {name}",
            kind=SpanKind.INTERNAL,
            attributes=attributes,
            set_status_on_exception=False,
        ) as span:
            try:
                result = await handler(request)
            except Exception as error:
                # Rare: our tools turn their errors into error results. Anything
                # else still reaches here and fails the turn.
                span.set_status(StatusCode.ERROR)
                span.set_attribute(tracing.ERROR_TYPE, type(error).__name__)
                raise
            # A result, not an exception, is how tools fail here (`handle_tool_error`
            # and ToolNode's argument validation). The turn goes on: the model reads
            # the error, so only this span is marked.
            if isinstance(result, ToolMessage) and result.status == "error":
                span.set_status(StatusCode.ERROR)
                span.set_attribute(tracing.ERROR_TYPE, TOOL_ERROR)
            if capture_content and isinstance(result, ToolMessage):
                span.set_attribute(tracing.GEN_AI_TOOL_CALL_RESULT, result.text)
            return result

    return wrap_tool_call


def customer_phone(args: dict[str, Any]) -> str | None:
    """The `phone` argument in E.164, or None. Every tool that takes a phone
    names it `phone`. A value that does not normalize is left out: it can be
    any text the model produced, and the Collector would hash it as a phone."""
    raw = args.get("phone")
    if not isinstance(raw, str):
        return None
    try:
        return normalize_phone(raw)
    except InvalidPhone:
        return None
