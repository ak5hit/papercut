# Engineering Tradeoffs

Every architectural choice involved an intentional tradeoff. This document captures the key decisions, alternatives considered, and consequences of each choice.

---

### 1. Modular Monolith

**What we chose:** A single FastAPI backend with three Docker containers (db, backend, frontend). All business logic in one process.

**Why:** Simpler to develop, deploy, and debug. A reviewer can understand the entire system in minutes. The problem domain (document intelligence) does not require horizontal scaling of independent services.

**What we rejected:** Microservices, Kafka, event-driven architectures, Kubernetes.

**Consequences:** Scales vertically rather than horizontally. If the application grows to serve thousands of concurrent users, services would need to be extracted. For an interview submission showing engineering judgement, simplicity wins.

---

### 2. PostgreSQL + pgvector (Persistent)

**What we chose:** PostgreSQL 16 with the pgvector extension for embedding storage and ANN search. HNSW index for fast vector retrieval.

**Why:** PostgreSQL provides persistence, transactional guarantees, and the ability to join structured and vector queries in a single database. One database for both structured fields and embeddings. Data survives container restarts.

**What we rejected:** Qdrant in-memory (data vanishes on restart), Pinecone, Weaviate, Milvus.

**Consequences:** pgvector ANN performance is not state-of-the-art compared to dedicated vector databases. For a single-user system with under 10,000 chunks, this is irrelevant. The simplicity of one database outweighs marginal performance gains.

---

### 3. FastEmbed (Local, Free)

**What we chose:** FastEmbed with BAAI/bge-small-en-v1.5 — 384-dimensional embeddings generated locally with no API calls.

**Why:** Zero cost, zero latency from network calls, no API key dependency. The model produces high-quality embeddings at 384 dimensions — compact enough for fast retrieval, expressive enough for semantic search.

**What we rejected:** OpenAI Embeddings API (cost per token, network latency, API key dependency), SentenceTransformers (heavier dependency).

**Consequences:** Embedding quality is lower than OpenAI's `text-embedding-3-large` (3,072 dimensions). For a document Q&A system with RAG retrieval, the BGE model is more than sufficient. The 130 MB model downloads on first use (~30s), which slows initial Docker startup.

---

### 4. Structured Answers: Direct Formatting

**What we chose:** When the query planner routes to `STRUCTURED`, results are formatted directly from database records. No LLM call is made for answer generation.

**Why:** Deterministic queries ("What is the total amount?", "Show invoices above ₹50,000") produce deterministic results. Wrapping them in an LLM would introduce hallucination risk, latency, and cost for no benefit. The system should not narrate known facts.

**What we rejected:** All answers going through an LLM synthesis step.

**Consequences:** Structured answers are terse and tabular — they don't read like natural language prose. This is intentional. The execution trace shows the user exactly how the answer was produced.

---

### 5. LLM-Based Query Classification

**What we chose:** An LLM prompt classifies each user query as `STRUCTURED`, `SEMANTIC`, or `HYBRID` before execution.

**Why:** Natural language queries don't follow simple patterns. "What are the payment terms in the AWS contract?" requires semantic search. "Show all invoices above ₹1 lakh" requires structured search. An LLM understands intent better than regex or keyword matching.

**What we rejected:** Rule-based regex classifiers, keyword matching, hardcoded route tables.

**Consequences:** Classification adds one LLM call per query (~0.5s latency, ~100 tokens). On failure, falls back to `SEMANTIC`. The classifier prompt is simple and deterministic in practice (temperature 0.0).

---

### 6. Single-Page Frontend

**What we chose:** A single Next.js page with three sections — upload dropzone, document list, query interface. No routing, no multi-page navigation.

**Why:** The core user flow is linear: upload, see document, ask question. One page makes this obvious. Less code, fewer components, simpler mental model for both users and reviewers.

**What we rejected:** Multi-page app with separate routes for upload, documents, and query. Complex React Router or Next.js App Router navigation.

**Consequences:** The UI would feel cramped with many documents or long conversation histories. For an interview submission showing the core flow end-to-end, a single page is ideal.

---

### 7. File Uploads Bypass Next.js Proxy

**What we chose:** File uploads in the frontend POST directly to `http://backend:8000/documents/upload`, bypassing the Next.js API proxy.

**Why:** Next.js API routes load the entire request body into memory on the server. For 8 MB+ PDFs, this causes memory pressure and can crash the Node.js process. The backend's FastAPI handles streaming multipart uploads efficiently.

**What we rejected:** Uploading through `app/api/[...path]/route.ts` proxy, using Next.js API routes for file handling.

**Consequences:** The frontend needs to know the backend URL directly. CORS is already open (`allow_origins=["*"]`). In production, a reverse proxy like nginx would handle this at the infrastructure layer.

---

### 8. GenericExtractor Size Threshold

**What we chose:** Documents below 100,000 characters get full LLM extraction (entities, structured fields). Documents at or above this threshold get only chunking and embeddings — no LLM extraction.

**Why:** Large documents exceed LLM context windows or become prohibitively expensive to process. Extracting entities from a 500-page contract is impractical. Chunking + embeddings provides semantic search without the cost.

**What we rejected:** Always running full LLM extraction on every document (expensive, slow, context-window-limited), never running LLM extraction (loses entity and structured field data for small documents).

**Consequences:** Large documents cannot answer structured queries ("total contract value") unless that information is captured through chunk-level semantic search, which is less precise. The tradeoff is explicitly documented. For structured extraction of large documents, a specialized extractor is the intended path.

---

### 9. CanonicalDocument (Unified Schema)

**What we chose:** All extractors output a `CanonicalDocument` with the same fields: `metadata`, `raw_text`, `structured_fields`, `entities`, `relationships`, `extraction_strategy`, `embedding_status`.

**Why:** Downstream modules (storage, query, embeddings, answer composition) should never depend on document-specific schemas. Adding a new document type should not require changes to the query planner or retrieval layer.

**What we rejected:** Per-document-type schemas (InvoiceDocument, ContractDocument, EmailDocument) with type-specific query logic.

**Consequences:** The schema is intentionally generic. Structured fields are stored as `dict[str, Any]` (JSONB), which sacrifices type safety at the schema level. Querying structured fields requires knowledge of what keys a given extractor produces — the system relies on the extractor's documentation rather than compile-time guarantees.
