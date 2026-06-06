import io
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfWriter

from extractors.base import DocumentInput
from extractors.resume import ResumeExtractor
from embeddings.base import EmbeddingProvider
from llm.base import LLMProvider
from storage.document_store import DocumentStore


def _create_blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _mock_reader(pages_text: list[str]) -> MagicMock:
    reader = MagicMock()
    reader.pages = []
    for text in pages_text:
        page = MagicMock()
        page.extract_text.return_value = text
        reader.pages.append(page)
    return reader


class MockLLMProvider(LLMProvider):
    def __init__(self, response: str = "{}") -> None:
        self.response = response

    async def complete(self, prompt: str, max_tokens: int = 2000) -> str:
        return self.response


@pytest.mark.asyncio
async def test_resume_extractor_populates_trace(session):
    store = DocumentStore(session)
    provider = MockLLMProvider(response='{"name": "John", "skills": [], "experience": [], "education": []}')
    extractor = ResumeExtractor(store, llm_provider=provider)

    page_text = "John Doe\njohn@example.com\n+91-9876543210\nSkills: Python, SQL"
    with patch("extractors.resume.PdfReader", return_value=_mock_reader([page_text])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="resume.pdf", document_type="resume")
        doc, trace = await extractor.extract(doc_input)

    assert trace.extractor == "ResumeExtractor"
    assert len(trace.steps) >= 5
    step_descriptions = [s["step"] for s in trace.steps]
    assert "Saved to database" in step_descriptions


@pytest.mark.asyncio
async def test_trace_contains_extractor_name(session):
    store = DocumentStore(session)
    provider = MockLLMProvider(response='{"name": "Alice", "skills": [], "experience": [], "education": []}')
    extractor = ResumeExtractor(store, llm_provider=provider)

    page_text = "Alice\nalice@example.com"
    with patch("extractors.resume.PdfReader", return_value=_mock_reader([page_text])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="cv.pdf", document_type="resume")
        doc, trace = await extractor.extract(doc_input)

    assert trace.extractor == "ResumeExtractor"


@pytest.mark.asyncio
async def test_trace_contains_deterministic_step(session):
    store = DocumentStore(session)
    provider = MockLLMProvider(response='{"name": "Bob", "skills": [], "experience": [], "education": []}')
    extractor = ResumeExtractor(store, llm_provider=provider)

    page_text = "Bob\nbob@example.com\n+91-9876543210"
    with patch("extractors.resume.PdfReader", return_value=_mock_reader([page_text])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="resume.pdf", document_type="resume")
        doc, trace = await extractor.extract(doc_input)

    step_descriptions = [s["step"] for s in trace.steps]
    assert any("deterministic" in s.lower() for s in step_descriptions)


@pytest.mark.asyncio
async def test_trace_contains_llm_step_when_provider_available(session):
    store = DocumentStore(session)
    provider = MockLLMProvider(response='{"name": "Carol", "skills": [], "experience": [], "education": []}')
    extractor = ResumeExtractor(store, llm_provider=provider)

    page_text = "Carol\ncarol@example.com"
    with patch("extractors.resume.PdfReader", return_value=_mock_reader([page_text])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="resume.pdf", document_type="resume")
        doc, trace = await extractor.extract(doc_input)

    step_descriptions = [s["step"] for s in trace.steps]
    assert any("semantic" in s.lower() for s in step_descriptions)
    assert any("LLM" in s for s in step_descriptions)


@pytest.mark.asyncio
async def test_trace_skip_llm_step_when_no_provider(session):
    store = DocumentStore(session)
    extractor = ResumeExtractor(store, llm_provider=None)

    page_text = "Dave\ndave@example.com"
    with patch("extractors.resume.PdfReader", return_value=_mock_reader([page_text])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="resume.pdf", document_type="resume")
        doc, trace = await extractor.extract(doc_input)

    step_descriptions = [s["step"] for s in trace.steps]
    assert not any("LLM" in s for s in step_descriptions)


@pytest.mark.asyncio
async def test_trace_skip_embedding_step_when_no_provider(session):
    store = DocumentStore(session)
    provider = MockLLMProvider(response='{"name": "Eve", "skills": [], "experience": [], "education": []}')
    extractor = ResumeExtractor(store, llm_provider=provider, embedding_provider=None)

    page_text = "Eve\neve@example.com"
    with patch("extractors.resume.PdfReader", return_value=_mock_reader([page_text])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="resume.pdf", document_type="resume")
        doc, trace = await extractor.extract(doc_input)

    step_descriptions = [s["step"] for s in trace.steps]
    assert not any("embeddings" in s.lower() for s in step_descriptions)


@pytest.mark.asyncio
async def test_trace_extracted_fields_populated(session):
    store = DocumentStore(session)
    provider = MockLLMProvider(response='{"name": "Frank", "skills": ["Python", "Java"], "experience": [{"company": "X"}], "education": [{"institution": "Y"}], "total_experience_years": 5}')
    extractor = ResumeExtractor(store, llm_provider=provider)

    page_text = "Frank\nfrank@example.com\n+91-9876543210\nSkills: Python, Java"
    with patch("extractors.resume.PdfReader", return_value=_mock_reader([page_text])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="resume.pdf", document_type="resume")
        doc, trace = await extractor.extract(doc_input)

    fields = trace.extracted_fields
    assert fields.get("name") == "Frank"
    assert fields.get("email") == "frank@example.com"
    assert fields.get("phone") == "+91-9876543210"
    assert "Python" in fields.get("skills", [])
    assert "Java" in fields.get("skills", [])
    assert fields.get("experience_count") == 1
    assert fields.get("education_count") == 1
    assert fields.get("total_experience_years") == 5
