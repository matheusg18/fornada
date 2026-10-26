"""A scripted chat model for runner tests: no network, answers from a queue.

A copy of `apps/api/tests/unit/agents/fakes.py`, which is not importable across apps,
plus queued exceptions for a provider that fails mid-case.
"""

from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable

USAGE = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}


class ScriptedChatModel(BaseChatModel):
    """Returns (or raises) the queued answers in order."""

    # `AIMessage`s and exceptions. Typed `Any` so pydantic leaves them as they are: with
    # a union, it tries to build an `AIMessage` from the exception.
    answers: list[Any]

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Runnable[Any, Any]:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        # Loops on the last answer when the queue runs out of fresh ones.
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        # A copy each time: `add_messages` replaces a message that comes back with the same id.
        return ChatResult(generations=[ChatGeneration(message=answer.model_copy(deep=True))])


def reply(text: str) -> AIMessage:
    return AIMessage(content=text, usage_metadata=USAGE)  # pyright: ignore[reportArgumentType]


def tool_call(name: str, args: dict[str, Any], call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id}],
        usage_metadata=USAGE,  # pyright: ignore[reportArgumentType]
    )
