import asyncio
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException

from config import settings
from graph.age_connection import get_age_graph

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["graph"])


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
        age_graph = get_age_graph(settings)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph database unavailable: {exc}")

    doc_id_str = str(document_id)

    try:
        entity_result = await asyncio.to_thread(age_graph.query, f"""
            MATCH (d:Document {{id: '{doc_id_str}'}})<--(c:Chunk)-->(e)
            RETURN DISTINCT id(e) AS internal_id, labels(e) AS labels, e.id AS entity_id
        """, {})

        entity_edge_result = await asyncio.to_thread(age_graph.query, f"""
            MATCH (d:Document {{id: '{doc_id_str}'}})<--(c:Chunk)-->(e)-[r]-(other)
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


async def _safe_count(age_graph: Any, cypher: str) -> int:
    try:
        rows = await asyncio.to_thread(age_graph.query, cypher, {})
        if not rows:
            return 0
        cnt = rows[0].get("cnt", 0)
        return int(cnt) if cnt is not None else 0
    except Exception as exc:
        logger.warning("stats query failed: %s -- %s", exc, cypher[:120])
        return 0


@router.get("/documents/{document_id}/stats")
async def get_document_graph_stats(document_id: UUID) -> dict[str, Any]:
    """Per-document AGE node/edge counts for production debugging."""
    try:
        age_graph = get_age_graph(settings)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Graph database unavailable: {exc}")

    doc_id_str = str(document_id)

    document_count = await _safe_count(age_graph,
        f"MATCH (d:Document {{id: '{doc_id_str}'}}) RETURN count(d) AS cnt"
    )
    chunk_count = await _safe_count(age_graph,
        f"MATCH (d:Document {{id: '{doc_id_str}'}})<--(c:Chunk) RETURN count(c) AS cnt"
    )
    entity_count = await _safe_count(age_graph,
        f"MATCH (d:Document {{id: '{doc_id_str}'}})<--(c:Chunk)-->(e) RETURN count(DISTINCT e) AS cnt"
    )
    has_entity_edges = await _safe_count(age_graph,
        f"MATCH (d:Document {{id: '{doc_id_str}'}})<--(c:Chunk)-->(e) RETURN count(e) AS cnt"
    )

    try:
        label_rows = await asyncio.to_thread(age_graph.query, f"""
            MATCH (d:Document {{id: '{doc_id_str}'}})<--(c:Chunk)-->(e)
            RETURN DISTINCT labels(e) AS labels
        """, {})
        distinct_labels = sorted({
            (row.get("labels") or ["Entity"])[0]
            for row in label_rows or []
            if (row.get("labels") or [None])[0] is not None
        })
    except Exception:
        distinct_labels = []

    return {
        "document_id": doc_id_str,
        "document_node_count": document_count,
        "chunk_node_count": chunk_count,
        "has_entity_edge_count": has_entity_edges,
        "entity_count": entity_count,
        "distinct_entity_labels": distinct_labels,
    }
