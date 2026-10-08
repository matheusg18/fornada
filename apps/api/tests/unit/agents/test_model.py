from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from fornada_api.agents.attendant.model import build_chat_model
from fornada_api.core.config import AnthropicSettings, LlmSettings, OpenAISettings


def test_default_provider_is_anthropic_haiku() -> None:
    llm = LlmSettings(anthropic=AnthropicSettings(api_key=SecretStr("sk-ant-test")))
    model = build_chat_model(llm)
    assert isinstance(model, ChatAnthropic)
    assert model.model == "claude-haiku-4-5"


def test_openai_provider() -> None:
    llm = LlmSettings(provider="openai", openai=OpenAISettings(api_key=SecretStr("sk-test")))
    model = build_chat_model(llm)
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "gpt-5-mini"
