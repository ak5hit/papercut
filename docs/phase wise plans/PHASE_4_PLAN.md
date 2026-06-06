# Phase 4: Extractor Registry & GenericExtractor — Execution Plan

## Objective

Create the Extractor interface, ExtractorRegistry, and GenericExtractor. Documents flow through the registry abstraction instead of being directly ingested. The existing `PDFIngester` logic is absorbed into `GenericExtractor` and removed.

**Deliverable:** Document upload routes through ExtractorRegistry → GenericExtractor → CanonicalDocument.

**Rule:** Do NOT implement Phase 5+ features. No LLM providers, no embeddings, no query planner, no frontend. Only the extractor abstraction and basic metadata extraction.

---

## 1. Design Decisions

### 1.1 No LLM in Phase 4

Phase 5 implements the LLM Provider Abstraction. GenericExtractor in Phase 4 only performs:

- Text extraction (pypdf)
- Text chunking (langchain-text-splitters)
- Basic metadata extraction (page count, file size, text length)
- Structured field population (derived metrics, not LLM-generated)

`entities` and `relationships` remain empty lists. Phase 5 will add LLM-based extraction.

### 1.2 Absorb PDFIngester

GenericExtractor absorbs PDFIngester's text extraction and chunking logic directly. `backend/ingestion/` is removed entirely. This eliminates an unnecessary layer and keeps the extraction pipeline cohesive within the extractor.

### 1.3 DocumentInput Dataclass

A simple, typed dataclass carries raw document data to the extractor interface. This is more extensible than raw parameters and allows future extractors to inspect content type, size, or other attributes without changing the interface signature.

### 1.4 Persistence Responsibility

GenericExtractor receives a `DocumentStore` via constructor injection and handles persistence (same pattern as the removed PDFIngester). The `extract()` method creates, persists, and returns the CanonicalDocument with its chunks. The Extractor interface itself does not mandate persistence — it's an implementation detail of GenericExtractor.

### 1.5 Size Threshold

GenericExtractor classifies documents as "small" or "large" based on extracted text length:

- **Small** (< 100,000 chars): `extraction_strategy = "generic_small"`, full structured_fields populated
- **Large** (>= 100,000 chars): `extraction_strategy = "generic_large"`, lightweight metadata only

The sample PDF produces 467,148 chars — classified as "large". The threshold is configurable via constructor parameter.

### 1.6 Registry Default Instance

A factory function `create_default_registry(document_store)` returns a registry pre-loaded with GenericExtractor. The upload route calls this factory. Test code can construct custom registries with mock extractors.

---

## 2. Target File Structure (Phase 4 Only)

Files to create:

```
multi-agent-intelligence/
├── backend/
│   └── extractors/
│       ├── __init__.py                  # Exports + create_default_registry()
│       ├── base.py                      # Extractor ABC + DocumentInput dataclass
│       ├── registry.py                  # ExtractorRegistry
│       └── generic.py                   # GenericExtractor
├── tests/
│   ├── test_extractor_registry.py       # Registry selection + fallback tests
│   └── test_generic_extractor.py        # GenericExtractor extraction tests
└── docs/
    └── PHASE_4_PLAN.md                  # (this file)
```

Files to modify:

| File | Change |
|------|--------|
| `backend/api/routes/documents.py` | Use ExtractorRegistry instead of PDFIngester |

Files to delete:

| File | Reason |
|------|--------|
| `backend/ingestion/pdf_ingester.py` | Logic absorbed into GenericExtractor |
| `backend/ingestion/__init__.py` | Empty package, no longer needed |
| `tests/test_ingestion.py` | Replaced by `test_generic_extractor.py` |

Files to NOT create (reserved for future phases):

- `backend/llm/` — Phase 5
- `backend/query/` — Phase 7
- `backend/evaluation/` — Phase 10
- `frontend/` — Phase 9
- Specialized extractors (Invoice, Contract, etc.) — future phases

