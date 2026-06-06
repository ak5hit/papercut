# Phase 5: LLM Provider Abstraction — Execution Plan

## Objective

Create the LLM Provider interface, implement OpenAI-compatible and Ollama providers, and integrate LLM-based entity extraction into GenericExtractor. The system gains the ability to extract entities and relationships from documents, with the provider swappable via configuration.

**Deliverable:** GenericExtractor uses an injected LLM provider to populate `entities` and `relationships` for small documents. Provider is configurable via environment variables.

**Rule:** Do NOT implement Phase 6+ features. No embeddings, no pgvector, no query planner, no frontend. Only the LLM abstraction and entity extraction.

---

## 1. Design Decisions

### 1.1 Provider Interface

The LLM provider interface is minimal: a single `complete()` method that takes a prompt and returns structured text. This is intentionally narrow — the system only needs text completion for entity extraction, not streaming, function calling, or multi-turn chat.

```python
class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, max_tokens: int = 2000) -> str:
        ...
```

**Key decisions:**
- ABC (not Protocol) — matches codebase style
- `complete()` is async — network I/O to external APIs
- Returns raw text — caller handles parsing
- `max_tokens` parameter — prevents runaway responses
- No streaming — entity extraction doesn't need it
- No chat history — single-turn extraction only

### 1.2 OpenAI-Compatible Provider (Default)

The default provider uses the OpenAI chat completions API format. This covers:
- OpenAI (GPT-4o-mini, GPT-4o)
- OpenCode models (via OpenAI-compatible endpoint)
- Any OpenAI-compatible API (Together, Groq, etc.)

Uses `httpx` (already in requirements for testing) directly — no additional LLM SDK dependency.

**Key decisions:**
- `httpx.AsyncClient` for HTTP calls — already a dependency, no new packages
- Chat completions format — universal across OpenAI-compatible APIs
- API key from environment variable — standard practice
- Model name configurable — allows switching without code changes
- Timeout of 60 seconds — prevents hanging on slow APIs

### 1.3 Ollama Provider (Optional)

Ollama provides local LLM inference. The provider uses Ollama's `/api/generate` endpoint.

**Key decisions:**
- Local HTTP endpoint (default `http://localhost:11434`)
- No API key required — local inference
- Model name configurable (default: `llama3`)
- Same `complete()` interface — drop-in replacement

### 1.4 Provider Factory

A factory function creates the appropriate provider based on environment configuration:

```python
def create_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "ollama":
        return OllamaProvider(...)
    return OpenAICompatibleProvider(...)
```

**Key decisions:**
- Factory pattern — keeps provider construction centralized
- Configuration-driven — `LLM_PROVIDER` env var selects implementation
- Defaults to OpenAI-compatible — most common use case
- Raises `ValueError` for unknown provider names

### 1.5 Entity Extraction Strategy

GenericExtractor uses the LLM to extract entities and relationships from **small documents only**. Large documents skip LLM extraction entirely (per AGENTS.md: "Do NOT attempt full-document LLM extraction for very large files").

**Small documents (< 100K chars):**
- Send full text to LLM with entity extraction prompt
- Parse JSON response into `entities` and `relationships` lists
- Populate `structured_fields` with LLM-generated summary

**Large documents (>= 100K chars):**
- Skip LLM extraction
- `entities` and `relationships` remain empty
- `structured_fields` contains only derived metrics (Phase 4 behavior)

**Key decisions:**
- Single prompt for entity extraction — simple, predictable
- JSON output format — easy to parse, structured
- Graceful degradation on LLM failure — log error, continue with empty entities
- No retry logic — premature for Phase 5

### 1.6 Entity Schema

Entities are stored as a list of dictionaries with a flexible schema:

```python
{
    "name": "Entity Name",
    "type": "PERSON|ORGANIZATION|LOCATION|DATE|MONEY|OTHER",
    "value": "normalized value"
}
```

Relationships connect entities:

```python
{
    "source": "Entity Name 1",
    "target": "Entity Name 2",
    "type": "WORKS_AT|LOCATED_IN|PART_OF|OTHER",
    "description": "optional description"
}
```

