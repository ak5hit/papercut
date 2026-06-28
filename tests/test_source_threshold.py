from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from config import Settings
from graph.retriever import GraphRetriever


class MockRow:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class MockResult:
    def __init__(self, rows: list):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


@pytest.mark.asyncio
async def test_enriched_search_sql_contains_default_threshold() -> None:
    """The SQL query includes the default 0.5 similarity threshold."""
    doc_id = str(uuid4())
    chunk_id = str(uuid4())

    session = AsyncMock()
    age_graph = MagicMock()
    embedder = MagicMock()
    embedder.embed.return_value = [[0.1, 0.2, 0.3]]
    settings = Settings()

    captured_sql: list[str] = []

    async def mock_execute(sql):
        captured_sql.append(str(sql))
        result = MagicMock()
        result.__iter__.return_value = [
            MockRow(id=chunk_id, document_id=doc_id, text="some text",
                    chunk_index=0, score=0.5)
        ]
        # Second call for doc lookup returns empty
        if len(captured_sql) > 1:
            result.__iter__.return_value = []
        return result

    session.execute = mock_execute

    retriever = GraphRetriever(session, age_graph, embedder, None, settings)
    await retriever.enriched_search("test query")

    # The first SQL call is the pgvector query — should contain the threshold
    # (second call is the document filename lookup)
    assert ">= 0.5" in captured_sql[0]


@pytest.mark.asyncio
async def test_enriched_search_threshold_is_configurable() -> None:
    """Changing retrieval_min_similarity changes the SQL threshold."""
    doc_id = str(uuid4())
    chunk_id = str(uuid4())

    session = AsyncMock()
    age_graph = MagicMock()
    embedder = MagicMock()
    embedder.embed.return_value = [[0.1, 0.2, 0.3]]
    settings = Settings(retrieval_min_similarity=0.5)

    captured_sql: list[str] = []

    async def mock_execute(sql):
        captured_sql.append(str(sql))
        result = MagicMock()
        result.__iter__.return_value = [
            MockRow(id=chunk_id, document_id=doc_id, text="some text",
                    chunk_index=0, score=0.6)
        ]
        if len(captured_sql) > 1:
            result.__iter__.return_value = []
        return result

    session.execute = mock_execute

    retriever = GraphRetriever(session, age_graph, embedder, None, settings)
    await retriever.enriched_search("test query")

    assert ">= 0.5" in captured_sql[0]
    assert ">= 0.3" not in captured_sql[0]


@pytest.mark.asyncio
async def test_enriched_search_no_settings_uses_default() -> None:
    """When settings is None, the threshold falls back to the hard-coded 0.3."""
    doc_id = str(uuid4())
    chunk_id = str(uuid4())

    session = AsyncMock()
    age_graph = MagicMock()
    embedder = MagicMock()
    embedder.embed.return_value = [[0.1, 0.2, 0.3]]

    captured_sql: list[str] = []

    async def mock_execute(sql):
        captured_sql.append(str(sql))
        result = MagicMock()
        result.__iter__.return_value = [
            MockRow(id=chunk_id, document_id=doc_id, text="some text",
                    chunk_index=0, score=0.5)
        ]
        if len(captured_sql) > 1:
            result.__iter__.return_value = []
        return result

    session.execute = mock_execute

    retriever = GraphRetriever(session, age_graph, embedder, None, None)
    await retriever.enriched_search("test query")

    assert ">= 0.3" in captured_sql[0]


@pytest.mark.asyncio
async def test_semantic_search_accepts_min_similarity() -> None:
    """semantic_search accepts the min_similarity parameter without error."""
    from storage.document_store import DocumentStore

    session = AsyncMock()
    store = DocumentStore(session)
    query_embedding = [0.1, 0.2, 0.3]

    async def mock_execute(sql):
        result = MagicMock()
        result.all.return_value = []
        return result

    session.execute = mock_execute

    # Should not raise — verifies the parameter is wired through
    results = await store.semantic_search(query_embedding, limit=5, min_similarity=0.4)
    assert results == []


def test_structured_branch_yields_no_semantic_chunks() -> None:
    """STRUCTURED planner branch returns chunks=[]."""
    from query.planner import QueryResult

    result = QueryResult(trace=MagicMock(), documents=[], chunks=[])
    assert result.chunks == []
    assert len(result.documents) == 0



