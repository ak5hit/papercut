import asyncio

from config import Settings
from embeddings.base import EmbeddingProvider
from embeddings.fastembed_provider import FastEmbedProvider


_embedding_provider: EmbeddingProvider | None = None
_embedding_lock = asyncio.Lock()


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """Factory: returns a fresh embedding provider instance. Use in tests."""
    provider = settings.embedding_provider.lower()
    if provider == "fastembed":
        return FastEmbedProvider(model=settings.embedding_model)
    raise ValueError(f"Unknown embedding provider: {provider}")


async def get_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """Cached singleton: reuse the same embedding model across requests."""
    global _embedding_provider
    if _embedding_provider is None:
        async with _embedding_lock:
            if _embedding_provider is None:
                _embedding_provider = create_embedding_provider(settings)
    return _embedding_provider
