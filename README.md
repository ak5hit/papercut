# Document Intelligence Platform

Universal document intelligence with structured and semantic retrieval. Not just "chat with PDF."

## The Problem

The brief: *"Turn messy documents into structured, queryable data."*

Most document Q&A systems treat every question as a vector search problem. But "What is the total contract value?" shouldn't require semantic similarity — it's a lookup. And "Summarize the payment obligations" shouldn't be answered by regex — it needs understanding.

This platform separates **symbolic knowledge** (structured fields, entities) from **semantic context** (embeddings, natural language). The query planner routes each question to the right retrieval strategy:

- **Structured** — Deterministic facts from JSONB fields. No LLM narration of known values.
- **Semantic** — Vector similarity for open-ended questions.
- **Hybrid** — Structured pre-filtering followed by semantic search.

## Scope Decisions

**What I built:**
- Plugin-based extractor registry (add new document types in ~50 lines)
- Dual retrieval engine (structured + semantic + hybrid)
- LLM-based query classifier (routes questions intelligently)
- Explainable answers (source references, page numbers, execution traces)
- Full-stack application (FastAPI + Next.js + PostgreSQL + pgvector)
- 100 tests across 19 files

**What I deliberately left out:**
- **Authentication/multi-tenancy** — Out of scope for a document intelligence demo
- **Multiple document formats** — PDF only, but the plugin architecture makes adding CSV/DOCX/XML trivial (see [Extensibility](#extensibility))
- **Conversation history** — Single-turn Q&A keeps the focus on retrieval quality
- **Production deployment** — Docker Compose for local development; no Kubernetes, no Terraform

**Why this scope:**
The goal was to demonstrate engineering judgement, not maximize feature count. Every decision prioritizes clarity, maintainability, and explainability over complexity.

## Quick Start

Create a `.env` file in the project root:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/doc_intelligence

# LLM Provider (choose one)
# Option 1: OpenAI-compatible API (OpenAI, OpenCode, etc.)
LLM_PROVIDER=openai-compatible
LLM_MODEL=gpt-4o-mini  # or deepseek-v4-flash, etc.
OPENAI_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://api.openai.com/v1

# Option 2: Ollama (local LLM)
# LLM_PROVIDER=ollama
# LLM_MODEL=llama3
# OLLAMA_BASE_URL=http://host.docker.internal:11434

# Embeddings (local, no API key needed)
EMBEDDING_PROVIDER=fastembed
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIMENSION=384
```

Then start the application:

```bash
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000) and upload a text-based PDF.

> **Note:** The included `Akshit_Bansal_Resume.pdf` works well for testing. For best results, use text-based PDFs (not scanned images).

## Architecture

```
User (Browser) → Next.js (:3000) → FastAPI (:8000) → PostgreSQL 16 + pgvector
                                                    → LLM Provider (OpenAI / Ollama)
                                                    → Embedding Provider (FastEmbed)
                                                    → Extractor Registry (plugin system)
```

### Ingestion Pipeline

```
PDF → Extractor Registry → GenericExtractor or ResumeExtractor
  → Text extraction (pypdf)
  → Chunking (langchain-text-splitters)
  → Embeddings (FastEmbed, 384-dim BGE vectors)
  → Entity extraction (LLM, small docs only)
  → PostgreSQL (JSONB fields + pgvector HNSW index)
```

Small documents (<100k chars) get full LLM extraction. Large documents skip expensive entity extraction — an intentional cost/latency tradeoff documented in [TRADEOFFS.md](docs/TRADEOFFS.md).

### Query Pipeline

```
User Question → QueryClassifier (LLM)
  → STRUCTURED: JSONB field/entity search
  → SEMANTIC: pgvector cosine distance
  → HYBRID: Structured pre-filter + semantic search
  → AnswerComposer (LLM synthesis or direct formatting)
  → Answer + Source References + Execution Trace
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for Mermaid diagrams and detailed flow descriptions.

## Key Engineering Decisions

### 1. Modular Monolith
Three Docker containers (db, backend, frontend), one cohesive application. No microservices, no Kafka, no Kubernetes. The problem domain doesn't require horizontal scaling of independent services.

### 2. PostgreSQL + pgvector
One database for both structured data (JSONB) and embeddings (Vector(384)). HNSW index for fast ANN search. Chosen over Qdrant in-memory — data persists across restarts and supports transactional queries.

### 3. FastEmbed (Local, Free)
BAAI/bge-small-en-v1.5 embeddings generated locally. Zero cost, zero network latency, no API key dependency. 384 dimensions — compact enough for fast retrieval, expressive enough for semantic search.

### 4. Structured Answers: Direct Formatting
When the query planner routes to STRUCTURED, results are formatted directly from database records. No LLM call. Deterministic questions get deterministic answers — no hallucination risk, no latency, no cost.

### 5. LLM-Based Query Classification
An LLM prompt classifies each query as STRUCTURED, SEMANTIC, or HYBRID. Natural language doesn't follow simple patterns — "What are the payment terms?" requires semantic search; "Show invoices above ₹50,000" requires structured search. An LLM understands intent better than regex.

See [docs/TRADEOFFS.md](docs/TRADEOFFS.md) for all 10 key decisions with alternatives considered and consequences.

## What's Inside

### Extractor Registry (Plugin System)
Every extractor implements:
```python
class Extractor(ABC):
    def supports(self, document: DocumentInput) -> float: ...
    async def extract(self, document: DocumentInput) -> CanonicalDocument: ...
```

The registry selects the highest-scoring extractor. Currently registered:
- **ResumeExtractor** (score 0.9 for resumes) — Deterministic extraction (email, phone, LinkedIn) + LLM semantic extraction (name, skills, experience, education)
- **GenericExtractor** (score 0.1 for any PDF) — Fallback with text extraction, chunking, embeddings, and lightweight metadata

### Three Retrieval Strategies
- **StructuredRetriever** — JSONB containment queries on `structured_fields` and `entities` columns
- **SemanticRetriever** — pgvector cosine distance search (< 0.8 threshold) against chunk embeddings
- **HybridRetriever** — Structured pre-filtering (limit 50) followed by semantic search over the filtered subset

### Explainable Answers
Every response includes:
- **Answer text** — LLM synthesis for semantic/hybrid, direct formatting for structured
- **Source references** — Document name, page number, excerpt
- **Execution trace** — Strategy used, steps taken, result counts

No fabricated confidence scores. Trust comes from evidence.

### LLM Provider Abstraction
Swap between OpenAI-compatible APIs and Ollama with one environment variable. All model interactions pass through a common interface.

## Extensibility

Adding a new document type is straightforward. Example: CSV support.

```python
# backend/extractors/csv_extractor.py
from extractors.base import Extractor, DocumentInput
from models.canonical_document import CanonicalDocument

class CSVExtractor(Extractor):
    def supports(self, document: DocumentInput) -> float:
        if document.filename.lower().endswith('.csv'):
            return 0.9
        return 0.0

    async def extract(self, document: DocumentInput) -> CanonicalDocument:
        # Parse CSV, populate structured_fields with columns/rows
        # Return CanonicalDocument
        pass
```

```python
# backend/extractors/registry.py — in create_default_registry()
from extractors.csv_extractor import CSVExtractor

def create_default_registry(store, llm_provider, embedding_provider):
    return ExtractorRegistry([
        CSVExtractor(store, llm_provider, embedding_provider),
        ResumeExtractor(store, llm_provider, embedding_provider),
        GenericExtractor(store, llm_provider, embedding_provider),
    ])
```

Done. The pipeline runs unchanged. See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for how to add extractors, LLM providers, and retrieval strategies.

## Testing & Quality

100 tests across 19 files covering:
- Extractor registry selection and scoring
- Generic extractor threshold logic (small vs. large documents)
- Canonical schema validation
- Query planner routing (structured/semantic/hybrid)
- Structured retrieval (JSONB queries)
- Semantic search (pgvector cosine distance)
- Hybrid retrieval (combined results)
- Answer composer (prompt verification, dispatch logic)
- Document store CRUD operations
- LLM provider initialization and completion
- Embedding generation and error handling

```bash
cd backend
.venv/bin/python -m pytest ../tests/ -v
```

DB-dependent tests require running PostgreSQL:
```bash
docker compose up -d
.venv/bin/python -m pytest ../tests/ -v
```

Type checking and linting:
```bash
cd backend
.venv/bin/python -m mypy .
.venv/bin/python -m ruff check .
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15.1, TypeScript, Tailwind |
| Backend | FastAPI, Python 3.11, Pydantic, SQLAlchemy 2.0 (async) |
| Database | PostgreSQL 16 + pgvector (HNSW index) |
| Embeddings | FastEmbed (BAAI/bge-small-en-v1.5, 384-dim) |
| LLM | OpenAI-compatible APIs or Ollama |
| PDF Parsing | pypdf |
| Text Splitting | langchain-text-splitters |
| Migrations | Alembic |
| Testing | pytest + pytest-asyncio |
| Linting | Ruff |
| Type Checking | mypy (strict mode) |
| Containerization | Docker Compose (3 services) |

## Project Structure

```
backend/              FastAPI application
  api/routes/         REST endpoints (health, documents, query)
  extractors/         Plugin-based document extractors
  query/              Query planner, classifier, retrievers
  answers/            Answer composer
  llm/                LLM provider abstraction
  embeddings/         Embedding provider abstraction
  storage/            Database connection, document store
  models/             Pydantic models, SQLAlchemy ORM

frontend/             Next.js application
  src/app/            Single-page UI
  src/components/     Upload, query, answer display
  src/hooks/          React hooks for state management
  src/lib/            API client, TypeScript types

docs/                 Architecture, tradeoffs, contributing guide
tests/                Backend test suite (100 tests)
```

## Known Limitations

- **Entity extraction disabled** — Commented out in `GenericExtractor` to speed up uploads. Re-enable by uncommenting lines 97-102 in `backend/extractors/generic.py`.
- **PDF only** — The plugin architecture supports any format, but only PDF extractors are implemented.
- **No CI/CD** — Tests run locally. No GitHub Actions, no automated deployment.
- **Single git commit** — The repository shows the final state, not incremental development.
- **Sample PDF quality** — `Akshit_Bansal_Resume.pdf` works well; the original `sample_technical_document.pdf` was image-dominant and produced poor extraction results.

## API

```bash
# Upload
curl -X POST -F "file=@document.pdf" http://localhost:8000/documents/upload

# List documents
curl http://localhost:8000/documents/

# Query
curl -X POST -H "Content-Type: application/json" \
  -d '{"query":"What is the email address?"}' \
  http://localhost:8000/query
```

## License

MIT
