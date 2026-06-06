# Purpose

This repository is an engineering interview submission.

The goal is NOT to maximize technical complexity.

The goal is to demonstrate strong engineering judgement, product thinking, maintainability, and clean execution.

Always optimize for reviewer experience.

---

# Core Philosophy

Prefer:

* Simplicity
* Clarity
* Extensibility
* Explainability

Avoid:

* Clever hacks
* Unnecessary abstractions
* Premature optimization
* Over-engineering

Every piece of complexity must justify itself.

---

# What We Are Building

A universal document intelligence platform.

Documents are transformed into a canonical internal representation and become queryable through both:

* Structured retrieval
* Semantic retrieval

The system should not simply be "chat with PDF".

---

# Architectural Rules

## Modular Monolith

Keep everything inside a single application.

Do NOT introduce:

* Microservices
* Kafka
* Event sourcing
* Kubernetes
* Complex distributed architectures

---

## Plugin-Based Extraction

Every extractor implements:

```typescript
interface Extractor {
    supports(document): number;
    extract(document): Promise<CanonicalDocument>;
}
```

Adding a new extractor should require only:

1. Create new extractor.
2. Register extractor.

The rest of the pipeline must remain unchanged.

---

## Generic Extractor

GenericExtractor is the fallback implementation.

Small documents:

* Full LLM extraction
* Entity extraction
* Structured fields
* Embeddings

Large documents:

* Chunking
* Embeddings
* Lightweight metadata extraction

Do NOT attempt full-document LLM extraction for very large files.

This is an intentional engineering tradeoff.

---

## Canonical Schema

All extractors output the same CanonicalDocument.

Never let downstream modules depend on document-specific structures.

---

## Query Planner

Queries must be routed into:

* STRUCTURED
* SEMANTIC
* HYBRID

Do not answer deterministic questions using semantic search if structured data exists.

---

# UX Principles

User should never need to understand the architecture.

Always prioritize:

* Simplicity
* Transparency
* Trust

Every answer should include:

* Source documents
* Page references
* Execution trace

Never expose fabricated LLM confidence scores.

---

# Code Quality

Prefer readable code over clever code.

Small functions.

Clear naming.

Minimal comments.

Good folder structure.

Every module should have a single responsibility.

---

# Build Incrementally

Never implement multiple phases at once.

Complete exactly one phase.

Then stabilize the codebase.

Then move forward.

---

# Plan Deviation Protocol

Every field, method, and behavior specified in the phase plan must appear in the implementation.

If the implementation deviates from the plan:

1. Flag it explicitly during review.
2. Document why the deviation was made.
3. Update the phase plan to reflect reality.

Silent deviations are not acceptable. A reviewer comparing the plan to the code should find exact correspondence, or a documented reason for any difference.

---

# Phase Completion Checklist

A phase is NOT complete until ALL of the following succeed.

## 1. Type Checking

Run:

```bash
npm run typecheck
```

Fix every error.

No ignored errors.

No temporary hacks.

---

## 2. Linting

Run:

```bash
npm run lint
```

Resolve all issues.

Do not disable lint rules unless absolutely necessary.

**Note:** The frontend (`frontend/package.json`) intentionally has no `lint` script because `next lint` has known circular-reference bugs with ESLint 9.x and Next.js 15.1. TypeScript validation during `next build` is the type-safety check for the frontend. Add a working lint configuration only when upgrading to a version that supports it.

---

## 3. Unit Tests

Run:

```bash
npm run test
```

All existing tests must continue passing.

Add tests for newly introduced behavior.

---

## 4. Build Verification

Run:

```bash
npm run build
```

Application must compile successfully.

---

## 5. Docker Validation

Run:

```bash
docker compose up --build
```

Verify:

* Application starts
* Database connects
* No startup errors
* Existing functionality works

---

## 6. Manual Smoke Test

Verify the core user flow.

For example:

* Upload document
* Process document
* Query document
* Receive valid answer

Ensure no regression has been introduced.

---

## 7. Fix Before Proceeding

If ANY check fails:

STOP.

Fix the issue completely.