Files to NOT modify:

- `ingest_and_search.py` — kept as legacy reference
- `agent_graph.py` — untouched
- `eval_pipeline.py` — untouched
- Root `requirements.txt` — untouched
- `backend/requirements.txt` — no new dependencies needed
- `backend/models/` — CanonicalDocument and DocumentChunk unchanged
- `backend/storage/` — DocumentStore and database unchanged
- `backend/alembic/` — no schema changes
- `backend/Dockerfile` — unchanged
- `docker-compose.yml` — unchanged

---

## 3. Schema Design

### 3.1 DocumentInput (Dataclass)

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentInput:
    content: bytes
    filename: str
    content_type: str | None = None
```

**Key decisions:**
- `frozen=True` — immutable; extractors should not modify input
- `content` — raw file bytes (same as `UploadFile.read()`)
- `filename` — original filename (used for extension-based matching)
- `content_type` — optional MIME type (available from `UploadFile.content_type`)
- No database IDs or timestamps — this is raw input, not a persisted entity

### 3.2 Extractor (Abstract Base Class)

```python
from abc import ABC, abstractmethod

from extractors.base import DocumentInput
from models.canonical_document import CanonicalDocument


class Extractor(ABC):
    @abstractmethod
    def supports(self, document: DocumentInput) -> float:
        ...

    @abstractmethod
    async def extract(self, document: DocumentInput) -> CanonicalDocument:
        ...
```

**Key decisions:**
- ABC (not Protocol) — explicit inheritance, matches codebase style
- `supports()` is synchronous — should be fast (filename/size checks, not full parsing)
- `extract()` is async — may involve I/O (database persistence)
- Returns `CanonicalDocument` — the universal output type
- No type parameters or generics — keeps it simple

### 3.3 ExtractorRegistry

```python
from extractors.base import DocumentInput, Extractor
from models.canonical_document import CanonicalDocument


class ExtractorRegistry:
    def __init__(self, extractors: list[Extractor]) -> None:
        self._extractors = extractors

    def select(self, document: DocumentInput) -> Extractor:
        best_extractor: Extractor | None = None
        best_score = 0.0

        for extractor in self._extractors:
            score = extractor.supports(document)
            if score > best_score:
                best_score = score
                best_extractor = extractor

        if best_extractor is None or best_score == 0.0:
            raise ValueError("No extractor available for this document type")

        return best_extractor

    async def process(self, document: DocumentInput) -> CanonicalDocument:
        extractor = self.select(document)
        return await extractor.extract(document)
```

**Key decisions:**
- `select()` is public — allows testing and inspection of routing decisions
- `process()` is the main entry point — selects and extracts in one call
- Raises `ValueError` if no extractor scores above 0.0 — fail-fast
- No logging framework — premature per AGENTS.md
- No caching or memoization — premature

### 3.4 GenericExtractor

```python
import os
import tempfile
from datetime import datetime
from typing import Any
from uuid import uuid4

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from extractors.base import DocumentInput, Extractor
from models.canonical_document import CanonicalDocument
from models.document_chunk import DocumentChunk
from storage.document_store import DocumentStore


class GenericExtractor(Extractor):
    DEFAULT_SIZE_THRESHOLD = 100_000

    def __init__(
        self,
        document_store: DocumentStore,
        size_threshold: int = DEFAULT_SIZE_THRESHOLD,
    ) -> None:
        self.document_store = document_store
        self.size_threshold = size_threshold

    def supports(self, document: DocumentInput) -> float:
        if document.filename.lower().endswith(".pdf"):
            return 0.1
        return 0.0

    async def extract(self, document: DocumentInput) -> CanonicalDocument:
        text, page_metadata = self._extract_text(document.content)
        is_small = len(text) < self.size_threshold

        metadata = self._build_metadata(document, page_metadata)
        strategy = "generic_small" if is_small else "generic_large"

        document_model = CanonicalDocument.create(
            raw_text=text,
            metadata=metadata,
            extraction_strategy=strategy,
        )

        if is_small:
            document_model.structured_fields = self._build_structured_fields(
                text, page_metadata
            )

        await self.document_store.save_document(document_model)

        chunks = self._create_chunks(text, document_model.id)
        await self.document_store.save_chunks(chunks)

        return document_model
