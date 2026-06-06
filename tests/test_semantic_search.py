from datetime import datetime
from uuid import uuid4

import pytest

from models.canonical_document import CanonicalDocument
from models.document_chunk import DocumentChunk
from storage.document_store import DocumentStore


def _make_vec(*indices: int, dim: int = 384) -> list[float]:
    vec = [0.0] * dim
    for i in indices:
        vec[i] = i + 1.0
    return vec


@pytest.mark.asyncio
async def test_save_and_retrieve_embeddings(session):
    store = DocumentStore(session)
    doc = CanonicalDocument.create(
        raw_text="Test",
        metadata={"filename": "test.pdf"},
        extraction_strategy="test",
    )
    await store.save_document(doc)

    chunks = [
        DocumentChunk(
            id=uuid4(),
            document_id=doc.id,
            chunk_index=0,
            text="First chunk",
            metadata={},
            created_at=datetime.utcnow(),
        ),
    ]
    await store.save_chunks(chunks)

    embeddings = [[0.5] * 384]
    await store.save_chunk_embeddings(doc.id, embeddings)

    retrieved = await store.get_chunks(doc.id)
    assert retrieved[0].embedding == [0.5] * 384


@pytest.mark.asyncio
async def test_semantic_search_ranking(session):
    store = DocumentStore(session)
    doc = CanonicalDocument.create(
        raw_text="Test",
        metadata={"filename": "test.pdf"},
        extraction_strategy="test",
    )
    await store.save_document(doc)

    vec_a = _make_vec(0)
    vec_b = _make_vec(10)

    chunks = [
        DocumentChunk(
            id=uuid4(),
            document_id=doc.id,
            chunk_index=0,
            text="Chunk A",
            metadata={},
            embedding=vec_a,
            created_at=datetime.utcnow(),
        ),
        DocumentChunk(
            id=uuid4(),
            document_id=doc.id,
            chunk_index=1,
            text="Chunk B",
            metadata={},
            embedding=vec_b,
            created_at=datetime.utcnow(),
        ),
    ]
    await store.save_chunks(chunks)
    await store.save_chunk_embeddings(doc.id, [vec_a, vec_b])

    query_vec = _make_vec(0)
    results = await store.semantic_search(query_vec, limit=5)

    assert len(results) == 2
    assert results[0].chunk.text == "Chunk A"
    assert results[0].score > results[1].score


@pytest.mark.asyncio
async def test_semantic_search_excludes_null_embeddings(session):
    store = DocumentStore(session)
    doc = CanonicalDocument.create(
        raw_text="Test",
        metadata={"filename": "test.pdf"},
        extraction_strategy="test",
    )
    await store.save_document(doc)

    chunk_no_emb = DocumentChunk(
        id=uuid4(),
        document_id=doc.id,
        chunk_index=0,
        text="No embedding",
        metadata={},
        created_at=datetime.utcnow(),
    )
    chunk_with_emb = DocumentChunk(
        id=uuid4(),
        document_id=doc.id,
        chunk_index=1,
        text="With embedding",
        metadata={},
        embedding=_make_vec(0),
        created_at=datetime.utcnow(),
    )
    await store.save_chunks([chunk_no_emb, chunk_with_emb])

    query_vec = _make_vec(0)
    results = await store.semantic_search(query_vec, limit=5)

    assert len(results) == 1
    assert results[0].chunk.text == "With embedding"
