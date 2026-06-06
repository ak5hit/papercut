# Phase 8: Answer Composer & Explainable Responses

## Objective

Build the `AnswerComposer` that transforms raw `QueryResult` retrieval output into a natural-language answer with verifiable source references. Every response must include the execution trace (from Phase 7) and source citations — no fabricated confidence scores.

## Context

- **Phase 7** built `QueryPlanner` with `QueryClassifier`, three retrievers (`Structured`, `Semantic`, `Hybrid`), and `ExecutionTrace`. The `POST /query` endpoint returns a `QueryResult` containing `trace`, `documents`, and `chunks`.
- **Phase 5** delivered the `LLMProvider` abstraction (`complete(prompt)`).
- **Phase 3** persists `CanonicalDocument` with `metadata` (including `filename`, `page_count`), `structured_fields`, `entities`, and `DocumentChunk` with `chunk_index`, `text`, `metadata`.
- **Phase 8** is the final layer of the backend pipeline. It consumes `QueryResult` and produces a user-facing response.

## Scope

### In Scope

- `AnswerComposer` module with strategy-aware answer generation
- Source reference formatting (document IDs, filenames, chunk indices, page numbers)
- Structured answer formatting (tabular/list for deterministic facts)
- Semantic answer synthesis (LLM-generated narrative from chunks)
- Hybrid answer synthesis (combined structured + semantic)
- Updated `/query` API response shape with `answer`, `sources`, `trace`
- Pydantic response model for API contract
- Tests for answer generation and source formatting

### Out of Scope

- Streaming answers
- Multi-turn conversation history
- Caching answers
- Faithfulness verification (Phase 10)
- UI rendering (Phase 9)

---

## 1. Architecture

```
POST /query
      │
      ▼
┌─────────────┐
│ QueryPlanner│  (Phase 7)
└──────┬──────┘
       │ QueryResult
       ▼
┌──────────────┐
│AnswerComposer│  (Phase 8)
└──────┬───────┘
       │ ComposedAnswer
       ▼
    Response
```

**Separation of concerns:**
- `QueryPlanner` = what to retrieve (Phase 7, unchanged)
- `AnswerComposer` = how to present it (Phase 8, new)
- `POST /query` endpoint wires both together

---

## 2. New Module: `backend/answers/`

### 2.1 `backend/answers/__init__.py`

```python
from answers.composer import AnswerComposer
from answers.models import ComposedAnswer, SourceReference

__all__ = ["AnswerComposer", "ComposedAnswer", "SourceReference"]
```

---

### 2.2 `backend/answers/models.py`

```python
from typing import Any

from pydantic import BaseModel


class SourceReference(BaseModel):
    document_id: str
    document_name: str
    chunk_index: int | None = None
    page: int | None = None
    excerpt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "document_name": self.document_name,
            "chunk_index": self.chunk_index,
            "page": self.page,
            "excerpt": self.excerpt,
        }


class ComposedAnswer(BaseModel):
    answer: str
    sources: list[SourceReference]
    trace: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "sources": [s.to_dict() for s in self.sources],
            "trace": self.trace,
        }
```

**Rationale:** `ComposedAnswer` is a Pydantic model for API validation and documentation. `SourceReference` explicitly does NOT include confidence scores. Trust comes from cited excerpts and document IDs.

---

### 2.3 `backend/answers/composer.py`