```

**Key decisions:**
- `supports()` returns `0.1` for PDFs — low score, acts as fallback
- `supports()` returns `0.0` for non-PDFs — cannot handle them
- `size_threshold` is configurable via constructor (default 100K chars)
- `extraction_strategy` is `"generic_small"` or `"generic_large"` based on threshold
- `structured_fields` only populated for small documents (lightweight for large)
- `entities` and `relationships` remain empty (Phase 5 LLM will populate)
- Text extraction logic absorbed from PDFIngester (pypdf + null-byte sanitization)
- Chunking config unchanged: 500 chars, 50 overlap, same separators
- Persistence via injected `DocumentStore` (same pattern as PDFIngester)

**Private methods:**

| Method | Purpose |
|--------|---------|
| `_extract_text(content: bytes)` | pypdf text extraction + null-byte sanitization |
| `_build_metadata(input, page_metadata)` | Build metadata dict (filename, page_count, file_size_bytes) |
| `_build_structured_fields(text, page_metadata)` | Build structured_fields dict for small documents |
| `_create_chunks(text, document_id)` | RecursiveCharacterTextSplitter → list[DocumentChunk] |

### 3.5 Structured Fields (Small Documents Only)

```python
{
    "page_count": 5,
    "total_characters": 45000,
    "total_chunks": 92,
    "avg_chunk_size": 489,
}
```

**Key decisions:**
- Only derived metrics — no LLM-generated content
- Only populated for "generic_small" documents
- Large documents get empty `structured_fields` (Phase 5 will add lightweight metadata)
- These fields are queryable via structured retrieval in Phase 7

---

## 4. Step-by-Step Execution

### Step 1: Create Extractor Package

#### 1.1 Create `backend/extractors/__init__.py`

```python
from extractors.base import DocumentInput, Extractor
from extractors.generic import GenericExtractor
from extractors.registry import ExtractorRegistry, create_default_registry

__all__ = [
    "DocumentInput",
    "Extractor",
    "ExtractorRegistry",
    "GenericExtractor",
    "create_default_registry",
]
```

**Rationale:** Clean public API. Importers can do `from extractors import ExtractorRegistry, GenericExtractor`.

#### 1.2 Create `backend/extractors/base.py`

Define `DocumentInput` dataclass and `Extractor` ABC as shown in Section 3.1 and 3.2.

**Verification:** `from extractors.base import DocumentInput, Extractor` succeeds. `Extractor` cannot be instantiated directly.

---

### Step 2: Create ExtractorRegistry

Create `backend/extractors/registry.py` as shown in Section 3.3.

Add factory function:

```python
def create_default_registry(document_store: DocumentStore) -> ExtractorRegistry:
    return ExtractorRegistry([GenericExtractor(document_store)])
