import asyncio
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from embeddings.base import EmbeddingProvider
from graph.age_wrapper import AgeGraphWrapper
from graph.llm_bridge import build_langchain_chat


class GraphRetriever:
    def __init__(
        self,
        session: AsyncSession,
        age_graph: Any,
        embedding_provider: EmbeddingProvider,
        llm_provider: Any,
        settings: Settings,
    ) -> None:
        self.session = session
        self.graph = age_graph
        self.embedder = embedding_provider
        self.llm = llm_provider
        self.settings = settings
        self._chain: Any = None

    def _get_age_wrapper(self) -> AgeGraphWrapper:
        if not isinstance(self.graph, AgeGraphWrapper):
            self.graph = AgeGraphWrapper(self.graph)
        return self.graph

    def _get_chain(self) -> Any:
        if self._chain is None:
            from langchain_neo4j.chains.graph_qa.cypher import GraphCypherQAChain

            wrapped = self._get_age_wrapper()
            langchain_llm = build_langchain_chat(self.settings)
            self._chain = GraphCypherQAChain.from_llm(
                cypher_llm=langchain_llm,
                qa_llm=langchain_llm,
                graph=wrapped,
                validate_cypher=True,
                return_intermediate_steps=True,
                top_k=10,
                allow_dangerous_requests=True,
            )
        return self._chain

    async def _resolve_source_documents(self, context: list[Any]) -> list[dict[str, str]]:
        """From raw AGE context rows, extract entity values and look up source documents."""
        entity_ids: set[str] = set()
        for row in context:
            if isinstance(row, dict):
                for v in row.values():
                    if isinstance(v, str) and v.strip():
                        entity_ids.add(v.strip())
            elif isinstance(row, list | tuple):
                for item in row:
                    if isinstance(item, str) and item.strip():
                        entity_ids.add(item.strip())

        if not entity_ids:
            return []

        ids_list = ",".join(f"'{eid}'" for eid in entity_ids)
        query_text = f"""
        MATCH (c:Chunk)-[:HAS_ENTITY]->(e)
        WHERE e.id IN [{ids_list}]
        RETURN DISTINCT c.document_id AS doc_id
        """
        try:
            graph_result = await asyncio.to_thread(self.graph.query, query_text, {})
        except Exception:
            return []

        doc_ids: set[str] = set()
        for row in graph_result or []:
            doc_id = row.get("doc_id")
            if doc_id:
                doc_ids.add(str(doc_id))

        if not doc_ids:
            return []

        placeholders = ",".join(f"'{did}'" for did in doc_ids)
        sql = text(
            f"SELECT id, metadata->>'filename' AS filename FROM documents WHERE id IN ({placeholders})"
        )
        pg_result = await self.session.execute(sql)
        return [
            {"document_id": str(row.id), "document_name": row.filename or "Unknown"}
            for row in pg_result
        ]

    async def graph_query(self, question: str) -> dict[str, Any]:
        """GRAPH mode: GraphCypherQAChain generates Cypher -> validates -> AGE executes -> LLM answers."""
        chain = self._get_chain()
        try:
            result = await asyncio.to_thread(chain.invoke, {"query": question})
        except Exception as exc:
            return {"answer": f"Graph query failed: {exc}", "cypher": "", "context": []}

        answer = result.get("result", "No answer generated")
        cypher = ""
        context = []
        for step in result.get("intermediate_steps", []):
            if "query" in step:
                cypher = step["query"]
            elif "context" in step:
                context = step["context"]

        source_documents = await self._resolve_source_documents(context)

        return {
            "answer": answer,
            "cypher": cypher,
            "context": context,
            "source_documents": source_documents,
        }

    async def enriched_search(self, question: str, limit: int = 5) -> dict[str, Any]:
        """graph_vector mode: vector search on chunks (pgvector) -> expand to entities + relationships (Cypher)."""
        raw_embedding = self.embedder.embed([question])[0]
        emb_str = "[" + ",".join(str(float(v)) for v in raw_embedding) + "]"

        threshold = self.settings.retrieval_min_similarity if self.settings else 0.3
        sql = text(
            f"""
            SELECT id, document_id, text, chunk_index,
                   1 - (embedding <=> '{emb_str}'::vector) AS score
            FROM document_chunks
            WHERE embedding IS NOT NULL
              AND 1 - (embedding <=> '{emb_str}'::vector) >= {threshold}
            ORDER BY embedding <=> '{emb_str}'::vector
            LIMIT {limit}
            """
        )
        result = await self.session.execute(sql)
        chunks: list[dict[str, Any]] = []
        chunk_ids: list[str] = []
        doc_ids: set[str] = set()
        for row in result:
            doc_id = str(row.document_id)
            chunks.append({
                "id": str(row.id),
                "document_id": doc_id,
                "text": row.text,
                "chunk_index": row.chunk_index,
                "score": round(float(row.score), 4),
            })
            chunk_ids.append(str(row.id))
            doc_ids.add(doc_id)

        # Look up document filenames for the unique document IDs
        if doc_ids:
            placeholders = ",".join(f"'{did}'" for did in doc_ids)
            doc_result = await self.session.execute(
                text(
                    f"SELECT id, metadata->>'filename' AS filename FROM documents WHERE id IN ({placeholders})"
                )
            )
            filename_map: dict[str, str] = {
                str(row.id): row.filename for row in doc_result
            }
            for chunk in chunks:
                chunk["filename"] = filename_map.get(chunk["document_id"], "Unknown")

        if not chunk_ids:
            return {"context": "", "chunks": [], "entities": [], "relationships": []}

        id_list = ",".join(f"'{cid}'" for cid in chunk_ids)
        query_text = f"""
        MATCH (c:Chunk)-[:HAS_ENTITY]->(e) WHERE c.id IN [{id_list}]
        RETURN DISTINCT labels(e) AS entity_labels, e.id AS entity_name
        LIMIT 50
        """
        try:
            graph_result = await asyncio.to_thread(self.graph.query, query_text, {})
        except Exception:
            graph_result = []

        entities = []
        relationships = []
        if graph_result:
            seen_ids = set()
            for row in graph_result:
                labels = row.get("entity_labels") or []
                eid = row.get("entity_name") or ""
                if eid not in seen_ids:
                    seen_ids.add(eid)
                    label = labels[0] if labels else "Entity"
                    entities.append({"id": eid, "label": label})

        # Get relationship info for discovered entities
        if entities:
            entity_ids_str = ",".join(f"'{e['id']}'" for e in entities)
            rel_cypher = f"""
            MATCH (a)-[r]-(b)
            WHERE a.id IN [{entity_ids_str}] AND b.id IN [{entity_ids_str}]
            RETURN DISTINCT type(r) AS rel_type, a.id AS source_id, b.id AS target_id
            LIMIT 50
            """
            try:
                rel_result = await asyncio.to_thread(self.graph.query, rel_cypher, {})
                for row in rel_result or []:
                    relationships.append({
                        "source": row.get("source_id", ""),
                        "type": row.get("rel_type", ""),
                        "target": row.get("target_id", ""),
                    })
            except Exception:
                pass

        context = self._build_graph_context(chunks, entities, relationships)
        return {"context": context, "chunks": chunks, "entities": entities, "relationships": relationships}

    def _build_graph_context(self, chunks: list[Any], entities: list[Any], relationships: list[Any]) -> str:
        texts = [c["text"] for c in chunks]
        text_content = "\n----\n".join(texts)

        entity_lines = []
        for e in entities:
            label = e.get("label", "") if isinstance(e, dict) else ""
            eid = e.get("id", "") if isinstance(e, dict) else str(e)
            entity_lines.append(f"{label}:{eid}")

        rel_lines = []
        for r in relationships:
            if isinstance(r, dict):
                rel_lines.append(f"{r.get('source', '')} {r.get('type', '')} {r.get('target', '')}")

        parts = [f"Text Content:\n{text_content}"]
        if entity_lines:
            parts.append("----\nEntities:\n" + "\n".join(entity_lines))
        if rel_lines:
            parts.append("----\nRelationships:\n" + "\n".join(rel_lines))
        return "\n".join(parts)

    async def has_graph_data(self) -> bool:
        try:
            result = await asyncio.to_thread(self.graph.query, "MATCH (n) RETURN count(n) AS total", {})
            return bool(result and result[0]["total"] > 0)
        except Exception:
            return False