```python
from typing import Any

from llm.base import LLMProvider
from query.result import QueryResult

from answers.models import ComposedAnswer, SourceReference


class AnswerComposer:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    async def compose(self, question: str, result: QueryResult) -> ComposedAnswer:
        strategy = result.trace.strategy

        if strategy == "structured":
            return self._compose_structured(question, result)
        if strategy == "semantic":
            return await self._compose_semantic(question, result)
        return await self._compose_hybrid(question, result)

    def _compose_structured(self, question: str, result: QueryResult) -> ComposedAnswer:
        """Structured results are formatted directly — no LLM narrative needed.

        Rationale: Deterministic facts (totals, counts, specific values) should
        be presented exactly as retrieved. An LLM would add latency and risk
        of paraphrasing errors without adding value.
        """
        docs = result.documents
        if not docs:
            answer = "No matching documents found."
        elif len(docs) == 1:
            doc = docs[0]
            fields = doc.get("structured_fields", {})
            lines = [f"**{k}:** {v}" for k, v in fields.items()]
            answer = "\n".join(lines) if lines else "Document found but no structured fields available."
        else:
            lines = [f"- **{doc.get('metadata', {}).get('filename', doc['id'])}**" for doc in docs]
            answer = f"Found {len(docs)} matching documents:\n" + "\n".join(lines)

        sources = [
            SourceReference(
                document_id=doc["id"],
                document_name=doc.get("metadata", {}).get("filename", "Unknown"),
            )
            for doc in docs
        ]

        result.trace.add_step("Formatted structured answer")
        return ComposedAnswer(
            answer=answer,
            sources=sources,
            trace=result.trace.to_dict(),
        )

    async def _compose_semantic(self, question: str, result: QueryResult) -> ComposedAnswer:
        chunks = result.chunks
        if not chunks:
            return ComposedAnswer(
                answer="I could not find relevant text in the documents.",
                sources=[],
                trace=result.trace.to_dict(),
            )

        context = self._build_context(chunks)
        prompt = self._build_semantic_prompt(question, context)
        answer_text = await self._llm.complete(prompt, max_tokens=1500)

        sources = [
            SourceReference(
                document_id=chunk["document_id"],
                document_name=chunk.get("metadata", {}).get("filename", "Unknown"),
                chunk_index=chunk["chunk_index"],
                page=chunk.get("metadata", {}).get("page"),
                excerpt=chunk["text"][:300],
            )
            for chunk in chunks
        ]

        result.trace.add_step("Generated semantic answer via LLM")
        return ComposedAnswer(
            answer=answer_text.strip(),
            sources=sources,
            trace=result.trace.to_dict(),
        )

    async def _compose_hybrid(self, question: str, result: QueryResult) -> ComposedAnswer:
        docs = result.documents
        chunks = result.chunks

        # Build structured context
        structured_context = ""
        if docs:
            structured_lines = []
            for doc in docs[:10]:  # cap to avoid prompt bloat
                filename = doc.get("metadata", {}).get("filename", "Unknown")
                fields = doc.get("structured_fields", {})
                field_str = ", ".join(f"{k}={v}" for k, v in fields.items())
                structured_lines.append(f"Document {filename}: {field_str}")
            structured_context = "\n".join(structured_lines)

        # Build semantic context
        semantic_context = self._build_context(chunks) if chunks else ""

        prompt = self._build_hybrid_prompt(
            question, structured_context, semantic_context
        )
        answer_text = await self._llm.complete(prompt, max_tokens=1500)

        # Deduplicate sources by document_id
        seen: set[str] = set()
        sources: list[SourceReference] = []

        for doc in docs:
            doc_id = doc["id"]
            if doc_id not in seen:
                seen.add(doc_id)
                sources.append(
                    SourceReference(
                        document_id=doc_id,
                        document_name=doc.get("metadata", {}).get("filename", "Unknown"),
                    )
                )

        for chunk in chunks:
            chunk_doc_id = chunk["document_id"]
            if chunk_doc_id not in seen:
                seen.add(chunk_doc_id)
                sources.append(
                    SourceReference(
                        document_id=chunk_doc_id,
                        document_name=chunk.get("metadata", {}).get("filename", "Unknown"),
                        chunk_index=chunk["chunk_index"],
                        page=chunk.get("metadata", {}).get("page"),
                        excerpt=chunk["text"][:300],
                    )
                )

        result.trace.add_step("Generated hybrid answer via LLM")
        return ComposedAnswer(
            answer=answer_text.strip(),
            sources=sources,
            trace=result.trace.to_dict(),
        )

    def _build_context(self, chunks: list[dict[str, Any]]) -> str:
        lines = []
        for i, chunk in enumerate(chunks, 1):
            text = chunk["text"]
            meta = chunk.get("metadata", {})
            page = meta.get("page")
            source = f"[Chunk {chunk['chunk_index']}" + (f", Page {page}]" if page else "]")
            lines.append(f"{source}\n{text}")
        return "\n\n".join(lines)

    def _build_semantic_prompt(self, question: str, context: str) -> str:
        return (
            "You are a precise document intelligence assistant. "
            "Answer the user's question using ONLY the provided document excerpts. "
            "If the answer is not in the excerpts, say 'The documents do not contain enough information to answer this question.'\n\n"
            "DOCUMENT EXCERPTS:\n"
            f"{context}\n\n"
            f"QUESTION: {question}\n\n"
            "Provide a concise, factual answer."
        )

    def _build_hybrid_prompt(
        self, question: str, structured_context: str, semantic_context: str
    ) -> str:
        parts = [
            "You are a precise document intelligence assistant. "
            "Answer the user's question using ONLY the provided structured data and document excerpts. "
            "If the answer is not in the provided data, say 'The documents do not contain enough information to answer this question.'\n\n",
        ]
        if structured_context:
            parts.append(f"STRUCTURED DATA:\n{structured_context}\n\n")
        if semantic_context:
            parts.append(f"DOCUMENT EXCERPTS:\n{semantic_context}\n\n")
        parts.append(f"QUESTION: {question}\n\nProvide a concise, factual answer.")
        return "".join(parts)
```

