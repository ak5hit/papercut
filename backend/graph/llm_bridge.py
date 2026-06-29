from typing import Any

from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from config import Settings


def build_langchain_chat(settings: Settings) -> Any:
    """Build a LangChain ChatModel matching the configured provider.
    Used only by the graph extractor (LLMGraphTransformer)."""
    name = settings.llm_provider.lower()
    if name == "ollama":
        return ChatOllama(base_url=settings.ollama_base_url, model=settings.llm_model, temperature=0)
    if name in ("openai", "openai-compatible"):
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY required for graph extraction")
        return ChatOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.llm_model,
            temperature=0,
            model_kwargs={"thinking": {"type": "disabled"}},
        )
    raise ValueError(f"Unknown LLM provider for graph extraction: {name}")
