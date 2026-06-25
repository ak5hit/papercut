from typing import Any

from config import Settings
from embeddings.base import EmbeddingProvider
from storage.document_store import DocumentStore


class SemanticRetriever:
    def __init__(
        self,
        document_store: DocumentStore,
        embedding_provider: EmbeddingProvider,
        settings: Settings | None = None,
    ) -> None:
        self.store = document_store
        self.embedder = embedding_provider
        self.settings = settings

    async def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        query_embedding = self.embedder.embed([query])[0]
        min_sim = self.settings.retrieval_min_similarity if self.settings else 0.3
        results = await self.store.semantic_search(query_embedding, limit=limit, min_similarity=min_sim)
        return [
            {
                "chunk_id": str(r.chunk.id),
                "document_id": str(r.chunk.document_id),
                "chunk_index": r.chunk.chunk_index,
                "text": r.chunk.text,
                "score": r.score,
                "filename": r.filename,
                "metadata": r.chunk.metadata,
            }
            for r in results
        ]
