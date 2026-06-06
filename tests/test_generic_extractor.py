import io
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfWriter

from extractors.base import DocumentInput
from extractors.generic import GenericExtractor
from embeddings.base import EmbeddingProvider
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
async def test_generic_extractor_small_document(session):
    store = DocumentStore(session)
    extractor = GenericExtractor(store, size_threshold=10_000_000)

    with patch("extractors.generic.PdfReader", return_value=_mock_reader(["Some text content here."])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="test.pdf")
        document = await extractor.extract(doc_input)

    assert document.extraction_strategy == "generic_small"
    assert "page_count" in document.structured_fields
    assert "total_characters" in document.structured_fields
    assert "total_chunks" in document.structured_fields
    assert "avg_chunk_size" in document.structured_fields
    assert document.structured_fields["page_count"] == 1
    assert document.structured_fields["total_characters"] > 0
    assert document.structured_fields["total_chunks"] > 0
    assert document.entities == []
    assert document.relationships == []
    assert document.metadata["filename"] == "test.pdf"

    retrieved = await store.get_document(document.id)
    assert retrieved is not None


@pytest.mark.asyncio
async def test_generic_extractor_large_document(session):
    store = DocumentStore(session)
    extractor = GenericExtractor(store, size_threshold=0)

    with patch("extractors.generic.PdfReader", return_value=_mock_reader(["Some text."])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="test.pdf")
        document = await extractor.extract(doc_input)

    assert document.extraction_strategy == "generic_large"
    assert document.structured_fields == {}
    assert document.entities == []
    assert document.relationships == []


@pytest.mark.asyncio
async def test_generic_extractor_creates_chunks(session):
    store = DocumentStore(session)
    extractor = GenericExtractor(store, size_threshold=10_000_000)

    page_text = "This is a test sentence for chunking purposes. " * 200

    with patch("extractors.generic.PdfReader", return_value=_mock_reader([page_text])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="test.pdf")
        document = await extractor.extract(doc_input)

    chunks = await store.get_chunks(document.id)
    assert len(chunks) > 1
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i
        assert chunk.document_id == document.id
        assert len(chunk.text) > 0


@pytest.mark.asyncio
async def test_generic_extractor_metadata(session):
    store = DocumentStore(session)
    extractor = GenericExtractor(store)

    with patch("extractors.generic.PdfReader", return_value=_mock_reader(["Page one text."])):
        pdf_bytes = _create_blank_pdf()
        doc_input = DocumentInput(content=pdf_bytes, filename="report.pdf")
        document = await extractor.extract(doc_input)

    assert document.metadata["filename"] == "report.pdf"
    assert document.metadata["page_count"] == 1
    assert document.metadata["file_size_bytes"] == len(pdf_bytes)


@pytest.mark.asyncio
async def test_generic_extractor_null_byte_sanitization(session):
    store = DocumentStore(session)
    extractor = GenericExtractor(store, size_threshold=10_000_000)

    with patch("extractors.generic.PdfReader", return_value=_mock_reader(["Hello\x00 World\x00"])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="test.pdf")
        document = await extractor.extract(doc_input)

    assert "\x00" not in document.raw_text
    assert "Hello" in document.raw_text
    assert "World" in document.raw_text


@pytest.mark.asyncio
async def test_extractor_triggers_embedding_and_status(session):
    store = DocumentStore(session)
    mock_embedder = MagicMock(spec=EmbeddingProvider)
    mock_embedder.embed.return_value = [[0.1] * 384]

    extractor = GenericExtractor(
        store,
        embedding_provider=mock_embedder,
        size_threshold=10_000_000,
    )

    with patch("extractors.generic.PdfReader", return_value=_mock_reader(["Some text."])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="test.pdf")
        document = await extractor.extract(doc_input)

    assert document.embedding_status == "completed"
    mock_embedder.embed.assert_called_once()
