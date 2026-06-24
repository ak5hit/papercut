import re
from typing import Any

from langchain_neo4j.graphs.graph_store import GraphStore

SKIP_SAMPLE_LABELS = {"Chunk", "Document"}


class AgeGraphWrapper(GraphStore):
    """Wraps AGEGraph to fix Cypher compatibility issues for GraphCypherQAChain.

    Fixes:
    1. RETURN n.property → RETURN n.property AS property (AGEGraph needs AS aliases)
    2. [:TYPE1|TYPE2] pipe syntax → [:TYPE1] (AGE doesn't support pipe operator)
    3. Enhanced schema with sample property values (matches Neo4jGraph enhanced_schema=True)
    """

    _enhanced_schema = True

    def __init__(self, age_graph: Any) -> None:
        self._g = age_graph

    @property
    def get_schema(self) -> str:
        result: str = self._g.get_schema
        return result

    @property
    def get_structured_schema(self) -> dict[str, Any]:
        base = self._g.get_structured_schema
        return self._enrich_with_samples(base)

    def _enrich_with_samples(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Add 'values' and 'distinct_count' to each node property dict.

        Queries the graph for sample node IDs, groups by label, and injects
        them into the structured schema so format_schema() can render them
        as 'Available options: [...]' in the Cypher generation prompt.

        Gracefully degrades on query failure — returns unenhanced schema.
        """
        try:
            rows = self.query(
                "MATCH (n) RETURN labels(n) AS label, n.id AS id LIMIT 200", {}
            )
        except Exception:
            return schema

        by_label: dict[str, list[str]] = {}
        for row in rows:
            labels = row.get("label") or []
            label = labels[0] if labels else None
            node_id = row.get("id")
            if label and label not in SKIP_SAMPLE_LABELS and node_id:
                by_label.setdefault(label, []).append(str(node_id))

        for label in by_label:
            by_label[label] = list(dict.fromkeys(by_label[label]))

        node_props = schema.get("node_props", {})
        for label, props in node_props.items():
            values = by_label.get(label, [])
            if not values:
                continue
            for prop in props:
                if prop.get("property") == "id":
                    prop["values"] = values
                    prop["distinct_count"] = len(values)

        return schema

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        cypher = self._fix_pipe_syntax(cypher)
        cypher = self._fix_return_aliases(cypher)
        result: list[dict[str, Any]] = self._g.query(cypher, params or {})
        return result

    def refresh_schema(self) -> None:
        self._g.refresh_schema()

    def add_graph_documents(self, *args: Any, **kwargs: Any) -> None:
        self._g.add_graph_documents(*args, **kwargs)

    @staticmethod
    def _fix_pipe_syntax(cypher: str) -> str:
        """Replace [:TYPE1|TYPE2] with [:TYPE1]. AGE doesn't support pipe operator."""
        return re.sub(r":(\w+)\|(\w+(?:\|\w+)*)", r":\1", cypher)

    @staticmethod
    def _fix_return_aliases(cypher: str) -> str:
        """Fix RETURN n.property → RETURN n.property AS property.
        Split on commas, add AS only for columns without existing AS."""
        idx = cypher.upper().find("RETURN")
        if idx < 0:
            return cypher

        before = cypher[:idx]
        after = cypher[idx + 6:]

        columns = after.split(",")
        fixed: list[str] = []
        for col in columns:
            col = col.strip()
            if re.search(r"\bAS\b", col, re.IGNORECASE):
                fixed.append(col)
            else:
                m = re.match(r"(\w+)\.(\w+)", col)
                if m:
                    prop = m.group(2)
                    fixed.append(f"{col} AS {prop}")
                else:
                    fixed.append(col)

        return before + "RETURN " + ", ".join(fixed)
