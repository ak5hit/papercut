from config import Settings
from embeddings.base import EmbeddingProvider
from embeddings.fastembed_provider import FastEmbedProvider


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    provider = settings.embedding_provider.lower()
    if provider == "fastembed":
        return FastEmbedProvider(model=settings.embedding_model)
    raise ValueError(f"Unknown embedding provider: {provider}")