**Key decisions:**
- Flexible dict schema — allows evolution without migrations
- Type enums — provides structure without rigidity
- `value` field — normalized/canonical form (e.g., dates, currencies)
- No confidence scores — per AGENTS.md: "Never expose fabricated LLM confidence scores"

### 1.7 Configuration

New environment variables added to `config.py`:

```python
llm_provider: str = "openai"  # "openai" or "ollama"
llm_model: str = "gpt-4o-mini"
openai_api_key: str = ""
openai_base_url: str = "https://api.openai.com/v1"
ollama_base_url: str = "http://localhost:11434"
```

**Key decisions:**
- `openai` as default provider — most accessible
- `gpt-4o-mini` as default model — cost-effective for extraction
- `openai_base_url` configurable — supports OpenAI-compatible APIs
- Empty `openai_api_key` default — must be set in `.env` for OpenAI provider
- All settings optional — Ollama provider doesn't need API keys

### 1.8 GenericExtractor Integration

GenericExtractor receives an optional `LLMProvider` via constructor injection:

```python
class GenericExtractor(Extractor):
    def __init__(
        self,
        document_store: DocumentStore,
        llm_provider: LLMProvider | None = None,
        size_threshold: int = DEFAULT_SIZE_THRESHOLD,
    ) -> None:
        ...
```

**Key decisions:**
- `llm_provider` is optional — allows Phase 4 behavior when `None`
- Constructor injection — explicit dependency, easy to test
- Extraction strategy unchanged — `"generic_small"` or `"generic_large"`
- LLM failure is non-fatal — extraction continues with empty entities

### 1.9 Registry Factory Update

`create_default_registry` now accepts and passes through the LLM provider:

```python
def create_default_registry(
    document_store: DocumentStore,
    llm_provider: LLMProvider | None = None,
) -> ExtractorRegistry:
    return ExtractorRegistry([GenericExtractor(document_store, llm_provider)])
```

**Key decisions:**
- Backward compatible — `llm_provider` defaults to `None`
- Upload route creates provider via factory — configuration-driven
- Test code can inject mock providers

---

## 2. Target File Structure (Phase 5 Only)

Files to create:

```
multi-agent-intelligence/
├── backend/
│   └── llm/
│       ├── __init__.py              # Exports + create_llm_provider()
│       ├── base.py                  # LLMProvider ABC
│       ├── openai_provider.py       # OpenAI-compatible provider
│       └── ollama_provider.py       # Ollama provider
├── tests/
│   ├── test_llm_provider.py         # Provider interface + factory tests
│   └── test_entity_extraction.py    # Entity extraction integration tests
└── docs/
    └── PHASE_5_PLAN.md              # (this file)
```

Files to modify:

| File | Change |
|------|--------|
| `backend/config.py` | Add LLM configuration fields |
| `backend/extractors/generic.py` | Accept LLM provider, add entity extraction |
| `backend/extractors/registry.py` | Pass LLM provider to GenericExtractor |
| `backend/api/routes/documents.py` | Create LLM provider, pass to registry |
| `backend/requirements.txt` | No new dependencies (httpx already present) |
| `.env.example` | Document LLM environment variables |

Files to NOT create (reserved for future phases):

- `backend/embeddings/` — Phase 6
- `backend/query/` — Phase 7
- `backend/evaluation/` — Phase 10
- `frontend/` — Phase 9
- Specialized extractors (Invoice, Contract, etc.) — future phases

Files to NOT modify:

- `ingest_and_search.py` — kept as legacy reference
- `agent_graph.py` — untouched
- `eval_pipeline.py` — untouched
- Root `requirements.txt` — untouched
- `backend/models/` — CanonicalDocument and DocumentChunk unchanged
- `backend/storage/` — DocumentStore and database unchanged
- `backend/alembic/` — no schema changes
- `backend/Dockerfile` — unchanged
- `docker-compose.yml` — unchanged

---

## 3. Schema Design

### 3.1 LLMProvider (Abstract Base Class)

```python
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, max_tokens: int = 2000) -> str:
        ...
```

**Key decisions:**
- Single method — minimal interface
- `prompt` is a string — caller formats the prompt
- Returns string — caller parses the response
- `max_tokens` prevents runaway responses

