# Phase 7: Query Planner & Dynamic Retrieval

## Objective

Implement the Query Planner that classifies incoming natural-language questions and routes them to the appropriate retrieval strategy: **Structured**, **Semantic**, or **Hybrid**. Each strategy must return retrieval results along with an **Execution Trace** that records exactly what was done.

## Context

- **Phase 3** built the persistence layer (`DocumentStore`, `CanonicalDocument`, `DocumentChunk`) with `structured_fields`, `entities`, and `metadata` stored as JSONB.
- **Phase 5** delivered the `LLMProvider` abstraction.
- **Phase 6** wired `EmbeddingProvider` and `pgvector`, providing `DocumentStore.semantic_search()`.
- **Phase 8** (Answer Composer) will synthesize final answers from retrieval results. Phase 7 stops at retrieval + trace.

## Scope

### In Scope

- Query classification (Structured / Semantic / Hybrid)
- Structured retrieval against `structured_fields`, `entities`, and `metadata`
- Semantic retrieval via `DocumentStore.semantic_search`
- Hybrid retrieval (structured pre-filter + semantic search)
- Execution trace recording every step
- Unified `/query` API endpoint
- Tests for classification, each retrieval mode, and planner routing

### Out of Scope

- Final answer synthesis / LLM answer generation (Phase 8)
- Source reference formatting (Phase 8)
- Keyword / sparse retrieval (Phase 10 evaluation may revisit)
- Background job processing

---

## 1. Architecture

```
POST /query
      │
      ▼
┌─────────────┐
│  QueryPlanner│
└──────┬──────┘
       │
       ▼
┌──────────────┐
│ QueryClassifier│  ──►  LLM-based classification
└──────┬───────┘
       │
   ┌───┴───┐
   │       │
   ▼       ▼
Structured Semantic  Hybrid
   │       │         │
   ▼       ▼         ▼
StructuredRetriever SemanticRetriever HybridRetriever
   │       │         │
   └───────┴─────────┘
            │
            ▼
     ExecutionTrace
            │
            ▼
      QueryResult
```

---

## 2. New Modules

### 2.1 `backend/query/`

#### `backend/query/__init__.py`

```python
from query.planner import QueryPlanner
from query.result import QueryResult

__all__ = ["QueryPlanner", "QueryResult"]
```

---

#### `backend/query/classifier.py`

```python
from llm.base import LLMProvider


class QueryClassifier:
    _PROMPT = """You are a query routing engine.
Classify the user question into exactly one of: STRUCTURED, SEMANTIC, HYBRID.

Definitions:
- STRUCTURED: Asks for concrete facts that could be answered from structured fields, entities, or metadata (e.g. totals, counts, dates, amounts, specific named values).
- SEMANTIC: Asks for explanation, summary, or meaning that requires reading document text (e.g. "summarize", "explain", "what does it say about").
- HYBRID: Combines a concrete filter with a semantic request (e.g. "Show contracts mentioning AWS with invoices above ₹1 lakh").

Respond with ONLY the single word: STRUCTURED, SEMANTIC, or HYBRID.

Question: {question}
"""

    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    async def classify(self, question: str) -> str:
        prompt = self._PROMPT.format(question=question)
        response = await self._llm.complete(prompt, max_tokens=20)
        cleaned = response.strip().upper()
        if cleaned in ("STRUCTURED", "SEMANTIC", "HYBRID"):
            return cleaned
        return "SEMANTIC"  # safe default
```

**Rationale:** A lightweight LLM prompt is sufficient for classification. The prompt is intentionally minimal. SEMANTIC is the safe fallback because vector search always returns results even when no structured data exists.

---

#### `backend/query/execution_trace.py`

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionTrace:
    strategy: str  # "structured" | "semantic" | "hybrid"
    steps: list[str] = field(default_factory=list)
    structured_results_count: int = 0
    semantic_results_count: int = 0

    def add_step(self, description: str) -> None:
        self.steps.append(description)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "steps": self.steps,
            "structured_results_count": self.structured_results_count,
            "semantic_results_count": self.semantic_results_count,
        }
```

---

#### `backend/query/result.py`

```python
from dataclasses import dataclass
from typing import Any

from query.execution_trace import ExecutionTrace


