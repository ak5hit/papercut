# Document Intelligence Platform

Universal document intelligence with structured and semantic retrieval. Not just "chat with PDF."

## Quick Start

```bash
cp .env.example .env
# Edit .env — set OPENAI_API_KEY for cloud LLM, or set LLM_PROVIDER=ollama for local
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000) and upload `sample_technical_document.pdf` from the repo root.

> **Note:** `sample_technical_document.pdf` is image-dominant (1 page, 8.4 MB). Text extraction is limited. For best results, use a text-based PDF.

## What It Does

1. **Upload** a PDF through the web UI or API.
2. The system **extracts text, chunks it, generates embeddings**, and runs LLM entity extraction on small documents.
3. **Ask questions** in natural language.
4. Receive **answers with source references, page numbers, and an execution trace** showing exactly what happened.

## Key Features

- **Structured Retrieval** — Deterministic queries against JSONB fields (totals, counts, filters). No LLM narration of known facts.
- **Semantic Retrieval** — Vector similarity search via pgvector and FastEmbed (384-dim BGE embeddings).
- **Hybrid Retrieval** — Structured pre-filtering followed by semantic search over the filtered subset.
- **Explainable Answers** — Every response shows source documents, page references, and an execution trace.
- **Plugin Extractors** — Add new document types by creating one class. The pipeline doesn't change.
- **LLM Abstraction** — Swap between OpenAI-compatible APIs and Ollama through one environment variable.

## Architecture

```
User (Browser) → Next.js (:3000) → FastAPI (:8000) → PostgreSQL 16 + pgvector
                                                    → LLM Provider (OpenAI / Ollama)
                                                    → Embedding Provider (FastEmbed)
                                                    → Extractor Registry (plugin system)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for Mermaid diagrams covering the ingestion pipeline, query pipeline, and plugin architecture.

## File: sample_technical_document.pdf

An 8.4 MB sample PDF is included in the repo root for immediate testing.

- **Content:** Scanned/image-dominant (1 page). Text extraction is limited.
- **Recommendation:** Use your own text-based PDF for better results.
- **How to use:** Upload via the web UI or with `curl` (see below).

## API

```bash
# Upload
curl -X POST -F "file=@sample_technical_document.pdf" http://localhost:8000/documents/upload

# List documents
curl http://localhost:8000/documents/

# Query
curl -X POST -H "Content-Type: application/json" \
  -d '{"query":"Summarize this document"}' \
  http://localhost:8000/query
```

## Testing

```bash
cd backend
.venv/bin/python -m pytest ../tests/ -v
```

> DB-dependent tests require a running PostgreSQL. Run `docker compose up -d` first.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15.1, TypeScript, Tailwind, shadcn/ui |
| Backend | FastAPI, Python 3.11, Pydantic, SQLAlchemy 2.0 |
| Database | PostgreSQL 16 + pgvector (HNSW index) |
| Embeddings | FastEmbed (BAAI/bge-small-en-v1.5, 384-dim) |
| LLM | OpenAI-compatible APIs or Ollama |
| Evaluation | RAGAS (Faithfulness, Context Precision) |

## Project Structure

```
backend/         FastAPI application — extractors, query planner, LLM, embeddings, API
frontend/        Next.js application — single-page upload + query interface
docs/            Architecture, tradeoffs, contributing, phase plans
tests/           Backend test suite (pytest + pytest-asyncio)
legacy/          Original prototype files (superseded, preserved for reference)
```

## Engineering Tradeoffs

See [docs/TRADEOFFS.md](docs/TRADEOFFS.md) for the 10 key decisions behind this architecture — what was chosen, why, and what was rejected.

## Contributing

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for how to add extractors, LLM providers, and retrieval strategies.

## License

MIT
