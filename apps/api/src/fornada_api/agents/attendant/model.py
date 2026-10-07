"""The attendant's chat model, chosen by `LLM__PROVIDER`."""

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from fornada_api.core.config import LlmSettings


def build_chat_model(llm: LlmSettings) -> BaseChatModel:
    """The active provider's model with its configured name and key."""
    if llm.provider == "anthropic":
        return ChatAnthropic(
            model_name=llm.anthropic.model,
            # LlmSettings already rejects a missing key for the active provider.
            api_key=llm.anthropic.api_key,  # pyright: ignore[reportArgumentType]
            timeout=None,
            stop=None,
        )
    return ChatOpenAI(model=llm.openai.model, api_key=llm.openai.api_key)
