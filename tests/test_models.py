from datetime import datetime
from uuid import uuid4

from models.canonical_document import CanonicalDocument
from models.document_chunk import DocumentChunk


def test_canonical_document_creation():
    doc = CanonicalDocument(
        id=uuid4(),
        metadata={"filename": "test.pdf"},
        raw_text="Hello world",
        extraction_strategy="pdf_basic",
        embedding_status="pending",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    assert doc.raw_text == "Hello world"
    assert doc.structured_fields == {}
    assert doc.entities == []


def test_canonical_document_factory():
    doc = CanonicalDocument.create(
        raw_text="Test text",
        metadata={"filename": "test.pdf"},
        extraction_strategy="pdf_basic",
    )
    assert doc.id is not None
    assert doc.embedding_status == "pending"
    assert doc.created_at is not None


def test_canonical_document_rejects_invalid_status():
    try:
        CanonicalDocument(
            id=uuid4(),
            metadata={},
            raw_text="text",
            extraction_strategy="pdf_basic",
            embedding_status="invalid",  # type: ignore[arg-type]
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        assert False, "Should have raised validation error"
    except Exception:
        pass


def test_document_chunk_creation():
    chunk = DocumentChunk(
        id=uuid4(),
        document_id=uuid4(),
        chunk_index=0,
        text="Chunk text",
        metadata={"page": 0},
        created_at=datetime.utcnow(),
    )
    assert chunk.chunk_index == 0
    assert chunk.embedding_id is None