### 3.2 OpenAICompatibleProvider

```python
import httpx

from llm.base import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def complete(self, prompt: str, max_tokens: int = 2000) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.0,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
```

**Key decisions:**
- `httpx.AsyncClient` — async HTTP, already a dependency
- `temperature=0.0` — deterministic extraction
- Single message (user role) — no chat history needed
- `raise_for_status()` — fail fast on HTTP errors
- Caller handles JSON parsing — provider returns raw text

### 3.3 OllamaProvider

```python
import httpx

from llm.base import LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        model: str = "llama3",
        base_url: str = "http://localhost:11434",
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def complete(self, prompt: str, max_tokens: int = 2000) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": max_tokens, "temperature": 0.0},
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["response"]
```

**Key decisions:**
- No API key — local inference
- Longer timeout (120s) — local models can be slow
- `stream=False` — single response, not streaming
- `num_predict` controls max tokens

### 3.4 Provider Factory

```python
from config import Settings
from llm.base import LLMProvider
from llm.ollama_provider import OllamaProvider
from llm.openai_provider import OpenAICompatibleProvider


def create_llm_provider(settings: Settings) -> LLMProvider:
    provider_name = settings.llm_provider.lower()

    if provider_name == "ollama":
        return OllamaProvider(
            model=settings.llm_model,
            base_url=settings.ollama_base_url,
        )

    if provider_name in ("openai", "openai-compatible"):
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI provider")
        return OpenAICompatibleProvider(
            api_key=settings.openai_api_key,
            model=settings.llm_model,
            base_url=settings.openai_base_url,
        )

    raise ValueError(f"Unknown LLM provider: {provider_name}")
```

**Key decisions:**
- Case-insensitive provider name
- Validates API key for OpenAI provider
- Raises `ValueError` for unknown providers
- Returns configured provider instance

### 3.5 Entity Extraction Prompt

```python
ENTITY_EXTRACTION_PROMPT = """You are an entity extraction system. Analyze the following document text and extract all entities and relationships.

Return ONLY valid JSON in this exact format:
{
  "entities": [
    {"name": "Entity Name", "type": "PERSON|ORGANIZATION|LOCATION|DATE|MONEY|OTHER", "value": "normalized value"}
  ],
  "relationships": [
    {"source": "Entity1", "target": "Entity2", "type": "WORKS_AT|LOCATED_IN|PART_OF|OTHER", "description": "optional"}
  ]
}

If no entities are found, return {"entities": [], "relationships": []}.

DOCUMENT TEXT:
{text}
"""
```

**Key decisions:**
- Single prompt template — simple, maintainable
- JSON output format — structured, parseable
- Explicit schema in prompt — guides LLM output
- Fallback for empty results — graceful degradation
- Type enums in prompt — constrains output

### 3.6 Entity Extraction Method

```python
import json

from llm.base import LLMProvider


async def _extract_entities(
    self,
    text: str,
    llm_provider: LLMProvider,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    prompt = ENTITY_EXTRACTION_PROMPT.format(text=text)

    try:
        response = await llm_provider.complete(prompt, max_tokens=4000)
        data = json.loads(response)
        entities = data.get("entities", [])
        relationships = data.get("relationships", [])
        return entities, relationships
    except (json.JSONDecodeError, KeyError, httpx.HTTPError):
        return [], []
```

**Key decisions:**
- `max_tokens=4000` — enough for entity lists
- Catches JSON parse errors — returns empty on failure
- Catches HTTP errors — non-fatal, continues extraction
- Returns tuple — entities and relationships together
- No logging — premature per AGENTS.md (could add later)

---

## 4. Step-by-Step Execution

### Step 1: Add LLM Configuration

Modify `backend/config.py`:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/doc_intelligence"
    host: str = "0.0.0.0"
    port: int = 8000

    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    ollama_base_url: str = "http://localhost:11434"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
```

Update `.env.example`:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/doc_intelligence

# Server
HOST=0.0.0.0
PORT=8000

# LLM Provider
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
OLLAMA_BASE_URL=http://localhost:11434
```

