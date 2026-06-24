import io
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfWriter

from extractors.base import DocumentInput
from extractors.generic import GenericExtractor
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


@pytest.mark.asyncio
async def test_generic_small_trace_steps(session):
    store = DocumentStore(session)
    extractor = GenericExtractor(store, size_threshold=10_000_000)

    with patch("extractors.generic.PdfReader", return_value=_mock_reader(["Some text content here."])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="test.pdf")
        doc, trace = await extractor.extract(doc_input)

    assert trace.extractor == "GenericExtractor"
    step_descriptions = [s["step"] for s in trace.steps]
    assert any("Saved document and chunks" in s for s in step_descriptions)
    assert any("Saved to database" in s for s in step_descriptions)


@pytest.mark.asyncio
async def test_generic_small_trace_fields(session):
    store = DocumentStore(session)
    extractor = GenericExtractor(store, size_threshold=10_000_000)

    with patch("extractors.generic.PdfReader", return_value=_mock_reader(["Some text content here."])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="test.pdf")
        doc, trace = await extractor.extract(doc_input)

    fields = trace.extracted_fields
    assert fields.get("page_count") == 1
    assert fields.get("total_characters") > 0
    assert fields.get("total_chunks") > 0


@pytest.mark.asyncio
async def test_generic_large_trace_steps(session):
    store = DocumentStore(session)
    extractor = GenericExtractor(store, size_threshold=0)

    with patch("extractors.generic.PdfReader", return_value=_mock_reader(["Some text."])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="test.pdf")
        doc, trace = await extractor.extract(doc_input)

    step_descriptions = [s["step"] for s in trace.steps]
    assert any("Saved document and chunks" in s for s in step_descriptions)


@pytest.mark.asyncio
async def test_generic_large_trace_fields(session):
    store = DocumentStore(session)
    extractor = GenericExtractor(store, size_threshold=0)

    with patch("extractors.generic.PdfReader", return_value=_mock_reader(["Some text."])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="test.pdf")
        doc, trace = await extractor.extract(doc_input)

    fields = trace.extracted_fields
    assert "page_count" in fields
    assert "total_characters" in fields
    assert "total_chunks" in fields


@pytest.mark.asyncio
async def test_trace_title_mentions_generic(session):
    store = DocumentStore(session)
    extractor = GenericExtractor(store)

    with patch("extractors.generic.PdfReader", return_value=_mock_reader(["Some text."])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="test.pdf")
        doc, trace = await extractor.extract(doc_input)

    assert trace.extractor == "GenericExtractor"
