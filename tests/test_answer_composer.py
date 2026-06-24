from unittest.mock import AsyncMock

import pytest

from answers.composer import AnswerComposer
from query.execution_trace import ExecutionTrace
from query.result import QueryResult


def _chunk(text="test", doc_id="d1"):
    return {"chunk_id": "c1", "document_id": doc_id, "chunk_index": 0, "text": text, "score": 0.5, "metadata": {}}


def _make_llm():
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="final answer")
    return llm


class TestAnswerComposerSemantic:

    @pytest.mark.asyncio
    async def test_compose_semantic_no_chunks(self) -> None:
        llm = _make_llm()
        composer = AnswerComposer(llm)
        result = QueryResult(trace=ExecutionTrace(strategy="semantic"), chunks=[])
        answer = await composer.compose("Q?", result)
        assert "could not find" in answer.answer.lower()

    @pytest.mark.asyncio
    async def test_compose_semantic_with_chunks_uses_llm(self) -> None:
        llm = _make_llm()
        composer = AnswerComposer(llm)
        result = QueryResult(trace=ExecutionTrace(strategy="semantic"), chunks=[_chunk()])
        answer = await composer.compose("Q?", result)
        llm.complete.assert_awaited_once()
        assert answer.answer == "final answer"
        assert "Generated semantic answer via LLM" in answer.trace["steps"]

    @pytest.mark.asyncio
    async def test_compose_semantic_sources(self) -> None:
        llm = _make_llm()
        composer = AnswerComposer(llm)
        result = QueryResult(
            trace=ExecutionTrace(strategy="semantic"),
            chunks=[_chunk(text="hello world", doc_id="doc1"), _chunk(text="goodbye", doc_id="doc2")],
        )
        answer = await composer.compose("Q?", result)
        assert len(answer.sources) == 2

    @pytest.mark.asyncio
    async def test_compose_semantic_includes_all_chunks(self) -> None:
        llm = _make_llm()
        composer = AnswerComposer(llm)
        chunks = [_chunk(text=f"chunk{i}") for i in range(5)]
        result = QueryResult(trace=ExecutionTrace(strategy="semantic"), chunks=chunks)
        await composer.compose("Q?", result)
        prompt: str = llm.complete.call_args[0][0]
        for i in range(5):
            assert f"chunk{i}" in prompt

    @pytest.mark.asyncio
    async def test_semantic_prompt_rules_present(self) -> None:
        llm = _make_llm()
        composer = AnswerComposer(llm)
        result = QueryResult(trace=ExecutionTrace(strategy="semantic"), chunks=[_chunk("text")])
        await composer.compose("Q?", result)
        prompt: str = llm.complete.call_args[0][0]
        assert "ONLY" in prompt


class TestAnswerComposerHybrid:

    @pytest.mark.asyncio
    async def test_hybrid_returns_both_result_sets(self) -> None:
        llm = _make_llm()
        composer = AnswerComposer(llm)
        result = QueryResult(
            trace=ExecutionTrace(strategy="hybrid"),
            documents=[{"id": "d1", "metadata": {"filename": "test.pdf"}, "structured_fields": {}, "entities": [], "extraction_strategy": ""}],
            chunks=[_chunk()],
        )
        answer = await composer.compose("Q?", result)
        assert len(answer.sources) == 1


class TestAnswerComposerDispatch:

    @pytest.mark.asyncio
    async def test_compose_dispatches_by_strategy(self) -> None:
        llm = _make_llm()
        g_llm = _make_llm()
        composer = AnswerComposer(llm)
        g_composer = AnswerComposer(g_llm)

        graph_result = QueryResult(
            trace=ExecutionTrace(strategy="graph"),
            graph_result={"answer": "graph ans", "cypher": "MATCH ...", "context": []},
        )
        semantic_result = QueryResult(
            trace=ExecutionTrace(strategy="semantic"),
            chunks=[_chunk()],
        )

        g_answer = await g_composer.compose("Q?", graph_result)
        sem_answer = await composer.compose("Q?", semantic_result)

        assert "Generated graph answer via Cypher" in g_answer.trace["steps"][-1]
        assert "Generated semantic answer via LLM" in sem_answer.trace["steps"]
        assert g_answer.generated_cypher is not None
