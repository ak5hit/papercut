# Contributing

The system is designed to be extended without modifying the core pipeline. This guide covers the three extension points.

---

## Adding a New Extractor

Extractors are how the system learns to handle new document types. Every extractor implements a common interface and competes in the registry by confidence score.

### 1. Create the extractor

```python
# backend/extractors/invoice_extractor.py

from extractors.base import Extractor, DocumentInput
from models.canonical_document import CanonicalDocument

class InvoiceExtractor(Extractor):
    def supports(self, document: DocumentInput) -> float:
        if document.filename.lower().endswith('.pdf'):
            return 0.9  # High confidence for invoice-like PDFs
        return 0.0

    async def extract(self, document: DocumentInput) -> CanonicalDocument:
        # 1. Extract text from the PDF
        # 2. Parse invoice-specific fields (amount, date, vendor)
        # 3. Extract entities (company names, line items)
        # 4. Return CanonicalDocument with structured_fields populated
        return CanonicalDocument.create(
            raw_text=extracted_text,
            metadata={"filename": document.filename, "type": "invoice"},
            extraction_strategy="invoice_extractor"
        )
```

### 2. Register the extractor

```python
# backend/extractors/registry.py — in create_default_registry()

def create_default_registry(store, llm_provider, embedding_provider):
    from extractors.generic import GenericExtractor
    from extractors.invoice_extractor import InvoiceExtractor
    return ExtractorRegistry([
        InvoiceExtractor(store, llm_provider, embedding_provider),
        GenericExtractor(store, llm_provider, embedding_provider),
    ])
```

### 3. Done

The pipeline runs unchanged. The registry will select your extractor when `supports()` returns the highest score.

### Interface Reference

```python
@dataclass(frozen=True)
class DocumentInput:
    content: bytes
    filename: str
    content_type: str | None = None

class Extractor(ABC):
    @abstractmethod
    def supports(self, document: DocumentInput) -> float:
        """Return confidence 0.0-1.0. Registry picks highest score."""

    @abstractmethod
    async def extract(self, document: DocumentInput) -> CanonicalDocument:
        """Process document. Populate structured_fields and entities."""
```

---

## Adding a New LLM Provider

The LLM abstraction lets you swap model providers without changing business logic.

### 1. Create the provider

```python
# backend/llm/anthropic_provider.py

from llm.base import LLMProvider
import httpx

class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self._client = httpx.AsyncClient(timeout=60.0)

    async def complete(self, prompt: str, max_tokens: int = 2000) -> str:
        response = await self._client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            json={
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        data = response.json()
        return data["content"][0]["text"]

    async def close(self) -> None:
        await self._client.aclose()
```

### 2. Wire into the factory

```python
# backend/llm/factory.py

def create_llm_provider() -> LLMProvider:
    s = settings
    if s.llm_provider == "anthropic":
        from llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider(api_key=s.anthropic_api_key, model=s.llm_model)
    # ... existing providers
```

### 3. Add environment variables

```bash
# .env.example
ANTHROPIC_API_KEY=your-key-here
```

### Interface Reference

```python
class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, max_tokens: int = 2000) -> str:
        """Send prompt to the model, return completion text."""
```

---

## Adding a New Retrieval Strategy

Retrieval strategies determine how the query planner finds relevant information.

### 1. Create the retriever

```python
# backend/query/keyword_retriever.py

from query.result import QueryResult
from query.execution_trace import ExecutionTrace

class KeywordRetriever:
    def __init__(self, document_store):
        self.document_store = document_store

    async def search(self, question: str) -> QueryResult:
        trace = ExecutionTrace(strategy="KEYWORD", steps=[])
        # Implement keyword-based search against raw_text
        # Return QueryResult with matching documents
        return QueryResult(trace=trace, documents=[], chunks=[])
```

### 2. Wire into the query planner

```python
# backend/query/planner.py — in QueryPlanner.execute()

async def execute(self, question: str) -> QueryResult:
    strategy = await self.classifier.classify(question)
    if strategy == "KEYWORD":
        return await self.keyword_retriever.search(question)
    # ... existing strategies
```

---

## Running Tests

```bash
cd backend
.venv/bin/python -m pytest ../tests/ -v
```

DB-dependent tests require a running PostgreSQL instance:

```bash
docker compose up -d    # Start the database
.venv/bin/python -m pytest ../tests/ -v
docker compose down     # Clean up when done
```

## Type Checking & Linting

```bash
cd backend
.venv/bin/python -m mypy .
.venv/bin/python -m ruff check .
```

## Project Conventions

- **Python 3.11** — Use `str | None` over `Optional[str]`.
- **Async** — All database and network calls are async.
- **Pydantic v2** — Models use `model_config`, not `Config` inner classes.
- **SQLAlchemy 2.0** — Use `select()` style, not `Query` objects.
- **No comments** — Code should be self-documenting through clear naming.
- **Single responsibility** — Each module does one thing.
