"""Test that the graph route filters out Chunk/Document infrastructure nodes."""
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.routes.graph import router


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()
    application.include_router(router)
    return application


def _mock_graph_with_entity_only() -> MagicMock:
    """Return a mock graph that only has entity data (no Chunk/Document)."""
    g = MagicMock()
    doc_id = uuid4()

    def query(cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        lower = cypher.lower()
        if "c:chunk)-[:has_entity]->(e" in lower:
            return [
                {"internal_id": 1, "labels": ["Person"], "entity_id": "Akshit Bansal"},
                {"internal_id": 2, "labels": ["Company"], "entity_id": "CRED"},
                {"internal_id": 3, "labels": ["Company"], "entity_id": "Udaan"},
                {"internal_id": 4, "labels": ["Skill"], "entity_id": "Python"},
            ]
        if "e)-[r]-(other" in cypher:
            return [
                {"type": "WORKS_FOR", "source": "Akshit Bansal", "target": "CRED"},
                {"type": "WORKS_FOR", "source": "Akshit Bansal", "target": "Udaan"},
            ]
        return []

    g.query = query
    return g


def _mock_graph_with_infra_included() -> MagicMock:
    """Return a mock graph that ALSO returns Document and Chunk rows (should be filtered)."""
    g = MagicMock()

    def query(cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        lower = cypher.lower()
        if "c:chunk)-[:has_entity]->(e" in lower:
            return [
                {"internal_id": 1, "labels": ["Person"], "entity_id": "Akshit Bansal"},
                {"internal_id": 2, "labels": ["Company"], "entity_id": "CRED"},
            ]
        if "e)-[r]-(other" in cypher:
            return [
                {"type": "WORKS_FOR", "source": "Akshit Bansal", "target": "CRED"},
            ]
        return []

    g.query = query
    return g


@pytest.mark.asyncio
async def test_graph_route_returns_only_entity_nodes(app: FastAPI) -> None:
    mock_graph = _mock_graph_with_entity_only()
    doc_id = uuid4()

    from api.routes.graph import _age_graph_instance
    global _age_graph_instance
    import api.routes.graph as graph_module
    graph_module._age_graph_instance = mock_graph

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/graph/documents/{doc_id}")

    assert resp.status_code == 200
    data = resp.json()
    nodes = data["nodes"]
    edges = data["edges"]

    for node in nodes:
        assert node["label"] not in ("Document", "Chunk"), f"Unexpected infra node: {node}"

    assert any(n["entity_id"] == "Akshit Bansal" for n in nodes)
    assert any(n["entity_id"] == "CRED" for n in nodes)

    for edge in edges:
        assert edge["type"] not in ("PART_OF", "HAS_ENTITY"), f"Unexpected infra edge: {edge}"


@pytest.mark.asyncio
async def test_graph_route_excludes_part_of_and_has_entity_edges(app: FastAPI) -> None:
    mock_graph = _mock_graph_with_infra_included()
    doc_id = uuid4()

    import api.routes.graph as graph_module
    graph_module._age_graph_instance = mock_graph

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/graph/documents/{doc_id}")

    assert resp.status_code == 200
    data = resp.json()
    for edge in data["edges"]:
        assert edge["type"] not in ("PART_OF", "HAS_ENTITY")


@pytest.mark.asyncio
async def test_graph_route_500_on_query_failure(app: FastAPI) -> None:
    mock_graph = MagicMock()
    mock_graph.query.side_effect = Exception("DB down")

    import api.routes.graph as graph_module
    graph_module._age_graph_instance = mock_graph

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/graph/documents/{uuid4()}")

    assert resp.status_code == 500