```

**Key decisions:**
- Factory function keeps registry construction explicit
- Phase 4 only registers GenericExtractor
- Future phases add specialized extractors to this function
- Easy to test — tests can construct custom registries

**Verification:**
- Registry with one extractor selects it for matching documents
- Registry raises `ValueError` when no extractor matches
- `process()` delegates to selected extractor
- `create_default_registry(store)` returns a working registry

---

### Step 3: Create GenericExtractor

Create `backend/extractors/generic.py` as shown in Section 3.4.

Absorb the following logic from `backend/ingestion/pdf_ingester.py`:
- `_extract_text()` — pypdf text extraction with temp file + null-byte sanitization
- `_create_chunks()` — RecursiveCharacterTextSplitter with same config (500/50)

Add new logic:
- `_build_metadata()` — constructs metadata dict from DocumentInput + page info
- `_build_structured_fields()` — constructs derived metrics for small documents
- Size threshold classification (small vs large)

**Verification:** GenericExtractor can extract from a PDF and produce a CanonicalDocument with correct `extraction_strategy`, `metadata`, and `structured_fields`.

---

### Step 4: Update Upload Route

Modify `backend/api/routes/documents.py`:

Replace:
```python
from ingestion.pdf_ingester import PDFIngester
# ...
store = DocumentStore(session)
ingester = PDFIngester(store)
document = await ingester.ingest(content, file.filename)
```

With:
```python
from extractors import DocumentInput, create_default_registry
# ...
store = DocumentStore(session)
registry = create_default_registry(store)
document_input = DocumentInput(
    content=content,
    filename=file.filename,
    content_type=file.content_type,
)
document = await registry.process(document_input)
```

**Note:** The existing PDF-only validation in the route provides a clearer error message (400 vs 500). Keep it.

**Verification:** Upload endpoint still works, returns same response shape. `extraction_strategy` changes from `"pdf_basic"` to `"generic_large"` (for the sample PDF).

---

### Step 5: Remove PDFIngester

Delete:
- `backend/ingestion/pdf_ingester.py`
- `backend/ingestion/__init__.py`
- `backend/ingestion/` directory
- `tests/test_ingestion.py`

**Verification:** No remaining imports of `ingestion.pdf_ingester` anywhere in the codebase.

---

### Step 6: Create Tests

#### 6.1 Create `tests/test_extractor_registry.py`

```python
# Tests (no database required):

def test_registry_selects_highest_scoring_extractor():
    # Two mock extractors: one scores 0.5, other scores 0.8
    # Registry should select the 0.8 extractor

def test_registry_raises_when_no_extractor_matches():
    # All extractors return 0.0
    # Registry.select() should raise ValueError

def test_registry_falls_back_to_generic():
    # Only GenericExtractor registered (score 0.1)
    # Registry should select it for PDF documents

def test_registry_process_delegates_to_selected_extractor():
    # Mock extractor returns a known CanonicalDocument
    # Registry.process() should return that document

def test_generic_extractor_supports_pdf():
    # GenericExtractor.supports() returns 0.1 for .pdf files

def test_generic_extractor_rejects_non_pdf():
    # GenericExtractor.supports() returns 0.0 for .txt, .docx, etc.

def test_create_default_registry():
    # Factory function returns registry with GenericExtractor
```

**Mock extractor for testing:**

```python
class MockExtractor(Extractor):
    def __init__(self, score: float) -> None:
        self._score = score

    def supports(self, document: DocumentInput) -> float:
        return self._score

    async def extract(self, document: DocumentInput) -> CanonicalDocument:
        return CanonicalDocument.create(
            raw_text="mock",
            metadata={"mock": True},
            extraction_strategy="mock",
        )
```

#### 6.2 Create `tests/test_generic_extractor.py`

```python
# Tests (require database session):

@pytest.mark.asyncio
async def test_generic_extractor_small_document(session):
    # Create a PDF with < 100K chars of text (or use low threshold)
    # Extract and verify:
    #   - extraction_strategy == "generic_small"
    #   - structured_fields is populated with page_count, total_characters, etc.
    #   - entities == [] (no LLM yet)
    #   - relationships == [] (no LLM yet)
    #   - document persisted to database

@pytest.mark.asyncio
async def test_generic_extractor_large_document(session):
    # Create a PDF with >= 100K chars of text (or use low threshold)
    # Extract and verify:
    #   - extraction_strategy == "generic_large"
    #   - structured_fields == {} (lightweight for large)
    #   - document persisted to database

@pytest.mark.asyncio
async def test_generic_extractor_creates_chunks(session):
    # Extract a PDF with text
    # Verify chunks are created and persisted with correct ordering

