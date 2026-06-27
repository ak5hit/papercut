import asyncio
import logging
import re
from typing import Any
from uuid import UUID

from config import Settings

logger = logging.getLogger(__name__)


def _strip(value: str | None) -> str:
    if not value:
        return ""
    return str(value).strip().replace("`", "")

def _strip_label(value: str | None) -> str:
    """Sanitize a node label for AGE compatibility (no spaces, no special chars)."""
    raw = _strip(value)
    if not raw:
        return raw
    return re.sub(r"[^a-zA-Z0-9_]", "", raw.replace(" ", "_").replace("-", "_"))




class GraphStore:
    def __init__(self, age_graph: Any, settings: Settings) -> None:
        self.graph = age_graph
        self.settings = settings

    async def add_document_and_chunks(
        self,
        document_id: UUID,
        filename: str,
        chunks: list[dict[str, Any]],
    ) -> int:
        cypher = f"CREATE (d:Document {{id: '{document_id}', filename: '{filename}'}})"
        await self._execute(cypher)

        chunks_created = 0
        first_error: str | None = None
        for chunk in chunks:
            chunk_id = chunk["id"]
            text_escaped = chunk["text"].replace("'", "\\'")
            position = chunk.get("position", 0)
            cypher = f"""
            MATCH (d:Document {{id: '{document_id}'}})
            CREATE (c:Chunk {{
                id: '{chunk_id}',
                text: '{text_escaped}',
                position: {position},
                document_id: '{document_id}'
            }})-[:PART_OF]->(d)
            """
            try:
                await self._execute(cypher)
                chunks_created += 1
            except Exception as exc:
                if first_error is None:
                    first_error = str(exc)
                logger.warning(
                    "Chunk CREATE failed for chunk_id=%s text_len=%d: %s",
                    chunk_id, len(chunk["text"]), exc,
                )

        if chunks_created < len(chunks):
            raise RuntimeError(
                f"add_document_and_chunks: created {chunks_created}/{len(chunks)} chunks"
                + (f" (first error: {first_error})" if first_error else "")
            )
        return chunks_created

    async def add_graph_documents(self, graph_documents: list[Any]) -> None:
        """Import graph documents with Python-level dedup.

        Matches Neo4j's baseEntityLabel outcome:
        - Same entity_id across chunks = one node (first label wins)
        - Same (source, type, target) edge = one edge
        """
        seen_nodes: dict[str, str] = {}
        seen_edges: set[tuple[str, str, str]] = set()

        for gd in graph_documents:
            for node in gd.nodes:
                node_id = _strip(node.id)
                node_type = _strip(node.type)
                if node_id and node_type and node_id not in seen_nodes:
                    seen_nodes[node_id] = node_type

            for rel in gd.relationships:
                src_id = _strip(rel.source.id) if rel.source else ""
                tgt_id = _strip(rel.target.id) if rel.target else ""
                rel_type = _strip(rel.type)
                if src_id and tgt_id and rel_type:
                    seen_edges.add((src_id, rel_type, tgt_id))

        for node_id, node_type in seen_nodes.items():
            escaped_id = node_id.replace("'", "\\'")
            safe_type = _strip_label(node_type)
            if safe_type:
                await self._execute(
                    f"MERGE (n:`{safe_type}` {{id: '{escaped_id}'}})"
                )

        for src_id, rel_type, tgt_id in seen_edges:
            escaped_src = src_id.replace("'", "\\'")
            escaped_tgt = tgt_id.replace("'", "\\'")
            cypher = f"""
            MATCH (a {{id: '{escaped_src}'}}), (b {{id: '{escaped_tgt}'}})
            MERGE (a)-[:`{rel_type}`]->(b)
            """
            try:
                await self._execute(cypher)
            except Exception as exc:
                logger.warning("Relationship MERGE failed %s -> %s: %s", escaped_src, escaped_tgt, exc)

    async def link_chunks_to_entities(
        self,
        graph_documents: list[Any],
        chunk_id_map: dict[str, Any],
    ) -> dict[str, Any]:
        success_count = 0
        failure_count = 0
        seen_errors: set[str] = set()
        unique_errors: list[str] = []

        for gd in graph_documents:
            source_ids = gd.source.metadata.get("combined_chunk_ids", [])
            if not source_ids:
                continue
            for node in gd.nodes:
                node_id = _strip(node.id)
                if not node_id:
                    continue
                escaped_id = node_id.replace("'", "\\'")
                for chunk_id in source_ids:
                    cypher = f"""
                    MATCH (c:Chunk {{id: '{chunk_id}'}})
                    MATCH (e {{id: '{escaped_id}'}})
                    MERGE (c)-[:HAS_ENTITY]->(e)
                    """
                    try:
                        await self._execute(cypher)
                        success_count += 1
                    except Exception as exc:
                        failure_count += 1
                        msg = str(exc)
                        if msg not in seen_errors:
                            seen_errors.add(msg)
                            if len(unique_errors) < 5:
                                unique_errors.append(msg)
                            logger.warning(
                                "HAS_ENTITY MERGE failed for chunk=%s entity=%s: %s",
                                chunk_id, escaped_id, msg,
                            )

        return {
            "linked": success_count,
            "failed": failure_count,
            "errors": unique_errors,
        }

    async def delete_document(self, document_id: UUID) -> None:
        """Delete a document and its chunks from AGE. Orphan-safe — shared entities survive."""
        doc_id = str(document_id)
        # 1. Detach this doc's chunks from shared entity nodes
        await self._execute(
            f"MATCH (d:Document {{id: '{doc_id}'}})<-[:PART_OF]-(c:Chunk) "
            f"MATCH (c)-[r:HAS_ENTITY]->() DELETE r"
        )
        # 2. Delete Chunk nodes + PART_OF edges
        await self._execute(
            f"MATCH (c:Chunk)-[r:PART_OF]->(d:Document {{id: '{doc_id}'}}) DELETE r, c"
        )
        # 3. Delete the Document node
        await self._execute(f"MATCH (d:Document {{id: '{doc_id}'}}) DELETE d")
        # 4. Delete edges on now-orphaned entity nodes (shared entities survive — still have HAS_ENTITY)
        await self._execute(
            "MATCH (e) WHERE NOT e:Chunk AND NOT e:Document "
            "AND NOT EXISTS { MATCH (:Chunk)-[:HAS_ENTITY]->(e) } "
            "MATCH (e)-[r]-() DELETE r"
        )
        # 5. Delete the edge-less orphan nodes
        await self._execute(
            "MATCH (e) WHERE NOT e:Chunk AND NOT e:Document "
            "AND NOT EXISTS { MATCH (:Chunk)-[:HAS_ENTITY]->(e) } "
            "AND NOT EXISTS { MATCH (e)-[]-() } DELETE e"
        )

    async def count_nodes(self, document_id: UUID) -> int:
        result = await asyncio.to_thread(
            self.graph.query,
            "MATCH (n) RETURN count(n) AS total",
            {},
        )
        return result[0]["total"] if result else 0

    async def count_edges(self, document_id: UUID) -> int:
        result = await asyncio.to_thread(
            self.graph.query,
            "MATCH ()-[r]->() RETURN count(r) AS total",
            {},
        )
        return result[0]["total"] if result else 0

    async def _execute(self, cypher: str) -> list[Any]:
        return await asyncio.to_thread(self.graph.query, cypher, {})
