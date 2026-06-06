from unittest.mock import patch

import pytest

from config import Settings
from embeddings.factory import create_embedding_provider
from embeddings.fastembed_provider import FastEmbedProvider


class TestFastEmbedProvider:
    def test_embed_returns_correct_shape(self) -> None:
        with patch("fastembed.TextEmbedding") as mock_te:
            instance = mock_te.return_value
            instance.embed.return_value = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
            provider = FastEmbedProvider()
            result = provider.embed(["text a", "text b"])
            mock_te.assert_called_once_with(model_name="BAAI/bge-small-en-v1.5")
            assert len(result) == 2
            assert len(result[0]) == 3
            assert result[0] == [0.1, 0.2, 0.3]

    def test_embed_empty_list_returns_empty(self) -> None:
        with patch("fastembed.TextEmbedding"):
            provider = FastEmbedProvider()
            result = provider.embed([])
            assert result == []


class TestEmbeddingFactory:
    def test_creates_fastembed_provider(self) -> None:
        with patch("fastembed.TextEmbedding"):
            s = Settings(embedding_provider="fastembed", embedding_model="test-model")
            provider = create_embedding_provider(s)
            assert isinstance(provider, FastEmbedProvider)

    def test_raises_on_unknown_provider(self) -> None:
        s = Settings(embedding_provider="unknown")
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            create_embedding_provider(s)

    def test_provider_name_case_insensitive(self) -> None:
        with patch("fastembed.TextEmbedding"):
            s = Settings(embedding_provider="FASTEMBED")
            provider = create_embedding_provider(s)
            assert isinstance(provider, FastEmbedProvider)