@pytest.mark.asyncio
async def test_generic_extractor_metadata(session):
    # Extract a PDF
    # Verify metadata contains filename, page_count, file_size_bytes

@pytest.mark.asyncio
async def test_generic_extractor_null_byte_sanitization(session):
    # Verify that null bytes in extracted text are sanitized
    # (Same behavior as the removed PDFIngester)
```

---

### Step 7: Run Full Validation

See Section 6 below.

---

## 5. Execution Order

| Order | Step | Files Created/Modified | Verification |
|-------|------|------------------------|--------------|
| 1 | Create extractor package | `backend/extractors/__init__.py`, `backend/extractors/base.py` | Imports succeed |
| 2 | Create registry + factory | `backend/extractors/registry.py` | Registry selects correctly |
| 3 | Create GenericExtractor | `backend/extractors/generic.py` | Extraction works |
| 4 | Update upload route | `backend/api/routes/documents.py` | Upload endpoint works |
| 5 | Remove PDFIngester | Delete `backend/ingestion/`, `tests/test_ingestion.py` | No broken imports |
| 6 | Create tests | `tests/test_extractor_registry.py`, `tests/test_generic_extractor.py` | All tests pass |
| 7 | Run full validation | — | See Section 6 |

---

## 6. Phase Completion Checklist

All checks MUST pass before Phase 4 is considered complete.

### 6.1 Type Checking

```bash
cd backend
mypy .
```

Expected: No errors. All new classes, methods, and routes fully typed. `strict = true` enforced.

### 6.2 Linting

```bash
cd backend
ruff check .
```

Expected: No issues. All imports sorted, no unused imports, PEP 8 naming.

### 6.3 Unit Tests

```bash
cd backend
pytest ../tests/ -v
```

Expected: All tests pass.

Non-DB tests:
- `test_health.py` — 2 tests (unchanged)
- `test_models.py` — 4 tests (unchanged)
- `test_extractor_registry.py` — ~7 tests (new)

DB tests:
- `test_document_store.py` — 4 tests (unchanged)
- `test_generic_extractor.py` — ~5 tests (new)

Removed:
- `test_ingestion.py` — 2 tests (replaced by `test_generic_extractor.py`)

Total: ~22 tests

### 6.4 Build Verification

```bash
docker compose build
```

Expected: Image builds successfully.

### 6.5 Docker Compose Startup

```bash
cp .env.example .env
docker compose up --build
```

Expected:
- PostgreSQL starts and passes health check
- Alembic migrations run (no new migrations, schema unchanged)
- Backend starts with no import errors
- No crash, no startup exceptions

### 6.6 Manual Smoke Test

With `docker compose up` running:

```bash
# Health checks still work
curl http://localhost:8000/health
# Expected: {"status":"ok"}

curl http://localhost:8000/health/db
# Expected: {"database":"connected","healthy":true}

# Upload a document (now flows through registry)
curl -X POST http://localhost:8000/documents/upload \
  -F "file=@sample_technical_document.pdf"
# Expected: 201 Created
# Expected: extraction_strategy is "generic_large" (was "pdf_basic")
# Expected: same response shape as Phase 3

# List documents
curl http://localhost:8000/documents/
# Expected: 200 OK, document listed

# Get specific document
curl http://localhost:8000/documents/{id}
# Expected: extraction_strategy: "generic_large"
# Expected: metadata contains filename, page_count, file_size_bytes

# Get chunks
curl http://localhost:8000/documents/{id}/chunks
# Expected: chunks returned in order

# Verify database state
docker exec -it multi-agent-intelligence-db-1 psql -U postgres \
  -d doc_intelligence \
  -c "SELECT extraction_strategy, metadata->>'filename' FROM documents;"
# Expected: "generic_large", sample filename

