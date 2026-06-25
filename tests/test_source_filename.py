from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from graph.retriever import GraphRetriever


class MockRow:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class MockResult:
    """Wraps a list of rows in a sync iterable for session.execute()."""

    def __init__(self, rows: list):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


@pytest.mark.asyncio
async def test_enriched_search_includes_filename() -> None:
    doc_id = str(uuid4())
    chunk_id = str(uuid4())

    session = AsyncMock()
    age_graph = MagicMock()
    embedder = MagicMock()
    embedder.embed.return_value = [[0.1, 0.2, 0.3]]
    settings = MagicMock()

    call_count = 0

    async def mock_execute(sql):
        nonlocal call_count
        if call_count == 0:
            # pgvector query returns one chunk
            result = MockResult([
                MockRow(id=chunk_id, document_id=doc_id, text="some text",
                        chunk_index=0, score=0.95)
            ])
        else:
            # document lookup returns the filename
            result = MockResult([
                MockRow(id=doc_id, filename="Akshit_Resume.pdf")
            ])
        call_count += 1
        return result

    session.execute = mock_execute

    retriever = GraphRetriever(session, age_graph, embedder, None, settings)
    result = await retriever.enriched_search("test query")

    assert len(result["chunks"]) == 1
    chunk = result["chunks"][0]
    assert chunk["document_id"] == doc_id
    assert chunk["filename"] == "Akshit_Resume.pdf"


@pytest.mark.asyncio
async def test_enriched_search_falls_back_to_unknown() -> None:
    doc_id = str(uuid4())
    chunk_id = str(uuid4())

    session = AsyncMock()
    age_graph = MagicMock()
    embedder = MagicMock()
    embedder.embed.return_value = [[0.1, 0.2, 0.3]]
    settings = MagicMock()

    call_count = 0

    async def mock_execute(sql):
        nonlocal call_count
        if call_count == 0:
            # pgvector query returns one chunk
            result = MockResult([
                MockRow(id=chunk_id, document_id=doc_id, text="some text",
                        chunk_index=0, score=0.95)
            ])
        else:
            # document lookup returns nothing (no matching doc)
            result = MockResult([])
        call_count += 1
        return result

    session.execute = mock_execute

    retriever = GraphRetriever(session, age_graph, embedder, None, settings)
    result = await retriever.enriched_search("test query")

    assert len(result["chunks"]) == 1
    chunk = result["chunks"][0]
    assert chunk["document_id"] == doc_id
    assert chunk["filename"] == "Unknown"
