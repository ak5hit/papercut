from typing import Any

from query.execution_trace import ExecutionTrace
from query.semantic_retriever import SemanticRetriever
from query.structured_retriever import StructuredRetriever


class HybridRetriever:
    def __init__(
        self,
        structured_retriever: StructuredRetriever,
        semantic_retriever: SemanticRetriever,
    ) -> None:
        self.structured = structured_retriever
        self.semantic = semantic_retriever

    async def search(
        self,
        query: str,
        field_filters: dict[str, Any] | None = None,
        entity_name: str | None = None,
        limit: int = 5,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], ExecutionTrace]:
        trace = ExecutionTrace(strategy="hybrid")

        trace.add_step("Running structured pre-filter")
        docs = await self.structured.search(
            field_filters=field_filters,
            entity_name=entity_name,
            limit=50,
        )
        trace.structured_results_count = len(docs)
        trace.add_step(f"Structured pre-filter returned {len(docs)} documents")

        trace.add_step("Running semantic search")
        chunks = await self.semantic.search(query, limit=limit)
        trace.semantic_results_count = len(chunks)
        trace.add_step(f"Semantic search returned {len(chunks)} chunks")

        return docs, chunks, trace
