from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from graph.store import GraphStore


@pytest.fixture
def age_graph() -> MagicMock:
    g = MagicMock()
    g.query.return_value = []
    return g


@pytest.fixture
def store(age_graph: MagicMock) -> GraphStore:
    from config import Settings
    return GraphStore(age_graph, Settings())


def _mock_graph_docs(
    node_ids: list[str],
    combined_chunk_ids: list[str] | None = None,
) -> list[Any]:
    """Build fake GraphDocument-compatible objects for testing link_chunks_to_entities."""
    docs: list[Any] = []
    for nid in node_ids:
        node = MagicMock()
        node.id = nid
        node.type = "TestType"

        source = MagicMock()
        source.metadata = {"combined_chunk_ids": combined_chunk_ids or ["c1", "c2"]}

        gd = MagicMock()
        gd.nodes = [node]
        gd.relationships = []
        gd.source = source
        docs.append(gd)
    return docs


# ─── link_chunks_to_entities ─────────────────────────────────────────────────


class TestLinkChunksToEntities:
    @pytest.mark.asyncio
    async def test_returns_success_count_on_clean_run(self, store: GraphStore, age_graph: MagicMock) -> None:
        """2 graph_docs × 1 node each × 2 chunk_ids = 4 successful MERGEs."""
        age_graph.query.return_value = []
        docs = _mock_graph_docs(["e1", "e2"], ["c1", "c2"])
        result = await store.link_chunks_to_entities(docs, {"c1": "c1", "c2": "c2"})
        assert result == {"linked": 4, "failed": 0, "errors": []}

    @pytest.mark.asyncio
    async def test_counts_failures_when_execute_raises(self, store: GraphStore, age_graph: MagicMock) -> None:
        """First 2 calls fail, next 2 succeed → 2 linked, 2 failed."""
        call_count: list[int] = [0]

        def side_effect(cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
            call_count[0] += 1
            if call_count[0] <= 2:
                raise RuntimeError("bad cypher")
            return []

        age_graph.query = side_effect
        docs = _mock_graph_docs(["e1", "e2"], ["c1", "c2"])
        result = await store.link_chunks_to_entities(docs, {"c1": "c1", "c2": "c2"})
        assert result["linked"] == 2
        assert result["failed"] == 2
        assert "bad cypher" in result["errors"]

    @pytest.mark.asyncio
    async def test_dedupes_error_messages(self, store: GraphStore, age_graph: MagicMock) -> None:
        """All 4 calls fail with same message → 1 unique error in list."""
        age_graph.query.side_effect = RuntimeError("same error")
        docs = _mock_graph_docs(["e1"], ["c1", "c2"])
        result = await store.link_chunks_to_entities(docs, {"c1": "c1", "c2": "c2"})
        assert result["linked"] == 0
        assert result["failed"] == 2
        assert len(result["errors"]) == 1
        assert result["errors"] == ["same error"]

    @pytest.mark.asyncio
    async def test_caps_errors_at_five_unique(self, store: GraphStore, age_graph: MagicMock) -> None:
        """7 distinct errors but only 5 are recorded."""
        call_count: list[int] = [0]

        def side_effect(cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
            call_count[0] += 1
            raise RuntimeError(f"err-{call_count[0]}")

        age_graph.query = side_effect
        docs = _mock_graph_docs(["e1", "e2", "e3", "e4"], ["c1", "c2"])
        result = await store.link_chunks_to_entities(docs, {"c1": "c1", "c2": "c2"})
        assert result["failed"] == 8
        assert len(result["errors"]) == 5

    @pytest.mark.asyncio
    async def test_logs_warning_on_failure(self, store: GraphStore, age_graph: MagicMock, caplog: Any) -> None:
        import logging
        caplog.set_level(logging.WARNING, logger="graph.store")

        age_graph.query.side_effect = RuntimeError("merge failed")
        docs = _mock_graph_docs(["e1"], ["c1"])
        await store.link_chunks_to_entities(docs, {"c1": "c1"})

        warnings = [r for r in caplog.records if "HAS_ENTITY MERGE failed" in r.message]
        assert len(warnings) == 1


# ─── add_document_and_chunks ─────────────────────────────────────────────────


class TestAddDocumentAndChunks:
    @pytest.mark.asyncio
    async def test_returns_chunks_created_count_on_success(self, store: GraphStore, age_graph: MagicMock) -> None:
        age_graph.query.return_value = []
        chunks = [
            {"id": "c1", "text": "chunk one", "position": 0},
            {"id": "c2", "text": "chunk two", "position": 1},
            {"id": "c3", "text": "chunk three", "position": 2},
        ]
        result = await store.add_document_and_chunks(uuid4(), "test.txt", chunks)
        assert result == 3

    @pytest.mark.asyncio
    async def test_partial_failure_raises_with_summary(self, store: GraphStore, age_graph: MagicMock) -> None:
        call_count: list[int] = [0]

        def side_effect(cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
            call_count[0] += 1
            if call_count[0] == 2:  # first chunk CREATE
                raise RuntimeError("bad escape sequence")
            return []

        age_graph.query = side_effect
        chunks = [
            {"id": "c1", "text": "chunk one", "position": 0},
            {"id": "c2", "text": "chunk two", "position": 1},
            {"id": "c3", "text": "chunk three", "position": 2},
        ]
        with pytest.raises(RuntimeError) as exc_info:
            await store.add_document_and_chunks(uuid4(), "test.txt", chunks)
        assert "created 2/3 chunks" in str(exc_info.value)
        assert "bad escape sequence" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_total_failure_raises(self, store: GraphStore, age_graph: MagicMock) -> None:
        call_count: list[int] = [0]

        def side_effect(cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
            call_count[0] += 1
            if call_count[0] >= 2:  # chunk CREATEs (call 1 is Document)
                raise RuntimeError("all chunks broken")
            return []

        age_graph.query = side_effect
        chunks = [
            {"id": "c1", "text": "chunk one", "position": 0},
            {"id": "c2", "text": "chunk two", "position": 1},
        ]
        with pytest.raises(RuntimeError) as exc_info:
            await store.add_document_and_chunks(uuid4(), "test.txt", chunks)
        assert "created 0/2 chunks" in str(exc_info.value)


# ─── /stats endpoint ─────────────────────────────────────────────────────────


@pytest.fixture
def stats_client() -> TestClient:
    """Build a TestClient with the graph router and a stubbed _age_graph_instance."""
    import api.routes.graph as graph_route_module
    app = FastAPI()
    app.include_router(graph_route_module.router)
    return TestClient(app)


class TestDocumentGraphStats:
    def test_returns_zeros_when_age_empty(self, stats_client: TestClient) -> None:
        import api.routes.graph as graph_route_module
        stub = MagicMock()
        stub.query.return_value = []
        graph_route_module._age_graph_instance = stub

        resp = stats_client.get(f"/graph/documents/{uuid4()}/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_node_count"] == 0
        assert data["chunk_node_count"] == 0
        assert data["has_entity_edge_count"] == 0
        assert data["entity_count"] == 0
        assert data["distinct_entity_labels"] == []

    def test_returns_real_counts(self, stats_client: TestClient) -> None:
        import api.routes.graph as graph_route_module

        def side_effect(cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
            # Match on the key distinguishing phrase
            if "count(d)" in cypher:
                return [{"cnt": 1}]
            if "count(c)" in cypher:
                return [{"cnt": 3}]
            if "count(DISTINCT e)" in cypher:
                return [{"cnt": 47}]
            if "count(r)" in cypher:
                return [{"cnt": 110}]
            if "labels(e)" in cypher:
                return [{"labels": ["Person"]}, {"labels": ["Company"]}, {"labels": ["Skill"]}]
            return []

        stub = MagicMock()
        stub.query = side_effect
        graph_route_module._age_graph_instance = stub

        resp = stats_client.get(f"/graph/documents/{uuid4()}/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_node_count"] == 1
        assert data["chunk_node_count"] == 3
        assert data["has_entity_edge_count"] == 110
        assert data["entity_count"] == 47
        assert data["distinct_entity_labels"] == ["Company", "Person", "Skill"]

    def test_never_500s_on_query_failure(self, stats_client: TestClient) -> None:
        import api.routes.graph as graph_route_module
        stub = MagicMock()
        stub.query.side_effect = RuntimeError("age down")
        graph_route_module._age_graph_instance = stub

        # Patch create_age_graph to return a working instance for reconnect attempts
        with patch.object(graph_route_module, "create_age_graph", return_value=stub):
            resp = stats_client.get(f"/graph/documents/{uuid4()}/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["document_node_count"] == 0


# ─── _get_age_graph reconnect ────────────────────────────────────────────────


class TestAgeGraphReconnect:
    def test_reconnects_when_stale(self) -> None:
        import api.routes.graph as graph_route_module

        stale = MagicMock()
        stale.query.side_effect = RuntimeError("connection lost")

        fresh = MagicMock()
        fresh.query.return_value = []

        with patch.object(graph_route_module, "create_age_graph", return_value=fresh) as factory:
            graph_route_module._age_graph_instance = stale
            result = graph_route_module._get_age_graph()

        assert result is fresh
        factory.assert_called_once()

    def test_reconnect_logs_info(self, caplog: Any) -> None:
        import api.routes.graph as graph_route_module
        import logging
        caplog.set_level(logging.INFO, logger="api.routes.graph")

        stale = MagicMock()
        stale.query.side_effect = RuntimeError("connection lost")
        fresh = MagicMock()
        fresh.query.return_value = []

        with patch.object(graph_route_module, "create_age_graph", return_value=fresh):
            graph_route_module._age_graph_instance = stale
            graph_route_module._get_age_graph()

        records = [r for r in caplog.records if "Reconnecting stale AGE graph instance" in r.message]
        assert len(records) == 1
