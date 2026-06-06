from typing import Any

from embeddings.base import EmbeddingProvider
from storage.document_store import DocumentStore


class SemanticRetriever:
    def __init__(
        self,
        document_store: DocumentStore,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.store = document_store
        self.embedder = embedding_provider

    async def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        query_embedding = self.embedder.embed([query])[0]
        results = await self.store.semantic_search(query_embedding, limit=limit)
        return [
            {
                "chunk_id": str(r.chunk.id),
                "document_id": str(r.chunk.document_id),
                "chunk_index": r.chunk.chunk_index,
                "text": r.chunk.text,
                "score": r.score,
                "metadata": r.chunk.metadata,
            }
            for r in results
        ]