**Verification:** `Settings` loads LLM config from environment. Default values work for OpenAI provider.

---

### Step 2: Create LLM Provider Package

#### 2.1 Create `backend/llm/__init__.py`

```python
from llm.base import LLMProvider
from llm.ollama_provider import OllamaProvider
from llm.openai_provider import OpenAICompatibleProvider
from llm.factory import create_llm_provider

__all__ = [
    "LLMProvider",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "create_llm_provider",
]
```

#### 2.2 Create `backend/llm/base.py`

Define `LLMProvider` ABC as shown in Section 3.1.

#### 2.3 Create `backend/llm/openai_provider.py`

Implement `OpenAICompatibleProvider` as shown in Section 3.2.

#### 2.4 Create `backend/llm/ollama_provider.py`

Implement `OllamaProvider` as shown in Section 3.3.

#### 2.5 Create `backend/llm/factory.py`

Implement `create_llm_provider` as shown in Section 3.4.

**Verification:**
- `from llm import LLMProvider, create_llm_provider` succeeds
- `LLMProvider` cannot be instantiated directly
- Factory creates correct provider based on config

---

### Step 3: Integrate LLM into GenericExtractor

Modify `backend/extractors/generic.py`:

1. Add `llm_provider` parameter to `__init__`
2. Add `_extract_entities` method
3. Call entity extraction for small documents in `extract()`
4. Add entity extraction prompt constant

**Updated `extract()` method:**

```python
async def extract(self, document: DocumentInput) -> CanonicalDocument:
    text, page_metadata = self._extract_text(document.content)
    is_small = len(text) < self.size_threshold

    metadata = self._build_metadata(document, page_metadata)
    strategy = "generic_small" if is_small else "generic_large"

    doc = CanonicalDocument.create(
        raw_text=text,
        metadata=metadata,
        extraction_strategy=strategy,
    )

    chunks = self._create_chunks(text, doc.id)

    if is_small:
        doc.structured_fields = self._build_structured_fields(text, page_metadata, chunks)

        if self.llm_provider:
            entities, relationships = await self._extract_entities(text, self.llm_provider)
            doc.entities = entities
            doc.relationships = relationships

    await self.document_store.save_document(doc)
    await self.document_store.save_chunks(chunks)

    return doc
```

**Key decisions:**
- Entity extraction only for small documents
- Only runs if `llm_provider` is provided
- LLM failure is non-fatal — continues with empty entities
- Extraction happens before persistence — single save

**Verification:**
- GenericExtractor works with `llm_provider=None` (Phase 4 behavior)
- GenericExtractor extracts entities when provider is injected
- LLM failure doesn't break extraction

---

### Step 4: Update Registry Factory

Modify `backend/extractors/registry.py`:

```python
def create_default_registry(
    document_store: DocumentStore,
    llm_provider: LLMProvider | None = None,
) -> ExtractorRegistry:
    return ExtractorRegistry([GenericExtractor(document_store, llm_provider)])
```

**Verification:**
- Factory accepts optional `llm_provider`
- Passes provider to GenericExtractor
- Backward compatible — works with `None`

---

### Step 5: Update Upload Route

Modify `backend/api/routes/documents.py`:

```python
from config import settings
from extractors import DocumentInput, create_default_registry
from llm import create_llm_provider
from storage.database import get_session
from storage.document_store import DocumentStore


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

    registry = create_default_registry(store, llm_provider)
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

**Key decisions:**
- Provider created only if API key is set or Ollama is configured
- Graceful degradation — works without LLM provider
- Response includes `entities_count` and `relationships_count`
- No breaking changes to response shape

**Verification:**
- Upload works without API key (Phase 4 behavior)
- Upload extracts entities when API key is configured
- Response includes entity counts

---

### Step 6: Create Tests

#### 6.1 Create `tests/test_llm_provider.py`

```python
# Tests (no database required, no real API calls):

def test_openai_provider_initialization():
    # Provider stores config correctly

def test_ollama_provider_initialization():
    # Provider stores config correctly

def test_factory_creates_openai_provider():
    # Factory with llm_provider="openai" returns OpenAICompatibleProvider

