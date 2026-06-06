# Universal Document Intelligence Platform

## Vision

Build a platform that transforms arbitrary unstructured or semi-structured documents into a structured, queryable knowledge base.

The goal is not simply to "chat with PDFs", but to build a document intelligence engine that supports both deterministic business queries and semantic reasoning.

Examples:

* "What is the total AWS spend?"
* "Summarize the payment obligations."
* "Show contracts mentioning AWS with invoices above ₹1 lakh."

---

# Design Philosophy

Modern document systems require two complementary capabilities:

1. Structured retrieval for deterministic facts.
2. Semantic retrieval for natural language understanding.

Rather than treating every question as a vector search problem, the platform separates symbolic knowledge from semantic context.

---

# High Level Architecture

```
                Upload
                   │
          Text Extraction
                   │
          Extractor Registry
                   │
    ┌──────────────┴──────────────┐
    │                             │
Specialized                 Generic
Extractors                  Extractor
    │                             │
    └──────────────┬──────────────┘
                   │
          Canonical Document
                   │
            Schema Validation
                   │
       ┌───────────┴───────────┐
       │                       │
Structured Storage      Embedding Pipeline
       │                       │
       └───────────┬───────────┘
                   │
          PostgreSQL + pgvector
                   │
            Query Planner
                   │
    Structured / Semantic / Hybrid
                   │
          Answer Composer
                   │
      Sources + Execution Trace
```

---

# Existing Foundation

The project builds upon an existing hybrid RAG implementation which already provides:

* PDF ingestion
* Recursive chunking
* Dense + sparse hybrid retrieval
* Retrieval evaluation using RAGAS

Rather than rewriting these components, the system evolves them into a production-oriented architecture.

---

# Extractor Registry

Every extractor implements a common interface.

```python
class Extractor:

    def supports(document) -> float:
        ...

    def extract(document) -> CanonicalDocument:
        ...
```

The registry selects the highest scoring extractor.

Future extractors should be plug-and-play.

Examples:

* GenericExtractor
* InvoiceExtractor
* ContractExtractor
* EmailExtractor
* XMLExtractor

---

# Generic Extractor

The Generic Extractor acts as the fallback implementation.

## Small Documents

If document size is below a configurable threshold:

* Full document LLM extraction
* Entity extraction
* Structured field generation
* Embedding generation

## Large Documents

If document size exceeds the threshold:

* Chunking
* Embedding generation
* Lightweight metadata extraction

Large documents intentionally avoid expensive full-document LLM extraction due to context window and cost limitations.

---

# Canonical Document

Every extractor emits a common internal representation.

```python
CanonicalDocument:

    id
    metadata
    raw_text
    structured_fields
    entities
    relationships
    extraction_strategy
    embedding_status
```

Downstream systems should never depend on document-specific schemas.

---

# Query Planner

Incoming queries are classified into one of three categories.

## Structured

Examples:

* Total AWS spend
* Show invoices above ₹50,000

Execution:

Structured database query.

---

## Semantic

Examples:

* Summarize payment obligations.
* Explain termination clauses.

Execution:

Hybrid retrieval + LLM.

---

## Hybrid

Examples:

* Show AWS contracts with invoices above ₹1 lakh.

Execution:

Structured retrieval + semantic retrieval + LLM synthesis.

---

# LLM Provider Abstraction

The system should not depend on a specific provider.

All model interactions should pass through a common interface.

Supported providers:

* OpenCode models
* OpenAI-compatible APIs
* Ollama (optional)

External API models are the default choice.

---

# Explainability

The platform should never expose fabricated confidence scores.

Every answer should contain:

* Source documents
* Page references
* Execution trace

Example:

Execution Trace

✓ Routed to Hybrid Search

✓ Retrieved 4 structured records

✓ Retrieved 3 semantic chunks

✓ Generated final response

---

# Extensibility

Future contributors should be able to add new extractors, retrieval strategies, or model providers without modifying the core pipeline.

The architecture should follow the Open-Closed Principle wherever possible.
