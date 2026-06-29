import asyncio

from config import Settings
from llm.base import LLMProvider
from llm.ollama_provider import OllamaProvider
from llm.openai_provider import OpenAICompatibleProvider


_llm_provider: LLMProvider | None = None
_llm_lock = asyncio.Lock()


def create_llm_provider(settings: Settings) -> LLMProvider:
    """Factory: returns a fresh LLM provider instance. Use in tests."""
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


async def get_llm_provider(settings: Settings) -> LLMProvider:
    """Cached singleton: reuse the same LLM provider across requests."""
    global _llm_provider
    if _llm_provider is None:
        async with _llm_lock:
            if _llm_provider is None:
                _llm_provider = create_llm_provider(settings)
    return _llm_provider
