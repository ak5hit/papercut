# Phase 6: Persistent Vector Storage & Semantic Retrieval

## Objective

Replace the original in-memory Qdrant vector store with persistent pgvector storage in PostgreSQL. Make semantic retrieval operational end-to-end: chunk embeddings are generated at ingestion time, stored in the database, and queryable via API.

## Context

- **Phase 3** built document/chunk persistence in PostgreSQL and added `embedding_status` and `embedding_id` fields, but neither embeddings nor retrieval are functional.
- **Phase 4** (Extractor Registry) and **Phase 5** (LLM Provider Abstraction) are complete, providing the extraction and LLM pipelines.
- The original codebase (`ingest_and_search.py`, `agent_graph.py`) used Qdrant in-memory with FastEmbed dense + sparse hybrid search. Phase 6 supersedes the vector storage aspect of that code within the new backend architecture.

## Scope

### In Scope

- pgvector extension activation and schema migration
- Dense embedding generation pipeline (local FastEmbed, consistent with original codebase)
- Embedding storage inline on `document_chunks`
- Semantic search retrieval service
- Search API endpoint
- Updating `embedding_status` lifecycle
- Tests for embedding generation, storage, and semantic retrieval

### Out of Scope

- Sparse vector / keyword search (hybrid retrieval comes in Phase 7)
- Background job queues (keep synchronous for simplicity)
- OpenAI embedding provider (FastEmbed only; interface leaves room for future providers)
- Deletion of original `ingest_and_search.py` / `agent_graph.py` (cleanup in Phase 12)

---

## 1. Database Schema Changes

**Migration:** `backend/alembic/versions/002_add_embeddings.py`

### Operations

1. `CREATE EXTENSION IF NOT EXISTS vector;`
2. Add `embedding` column to `document_chunks`:
   ```sql
   ALTER TABLE document_chunks ADD COLUMN embedding vector(384);
   ```
3. Create HNSW index for approximate nearest neighbor search:
   ```sql
   CREATE INDEX ix_document_chunks_embedding_hnsw
   ON document_chunks USING hnsw (embedding vector_cosine_ops);
   ```

### Rationale

- Dimension `384` matches `BAAI/bge-small-en-v1.5` used in the original foundation.
- `embedding_id` (String, added in Phase 3) becomes unused but is left in place to avoid breaking existing data. No code should write to it.
- Cosine distance is the standard metric for BGE sentence embeddings.

### Alembic Migration (reference)

```python
"""add embedding column and pgvector extension

Revision ID: 002
Revises: 001
Create Date: 2026-06-05
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "document_chunks",
        sa.Column("embedding", Vector(384), nullable=True),
    )
    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_embedding_hnsw", table_name="document_chunks")
    op.drop_column("document_chunks", "embedding")
```

---

## 2. Dependencies

Add to `backend/requirements.txt`:

```
fastembed>=0.3.0,<0.5.0
pgvector>=0.2.5
```

**Rationale:** `fastembed` preserves the existing FastEmbed dense model from the original codebase. `pgvector` provides the SQLAlchemy `Vector` type.

---

## 3. Configuration

Add to `backend/config.py` (`Settings` class):

```python
embedding_provider: str = "fastembed"
embedding_model: str = "BAAI/bge-small-en-v1.5"
embedding_dimension: int = 384
```

Update `.env.example`:

```bash
# Embeddings
EMBEDDING_PROVIDER=fastembed
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIMENSION=384
```

---

## 4. New Modules: `backend/embeddings/`

### `backend/embeddings/__init__.py`

```python
from embeddings.base import EmbeddingProvider
from embeddings.factory import create_embedding_provider

__all__ = ["EmbeddingProvider", "create_embedding_provider"]
```

### `backend/embeddings/base.py`

```python
from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        ...
```

### `backend/embeddings/fastembed_provider.py`

```python
from embeddings.base import EmbeddingProvider


class FastEmbedProvider(EmbeddingProvider):
    def __init__(self, model: str = "BAAI/bge-small-en-v1.5") -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return list(self._model.embed(texts))
```

### `backend/embeddings/factory.py`

