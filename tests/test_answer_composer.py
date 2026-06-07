from unittest.mock import AsyncMock

import pytest

from answers.composer import AnswerComposer
from query.execution_trace import ExecutionTrace
from query.result import QueryResult


_RESUME_FIELDS = {
    "name": "Akshit Bansal",
    "email": "bansalakshit56@gmail.com",
    "phone": "8872800037",
    "skills": ["Python", "Java", "SQL"],
    "experience": [
        {"company": "CRED", "role": "Engineer II", "start_date": "2024-03", "end_date": "Present"},
        {"company": "Udaan", "role": "Full Stack Engineer", "start_date": "2021-01", "end_date": "2022-09"},
    ],
    "education": [
        {"institution": "IIIT Allahabad", "degree": "B.Tech", "field": "IT", "year": "2021"},
    ],
    "document_type": "resume",
    "total_experience_years": 5,
    "linkedin_url": None,
    "summary": "Experienced engineer...",
    "location": "Bangalore",
    "current_role": "Engineer II",
    "urls": [],
}


class TestAnswerComposerStructured:

    @pytest.mark.asyncio
    async def test_compose_structured_single_document_uses_llm(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "8872800037"
        composer = AnswerComposer(llm)
        result = QueryResult(
            trace=ExecutionTrace(strategy="structured"),
            documents=[{
                "id": "doc-1",
                "metadata": {"filename": "resume.pdf"},
                "structured_fields": {"phone": "8872800037", "name": "Akshit"},
                "entities": [],
                "extraction_strategy": "resume",
            }],
        )
        answer = await composer._compose_structured("what is the phone", result)
        assert answer.answer == "8872800037"
        assert len(answer.sources) == 1
        assert answer.sources[0].document_name == "resume.pdf"
        assert "Formatted structured answer" in answer.trace["steps"]
        prompt = llm.complete.call_args[0][0]
        assert "phone" in prompt
        assert "8872800037" in prompt

    @pytest.mark.asyncio
    async def test_compose_structured_multiple_documents(self) -> None:
        llm = AsyncMock()
        composer = AnswerComposer(llm)
        result = QueryResult(
            trace=ExecutionTrace(strategy="structured"),
            documents=[
                {"id": "d1", "metadata": {"filename": "a.pdf"}, "structured_fields": {}, "entities": [], "extraction_strategy": ""},
                {"id": "d2", "metadata": {"filename": "b.pdf"}, "structured_fields": {}, "entities": [], "extraction_strategy": ""},
            ],
        )
        answer = await composer._compose_structured("List them", result)
        assert "Found 2 matching documents" in answer.answer
        assert len(answer.sources) == 2
        llm.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_compose_structured_empty(self) -> None:
        llm = AsyncMock()
        composer = AnswerComposer(llm)
        result = QueryResult(trace=ExecutionTrace(strategy="structured"), documents=[])
        answer = await composer._compose_structured("Total?", result)
        assert answer.answer == "No matching documents found."
        assert answer.sources == []

    @pytest.mark.asyncio
    async def test_compose_structured_phone_only(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "8872800037"
        composer = AnswerComposer(llm)
        result = QueryResult(
            trace=ExecutionTrace(strategy="structured"),
            documents=[{"id": "d1", "metadata": {"filename": "r.pdf"}, "structured_fields": _RESUME_FIELDS, "entities": [], "extraction_strategy": "resume"}],
        )
        answer = await composer._compose_structured("what is akshit phone", result)
        assert answer.answer == "8872800037"
        prompt = llm.complete.call_args[0][0]
        assert "phone" in prompt
        assert "QUESTION" in prompt
        assert "what is akshit phone" in prompt

    @pytest.mark.asyncio
    async def test_compose_structured_email_only(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "bansalakshit56@gmail.com"
        composer = AnswerComposer(llm)
        result = QueryResult(
            trace=ExecutionTrace(strategy="structured"),
            documents=[{"id": "d1", "metadata": {"filename": "r.pdf"}, "structured_fields": _RESUME_FIELDS, "entities": [], "extraction_strategy": "resume"}],
        )
        answer = await composer._compose_structured("what is akshit email", result)
        assert answer.answer == "bansalakshit56@gmail.com"

    @pytest.mark.asyncio
    async def test_compose_structured_skills_only(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "Python, Java, SQL"
        composer = AnswerComposer(llm)
        result = QueryResult(
            trace=ExecutionTrace(strategy="structured"),
            documents=[{"id": "d1", "metadata": {"filename": "r.pdf"}, "structured_fields": _RESUME_FIELDS, "entities": [], "extraction_strategy": "resume"}],
        )
        answer = await composer._compose_structured("what skills does akshit have", result)
        assert "Python" in answer.answer or "Java" in answer.answer

    @pytest.mark.asyncio
    async def test_compose_structured_full_resume(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "Name: Akshit Bansal\nEmail: bansalakshit56@gmail.com\nSkills: Python, Java, SQL"
        composer = AnswerComposer(llm)
        result = QueryResult(
            trace=ExecutionTrace(strategy="structured"),
            documents=[{"id": "d1", "metadata": {"filename": "r.pdf"}, "structured_fields": _RESUME_FIELDS, "entities": [], "extraction_strategy": "resume"}],
        )
        answer = await composer._compose_structured("show full resume", result)
        assert "Akshit" in answer.answer or "bansalakshit" in answer.answer

    @pytest.mark.asyncio
    async def test_compose_structured_field_not_found(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "Passport number not found in the resume."
        composer = AnswerComposer(llm)
        result = QueryResult(
            trace=ExecutionTrace(strategy="structured"),
            documents=[{"id": "d1", "metadata": {"filename": "r.pdf"}, "structured_fields": _RESUME_FIELDS, "entities": [], "extraction_strategy": "resume"}],
        )
        answer = await composer._compose_structured("what is passport number", result)
        assert "not found" in answer.answer.lower()

    @pytest.mark.asyncio
    async def test_structured_prompt_includes_list_completeness(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "ok"
        composer = AnswerComposer(llm)
        result = QueryResult(
            trace=ExecutionTrace(strategy="structured"),
            documents=[{"id": "d1", "metadata": {"filename": "r.pdf"}, "structured_fields": _RESUME_FIELDS, "entities": [], "extraction_strategy": "resume"}],
        )
        await composer._compose_structured("list all responsibilities at CRED", result)
        prompt = llm.complete.call_args[0][0]
        assert "include ALL items" in prompt
        assert "Do not summarize or skip" in prompt
        assert "bullet points" in prompt


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
        assert answer.sources[0].document_name == "contract.pdf"
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
    async def test_semantic_prompt_has_thoroughness_not_conciseness(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "ok"
        composer = AnswerComposer(llm)
        result = QueryResult(
            trace=ExecutionTrace(strategy="semantic"),
            chunks=[{"chunk_id": "c1", "document_id": "d1", "chunk_index": 0, "text": "text", "score": 0.5, "metadata": {}}],
        )
        await composer._compose_semantic("Q?", result)
        prompt = llm.complete.call_args[0][0]
        assert "Be thorough" in prompt
        assert "Do not compress" in prompt
        assert "no more than 3" not in prompt
        assert "Be concise" not in prompt

    @pytest.mark.asyncio
    async def test_semantic_prompt_is_generic(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "ok"
        composer = AnswerComposer(llm)
        result = QueryResult(
            trace=ExecutionTrace(strategy="semantic"),
            chunks=[{"chunk_id": "c1", "document_id": "d1", "chunk_index": 0, "text": "text", "score": 0.5, "metadata": {}}],
        )
        await composer._compose_semantic("Q?", result)
        prompt = llm.complete.call_args[0][0]
        assert "work history" not in prompt.lower()
        assert "role" not in prompt.lower()


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

    @pytest.mark.asyncio
    async def test_hybrid_prompt_includes_list_completeness(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "ok"
        composer = AnswerComposer(llm)
        result = QueryResult(
            trace=ExecutionTrace(strategy="hybrid"),
            documents=[{"id": "d1", "metadata": {"filename": "x"}, "structured_fields": {"items": [1, 2, 3]}, "entities": [], "extraction_strategy": ""}],
            chunks=[],
        )
        await composer._compose_hybrid("list all", result)
        prompt = llm.complete.call_args[0][0]
        assert "include ALL items" in prompt
        assert "bullet points" in prompt

    def test_strip_reasoning_prefix(self) -> None:
        composer = AnswerComposer(AsyncMock())
        result = composer._strip_reasoning(
            "We are asked: find the answer.\n"
            "Let me analyze the data.\n\n"
            "Here is the actual answer.\n"
            "It has two sentences."
        )
        assert "We are asked" not in result
        assert result.startswith("Here is the actual answer.")

    def test_strip_reasoning_no_match(self) -> None:
        composer = AnswerComposer(AsyncMock())
        result = composer._strip_reasoning(
            "Here is a clean answer without reasoning."
        )
        assert result == "Here is a clean answer without reasoning."


class TestAnswerComposerDispatch:

    @pytest.mark.asyncio
    async def test_compose_dispatches_by_strategy(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "semantic ans"
        composer = AnswerComposer(llm)

        structured_result = QueryResult(
            trace=ExecutionTrace(strategy="structured"),
            documents=[{"id": "d1", "metadata": {}, "structured_fields": {"x": 1}, "entities": [], "extraction_strategy": ""}],
        )
        semantic_result = QueryResult(
            trace=ExecutionTrace(strategy="semantic"),
            chunks=[{"chunk_id": "c1", "document_id": "d1", "chunk_index": 0, "text": "t", "score": 0, "metadata": {}}],
        )

        s_answer = await composer.compose("Q?", structured_result)
        sem_answer = await composer.compose("Q?", semantic_result)

        assert "Formatted structured answer" in s_answer.trace["steps"]
        assert "Generated semantic answer via LLM" in sem_answer.trace["steps"]