def test_factory_creates_ollama_provider():
    # Factory with llm_provider="ollama" returns OllamaProvider

def test_factory_raises_on_unknown_provider():
    # Factory raises ValueError for unknown provider name

def test_factory_validates_openai_api_key():
    # Factory raises ValueError if OpenAI provider has no API key

@pytest.mark.asyncio
async def test_openai_provider_complete():
    # Mock httpx response, verify complete() returns text

@pytest.mark.asyncio
async def test_ollama_provider_complete():
    # Mock httpx response, verify complete() returns text
```

#### 6.2 Create `tests/test_entity_extraction.py`

```python
# Tests (require database session):

@pytest.mark.asyncio
async def test_generic_extractor_without_llm_provider(session):
    # Extractor with llm_provider=None
    # entities == [], relationships == []

@pytest.mark.asyncio
async def test_generic_extractor_with_llm_provider(session):
    # Mock LLM provider returns JSON with entities
    # Verify entities and relationships are populated

@pytest.mark.asyncio
async def test_generic_extractor_llm_failure(session):
    # Mock LLM provider raises exception
    # Verify extraction continues with empty entities

@pytest.mark.asyncio
async def test_generic_extractor_malformed_json(session):
    # Mock LLM provider returns invalid JSON
    # Verify extraction continues with empty entities

@pytest.mark.asyncio
async def test_entity_extraction_prompt_format():
    # Verify prompt contains document text
    # Verify prompt requests JSON format
```

**Mock LLM provider for testing:**

```python
class MockLLMProvider(LLMProvider):
    def __init__(self, response: str = '{"entities": [], "relationships": []}') -> None:
        self.response = response

    async def complete(self, prompt: str, max_tokens: int = 2000) -> str:
        return self.response
```

---

### Step 7: Run Full Validation

See Section 6 below.

---

## 5. Execution Order

| Order | Step | Files Created/Modified | Verification |
|-------|------|------------------------|--------------|
| 1 | Add LLM config | `backend/config.py`, `.env.example` | Settings loads LLM fields |
| 2 | Create LLM package | `backend/llm/__init__.py`, `base.py`, `openai_provider.py`, `ollama_provider.py`, `factory.py` | Imports succeed, factory works |
| 3 | Integrate LLM | `backend/extractors/generic.py` | Entity extraction works |
| 4 | Update registry | `backend/extractors/registry.py` | Factory passes provider |
| 5 | Update upload route | `backend/api/routes/documents.py` | Upload extracts entities |
| 6 | Create tests | `tests/test_llm_provider.py`, `tests/test_entity_extraction.py` | All tests pass |
| 7 | Run full validation | — | See Section 6 |

---

## 6. Phase Completion Checklist

All checks MUST pass before Phase 5 is considered complete.

### 6.1 Type Checking

```bash
cd backend
.venv/bin/python -m mypy .
```

Expected: No errors. All new classes, methods, and routes fully typed. `strict = true` enforced.

### 6.2 Linting

```bash
cd backend
.venv/bin/python -m ruff check .
```

Expected: No issues. All imports sorted, no unused imports, PEP 8 naming.

### 6.3 Unit Tests

```bash
cd backend
.venv/bin/python -m pytest ../tests/ -v
```

Expected: All tests pass.

Non-DB tests:
- `test_health.py` — 2 tests (unchanged)
- `test_models.py` — 4 tests (unchanged)
- `test_extractor_registry.py` — 8 tests (unchanged)
- `test_llm_provider.py` — ~8 tests (new)

DB tests:
- `test_document_store.py` — 4 tests (unchanged)
- `test_generic_extractor.py` — 5 tests (unchanged)
- `test_entity_extraction.py` — ~5 tests (new)

Total: ~36 tests

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
- Works even without `OPENAI_API_KEY` set (graceful degradation)

### 6.6 Manual Smoke Test

With `docker compose up` running:

```bash
# Health checks still work
curl http://localhost:8000/health
# Expected: {"status":"ok"}

curl http://localhost:8000/health/db
# Expected: {"database":"connected","healthy":true}

# Upload a document WITHOUT API key (Phase 4 behavior)
curl -X POST http://localhost:8000/documents/upload \
  -F "file=@sample_technical_document.pdf"
