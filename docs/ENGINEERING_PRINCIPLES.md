# Purpose

This repository is an engineering interview submission.

The objective is not maximum technical complexity.

The objective is to demonstrate good engineering judgement, product thinking, maintainability, and execution quality.

---

# Core Principles

Prefer:

* Simplicity
* Clarity
* Extensibility
* Explainability

Avoid:

* Premature optimization
* Unnecessary abstractions
* Over-engineering
* Complex distributed systems

Every piece of complexity must justify itself.

---

# Architecture Principles

## Modular Monolith

Keep the system as a modular monolith.

Frontend and backend may be separate containers, but business logic should remain cohesive.

Do not introduce:

* Microservices
* Kafka
* Event sourcing
* Kubernetes

---

## Build On Existing Components

Reuse working components whenever possible.

Prefer refactoring over rewriting.

The existing hybrid retrieval and evaluation pipelines should be preserved.

---

## Plugin Architecture

New extractors should be plug-and-play.

Adding a new extractor should require only:

1. Create extractor.
2. Register extractor.

No other pipeline changes should be necessary.

---

## Separation of Concerns

Extractors generate CanonicalDocuments.

Embedding generation is a separate indexing concern.

Retrieval is separate from ingestion.

Query planning is separate from answer generation.

---

# Product Principles

The user should never need to understand the architecture.

The experience should feel simple.

Upload documents.

Wait for processing.

Ask questions.

Receive answers with evidence.

---

# Explainability

Every answer should include:

* Sources
* Page references
* Execution trace

Do not expose arbitrary LLM confidence scores.

Trust should come from evidence.

---

# Code Quality

Prefer readable code over clever code.

Small functions.

Clear naming.

Minimal comments.

Good folder structure.

Every module should have a single responsibility.

---

# Technology Stack

Frontend:

* Next.js
* TypeScript
* Tailwind
* shadcn/ui

Backend:

* FastAPI
* Python
* Pydantic

Database:

* PostgreSQL
* pgvector

Storage:

* Local filesystem

LLM:

* External API providers
* Provider abstraction layer

---

# Testing Philosophy

Test behavior.

Do not chase coverage numbers.

Important tests:

* Extractor Registry selection
* Generic Extractor threshold logic
* Canonical schema validation
* Query Planner routing
* Structured retrieval
* Hybrid retrieval

Existing tests must never break.

---

# Phase Completion Rules

A phase is NOT complete until all checks pass.

Run:

* type checking
* linting
* unit tests
* application build
* docker compose startup
* manual smoke test

If any check fails:

STOP.

Fix the issue completely.

Do not proceed to the next phase.

---

# Setup Experience

A reviewer should only need:

```
cp .env.example .env

docker compose up --build
```

The application should start successfully and contain sample documents for exploration.

---

# Reviewer Experience

Assume the reviewer has fifteen minutes.

They should be able to:

1. Run the project.
2. Upload or use sample documents.
3. Query the system.
4. Understand the architecture.
5. See the engineering tradeoffs.

Every decision should optimize for this experience.
