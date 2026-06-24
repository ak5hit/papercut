from typing import Any
from unittest.mock import MagicMock

import pytest

from graph.age_wrapper import AgeGraphWrapper
from neo4j_graphrag.schema import format_schema


def _make_mock_age(schema_nodes: list[dict[str, Any]] | None = None) -> MagicMock:
    """Create a mock AGEGraph with a realistic structured schema and optional sample rows."""
    age = MagicMock()

    age.get_schema = "Node properties: ..."
    age.get_structured_schema = {
        "node_props": {
            "Person": [{"property": "id", "type": "STRING"}],
            "Email": [{"property": "id", "type": "STRING"}],
            "Company": [{"property": "id", "type": "STRING"}],
            "Skill": [{"property": "id", "type": "STRING"}],
            "Technology": [{"property": "id", "type": "STRING"}],
            "Chunk": [{"property": "id", "type": "STRING"}],
            "Document": [{"property": "id", "type": "STRING"}],
        },
        "rel_props": {},
        "relationships": [
            {"start": "Person", "type": "HAS_EMAIL", "end": "Email"},
            {"start": "Person", "type": "WORKS_FOR", "end": "Company"},
        ],
        "metadata": {},
    }

    if schema_nodes is not None:
        age.query.return_value = schema_nodes
    else:
        age.query.return_value = []

    age.refresh_schema = MagicMock()
    age.add_graph_documents = MagicMock()

    return age


class TestSchemaEnhancement:
    def test_get_structured_schema_includes_values(self):
        schema_nodes = [
            {"label": ["Person"], "id": "Akshit Bansal"},
            {"label": ["Email"], "id": "bansalakshit56@gmail.com"},
        ]
        age = _make_mock_age(schema_nodes)
        wrapper = AgeGraphWrapper(age)

        result = wrapper.get_structured_schema

        person_props = result["node_props"]["Person"]
        assert person_props[0]["property"] == "id"
        assert person_props[0]["values"] == ["Akshit Bansal"]
        assert person_props[0]["distinct_count"] == 1

        email_props = result["node_props"]["Email"]
        assert email_props[0]["values"] == ["bansalakshit56@gmail.com"]
        assert email_props[0]["distinct_count"] == 1

    def test_labels_with_few_values_show_all(self):
        schema_nodes = [
            {"label": ["Company"], "id": "CRED"},
            {"label": ["Company"], "id": "Udaan"},
            {"label": ["Company"], "id": "Amazon"},
        ]
        age = _make_mock_age(schema_nodes)
        wrapper = AgeGraphWrapper(age)

        result = wrapper.get_structured_schema
        company_props = result["node_props"]["Company"]
        assert set(company_props[0]["values"]) == {"CRED", "Udaan", "Amazon"}
        assert company_props[0]["distinct_count"] == 3

    def test_labels_with_many_values_show_one_example(self):
        schema_nodes = [
            {"label": ["Technology"], "id": f"Tech{i}"}
            for i in range(15)
        ]
        age = _make_mock_age(schema_nodes)
        wrapper = AgeGraphWrapper(age)

        result = wrapper.get_structured_schema
        tech_props = result["node_props"]["Technology"]
        assert tech_props[0]["distinct_count"] == 15
        assert len(tech_props[0]["values"]) == 15

    def test_chunk_and_document_skipped(self):
        schema_nodes = [
            {"label": ["Chunk"], "id": "b17f06a5-3540-4a91-9f28-1c0054f79c0e"},
            {"label": ["Document"], "id": "2de9b02e-9283-4eca-98cf-50b99791d9c6"},
        ]
        age = _make_mock_age(schema_nodes)
        wrapper = AgeGraphWrapper(age)

        result = wrapper.get_structured_schema
        chunk_props = result["node_props"]["Chunk"]
        assert "values" not in chunk_props[0]

        doc_props = result["node_props"]["Document"]
        assert "values" not in doc_props[0]

    def test_query_failure_returns_unenhanced_schema(self):
        age = _make_mock_age()
        age.query.side_effect = Exception("Graph unavailable")
        wrapper = AgeGraphWrapper(age)

        result = wrapper.get_structured_schema
        person_props = result["node_props"]["Person"]
        assert "values" not in person_props[0]

    def test_format_schema_renders_enhanced(self):
        age = _make_mock_age()
        age.query.return_value = [
            {"label": ["Person"], "id": "Akshit Bansal"},
            {"label": ["Email"], "id": "bansalakshit56@gmail.com"},
        ]
        wrapper = AgeGraphWrapper(age)

        structured = wrapper.get_structured_schema
        rendered = format_schema(structured, is_enhanced=True)

        assert "Akshit Bansal" in rendered
        assert "bansalakshit56@gmail.com" in rendered
        assert "Available options:" in rendered

    def test_format_schema_company_values_rendered(self):
        age = _make_mock_age()
        age.query.return_value = [
            {"label": ["Company"], "id": "CRED"},
            {"label": ["Company"], "id": "Udaan"},
        ]
        wrapper = AgeGraphWrapper(age)

        structured = wrapper.get_structured_schema
        rendered = format_schema(structured, is_enhanced=True)

        assert "CRED" in rendered
        assert "Udaan" in rendered
        assert "Available options:" in rendered

    def test_format_schema_many_values_shows_example(self):
        age = _make_mock_age()
        age.query.return_value = [
            {"label": ["Technology"], "id": f"Tech{i}"}
            for i in range(15)
        ]
        wrapper = AgeGraphWrapper(age)

        structured = wrapper.get_structured_schema
        rendered = format_schema(structured, is_enhanced=True)

        assert "Example:" in rendered

    def test_empty_graph_returns_unenhanced(self):
        age = _make_mock_age()
        age.query.return_value = []
        wrapper = AgeGraphWrapper(age)

        result = wrapper.get_structured_schema

        for label in ["Person", "Email", "Company"]:
            props = result["node_props"][label]
            assert "values" not in props[0]

    def test_skipped_labels_not_in_samples(self):
        """Verify that SKIP_SAMPLE_LABELS is respected."""
        from graph.age_wrapper import SKIP_SAMPLE_LABELS

        assert "Chunk" in SKIP_SAMPLE_LABELS
        assert "Document" in SKIP_SAMPLE_LABELS


class TestPlannerFallback:
    @pytest.mark.asyncio
    async def test_falls_back_on_empty_context(self):
        """Planner should fall back to enriched search when Cypher returns empty context."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from query.planner import QueryPlanner

        store = MagicMock()
        store.session = MagicMock()
        llm = AsyncMock()
        embedder = MagicMock()

        planner = QueryPlanner(store, llm, embedder)

        with patch.object(
            planner.classifier, "classify",
            return_value=MagicMock(category="GRAPH"),
        ):
            mock_graph = MagicMock()
            mock_graph.has_graph_data = AsyncMock(return_value=True)
            mock_graph.graph_query = AsyncMock(return_value={
                "cypher": "MATCH ... WHERE p.id = 'akshit'",
                "answer": "I don't know",
                "context": [],
            })
            mock_graph.enriched_search = AsyncMock(return_value={
                "chunks": [{"id": "c1", "text": "email: x@y.com"}],
                "context": "email: x@y.com",
                "entities": [{"id": "Person", "label": "Person"}],
                "relationships": [],
            })
            planner.graph = mock_graph

            result = await planner.execute("What's akshit's email?")

        assert result.trace.strategy == "graph"
        assert len(result.chunks) == 1
        assert mock_graph.enriched_search.awaited_once
        mock_graph.graph_query.assert_awaited_once()