```python
from config import Settings
from embeddings.base import EmbeddingProvider
from embeddings.fastembed_provider import FastEmbedProvider


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    provider = settings.embedding_provider.lower()
    if provider == "fastembed":
        return FastEmbedProvider(model=settings.embedding_model)
    raise ValueError(f"Unknown embedding provider: {provider}")
```

---

## 5. Model Updates

### `backend/models/document_chunk.py`

Add field:

```python
embedding: list[float] | None = None
```

### `backend/models/db_models.py`

Update `DocumentChunkModel`:

```python
from pgvector.sqlalchemy import Vector

class DocumentChunkModel(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, server_default="{}")
    embedding_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    document: Mapped[DocumentModel] = relationship("DocumentModel", back_populates="chunks")

    def to_model(self) -> DocumentChunk:
        from models.document_chunk import DocumentChunk

        return DocumentChunk(
            id=self.id,
            document_id=self.document_id,
            chunk_index=self.chunk_index,
            text=self.text,
            metadata=self.metadata_,
            embedding_id=self.embedding_id,
            embedding=self.embedding,
            created_at=self.created_at,
        )

    @classmethod
    def from_model(cls, chunk: DocumentChunk) -> DocumentChunkModel:
        return cls(
            id=chunk.id,
            document_id=chunk.document_id,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            metadata_=chunk.metadata,
            embedding_id=chunk.embedding_id,
            embedding=chunk.embedding,
            created_at=chunk.created_at,
        )
```

**Note:** `embedding_id` remains in the table but is no longer the primary retrieval mechanism. The `embedding` vector column is used for semantic search instead.

---

## 6. Storage Layer Updates

### `backend/storage/document_store.py`

Add `ChunkSearchResult` dataclass and new methods:

```python
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.db_models import DocumentChunkModel, DocumentModel
from models.document_chunk import DocumentChunk


@dataclass
class ChunkSearchResult:
    chunk: DocumentChunk
    score: float


class DocumentStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ... existing methods unchanged ...

    async def save_chunk_embeddings(
        self, document_id: UUID, embeddings: list[list[float]]
    ) -> None:
        """Update chunks for a document with their embeddings, matched by chunk_index order."""
        result = await self.session.execute(
            select(DocumentChunkModel)
            .where(DocumentChunkModel.document_id == document_id)
            .order_by(DocumentChunkModel.chunk_index)
        )
        models = result.scalars().all()
        for model, embedding in zip(models, embeddings, strict=True):
            model.embedding = embedding
        await self.session.commit()

    async def semantic_search(
        self, query_embedding: list[float], limit: int = 5
    ) -> list[ChunkSearchResult]:
        """Return top-k most similar chunks using cosine distance."""
        result = await self.session.execute(
            select(
                DocumentChunkModel,
                DocumentChunkModel.embedding.cosine_distance(query_embedding).label("distance"),
            )
            .where(DocumentChunkModel.embedding.is_not(None))
            .order_by("distance")
            .limit(limit)
        )
        rows = result.all()
        return [
            ChunkSearchResult(
                chunk=model.to_model(),
                score=round(1.0 - distance, 4),
            )
            for model, distance in rows
        ]
```

---

## 7. Extractor Integration

### `backend/extractors/generic.py`

Update constructor to accept `embedding_provider`:

```python
from embeddings.base import EmbeddingProvider


class GenericExtractor(Extractor):
    DEFAULT_SIZE_THRESHOLD = 100_000

    def __init__(
        self,
        document_store: DocumentStore,
        llm_provider: LLMProvider | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        size_threshold: int = DEFAULT_SIZE_THRESHOLD,
    ) -> None:
        self.document_store = document_store
        self.llm_provider = llm_provider
        self.embedding_provider = embedding_provider
        self.size_threshold = size_threshold
```

In `extract()`, after `await self.document_store.save_chunks(chunks)`, add:

```python
if self.embedding_provider:
    texts = [chunk.text for chunk in chunks]
    embeddings = self.embedding_provider.embed(texts)
    await self.document_store.save_chunk_embeddings(doc.id, embeddings)
    await self.document_store.update_embedding_status(doc.id, "completed")
else:
    await self.document_store.update_embedding_status(doc.id, "failed")
```