# OpenAPI docs
open http://localhost:8000/docs
# Expected: Swagger UI with health + document endpoints
```

### 6.7 Fix Before Proceeding

If ANY check fails:
1. STOP.
2. Diagnose root cause.
3. Fix completely.
4. Re-run ALL checks from 6.1.

---

## 7. Testing Strategy

### 7.1 Unit Tests

| Test | File | What it verifies |
|------|------|-----------------|
| `test_registry_selects_highest_scoring_extractor` | `test_extractor_registry.py` | Registry picks highest score |
| `test_registry_raises_when_no_extractor_matches` | `test_extractor_registry.py` | ValueError on no match |
| `test_registry_falls_back_to_generic` | `test_extractor_registry.py` | GenericExtractor selected as fallback |
| `test_registry_process_delegates_to_selected` | `test_extractor_registry.py` | process() calls correct extractor |
| `test_generic_extractor_supports_pdf` | `test_extractor_registry.py` | supports() returns 0.1 for PDFs |
| `test_generic_extractor_rejects_non_pdf` | `test_extractor_registry.py` | supports() returns 0.0 for non-PDFs |
| `test_create_default_registry` | `test_extractor_registry.py` | Factory creates working registry |
| `test_generic_extractor_small_document` | `test_generic_extractor.py` | Small doc → "generic_small" + structured_fields |
| `test_generic_extractor_large_document` | `test_generic_extractor.py` | Large doc → "generic_large" + empty structured_fields |
| `test_generic_extractor_creates_chunks` | `test_generic_extractor.py` | Chunks created and persisted |
| `test_generic_extractor_metadata` | `test_generic_extractor.py` | Metadata has filename, page_count, file_size_bytes |
| `test_generic_extractor_null_byte_sanitization` | `test_generic_extractor.py` | Null bytes sanitized in extracted text |

### 7.2 Integration Tests (Docker)

| Test | How | What it verifies |
|------|-----|-----------------|
| Upload via registry | `curl /documents/upload` | End-to-end through registry |
| extraction_strategy | Response JSON | "generic_large" for sample PDF |
| structured_fields | `psql` query | Empty for large documents |
| Existing endpoints | `curl` all endpoints | No regression |

### 7.3 What NOT to Test Yet

- LLM-based extraction (Phase 5)
- Specialized extractor selection (future phases)
- Entity extraction (Phase 5)
- Embedding generation (Phase 6)
- Query routing (Phase 7)
- Frontend integration (Phase 9)

---

## 8. What NOT to Do

| Anti-pattern | Why |
|-------------|-----|
| Add LLM-based extraction | Phase 5 (LLM Provider Abstraction) |
| Add entity/relationship extraction | Phase 5 (requires LLM) |
| Add specialized extractors (Invoice, Contract) | Future phases |
| Add pgvector columns or embeddings | Phase 6 |
| Add query endpoints | Phase 7 |
| Add authentication | Not in scope |
| Add background task queue | Premature |
| Add logging framework | Premature |
| Modify CanonicalDocument schema | Not needed — fields already exist |
| Add new database migrations | Not needed — schema unchanged |
| Modify DocumentStore | Not needed — already has all required methods |
| Modify `ingest_and_search.py` | Keep as legacy reference |
| Add API versioning | Premature |

---

## 9. Dependency Decisions

### 9.1 No New Dependencies

Phase 4 requires no new packages. All needed libraries are already in `backend/requirements.txt`:

| Package | Purpose | Already present |
|---------|---------|----------------|
| `pypdf` | PDF text extraction | Yes (Phase 3) |
| `langchain-text-splitters` | Text chunking | Yes (Phase 3) |
| `pydantic` | Validation (via FastAPI) | Yes (Phase 2) |
| `sqlalchemy` | ORM (via DocumentStore) | Yes (Phase 2) |

### 9.2 Why ABC over Protocol?

- ABC makes the inheritance relationship explicit
- `@abstractmethod` prevents instantiation of incomplete implementations
- Matches the codebase style (Pydantic BaseModel, DeclarativeBase)
- Protocol would work but adds implicit structural subtyping — unnecessary here

### 9.3 Why `frozen=True` on DocumentInput?

- Extractors should not modify the input
- Immutability prevents accidental side effects
- Signals intent: this is input data, not a mutable state object

### 9.4 Why 0.1 as GenericExtractor's support score?

- Low enough that any specialized extractor (scoring 0.5+) takes priority
- Non-zero so the registry can still process documents when GenericExtractor is the only option
- The exact value is arbitrary — what matters is relative ordering

---

## 10. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Removing PDFIngester breaks upload route | Update route first, verify with tests, then delete |
| GenericExtractor text extraction differs from PDFIngester | Copy logic verbatim, verify same output on sample PDF |
| Registry raises ValueError for non-PDF uploads | Route already validates PDF extension before registry call |
| Mock extractors in tests leak into production | Mock extractors only exist in test files |
| Large PDF memory usage during extraction | Same as Phase 3 — temp file approach, 8.4MB is manageable |
| `structured_fields` empty for large docs confuses reviewers | Document in extraction_strategy field; Phase 5 will add lightweight metadata |

---

## 11. Post-Phase 4 State

After Phase 4 is complete, the repository will have:

```
multi-agent-intelligence/
├── docker-compose.yml              ← UNCHANGED
├── .env.example                    ← UNCHANGED
├── .gitignore                      ← UNCHANGED
├── backend/
│   ├── Dockerfile                  ← UNCHANGED
│   ├── requirements.txt            ← UNCHANGED
│   ├── pyproject.toml              ← UNCHANGED
│   ├── main.py                     ← UNCHANGED
│   ├── config.py                   ← UNCHANGED
│   ├── alembic.ini                 ← UNCHANGED
│   ├── alembic/                    ← UNCHANGED
│   ├── models/                     ← UNCHANGED
│   ├── storage/                    ← UNCHANGED
│   ├── extractors/                 ← NEW
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── registry.py
│   │   └── generic.py
│   ├── ingestion/                  ← DELETED
│   └── api/
│       ├── __init__.py             ← UNCHANGED
│       └── routes/
│           ├── __init__.py         ← UNCHANGED
│           ├── health.py           ← UNCHANGED
│           └── documents.py        ← MODIFIED (use registry)
├── tests/
│   ├── __init__.py                 ← UNCHANGED
│   ├── conftest.py                 ← UNCHANGED
│   ├── test_health.py              ← UNCHANGED
│   ├── test_models.py              ← UNCHANGED
│   ├── test_document_store.py      ← UNCHANGED
│   ├── test_ingestion.py           ← DELETED
│   ├── test_extractor_registry.py  ← NEW
│   └── test_generic_extractor.py   ← NEW
├── ingest_and_search.py            ← UNCHANGED
├── agent_graph.py                  ← UNCHANGED
├── eval_pipeline.py                ← UNCHANGED
├── requirements.txt                ← UNCHANGED (root-level, legacy)
├── sample_technical_document.pdf   ← UNCHANGED
├── AGENTS.md                       ← UNCHANGED
└── docs/
    ├── PROJECT_SPEC.md             ← UNCHANGED
    ├── ENGINEERING_PRINCIPLES.md   ← UNCHANGED
    ├── PHASES.md                   ← UNCHANGED
    ├── PHASE_3_PLAN.md             ← UNCHANGED
    └── PHASE_4_PLAN.md             ← THIS FILE
```

**Total new files:** 6 (4 source + 2 test)
**Total modified files:** 1 (`documents.py`)
**Total deleted files:** 3 (`pdf_ingester.py`, `ingestion/__init__.py`, `test_ingestion.py`)
**Existing files broken:** 0

Phase 5 will then add the LLM Provider Abstraction, enabling GenericExtractor to perform LLM-based entity extraction and structured field generation.