Do not start the next phase until the current phase is stable.

---

# Review Checklist

When reviewing a completed phase, follow this sequence:

1. **Read the phase plan** — understand every specified field, method, behavior, and test.
2. **Read the implementation** — compare line-by-line against the plan. Flag any deviation.
3. **Run static checks** — type checking and linting must pass with zero errors.
4. **Run all tests** — existing tests must not break. New tests must cover new behavior.
5. **Assess test quality** — no trivial assertions, no vacuous passes, mocks at correct boundaries.
6. **Build and start Docker** — image builds, services start, no import errors.
7. **Smoke test the core flow** — upload, process, query, verify response shape and values.
8. **Verify deletions** — files marked for deletion in the plan must actually be gone.
9. **Check for stale state** — Docker volumes, migration stamps, leftover data from prior phases.

A review is not complete until every step passes or a fix is applied and re-verified.

---

# Known Environment Gotchas

## Docker Compose Volumes Persist Across Restarts

`docker compose down` does NOT remove named volumes. The `pgdata` volume survives, carrying stale database state including `alembic_version` stamps.

If migrations appear to have run but tables don't exist:

```bash
docker compose exec db psql -U postgres -d doc_intelligence -c "DELETE FROM alembic_version;"
docker compose exec backend alembic upgrade head
```

Or destroy the volume entirely:

```bash
docker compose down -v
docker compose up --build
```

## Python Virtual Environment

All Python commands must use the project venv:

```bash
.venv/bin/python -m mypy .
.venv/bin/python -m ruff check .
.venv/bin/python -m pytest ../tests/ -v
```

## DB-Dependent Tests Require Running PostgreSQL

Tests using the `session` fixture connect to `localhost:5432`. Run `docker compose up -d` before executing DB tests, or they will fail with connection refused errors.

## Frontend File Uploads Bypass Next.js API Routes

Send file uploads directly to the backend (`http://<host>:<backend-port>`), not through Next.js API route handlers. API routes load the entire request body into memory, which breaks for large files (PDFs, images, CSVs). Reserve API routes for small JSON requests. Backend CORS is already open (`allow_origins=["*"]`).

## Frontend Lint Is Not Enforced

`next lint` has known circular-reference bugs with ESLint 9.x and Next.js 15.1. The TypeScript build (`next build`) already validates types, which is sufficient. The `lint` script is intentionally absent from `frontend/package.json` — do not add it back. Add proper ESLint configuration only when upgrading to a version that supports it.

---

# Testing Philosophy

Test behavior.

Do not chase coverage numbers.

High-value tests include:

* Extractor Registry selection
* Generic Extractor threshold logic
* Canonical schema validation
* Query Planner routing
* Structured query execution
* Hybrid retrieval behavior

A few meaningful tests are better than many trivial tests.

---

# Test Quality Standards

Every test must verify real behavior.

**Forbidden patterns:**

* `isinstance(x, list)` — proves nothing about content
* Tests that pass on empty or blank input without exercising the code path
* Mocks that bypass the logic under test

**Required patterns:**

* Mock at the correct boundary (e.g., external I/O, not internal methods)
* Assert specific values, not just types
* Verify ordering, counts, and content where applicable
* Null-byte and edge-case tests must inject actual problematic data, not rely on benign input

A test that passes vacuously is worse than no test. It creates false confidence.

---

# Documentation Philosophy

Every important architectural decision should be easy to explain.

Future contributors should understand:

* Why this exists.
* Why this approach was chosen.
* What alternatives were rejected.

Optimize for maintainability.

---

# Reviewer Experience

Assume the reviewer has 15 minutes.

They should be able to:

1. Clone repository.
2. Copy .env.
3. Run docker compose up --build.
4. Open the application.
5. Upload or use sample documents.
6. Understand the architecture quickly.
7. Leave with the impression that this was built by a thoughtful engineer.

Every implementation decision should improve this experience.

---

# Golden Rule

When choosing between two implementations:

Choose the solution that is easier to explain, easier to maintain, and more likely to impress an experienced engineer reviewing the repository.