@dataclass
class QueryResult:
    trace: ExecutionTrace
    documents: list[dict[str, Any]] = field(default_factory=list)
    chunks: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace": self.trace.to_dict(),
            "documents": self.documents,
            "chunks": self.chunks,
        }
```

---

#### `backend/query/structured_retriever.py`

```python
from typing import Any
from uuid import UUID

from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from models.db_models import DocumentModel


class StructuredRetriever:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(
        self,
        field_filters: dict[str, Any] | None = None,
        entity_name: str | None = None,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        stmt = select(DocumentModel)

        if field_filters:
            for key, value in field_filters.items():
                # JSONB containment for nested keys: {"total_amount": 100000}
                if isinstance(value, dict):
                    stmt = stmt.where(
                        DocumentModel.structured_fields.contains(cast(value, JSONB))
                    )
                else:
                    # Top-level key equality via JSONB operator
                    stmt = stmt.where(
                        DocumentModel.structured_fields[key].astext == str(value)
                    )

        if entity_name:
            stmt = stmt.where(
                DocumentModel.entities.contains(
                    cast([{"name": entity_name}], JSONB)
                )
            )

        if entity_type:
            stmt = stmt.where(
                DocumentModel.entities.contains(
                    cast([{"type": entity_type}], JSONB)
                )
            )

        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        rows = result.scalars().all()

        return [
            {
                "id": str(row.id),
                "metadata": row.metadata_,
                "structured_fields": row.structured_fields,
                "entities": row.entities,
                "extraction_strategy": row.extraction_strategy,
            }
            for row in rows
        ]
```

**Rationale:** PostgreSQL JSONB operators provide sufficient structured search for the demo. Containment (`@>`) works for exact matches on nested structures. Text search on JSONB values is acceptable for the current scope. No full SQL parser or query DSL is introduced.

---

#### `backend/query/semantic_retriever.py`

```python
from embeddings.base import EmbeddingProvider
from storage.document_store import DocumentStore


class SemanticRetriever:
    def __init__(
        self,
        document_store: DocumentStore,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.store = document_store
        self.embedder = embedding_provider

    async def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        query_embedding = self.embedder.embed([query])[0]
        results = await self.store.semantic_search(query_embedding, limit=limit)
        return [
            {
                "chunk_id": str(r.chunk.id),
                "document_id": str(r.chunk.document_id),
                "chunk_index": r.chunk.chunk_index,
                "text": r.chunk.text,
                "score": r.score,
                "metadata": r.chunk.metadata,
            }
            for r in results
        ]
```

---

#### `backend/query/hybrid_retriever.py`

```python
from typing import Any

from embeddings.base import EmbeddingProvider
from query.execution_trace import ExecutionTrace
from query.semantic_retriever import SemanticRetriever
from query.structured_retriever import StructuredRetriever
from storage.document_store import DocumentStore


class HybridRetriever:
    def __init__(
        self,
        structured_retriever: StructuredRetriever,
        semantic_retriever: SemanticRetriever,
    ) -> None:
        self.structured = structured_retriever
        self.semantic = semantic_retriever

    async def search(
        self,
        query: str,
        field_filters: dict[str, Any] | None = None,
        entity_name: str | None = None,
        limit: int = 5,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], ExecutionTrace]:
        trace = ExecutionTrace(strategy="hybrid")

        trace.add_step("Running structured pre-filter")
        docs = await self.structured.search(
            field_filters=field_filters,
            entity_name=entity_name,
            limit=50,
        )
        trace.structured_results_count = len(docs)
        trace.add_step(f"Structured pre-filter returned {len(docs)} documents")

        trace.add_step("Running semantic search")
        chunks = await self.semantic.search(query, limit=limit)
        trace.semantic_results_count = len(chunks)
        trace.add_step(f"Semantic search returned {len(chunks)} chunks")

        # Future enhancement: restrict semantic search to doc IDs from structured filter.
        # For this phase, we return both sets and let the consumer intersect if desired.
        return docs, chunks, trace
```

**Rationale:** The hybrid retriever runs both queries independently and returns both result sets. This is simple, observable, and sufficient for the current phase. A future optimization (not in this phase) could push the structured document ID list into the pgvector query as a `WHERE document_id IN (...)` filter.

---

#### `backend/query/planner.py`

```python
from embeddings.base import EmbeddingProvider
from llm.base import LLMProvider
from query.classifier import QueryClassifier
from query.execution_trace import ExecutionTrace
from query.hybrid_retriever import HybridRetriever
from query.result import QueryResult
from query.semantic_retriever import SemanticRetriever
from query.structured_retriever import StructuredRetriever
from storage.document_store import DocumentStore


class QueryPlanner:
    def __init__(
        self,
        document_store: DocumentStore,
        llm_provider: LLMProvider,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.classifier = QueryClassifier(llm_provider)
        self.structured = StructuredRetriever(document_store.session)
        self.semantic = SemanticRetriever(document_store, embedding_provider)
        self.hybrid = HybridRetriever(self.structured, self.semantic)
        self.store = document_store

    async def execute(self, question: str) -> QueryResult:
        category = await self.classifier.classify(question)

        if category == "STRUCTURED":
            trace = ExecutionTrace(strategy="structured")
            trace.add_step("Routed to Structured Search")
            docs = await self.structured.search()
            trace.structured_results_count = len(docs)
            trace.add_step(f"Retrieved {len(docs)} documents")
            return QueryResult(trace=trace, documents=docs)

        if category == "SEMANTIC":
            trace = ExecutionTrace(strategy="semantic")
            trace.add_step("Routed to Semantic Search")
            chunks = await self.semantic.search(question)
            trace.semantic_results_count = len(chunks)
            trace.add_step(f"Retrieved {len(chunks)} chunks")
            return QueryResult(trace=trace, chunks=chunks)

        # HYBRID
        docs, chunks, trace = await self.hybrid.search(question)
        return QueryResult(trace=trace, documents=docs, chunks=chunks)
```

**Note:** `StructuredRetriever` needs access to the same `AsyncSession` as `DocumentStore`. The simplest approach is to accept the session directly, as shown above.

---

## 3. API Layer

### New router: `backend/api/routes/query.py`

```python
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from embeddings import create_embedding_provider
from llm import create_llm_provider
from query.planner import QueryPlanner
from storage.database import get_session
from storage.document_store import DocumentStore

router = APIRouter(prefix="/query", tags=["query"])


@router.post("")
async def query_documents(
    payload: dict[str, Any],
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    question = payload.get("query", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Query is required")

    store = DocumentStore(session)

    llm_provider = None
    if settings.openai_api_key or settings.llm_provider == "ollama":
        llm_provider = create_llm_provider(settings)

    if llm_provider is None:
        raise HTTPException(status_code=503, detail="LLM provider not configured")

    embedding_provider = create_embedding_provider(settings)
    planner = QueryPlanner(store, llm_provider, embedding_provider)
    result = await planner.execute(question)

    return result.to_dict()
```

### Update `backend/main.py`

```python
from api.routes.query import router as query_router

app.include_router(query_router)
```

---

## 4. Storage Layer Tweaks

### `backend/storage/document_store.py`

Add a `session` property (or make the attribute public) so `StructuredRetriever` can share the same session:

```python
class DocumentStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
```

The attribute is already public; no change required.

---

## 5. Test Plan

### `tests/test_query_classifier.py`

```python
from unittest.mock import AsyncMock

import pytest

from query.classifier import QueryClassifier


class TestQueryClassifier:
    @pytest.mark.asyncio
    async def test_classifies_structured(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "STRUCTURED"
        classifier = QueryClassifier(llm)
        result = await classifier.classify("What is the total AWS spend?")
        assert result == "STRUCTURED"

    @pytest.mark.asyncio
    async def test_classifies_semantic(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "SEMANTIC"
        classifier = QueryClassifier(llm)
        result = await classifier.classify("Summarize payment obligations")
        assert result == "SEMANTIC"

    @pytest.mark.asyncio
    async def test_classifies_hybrid(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "HYBRID"
        classifier = QueryClassifier(llm)
        result = await classifier.classify("Show AWS contracts with invoices above 1 lakh")
        assert result == "HYBRID"

    @pytest.mark.asyncio
    async def test_defaults_to_semantic_on_garbage(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "something weird"
        classifier = QueryClassifier(llm)
        result = await classifier.classify("???")
        assert result == "SEMANTIC"
```

### `tests/test_structured_retriever.py`

```python
from datetime import datetime
from uuid import uuid4

import pytest

from models.canonical_document import CanonicalDocument
from models.document_chunk import DocumentChunk
from query.structured_retriever import StructuredRetriever
from storage.document_store import DocumentStore


@pytest.mark.asyncio
async def test_search_by_structured_field(session):
    store = DocumentStore(session)
    retriever = StructuredRetriever(session)

    doc = CanonicalDocument.create(
        raw_text="Invoice data",
        metadata={"filename": "inv.pdf"},
        extraction_strategy="generic_small",
    )
    doc.structured_fields = {"total_amount": 150000, "currency": "INR"}
    await store.save_document(doc)

    results = await retriever.search(field_filters={"total_amount": 150000})
    assert len(results) == 1
    assert results[0]["structured_fields"]["total_amount"] == 150000


@pytest.mark.asyncio
async def test_search_by_entity_name(session):
    store = DocumentStore(session)
    retriever = StructuredRetriever(session)

    doc = CanonicalDocument.create(
        raw_text="AWS contract",
        metadata={"filename": "aws.pdf"},
        extraction_strategy="generic_small",
    )
    doc.entities = [{"name": "Amazon Web Services", "type": "ORGANIZATION", "value": "AWS"}]
    await store.save_document(doc)

    results = await retriever.search(entity_name="Amazon Web Services")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_no_match_returns_empty(session):
    retriever = StructuredRetriever(session)
    results = await retriever.search(field_filters={"nonexistent": "value"})
    assert results == []
```

### `tests/test_hybrid_retriever.py`

```python
from datetime import datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from embeddings.base import EmbeddingProvider
from query.hybrid_retriever import HybridRetriever
from query.semantic_retriever import SemanticRetriever
from query.structured_retriever import StructuredRetriever
from storage.document_store import DocumentStore


@pytest.mark.asyncio
async def test_hybrid_returns_both_result_sets(session):
    structured = MagicMock(spec=StructuredRetriever)
    structured.search.return_value = [{"id": "doc-1", "structured_fields": {}}]

    semantic = MagicMock(spec=SemanticRetriever)
    semantic.search.return_value = [{"chunk_id": "chunk-1", "text": "hello"}]

    hybrid = HybridRetriever(structured, semantic)
    docs, chunks, trace = await hybrid.search("test query")

    assert len(docs) == 1
    assert len(chunks) == 1
    assert trace.strategy == "hybrid"
    assert any("structured" in step.lower() for step in trace.steps)
    assert any("semantic" in step.lower() for step in trace.steps)
```

### `tests/test_query_planner.py`

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from query.planner import QueryPlanner


class TestQueryPlannerRouting:
    @pytest.mark.asyncio
    async def test_routes_to_structured(self):
        store = MagicMock()
        store.session = MagicMock()
        llm = AsyncMock()
        embedder = MagicMock()

        planner = QueryPlanner(store, llm, embedder)

        with patch.object(planner.classifier, "classify", return_value="STRUCTURED"):
            with patch.object(planner.structured, "search", return_value=[{"id": "d1"}]) as mock_struct:
                result = await planner.execute("Total spend?")

        assert result.trace.strategy == "structured"
        assert result.trace.structured_results_count == 1
        mock_struct.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_routes_to_semantic(self):
        store = MagicMock()
        store.session = MagicMock()
        llm = AsyncMock()
        embedder = MagicMock()
        embedder.embed.return_value = [[0.1] * 384]

        planner = QueryPlanner(store, llm, embedder)

        with patch.object(planner.classifier, "classify", return_value="SEMANTIC"):
            with patch.object(planner.semantic, "search", return_value=[{"chunk_id": "c1"}]) as mock_sem:
                result = await planner.execute("Explain termination")

        assert result.trace.strategy == "semantic"
        assert result.trace.semantic_results_count == 1
        mock_sem.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_routes_to_hybrid(self):
        store = MagicMock()
        store.session = MagicMock()
        llm = AsyncMock()
        embedder = MagicMock()

        planner = QueryPlanner(store, llm, embedder)

        with patch.object(planner.classifier, "classify", return_value="HYBRID"):
            with patch.object(planner.hybrid, "search", return_value=([], [], MagicMock())) as mock_hyb:
                result = await planner.execute("AWS contracts above 1 lakh")

        assert result.trace.strategy == "hybrid"
        mock_hyb.assert_awaited_once()
```

---

## 6. Files Summary

### Created (8)

| File | Purpose |
|------|---------|
| `backend/query/__init__.py` | Package init |
| `backend/query/classifier.py` | LLM-based query classification |
| `backend/query/execution_trace.py` | Immutable trace of execution steps |
| `backend/query/result.py` | Unified retrieval result container |
| `backend/query/structured_retriever.py` | JSONB-based structured search |
| `backend/query/semantic_retriever.py` | Thin wrapper around existing semantic search |
| `backend/query/hybrid_retriever.py` | Combines structured + semantic |
| `backend/query/planner.py` | Orchestrates classification + retrieval |
| `backend/api/routes/query.py` | `/query` endpoint |
| `tests/test_query_classifier.py` | Classification behavior |
| `tests/test_structured_retriever.py` | JSONB search against DB |
| `tests/test_hybrid_retriever.py` | Hybrid composition logic |
| `tests/test_query_planner.py` | Routing logic |

### Modified (1)

| File | Changes |
|------|---------|
| `backend/main.py` | Register `query_router` |

---

## 7. Deviation Protocol

Any deviation from the above during implementation must be:

1. Flagged explicitly in the phase review.
2. Documented with the reason for deviation.
3. Reflected in an updated plan document.

No silent deviations are acceptable.

---

## 8. Phase Completion Checklist

Before Phase 8 begins, ALL of the following must pass:

- [ ] `mypy .` — zero errors
- [ ] `ruff check .` — zero issues
- [ ] `pytest -v` — all existing tests pass + new tests pass
- [ ] `docker compose build` — succeeds
- [ ] `docker compose up --build` — app and db start, migrations run
- [ ] Manual smoke test:
  - [ ] Upload a PDF document with known structured fields
  - [ ] `POST /query` with `"What is the total amount?"` → returns `structured` strategy and matching documents
  - [ ] `POST /query` with `"Summarize the contract"` → returns `semantic` strategy and matching chunks
  - [ ] `POST /query` with a hybrid-style question → returns both documents and chunks with trace
  - [ ] Every response contains a non-empty `trace` object with `strategy`, `steps`, and result counts
- [ ] No import errors or runtime crashes on startup

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| LLM classification adds latency (~1s per query) | Acceptable for demo; cache classification results if needed in future |
| JSONB containment is exact-match only | Document limitation; full text search within JSONB can be added later without breaking the interface |
| Hybrid retriever does not intersect results yet | Document that current hybrid returns both sets; intersection filtering is a future optimization |
| QueryClassifier prompt drift | Include explicit "Respond with ONLY..." instruction; safe SEMANTIC fallback |
| No LLM configured → /query fails | Return 503 with clear error message |

---

## 10. Interface Contract

### POST `/query`

**Request:**
```json
{
  "query": "What is the total AWS spend?"
}
```

**Response (Structured):**
```json
{
  "trace": {
    "strategy": "structured",
    "steps": [
      "Routed to Structured Search",
      "Retrieved 2 documents"
    ],
    "structured_results_count": 2,
    "semantic_results_count": 0
  },
  "documents": [
    {
      "id": "...",
      "metadata": {...},
      "structured_fields": {"total_amount": 150000},
      "entities": [...],
      "extraction_strategy": "generic_small"
    }
  ],
  "chunks": []
}
```

**Response (Semantic):**
```json
{
  "trace": {
    "strategy": "semantic",
    "steps": [
      "Routed to Semantic Search",
      "Retrieved 5 chunks"
    ],
    "structured_results_count": 0,
    "semantic_results_count": 5
  },
  "documents": [],
  "chunks": [
    {
      "chunk_id": "...",
      "document_id": "...",
      "chunk_index": 0,
      "text": "...",
      "score": 0.8421,
      "metadata": {}
    }
  ]
}
```

**Response (Hybrid):**
```json
{
  "trace": {
    "strategy": "hybrid",
    "steps": [
      "Running structured pre-filter",
      "Structured pre-filter returned 3 documents",
      "Running semantic search",
      "Semantic search returned 5 chunks"
    ],
    "structured_results_count": 3,
    "semantic_results_count": 5
  },
  "documents": [...],
  "chunks": [...]
}
```

This contract is intentionally simple. Phase 8 will add answer synthesis on top of these results without changing the retrieval layer.
