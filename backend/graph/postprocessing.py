import asyncio
from typing import Any

from config import Settings
from llm.base import LLMProvider

_SKIP_REL_TYPES = {"PART_OF", "HAS_ENTITY"}



class GraphPostProcessor:
    def __init__(self, age_graph: Any, llm_provider: LLMProvider, settings: Settings) -> None:
        self.graph = age_graph
        self.llm = llm_provider
        self.settings = settings

    async def consolidate_labels(self) -> dict[str, int]:
        labels_result = await asyncio.to_thread(
            self.graph.query, "MATCH (n) RETURN DISTINCT labels(n) as labels", {}
        )
        types_result = await asyncio.to_thread(
            self.graph.query, "MATCH ()-[r]-() RETURN DISTINCT type(r) as types", {}
        )

        all_labels: set[str] = set()
        for row in labels_result:
            for label in row.get("labels") or []:
                if label not in ("Chunk", "Document", "__Entity__"):
                    all_labels.add(label)

        all_types: set[str] = set()
        for row in types_result:
            t = row.get("types") or ""
            if t and t not in _SKIP_REL_TYPES:
                all_types.add(t)

        if not all_labels and not all_types:
            return {"labels_consolidated": 0, "types_consolidated": 0}

        prompt = (
            "You are a knowledge graph schema cleaner. Group synonyms.\n"
            f"Node labels: {', '.join(sorted(all_labels))}\n"
            f"Relationship types: {', '.join(sorted(all_types))}\n\n"
            "Return ONLY JSON:\n"
            '{"nodes": {"Canonical": ["synonym1", "synonym2"]}, '
            '"relationships": {"CANONICAL": ["SYNONYM1"]}}\n'
            "Only include groups with more than one member."
        )
        response = await self.llm.complete(prompt, max_tokens=1000)

        try:
            import json_repair
            mapping: Any = json_repair.loads(response)
        except Exception:
            return {"labels_consolidated": 0, "types_consolidated": 0}

        if not isinstance(mapping, dict):
            return {"labels_consolidated": 0, "types_consolidated": 0}

        nodes_merged = 0
        for canonical, synonyms in (mapping.get("nodes") or {}).items():
            for synonym in synonyms:
                if synonym == canonical:
                    continue
                cypher = f"MATCH (n:`{synonym}`) SET n:`{canonical}` REMOVE n:`{synonym}`"
                try:
                    await asyncio.to_thread(self.graph.query, cypher, {})
                    nodes_merged += 1
                except Exception:
                    pass

        rels_merged = 0
        for canonical, synonyms in (mapping.get("relationships") or {}).items():
            for synonym in synonyms:
                if synonym == canonical:
                    continue
                cypher = (
                    f"MATCH (a)-[r:`{synonym}`]->(b) "
                    f"CREATE (a)-[r2:`{canonical}`]->(b) "
                    f"SET r2 = properties(r) DELETE r"
                )
                try:
                    await asyncio.to_thread(self.graph.query, cypher, {})
                    rels_merged += 1
                except Exception:
                    pass

        return {"labels_consolidated": nodes_merged, "types_consolidated": rels_merged}

    async def merge_duplicates(self, threshold: float = 0.95) -> dict[str, int]:
        cypher = """
        MATCH (a), (b)
        WHERE labels(a) = labels(b)
          AND id(a) < id(b)
          AND a.id IS NOT NULL AND b.id IS NOT NULL
          AND (toLower(a.id) CONTAINS toLower(b.id)
               OR toLower(b.id) CONTAINS toLower(a.id))
          AND NOT EXISTS { MATCH (a)-[:PART_OF]->() }
          AND NOT EXISTS { MATCH (b)-[:PART_OF]->() }
        RETURN id(a) as keep_id, id(b) as dup_id
        LIMIT 50
        """
        try:
            pairs = await asyncio.to_thread(self.graph.query, cypher, {})
        except Exception:
            pairs = []

        merged = 0
        for pair in pairs:
            keep_id = pair["keep_id"]
            dup_id = pair["dup_id"]

            # Redirect outgoing edges from dup to keep
            redirect_out = f"""
            MATCH (dup) WHERE id(dup) = {dup_id}
            MATCH (dup)-[r_out]->(target)
            MATCH (keep) WHERE id(keep) = {keep_id}
            CREATE (keep)-[r_new]->(target) SET r_new = properties(r_out)
            DELETE r_out
            """
            try:
                await asyncio.to_thread(self.graph.query, redirect_out, {})
            except Exception:
                pass

            # Redirect incoming edges from dup to keep
            redirect_in = f"""
            MATCH (dup) WHERE id(dup) = {dup_id}
            MATCH (source)-[r_in]->(dup)
            MATCH (keep) WHERE id(keep) = {keep_id}
            CREATE (source)-[r_new]->(keep) SET r_new = properties(r_in)
            DELETE r_in
            """
            try:
                await asyncio.to_thread(self.graph.query, redirect_in, {})
            except Exception:
                pass

            try:
                await asyncio.to_thread(
                    self.graph.query, f"MATCH (dup) WHERE id(dup) = {dup_id} DELETE dup", {}
                )
                merged += 1
            except Exception:
                pass

        return {"pairs_found": len(pairs), "nodes_merged": merged}