### `backend/extractors/registry.py`

Update `create_default_registry`:

```python
from embeddings.base import EmbeddingProvider


def create_default_registry(
    document_store: DocumentStore,
    llm_provider: LLMProvider | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> ExtractorRegistry:
    return ExtractorRegistry([
        GenericExtractor(document_store, llm_provider, embedding_provider)
    ])
```

---

## 8. API Layer

### `backend/api/routes/documents.py`

Update the upload endpoint to pass the `embedding_provider`:

```python
from embeddings import create_embedding_provider


@router.post("/upload", status_code=201)
async def upload_document(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    content = await file.read()
    store = DocumentStore(session)

    llm_provider = None
    if settings.openai_api_key or settings.llm_provider == "ollama":
        llm_provider = create_llm_provider(settings)

    embedding_provider = create_embedding_provider(settings)

    registry = create_default_registry(store, llm_provider, embedding_provider)
    document_input = DocumentInput(
        content=content,
        filename=file.filename,
        content_type=file.content_type,
    )
    document = await registry.process(document_input)

    return {
        "id": str(document.id),
        "filename": document.metadata.get("filename"),
        "page_count": document.metadata.get("page_count"),
        "extraction_strategy": document.extraction_strategy,
        "embedding_status": document.embedding_status,
        "entities_count": len(document.entities),
        "relationships_count": len(document.relationships),
        "created_at": document.created_at.isoformat(),
    }
```

Add semantic search endpoint:

```python
@router.post("/search/semantic")
async def semantic_search(
    query: str,
    limit: int = 5,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    provider = create_embedding_provider(settings)
    query_embedding = provider.embed([query])[0]

    store = DocumentStore(session)
    results = await store.semantic_search(query_embedding, limit=limit)

    return [
        {
            "chunk_id": str(result.chunk.id),
            "document_id": str(result.chunk.document_id),
            "chunk_index": result.chunk.chunk_index,
            "text": result.chunk.text,
            "score": result.score,
            "metadata": result.chunk.metadata,
        }
        for result in results
    ]
```

---

## 9. Test Plan

### Unit Tests: `tests/test_embeddings.py`

**`TestFastEmbedProvider`**

```python
from unittest.mock import MagicMock, patch

from embeddings.fastembed_provider import FastEmbedProvider


class TestFastEmbedProvider:
    def test_embed_returns_correct_shape(self) -> None:
        with patch("fastembed.TextEmbedding") as mock_te:
            instance = mock_te.return_value
            instance.embed.return_value = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
            provider = FastEmbedProvider()
            result = provider.embed(["text a", "text b"])
            mock_te.assert_called_once_with(model_name="BAAI/bge-small-en-v1.5")
            assert len(result) == 2
            assert len(result[0]) == 3
            assert result[0] == [0.1, 0.2, 0.3]

    def test_embed_empty_list_returns_empty(self) -> None:
        with patch("fastembed.TextEmbedding"):
            provider = FastEmbedProvider()
            result = provider.embed([])
            assert result == []
```

**`TestEmbeddingFactory`**

```python
from config import Settings
from embeddings.factory import create_embedding_provider
from embeddings.fastembed_provider import FastEmbedProvider


class TestEmbeddingFactory:
    def test_creates_fastembed_provider(self) -> None:
        s = Settings(embedding_provider="fastembed", embedding_model="test-model")
        provider = create_embedding_provider(s)
        assert isinstance(provider, FastEmbedProvider)

    def test_raises_on_unknown_provider(self) -> None:
        import pytest
        s = Settings(embedding_provider="unknown")
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            create_embedding_provider(s)

    def test_provider_name_case_insensitive(self) -> None:
        s = Settings(embedding_provider="FASTEMBED")
        provider = create_embedding_provider(s)
        assert isinstance(provider, FastEmbedProvider)
```

### DB Tests: `tests/test_semantic_search.py`

**`TestDocumentStoreEmbeddings`**

