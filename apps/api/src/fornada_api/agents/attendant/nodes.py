"""The graph's model node. The tool node is LangGraph's prebuilt `ToolNode`."""

from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from opentelemetry.trace import Span, SpanKind, StatusCode

from fornada_api.agents.attendant import tracing
from fornada_api.agents.attendant.prompt import SystemPrompt
from fornada_api.agents.attendant.state import AttendantState

PROMPT_VERSION_KEY = "prompt_version"


def make_call_model(model: BaseChatModel, tools: Sequence[BaseTool], prompt: SystemPrompt):
    """The model node, with `tools` bound to `model` once, when the graph is built.

    The system prompt goes first in every call and is never returned, so it is
    not saved in the conversation. The answer records the prompt version.
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
