from unittest.mock import MagicMock

import pytest

from query.hybrid_retriever import HybridRetriever
from query.semantic_retriever import SemanticRetriever
from query.structured_retriever import StructuredRetriever


@pytest.mark.asyncio
async def test_hybrid_returns_both_result_sets(session):
    structured = MagicMock(spec=StructuredRetriever)
    structured.search.return_value = [{"id": "doc-1", "structured_fields": {}}]

    semantic = MagicMock(spec=SemanticRetriever)
    semantic.search.return_value = [{"chunk_id": "chunk-1", "text": "hello"}]

    hybrid = HybridRetriever(structured, semantic)
    docs, chunks, trace = await hybrid.search("test query")

    assert len(docs) == 1
    assert len(chunks) == 1
    assert trace.strategy == "hybrid"
    assert any("structured" in step.lower() for step in trace.steps)
    assert any("semantic" in step.lower() for step in trace.steps)
