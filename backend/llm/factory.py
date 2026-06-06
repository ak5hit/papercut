from config import Settings
from llm.base import LLMProvider
from llm.ollama_provider import OllamaProvider
from llm.openai_provider import OpenAICompatibleProvider


def create_llm_provider(settings: Settings) -> LLMProvider:
    provider_name = settings.llm_provider.lower()

    if provider_name == "ollama":
        return OllamaProvider(
            model=settings.llm_model,
            base_url=settings.ollama_base_url,
        )

    if provider_name in ("openai", "openai-compatible"):
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI provider")
        return OpenAICompatibleProvider(
            api_key=settings.openai_api_key,
            model=settings.llm_model,
            base_url=settings.openai_base_url,
        )

    raise ValueError(f"Unknown LLM provider: {provider_name}")
