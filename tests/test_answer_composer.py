from unittest.mock import AsyncMock

import pytest

from answers.composer import AnswerComposer
from query.execution_trace import ExecutionTrace
from query.result import QueryResult


class TestAnswerComposerStructured:
    def test_compose_structured_single_document(self) -> None:
        llm = AsyncMock()
        composer = AnswerComposer(llm)
        result = QueryResult(
            trace=ExecutionTrace(strategy="structured"),
            documents=[{
                "id": "doc-1",
                "metadata": {"filename": "inv.pdf"},
                "structured_fields": {"total": 1000},
                "entities": [],
                "extraction_strategy": "generic_small",
            }],
        )
        answer = composer._compose_structured("Total?", result)
        assert "total:** 1000" in answer.answer
        assert len(answer.sources) == 1
        assert answer.sources[0].document_name == "inv.pdf"
        assert "Formatted structured answer" in answer.trace["steps"]

    def test_compose_structured_multiple_documents(self) -> None:
        llm = AsyncMock()
        composer = AnswerComposer(llm)
        result = QueryResult(
            trace=ExecutionTrace(strategy="structured"),
            documents=[
                {"id": "d1", "metadata": {"filename": "a.pdf"}, "structured_fields": {}, "entities": [], "extraction_strategy": ""},
                {"id": "d2", "metadata": {"filename": "b.pdf"}, "structured_fields": {}, "entities": [], "extraction_strategy": ""},
            ],
        )
        answer = composer._compose_structured("List them", result)
        assert "Found 2 matching documents" in answer.answer
        assert len(answer.sources) == 2

    def test_compose_structured_empty(self) -> None:
        llm = AsyncMock()
        composer = AnswerComposer(llm)
        result = QueryResult(trace=ExecutionTrace(strategy="structured"), documents=[])
        answer = composer._compose_structured("Total?", result)
        assert answer.answer == "No matching documents found."
        assert answer.sources == []


class TestAnswerComposerSemantic:
    @pytest.mark.asyncio
    async def test_compose_semantic_with_chunks(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "  The answer is 42.  "
        composer = AnswerComposer(llm)
        result = QueryResult(
            trace=ExecutionTrace(strategy="semantic"),
            chunks=[{
                "chunk_id": "c1",
                "document_id": "doc-1",
                "chunk_index": 3,
                "text": "The answer is clearly forty-two according to the contract.",
                "score": 0.95,
                "metadata": {"page": 7, "filename": "contract.pdf"},
            }],
        )
        answer = await composer._compose_semantic("What is the answer?", result)
        assert answer.answer == "The answer is 42."
        assert len(answer.sources) == 1
        assert answer.sources[0].document_id == "doc-1"
        assert answer.sources[0].chunk_index == 3
        assert answer.sources[0].page == 7
        assert "forty-two" in answer.sources[0].excerpt

    @pytest.mark.asyncio
    async def test_compose_semantic_empty_chunks(self) -> None:
        llm = AsyncMock()
        composer = AnswerComposer(llm)
        result = QueryResult(trace=ExecutionTrace(strategy="semantic"), chunks=[])
        answer = await composer._compose_semantic("What?", result)
        assert "could not find" in answer.answer.lower()
        assert answer.sources == []

    @pytest.mark.asyncio
    async def test_compose_semantic_prompt_contains_only_instruction(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "ok"
        composer = AnswerComposer(llm)
        result = QueryResult(
            trace=ExecutionTrace(strategy="semantic"),
            chunks=[{"chunk_id": "c1", "document_id": "d1", "chunk_index": 0, "text": "text", "score": 0.5, "metadata": {}}],
        )
        await composer._compose_semantic("Q?", result)
        prompt = llm.complete.call_args[0][0]
        assert "ONLY the provided document excerpts" in prompt


class TestAnswerComposerHybrid:
    @pytest.mark.asyncio
    async def test_compose_hybrid_combines_contexts(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "Combined answer."
        composer = AnswerComposer(llm)
        result = QueryResult(
            trace=ExecutionTrace(strategy="hybrid"),
            documents=[{
                "id": "doc-1",
                "metadata": {"filename": "inv.pdf"},
                "structured_fields": {"amount": 100},
                "entities": [],
                "extraction_strategy": "",
            }],
            chunks=[{
                "chunk_id": "c1",
                "document_id": "doc-1",
                "chunk_index": 0,
                "text": "Payment terms are net 30.",
                "score": 0.9,
                "metadata": {"page": 2},
            }],
        )
        answer = await composer._compose_hybrid("What are the terms?", result)
        assert answer.answer == "Combined answer."
        assert len(answer.sources) == 1
        prompt = llm.complete.call_args[0][0]
        assert "STRUCTURED DATA" in prompt
        assert "DOCUMENT EXCERPTS" in prompt


class TestAnswerComposerDispatch:
    @pytest.mark.asyncio
    async def test_compose_dispatches_by_strategy(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "semantic ans"
        composer = AnswerComposer(llm)

        structured_result = QueryResult(trace=ExecutionTrace(strategy="structured"), documents=[{"id": "d1", "metadata": {}, "structured_fields": {}, "entities": [], "extraction_strategy": ""}])
        semantic_result = QueryResult(trace=ExecutionTrace(strategy="semantic"), chunks=[{"chunk_id": "c1", "document_id": "d1", "chunk_index": 0, "text": "t", "score": 0, "metadata": {}}])

        s_answer = await composer.compose("Q?", structured_result)
        sem_answer = await composer.compose("Q?", semantic_result)

        assert "Formatted structured answer" in s_answer.trace["steps"]
        assert "Generated semantic answer via LLM" in sem_answer.trace["steps"]