# Expected: 201 Created
# Expected: extraction_strategy is "generic_large"
# Expected: entities_count: 0, relationships_count: 0

# Upload a small document WITH API key configured
# (Set OPENAI_API_KEY in .env, restart backend)
curl -X POST http://localhost:8000/documents/upload \
  -F "file=@small_test.pdf"
# Expected: 201 Created
# Expected: extraction_strategy is "generic_small"
# Expected: entities_count > 0 (if LLM extraction succeeded)

# List documents
curl http://localhost:8000/documents/
# Expected: 200 OK, documents listed

# Get specific document
curl http://localhost:8000/documents/{id}
# Expected: entities and relationships arrays present

# Verify database state
docker exec -it multi-agent-intelligence-db-1 psql -U postgres \
  -d doc_intelligence \
  -c "SELECT extraction_strategy, jsonb_array_length(entities) as entity_count FROM documents;"
# Expected: entity counts per document

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
| `test_openai_provider_initialization` | `test_llm_provider.py` | Provider stores config |
| `test_ollama_provider_initialization` | `test_llm_provider.py` | Provider stores config |
| `test_factory_creates_openai_provider` | `test_llm_provider.py` | Factory returns correct type |
| `test_factory_creates_ollama_provider` | `test_llm_provider.py` | Factory returns correct type |
| `test_factory_raises_on_unknown_provider` | `test_llm_provider.py` | ValueError on bad input |
| `test_factory_validates_openai_api_key` | `test_llm_provider.py` | ValueError on missing key |
| `test_openai_provider_complete` | `test_llm_provider.py` | HTTP call + response parsing |
| `test_ollama_provider_complete` | `test_llm_provider.py` | HTTP call + response parsing |
| `test_generic_extractor_without_llm_provider` | `test_entity_extraction.py` | Phase 4 behavior preserved |
| `test_generic_extractor_with_llm_provider` | `test_entity_extraction.py` | Entities extracted |
| `test_generic_extractor_llm_failure` | `test_entity_extraction.py` | Graceful degradation |
| `test_generic_extractor_malformed_json` | `test_entity_extraction.py` | JSON parse error handled |
| `test_entity_extraction_prompt_format` | `test_entity_extraction.py` | Prompt contains text + schema |

### 7.2 Integration Tests (Docker)

| Test | How | What it verifies |
|------|-----|-----------------|
| Upload without API key | `curl /documents/upload` | Phase 4 behavior, no entities |
| Upload with API key | `curl /documents/upload` | Entities extracted |
| Entity counts | Response JSON | `entities_count` field present |
| Database state | `psql` query | Entities stored in JSONB |
| Existing endpoints | `curl` all endpoints | No regression |

### 7.3 What NOT to Test Yet

- Embedding generation (Phase 6)
- Query routing (Phase 7)
- Frontend integration (Phase 9)
- RAGAS evaluation (Phase 10)
- Multi-turn chat (not in scope)
- Streaming responses (not in scope)

---

## 8. What NOT to Do

| Anti-pattern | Why |
|-------------|-----|
| Add embeddings or pgvector | Phase 6 |
| Add query endpoints | Phase 7 |
| Add authentication | Not in scope |
| Add retry logic for LLM calls | Premature |
| Add logging framework | Premature |
| Add streaming responses | Not needed for extraction |
| Add multi-turn chat | Not needed for extraction |
| Add function calling | Not needed for extraction |
| Modify CanonicalDocument schema | Not needed — fields already exist |
| Add new database migrations | Not needed — schema unchanged |
| Modify DocumentStore | Not needed — already has all required methods |
| Add langchain as dependency | httpx is sufficient |
| Add specialized extractors | Future phases |
| Modify `ingest_and_search.py` | Keep as legacy reference |

---

## 9. Dependency Decisions

### 9.1 No New Dependencies

Phase 5 requires no new packages. All needed libraries are already in `backend/requirements.txt`:

| Package | Purpose | Already present |
|---------|---------|----------------|
| `httpx` | HTTP client for LLM APIs | Yes (testing dependency) |
| `pydantic-settings` | Configuration | Yes (Phase 2) |

