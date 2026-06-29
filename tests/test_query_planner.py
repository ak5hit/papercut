from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import Settings
from query.classifier import ClassificationResult
from query.execution_trace import ExecutionTrace
from query.planner import QueryPlanner


class TestQueryPlannerRouting:
    @pytest.mark.asyncio
    async def test_routes_to_structured(self):
        store = MagicMock()
        store.session = MagicMock()
        llm = AsyncMock()
        embedder = MagicMock()

        planner = QueryPlanner(store, llm, embedder)

        with patch.object(
            planner.classifier, "classify",
            return_value=ClassificationResult(category="STRUCTURED"),
        ):
            with patch.object(planner.structured, "search", return_value=[{"id": "d1"}]) as mock_struct:
                with patch.object(planner.semantic, "search", return_value=[]) as mock_sem:
                    result = await planner.execute("Total spend?")

        assert result.trace.strategy == "structured"
        assert result.trace.structured_results_count == 1
        mock_struct.assert_awaited_once()
        mock_sem.assert_awaited_once_with("Total spend?", limit=10)

    @pytest.mark.asyncio
    async def test_routes_to_semantic(self):
        store = MagicMock()
        store.session = MagicMock()
        llm = AsyncMock()
        embedder = MagicMock()
        embedder.embed.return_value = [[0.1] * 384]

        planner = QueryPlanner(store, llm, embedder)

        with patch.object(
            planner.classifier, "classify",
            return_value=ClassificationResult(category="SEMANTIC"),
        ):
            with patch.object(planner.semantic, "search", return_value=[{"chunk_id": "c1"}]) as mock_sem:
                result = await planner.execute("Explain termination")

        assert result.trace.strategy == "semantic"
        assert result.trace.semantic_results_count == 1
        mock_sem.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_routes_to_hybrid(self):
        store = MagicMock()
        store.session = MagicMock()
        llm = AsyncMock()
        embedder = MagicMock()

        planner = QueryPlanner(store, llm, embedder)

        with patch.object(
            planner.classifier, "classify",
            return_value=ClassificationResult(category="HYBRID"),
        ):
            with patch.object(
                planner.hybrid, "search",
                return_value=([], [], ExecutionTrace(strategy="hybrid")),
            ) as mock_hyb:
                result = await planner.execute("AWS contracts above 1 lakh")

        assert result.trace.strategy == "hybrid"
        mock_hyb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_routes_structured_with_filters(self):
        store = MagicMock()
        store.session = MagicMock()
        llm = AsyncMock()
        embedder = MagicMock()

        planner = QueryPlanner(store, llm, embedder)

        with patch.object(
            planner.classifier, "classify",
            return_value=ClassificationResult(
                category="STRUCTURED",
                document_type="resume",
                field_filters={"skills": "Python"},
            ),
        ):
            with patch.object(planner.structured, "search", return_value=[{"id": "d1"}]) as mock_struct:
                with patch.object(planner.semantic, "search", return_value=[]):
                    result = await planner.execute("Show me candidates with Python experience")

        assert result.trace.strategy == "structured"
        mock_struct.assert_awaited_once_with(
            field_filters={"document_type": "resume", "skills": "Python"},
            entity_name=None,
        )


def test_query_planner_uses_get_age_graph() -> None:
    """QueryPlanner should use the cached get_age_graph when graph extraction is enabled."""
    settings = Settings(graph_extraction_enabled=True)
    with patch("graph.age_connection.get_age_graph") as mock_get_age:
        mock_age = MagicMock()
        mock_get_age.return_value = mock_age
        planner = QueryPlanner(
            document_store=MagicMock(),
            llm_provider=MagicMock(),
            embedding_provider=MagicMock(),
            settings=settings,
        )
        mock_get_age.assert_called_once_with(settings)
        assert planner.graph is not None
