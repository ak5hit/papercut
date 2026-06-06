from datetime import datetime
from uuid import uuid4

import pytest

from models.canonical_document import CanonicalDocument
from models.document_chunk import DocumentChunk
from storage.document_store import DocumentStore


@pytest.mark.asyncio
async def test_save_and_retrieve_document(session):
    store = DocumentStore(session)
    doc = CanonicalDocument.create(
        raw_text="Test document text",
        metadata={"filename": "test.pdf", "page_count": 1},
        extraction_strategy="pdf_basic",
    )
    await store.save_document(doc)

    retrieved = await store.get_document(doc.id)
    assert retrieved is not None
    assert retrieved.id == doc.id
    assert retrieved.raw_text == "Test document text"
    assert retrieved.metadata["filename"] == "test.pdf"


@pytest.mark.asyncio
async def test_list_documents(session):
    store = DocumentStore(session)
    doc = CanonicalDocument.create(
        raw_text="Another test",
        metadata={"filename": "test2.pdf"},
        extraction_strategy="pdf_basic",
    )
    await store.save_document(doc)

    documents = await store.list_documents()
    assert len(documents) >= 1


@pytest.mark.asyncio
async def test_save_and_retrieve_chunks(session):
    store = DocumentStore(session)
    doc = CanonicalDocument.create(
        raw_text="Chunked document",
        metadata={"filename": "chunked.pdf"},
        extraction_strategy="pdf_basic",
    )
    await store.save_document(doc)

    chunks = [
        DocumentChunk(
            id=uuid4(),
            document_id=doc.id,
            chunk_index=0,
            text="First chunk",
            metadata={"page": 0},
            created_at=datetime.utcnow(),
        ),
        DocumentChunk(
            id=uuid4(),
            document_id=doc.id,
            chunk_index=1,
            text="Second chunk",
            metadata={"page": 0},
            created_at=datetime.utcnow(),
        ),
    ]
    await store.save_chunks(chunks)

    retrieved = await store.get_chunks(doc.id)
    assert len(retrieved) == 2
    assert retrieved[0].chunk_index == 0
    assert retrieved[1].chunk_index == 1


@pytest.mark.asyncio
async def test_get_nonexistent_document(session):
    store = DocumentStore(session)
    result = await store.get_document(uuid4())
    assert result is None
