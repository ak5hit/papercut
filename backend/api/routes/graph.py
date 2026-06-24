import asyncio
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException

from config import settings
from graph.age_connection import create_age_graph

router = APIRouter(prefix="/graph", tags=["graph"])

_age_graph_instance = None


def _get_age_graph():
    global _age_graph_instance
    if _age_graph_instance is None:
        _age_graph_instance = create_age_graph(settings)
    return _age_graph_instance


def _parse_row(row: dict[str, Any]) -> tuple[str, str, str]:
    labels_list = row.get("labels") or []
    label = labels_list[0] if labels_list else "Entity"
    entity_id = str(row.get("entity_id") or "")
    internal_id = str(row.get("internal_id", ""))
    return internal_id, label, entity_id


@router.get("/documents/{document_id}")
async def get_document_graph(document_id: UUID) -> dict[str, Any]:
    """Return entity nodes and entity-to-entity edges for a document's knowledge graph."""
    try:
        age_graph = _get_age_graph()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph database unavailable: {exc}")

    doc_id_str = str(document_id)

    try:
        entity_result = await asyncio.to_thread(age_graph.query, f"""
            MATCH (d:Document {{id: '{doc_id_str}'}})<-[:PART_OF]-(c:Chunk)-[:HAS_ENTITY]->(e)
            RETURN DISTINCT id(e) AS internal_id, labels(e) AS labels, e.id AS entity_id
        """, {})

        entity_edge_result = await asyncio.to_thread(age_graph.query, f"""
            MATCH (d:Document {{id: '{doc_id_str}'}})<-[:PART_OF]-(c:Chunk)-[:HAS_ENTITY]->(e)-[r]-(other)
            WHERE e.id IS NOT NULL AND other.id IS NOT NULL
            RETURN DISTINCT type(r) AS type, e.id AS source, other.id AS target
        """, {})

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph query failed: {exc}")

    nodes: list[dict[str, Any]] = []
    for row in entity_result or []:
        iid, label, eid = _parse_row(row)
        if eid:
            nodes.append({"id": iid, "label": label, "entity_id": eid})

    valid_ids: set[str] = {n["entity_id"] for n in nodes}

    edges: list[dict[str, Any]] = []
    for row in entity_edge_result or []:
        source = str(row.get("source") or "")
        target = str(row.get("target") or "")
        rel_type = str(row.get("type") or "")
        if source and target and source in valid_ids and target in valid_ids:
            edges.append({"source": source, "target": target, "type": rel_type})

    return {"nodes": nodes, "edges": edges}
