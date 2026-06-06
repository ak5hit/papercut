from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from evaluation.context_extractor import ContextExtractor
from evaluation.dataset import EvaluationDataset
from evaluation.harness import EvaluationHarness, EvaluationResult


class TestEvaluationDataset:
    def test_valid_dataset(self) -> None:
        ds = EvaluationDataset(
            questions=["Q1", "Q2"],
            ground_truths=["A1", "A2"],
        )
        assert len(ds) == 2

    def test_mismatched_lengths_raises(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            EvaluationDataset(questions=["Q1"], ground_truths=["A1", "A2"])


class TestContextExtractor:
    def test_extracts_chunk_text(self) -> None:
        from query.execution_trace import ExecutionTrace
        from query.result import QueryResult

        result = QueryResult(
            trace=ExecutionTrace(strategy="semantic"),
            chunks=[{"text": "Chunk one text."}, {"text": "Chunk two text."}],
        )
        contexts = ContextExtractor.extract(result)
        assert contexts == ["Chunk one text.", "Chunk two text."]

    def test_extracts_structured_fields(self) -> None:
        from query.execution_trace import ExecutionTrace
        from query.result import QueryResult

        result = QueryResult(
            trace=ExecutionTrace(strategy="structured"),
            documents=[{
                "id": "d1",
                "metadata": {"filename": "inv.pdf"},
                "structured_fields": {"total": 100},
                "entities": [{"name": "AWS", "type": "ORG"}],
                "extraction_strategy": "",
            }],
        )
        contexts = ContextExtractor.extract(result)
        assert any("total=100" in ctx for ctx in contexts)
        assert any("AWS (ORG)" in ctx for ctx in contexts)

    def test_fallback_for_empty_result(self) -> None:
        from query.execution_trace import ExecutionTrace
        from query.result import QueryResult

        result = QueryResult(trace=ExecutionTrace(strategy="structured"))
        contexts = ContextExtractor.extract(result)
        assert contexts == ["No context was retrieved for this query."]


class TestEvaluationHarness:
    @pytest.mark.asyncio
    async def test_evaluate_returns_scores(self) -> None:
        from query.execution_trace import ExecutionTrace
        from query.result import QueryResult

        mock_store = MagicMock()
        mock_llm = AsyncMock()
        mock_embedder = MagicMock()

        harness = EvaluationHarness(mock_store, mock_llm, mock_embedder)

        dataset = EvaluationDataset(
            questions=["What is X?"],
            ground_truths=["X is Y."],
        )

        query_result = QueryResult(
            trace=ExecutionTrace(strategy="semantic"),
            chunks=[{"text": "ctx"}],
        )

        with patch.object(harness.planner, "execute", return_value=query_result):
            with patch.object(
                harness.composer, "compose", return_value=MagicMock(answer="X is Y.")
            ):
                with patch("evaluation.harness.evaluate") as mock_ragas_eval:
                    with patch(
                        "evaluation.harness.asyncio.to_thread",
                        new_callable=AsyncMock,
                    ) as mock_to_thread:
                        import pandas as pd

                        mock_df = pd.DataFrame({
                            "question": ["What is X?"],
                            "answer": ["X is Y."],
                            "ground_truth": ["X is Y."],
                            "faithfulness": [0.85],
                            "context_precision": [0.90],
                        })
                        mock_ragas_result = MagicMock()
                        mock_ragas_result.to_pandas.return_value = mock_df
                        mock_ragas_eval.return_value = mock_ragas_result
                        mock_to_thread.return_value = mock_ragas_result

                        result = await harness.evaluate(dataset)

        assert result.overall_scores["faithfulness"] == 0.85
        assert result.overall_scores["context_precision"] == 0.90
        assert len(result.per_question) == 1
