# Engineering Tradeoffs

Every architectural choice involved an intentional tradeoff. This document captures the five most impactful decisions.

---

### 1. Modular Monolith

**What we chose:** A single FastAPI backend with three Docker containers (db, backend, frontend). All business logic in one process.

**Why:** Simpler to develop, deploy, and debug. A reviewer can understand the entire system in minutes. The problem domain does not require horizontal scaling of independent services.

**What we rejected:** Microservices, Kafka, event-driven architectures, Kubernetes.

**Consequences:** Scales vertically rather than horizontally. For an interview submission showing engineering judgement, simplicity wins.

---

### 2. PostgreSQL + pgvector (Persistent)

**What we chose:** PostgreSQL 16 with the pgvector extension for embedding storage and ANN search. HNSW index for fast vector retrieval.

**Why:** One database for both structured fields and embeddings. Data survives container restarts and supports transactional queries.

**What we rejected:** Qdrant in-memory, Pinecone, Weaviate, Milvus.

**Consequences:** pgvector ANN performance is not state-of-the-art compared to dedicated vector databases. For a single-user system with under 10,000 chunks, this is irrelevant.

---

### 3. FastEmbed (Local, Free)

**What we chose:** FastEmbed with BAAI/bge-small-en-v1.5 — 384-dimensional embeddings generated locally.

**Why:** Zero cost, zero network latency, no API key dependency. The model produces high-quality embeddings at 384 dimensions.

**What we rejected:** OpenAI Embeddings API, SentenceTransformers.

**Consequences:** Embedding quality is lower than OpenAI's `text-embedding-3-large`. For RAG retrieval, BGE is sufficient. The 130 MB model downloads on first Docker startup.

---

### 4. LLM-Based Query Classification

**What we chose:** An LLM prompt classifies each query as `STRUCTURED`, `SEMANTIC`, or `HYBRID`.

**Why:** Natural language queries don't follow simple patterns. An LLM understands intent better than regex or keyword matching.

**What we rejected:** Rule-based regex classifiers, keyword matching.

**Consequences:** Classification adds one LLM call per query (~0.5s latency, ~100 tokens). On failure, falls back to `SEMANTIC`.

---

### 5. GenericExtractor Size Threshold

**What we chose:** Documents below 100,000 characters get full LLM extraction. Documents at or above this threshold get only chunking and embeddings.

**Why:** Large documents exceed LLM context windows or become prohibitively expensive. Chunking + embeddings provides semantic search without the cost.

**What we rejected:** Always running full LLM extraction, never running LLM extraction.

**Consequences:** Large documents cannot answer structured queries unless the information is captured through semantic search. Specialized extractors are the intended path for precise structured extraction of large documents.