**Rationale:**
- **Structured** answers skip the LLM entirely. Deterministic facts should not be narrated — that adds latency, cost, and hallucination risk.
- **Semantic** answers use an LLM but constrain it to the retrieved context with an explicit "ONLY" instruction.
- **Hybrid** answers combine both context types and deduplicate sources.
- Context is capped (10 structured docs, chunk text truncated to 300 chars in excerpts) to stay within reasonable prompt sizes.

---

## 3. API Layer Update

### 3.1 Update `backend/api/routes/query.py`

```python
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from answers.composer import AnswerComposer
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
    composer = AnswerComposer(llm_provider)

    result = await planner.execute(question)
    composed = await composer.compose(question, result)

    return composed.to_dict()
```

**Rationale:** The endpoint now returns a `ComposedAnswer` instead of raw `QueryResult`. The `answer` field is the human-readable response; `sources` and `trace` provide evidence and observability.

---

## 4. Response Contract

### POST `/query` — Response Shape

**Structured query:**
```json
{
  "answer": "**total_amount:** 150000\n**currency:** INR",
  "sources": [
    {
      "document_id": "550e8400-e29b-41d4-a716-446655440000",
      "document_name": "invoice_march.pdf",
      "chunk_index": null,
      "page": null,
      "excerpt": ""
    }
  ],
  "trace": {
    "strategy": "structured",
    "steps": [
      "Routed to Structured Search",
      "Retrieved 1 documents",
      "Formatted structured answer"
    ],
    "structured_results_count": 1,
    "semantic_results_count": 0
  }
}
```

**Semantic query:**
```json
{
  "answer": "The termination clause requires 30 days written notice and includes a mutual non-disparagement obligation.",
  "sources": [
    {
      "document_id": "550e8400-e29b-41d4-a716-446655440000",
      "document_name": "contract.pdf",
      "chunk_index": 12,
      "page": 7,
      "excerpt": "Either party may terminate this agreement with thirty (30) days prior written notice..."
    }
  ],
  "trace": {
    "strategy": "semantic",
    "steps": [
      "Routed to Semantic Search",
      "Retrieved 5 chunks",
      "Generated semantic answer via LLM"
    ],
    "structured_results_count": 0,
    "semantic_results_count": 5
  }
}
```

**Hybrid query:**
```json
{
  "answer": "Two AWS contracts have invoices above ₹1 lakh: contract_A.pdf (₹150,000) and contract_B.pdf (₹200,000). Both include standard termination clauses.",
  "sources": [
    {
      "document_id": "...",
      "document_name": "contract_A.pdf",
      "chunk_index": null,
      "page": null,
      "excerpt": ""
    },
    {
      "document_id": "...",
      "document_name": "contract_B.pdf",
      "chunk_index": 8,
      "page": 5,
      "excerpt": "The total invoice amount for AWS services is ₹200,000..."
    }
  ],
  "trace": {
    "strategy": "hybrid",
    "steps": [
      "Running structured pre-filter",
      "Structured pre-filter returned 2 documents",
      "Running semantic search",
      "Semantic search returned 4 chunks",
      "Generated hybrid answer via LLM"
    ],
    "structured_results_count": 2,
    "semantic_results_count": 4
  }
}
```

---

## 5. Test Plan

### 5.1 `tests/test_answer_composer.py`

```python
from unittest.mock import AsyncMock

import pytest

from answers.composer import AnswerComposer
from answers.models import SourceReference
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
        prompt = llm.complete.call_args.kwargs["prompt"]
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
        assert len(answer.sources) == 1  # deduplicated
        prompt = llm.complete.call_args.kwargs["prompt"]
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
```

### 5.2 `tests/test_answer_models.py`