```python
from datetime import datetime
from uuid import uuid4

import pytest

from models.canonical_document import CanonicalDocument
from models.document_chunk import DocumentChunk
from storage.document_store import DocumentStore


def _make_vec(*indices: int, dim: int = 384) -> list[float]:
    """Create a 384-dim vector with 1.0 at given indices, 0.0 elsewhere."""
    vec = [0.0] * dim
    for i in indices:
        vec[i] = i + 1.0  # ascending weights for tie-breaking
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

    vec_a = _make_vec(0)       # [1.0, 0, 0, ...]
    vec_b = _make_vec(10)      # [0, ..., 1.0 at pos 10, 0, ...]

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

    # Query vector matches vec_a exactly
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
    await store.save_chunk_embeddings(doc.id, [_make_vec(0)])

    query_vec = _make_vec(0)
    results = await store.semantic_search(query_vec, limit=5)

    assert len(results) == 1
    assert results[0].chunk.text == "With embedding"
```

### Integration Tests: Update `tests/test_generic_extractor.py`

Existing tests must pass `embedding_provider=None` to `GenericExtractor`. Add a new test for the embedding flow:

```python
from unittest.mock import MagicMock

from embeddings.base import EmbeddingProvider


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
```

---

## 10. Files Summary

### Created (7)

| File | Purpose |
|------|---------|
| `backend/embeddings/__init__.py` | Package init, re-exports |
| `backend/embeddings/base.py` | `EmbeddingProvider` ABC |
| `backend/embeddings/fastembed_provider.py` | FastEmbed implementation |
| `backend/embeddings/factory.py` | Provider creation from settings |
| `backend/alembic/versions/002_add_embeddings.py` | pgvector extension, vector column, HNSW index |
| `tests/test_embeddings.py` | Embedding provider + factory tests |
| `tests/test_semantic_search.py` | Vector storage + semantic retrieval tests |

### Modified (10)

| File | Changes |
|------|---------|
| `backend/requirements.txt` | Add `fastembed`, `pgvector` |
| `backend/config.py` | Add `embedding_provider`, `embedding_model`, `embedding_dimension` |
| `backend/models/document_chunk.py` | Add `embedding: list[float] \| None` field |
| `backend/models/db_models.py` | Add `embedding` Vector column; update `to_model`/`from_model` |
| `backend/storage/document_store.py` | Add `save_chunk_embeddings`, `semantic_search`, `ChunkSearchResult` |
| `backend/extractors/generic.py` | Accept `embedding_provider`; generate embeddings post-extraction |
| `backend/extractors/registry.py` | Pass `embedding_provider` through factory |
| `backend/api/routes/documents.py` | Wire `embedding_provider` into upload; add search endpoint |
| `tests/test_generic_extractor.py` | Update constructor calls; add embedding flow test |
| `.env.example` | Add embedding env vars |

---

## 11. Deviation Protocol

Any deviation from the above during implementation must be:

1. Flagged explicitly in the phase review.
2. Documented with the reason for deviation.
3. Reflected in an updated plan document.

No silent deviations are acceptable.

---

## 12. Phase Completion Checklist

Before Phase 7 begins, ALL of the following must pass:

- [ ] `mypy .` — zero errors
- [ ] `ruff check .` — zero issues
- [ ] `pytest -v` — all existing tests pass + new tests pass
- [ ] `docker compose build` — succeeds
- [ ] `docker compose up --build` — app and db start, migrations run
- [ ] Manual smoke test:
  - [ ] Upload a PDF document
  - [ ] `embedding_status` transitions to `"completed"`
  - [ ] `POST /documents/search/semantic` with a relevant query returns chunks ordered by score
  - [ ] `GET /documents/{id}/chunks` does NOT leak raw embedding vectors
- [ ] No import errors or runtime crashes on startup

---

## 13. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| FastEmbed downloads model on first use (~130MB) | Acceptable for demo; document that first upload incurs a one-time download |
| Embedding generation for 1000+ chunks may take seconds | Within acceptable demo latency; do not add background queue complexity in this phase |
| pgvector extension not created in fresh DB | Migration includes `CREATE EXTENSION IF NOT EXISTS vector` |
| `Vector(384)` dimension mismatch if model changes | Document that `EMBEDDING_DIMENSION` must match the model; validate on startup if desired |
