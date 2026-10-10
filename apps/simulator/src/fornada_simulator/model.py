"""The chat model that plays the customer, chosen by `SIMULATOR__PROVIDER`."""

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from fornada_simulator.settings import SimulatorSettings

# Above 0 on purpose: four runs of one persona should not read the same.
TEMPERATURE = 0.9


def build_chat_model(settings: SimulatorSettings) -> BaseChatModel:
    """The active provider's model with its configured name and key."""
    if settings.provider == "anthropic":
        return ChatAnthropic(
            model_name=settings.anthropic.model,
            # SimulatorSettings already rejects a missing key for the active provider.
            api_key=settings.anthropic.api_key,  # pyright: ignore[reportArgumentType]
            temperature=TEMPERATURE,
            timeout=None,
            stop=None,
        )
    # No temperature: the GPT-5 family only accepts its default.
    return ChatOpenAI(model=settings.openai.model, api_key=settings.openai.api_key)