```python
from answers.models import ComposedAnswer, SourceReference


class TestSourceReference:
    def test_to_dict_omits_none_gracefully(self) -> None:
        ref = SourceReference(document_id="id-1", document_name="file.pdf")
        d = ref.to_dict()
        assert d["document_id"] == "id-1"
        assert d["document_name"] == "file.pdf"
        assert d["chunk_index"] is None
        assert d["page"] is None

    def test_excerpt_truncation_not_built_in(self) -> None:
        # Excerpt truncation happens in composer, not the model
        ref = SourceReference(document_id="id", document_name="f", excerpt="a" * 1000)
        assert len(ref.excerpt) == 1000


class TestComposedAnswer:
    def test_to_dict_roundtrip(self) -> None:
        answer = ComposedAnswer(
            answer="Hello",
            sources=[SourceReference(document_id="d1", document_name="a.pdf")],
            trace={"strategy": "test"},
        )
        d = answer.to_dict()
        assert d["answer"] == "Hello"
        assert d["sources"][0]["document_name"] == "a.pdf"
        assert d["trace"]["strategy"] == "test"
```

---

## 6. Files Summary

### Created (3)

| File | Purpose |
|------|---------|
| `backend/answers/__init__.py` | Package init, re-exports |
| `backend/answers/models.py` | `ComposedAnswer` + `SourceReference` Pydantic models |
| `backend/answers/composer.py` | `AnswerComposer` with strategy-aware generation |
| `tests/test_answer_composer.py` | Unit tests for all composition paths |
| `tests/test_answer_models.py` | Model serialization tests |

### Modified (1)

| File | Changes |
|------|---------|
| `backend/api/routes/query.py` | Wire `AnswerComposer` into `/query`; return `ComposedAnswer` |

---

## 7. Deviation Protocol

Any deviation from the above during implementation must be:

1. Flagged explicitly in the phase review.
2. Documented with the reason for deviation.
3. Reflected in an updated plan document.

No silent deviations are acceptable.

---

## 8. Phase Completion Checklist

Before Phase 9 begins, ALL of the following must pass:

- [ ] `mypy .` — zero errors
- [ ] `ruff check .` — zero issues
- [ ] `pytest -v` — all existing tests pass + new tests pass
- [ ] `docker compose build` — succeeds
- [ ] `docker compose up --build` — app and db start, migrations run
- [ ] Manual smoke test:
  - [ ] Upload a PDF with known structured fields
  - [ ] `POST /query` `"What is the total amount?"` → returns formatted structured data + sources + trace
  - [ ] `POST /query` `"Summarize the contract"` → returns synthesized answer with chunk excerpts as sources
  - [ ] `POST /query` `"Show contracts above 1 lakh"` → returns hybrid answer with both structured and semantic sources
  - [ ] Every response contains `answer`, `sources` (with `document_id`, `document_name`), and `trace`
  - [ ] No `confidence` or `score` fields appear in the answer object
- [ ] No import errors or runtime crashes on startup

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| LLM hallucinates despite "ONLY" instruction | Constrain prompt explicitly; safe fallback message; source excerpts included so user can verify |
| Prompt too long for large retrieval results | Cap structured docs to 10 and chunk excerpts to 300 chars; semantic chunks already limited by retriever limit |
| Structured answers for single-value queries look too raw | Present as `**key:** value` — clear, scannable, no LLM latency |
| Source deduplication in hybrid loses chunk-level detail | Deduplicate by document_id but prefer chunk sources (which include excerpt) over bare document sources |
| LLM not configured → /query fails | Endpoint already returns 503 from Phase 7; no change needed |

---

## 10. Design Decisions & Tradeoffs

### Why skip LLM for structured answers?

Deterministic facts should be presented as-is. An LLM adds:
- Latency (~1s external API call)
- Cost (token usage)
- Hallucination risk (paraphrasing numbers incorrectly)

No user benefit justifies these costs for "What is the total?" style queries.

### Why include excerpts in sources?

Trust comes from evidence, not scores. A source reference with a verifiable text excerpt lets the user confirm the answer themselves.

### Why no confidence scores?

The PROJECT_SPEC explicitly forbids fabricated confidence scores. Cosine similarity from pgvector is a distance metric, not a probability. Presenting it as "confidence" would be misleading.

### Why cap context at 10 docs / 300 chars?

Prompt size grows with retrieval results. These caps keep the prompt within a few thousand tokens, ensuring:
- Fast LLM response times
- Low API cost
- No truncation of the answer itself

These values are configurable constants in `composer.py` and can be adjusted without changing the interface.
