from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

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


@pytest.mark.asyncio
async def test_delete_document_emits_5_cypher_statements(store: GraphStore, age_graph: MagicMock) -> None:
    executed: list[str] = []
    age_graph.query = lambda c, p: executed.append(c) or []

    doc_id = uuid4()
    await store.delete_document(doc_id)

    assert len(executed) == 5


@pytest.mark.asyncio
async def test_delete_document_first_statement_removes_has_entity(store: GraphStore, age_graph: MagicMock) -> None:
    executed: list[str] = []
    age_graph.query = lambda c, p: executed.append(c) or []

    doc_id = uuid4()
    await store.delete_document(doc_id)

    stmt1 = executed[0]
    assert "HAS_ENTITY" in stmt1
    assert "DELETE r" in stmt1
    assert str(doc_id) in stmt1


@pytest.mark.asyncio
async def test_delete_document_second_statement_removes_part_of_and_chunks(store: GraphStore, age_graph: MagicMock) -> None:
    executed: list[str] = []
    age_graph.query = lambda c, p: executed.append(c) or []

    doc_id = uuid4()
    await store.delete_document(doc_id)

    stmt2 = executed[1]
    assert "PART_OF" in stmt2
    assert "DELETE r, c" in stmt2 or "DELETE c, r" in stmt2


@pytest.mark.asyncio
async def test_delete_document_third_statement_removes_document(store: GraphStore, age_graph: MagicMock) -> None:
    executed: list[str] = []
    age_graph.query = lambda c, p: executed.append(c) or []

    doc_id = uuid4()
    await store.delete_document(doc_id)

    stmt3 = executed[2]
    assert "DELETE d" in stmt3
    assert str(doc_id) in stmt3


@pytest.mark.asyncio
async def test_delete_document_orphan_sweep_has_not_exists_subquery(store: GraphStore, age_graph: MagicMock) -> None:
    executed: list[str] = []
    age_graph.query = lambda c, p: executed.append(c) or []

    doc_id = uuid4()
    await store.delete_document(doc_id)

    stmt4 = executed[3]
    assert "NOT EXISTS" in stmt4.upper()
    assert "HAS_ENTITY" in stmt4


@pytest.mark.asyncio
async def test_delete_document_orphan_sweep_excludes_chunk_and_document(store: GraphStore, age_graph: MagicMock) -> None:
    executed: list[str] = []
    age_graph.query = lambda c, p: executed.append(c) or []

    doc_id = uuid4()
    await store.delete_document(doc_id)

    for stmt in [executed[3], executed[4]]:
        assert "NOT e:Chunk" in stmt
        assert "NOT e:Document" in stmt


@pytest.mark.asyncio
async def test_delete_document_shared_entity_survives(store: GraphStore, age_graph: MagicMock) -> None:
    shared_entity_alive = False

    def side_effect(cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        nonlocal shared_entity_alive

        if "NOT EXISTS { MATCH (:Chunk)-[:HAS_ENTITY]->(e) }" in cypher:
            return [] if shared_entity_alive else []
        return []

    age_graph.query = side_effect
    doc_id = uuid4()
    await store.delete_document(doc_id)