**Note:** `httpx` is currently listed under "Dev / testing" dependencies. It should be moved to the main dependencies section since it's now used in production code.

### 9.2 Why httpx Over SDKs?

- **No vendor lock-in** — works with any OpenAI-compatible API
- **Already a dependency** — no new packages
- **Async-native** — built for async/await
- **Lightweight** — no transitive dependencies
- **Explicit control** — caller handles request/response formatting

Alternatives rejected:
- `openai` SDK — vendor-specific, heavy dependencies
- `langchain` — overkill for single-turn extraction
- `litellm` — unnecessary abstraction layer

### 9.3 Why Single `complete()` Method?

- **Minimal interface** — only what's needed for entity extraction
- **Easy to test** — mock a single method
- **Easy to extend** — add methods in future phases if needed
- **Clear responsibility** — text in, text out

Alternatives rejected:
- Chat interface with history — not needed for extraction
- Streaming interface — not needed for extraction
- Function calling interface — premature

---

## 10. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| LLM API is slow or times out | 60s timeout for OpenAI, 120s for Ollama; non-fatal on failure |
| LLM returns malformed JSON | Catch `JSONDecodeError`, return empty entities |
| LLM API key is invalid | Catch `HTTPError`, return empty entities |
| Entity extraction is expensive | Only for small documents (< 100K chars) |
| Provider factory fails | Raises clear `ValueError` with provider name |
| Tests make real API calls | All tests use mock providers |
| Breaking Phase 4 behavior | `llm_provider` is optional, defaults to `None` |
| `httpx` not in production deps | Move from dev to main dependencies |

---

## 11. Post-Phase 5 State

After Phase 5 is complete, the repository will have:

```
multi-agent-intelligence/
├── docker-compose.yml              ← UNCHANGED
├── .env.example                    ← MODIFIED (LLM config documented)
├── .gitignore                      ← UNCHANGED
├── backend/
│   ├── Dockerfile                  ← UNCHANGED
│   ├── requirements.txt            ← MODIFIED (httpx moved to main)
│   ├── pyproject.toml              ← UNCHANGED
│   ├── main.py                     ← UNCHANGED
│   ├── config.py                   ← MODIFIED (LLM settings added)
│   ├── alembic.ini                 ← UNCHANGED
│   ├── alembic/                    ← UNCHANGED
│   ├── models/                     ← UNCHANGED
│   ├── storage/                    ← UNCHANGED
│   ├── extractors/
│   │   ├── __init__.py             ← UNCHANGED
│   │   ├── base.py                 ← UNCHANGED
│   │   ├── registry.py             ← MODIFIED (accepts llm_provider)
│   │   └── generic.py              ← MODIFIED (entity extraction)
│   ├── llm/                        ← NEW
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── openai_provider.py
│   │   ├── ollama_provider.py
│   │   └── factory.py
│   └── api/
│       ├── __init__.py             ← UNCHANGED
│       └── routes/
│           ├── __init__.py         ← UNCHANGED
│           ├── health.py           ← UNCHANGED
│           └── documents.py        ← MODIFIED (creates LLM provider)
├── tests/
│   ├── __init__.py                 ← UNCHANGED
│   ├── conftest.py                 ← UNCHANGED
│   ├── test_health.py              ← UNCHANGED
│   ├── test_models.py              ← UNCHANGED
│   ├── test_document_store.py      ← UNCHANGED
│   ├── test_extractor_registry.py  ← UNCHANGED
│   ├── test_generic_extractor.py   ← UNCHANGED
│   ├── test_llm_provider.py        ← NEW
│   └── test_entity_extraction.py   ← NEW
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
    ├── PHASE_4_PLAN.md             ← UNCHANGED
    └── PHASE_5_PLAN.md             ← THIS FILE
```

**Total new files:** 7 (5 source + 2 test)
**Total modified files:** 5 (`config.py`, `requirements.txt`, `registry.py`, `generic.py`, `documents.py`, `.env.example`)
**Total deleted files:** 0
**Existing files broken:** 0

Phase 6 will then add embeddings and pgvector integration, enabling semantic search over document chunks.
