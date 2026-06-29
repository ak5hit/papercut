import pytest

from config import Settings
from embeddings.factory import create_embedding_provider, get_embedding_provider


@pytest.mark.asyncio
async def test_get_embedding_provider_returns_cached_instance() -> None:
    """get_embedding_provider should return the same instance on repeated calls."""
    s = Settings(
        embedding_provider="fastembed",
        embedding_model="BAAI/bge-small-en-v1.5",
    )
    p1 = await get_embedding_provider(s)
    p2 = await get_embedding_provider(s)
    assert p1 is p2
