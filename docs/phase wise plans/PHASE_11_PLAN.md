# Phase 11: Testing and Stabilization

## Objective

Systematically verify the entire codebase across all prior phases. Run every check from the Phase Completion Checklist, identify and fix any accumulated issues, and ensure the system is production-stable before Phase 12 final polish. No new features.

## Context

- **Phases 1–10** built the complete application. Some phases shipped with documented deviations (e.g., Phase 3: null-byte sanitization; Phase 10: RAGAS version pinning, `asyncio.to_thread()` for sync RAGAS).
- **Phase 10 checklist** had several unchecked items: manual smoke test of evaluation with actual documents and LLM was not completed.
- **Known gotchas** from `AGENTS.md`:
  - Docker Compose volumes persist across restarts (`pgdata` carries stale state)
  - DB-dependent tests require running PostgreSQL on `localhost:5432`
  - Frontend lint is intentionally not enforced (Next.js 15.1 + ESLint 9.x bug)
- **Current test count:** 17 test files across `tests/`
- **Backend:** ~50 Python source files, ~20 test files
- **Frontend:** Next.js 15.1 + TypeScript + Tailwind, single-page app

## Scope

### In Scope

- Run every check from the AGENTS.md Phase Completion Checklist
- Fix any issues found (type errors, lint errors, test failures, build failures, Docker issues)
- Verify test quality (no vacuous tests, mocks at correct boundaries)
- Code cleanup (unused imports, dead code, TODO/FIXME removal)
- Verify legacy files still parse correctly (`eval_pipeline.py`, `agent_graph.py`, `ingest_and_search.py`)
- Check for stale Docker state and document how to reset
- Manual smoke test of the complete end-to-end flow in Docker
- Re-run the full validation pipeline after every fix

### Out of Scope

- New features or API endpoints
- Phase 12 deliverables (README, architecture diagrams, seed documents)
- Performance optimization
- Refactoring for refactoring's sake

---

## 1. Stabilization Procedure

Phase 11 is executed as a sequence of verification passes. Each pass identifies issues. All identified issues are fixed before the next pass begins. The phase is complete only when a full clean pass succeeds with zero issues.

```
Pass 1: Static Analysis (type check + lint)
    |
    ▼ (if issues found → fix → restart from Pass 1)
Pass 2: Unit Tests (non-DB)
    |
    ▼ (if issues found → fix → restart from Pass 1)
Pass 3: Unit Tests (DB-dependent)
    |
    ▼ (if issues found → fix → restart from Pass 1)
Pass 4: Build Verification (backend + frontend)
    |
    ▼ (if issues found → fix → restart from Pass 1)
Pass 5: Docker Validation
    |
    ▼ (if issues found → fix → restart from Pass 1)
Pass 6: Manual Smoke Test
    |
    ▼ (if issues found → fix → restart from Pass 1)
Pass 7: Code Quality Review
    |
    ▼ (if issues found → fix → restart from Pass 1)
DONE
```

---

## 2. Pass 1: Static Analysis

### 2.1 Backend Type Checking

Run:
```bash
cd backend
.venv/bin/python -m mypy . --strict
```

Expected: zero errors in source files. Library stub warnings for `fastembed` and `pgvector` are acceptable (already ignored in `pyproject.toml`).

**Known issue to watch for:** `ragas==0.4.3` may have missing type stubs. If mypy reports import errors for `ragas` modules, add them to `ignore_missing_imports` in `pyproject.toml`.

### 2.2 Backend Linting

Run:
```bash
cd backend
.venv/bin/python -m ruff check .
```

Expected: zero issues.

**Watch for:**
- Unused imports (likely accumulated across 10 phases)
- Dead code in `__init__.py` files
- Missing `__all__` in new packages

### 2.3 Frontend Type Checking

Run:
```bash
cd frontend
npm run build
```

Expected: TypeScript compilation succeeds with zero type errors.

**Note:** `next lint` is intentionally absent per AGENTS.md. `npm run build` is the type-safety check.

---

## 3. Pass 2: Unit Tests (Non-DB)

Run:
```bash
cd backend
.venv/bin/python -m pytest ../tests/ -v -m "not db"
```

Or exclude DB-dependent tests by marker if not available:
```bash
cd backend
.venv/bin/python -m pytest ../tests/test_health.py ../tests/test_models.py ../tests/test_embeddings.py ../tests/test_llm_provider.py ../tests/test_extractor_registry.py ../tests/test_query_classifier.py ../tests/test_answer_models.py -v
```

Expected: All non-DB tests pass.

---

## 4. Pass 3: Unit Tests (DB-Dependent)

Prerequisite: PostgreSQL running on `localhost:5432`.

```bash
docker compose up -d db
```

Run:
```bash
cd backend
.venv/bin/python -m pytest ../tests/test_document_store.py ../tests/test_generic_extractor.py ../tests/test_semantic_search.py ../tests/test_structured_retriever.py ../tests/test_query_planner.py ../tests/test_answer_composer.py ../tests/test_hybrid_retriever.py ../tests/test_evaluation.py -v
```

Expected: All DB-dependent tests pass.

**Known gotcha:** If migrations appear to have run but tables don't exist, the `pgdata` volume may have stale `alembic_version` stamps. Reset per AGENTS.md:

```bash
docker compose exec db psql -U postgres -d doc_intelligence -c "DELETE FROM alembic_version;"
docker compose exec backend alembic upgrade head
```

Or destroy volume entirely:
```bash
docker compose down -v
docker compose up -d db
```

---

## 5. Pass 4: Build Verification

### 5.1 Backend Build

Backend has no explicit build step (Python), but verify all imports resolve:

```bash
cd backend
.venv/bin/python -c "from main import app; print('Import OK')"
```

Expected: No `ImportError` or `ModuleNotFoundError`.

**Watch for:** Legacy `eval_pipeline.py` imports `agent_graph` which imports `ingest_and_search`. This chain should still work because the root `requirements.txt` has all legacy deps. Do NOT test legacy import chain if it would pull in conflicting packages — just verify the files parse with `python -m py_compile`.

### 5.2 Frontend Build

```bash
cd frontend
npm run build
```

Expected:
- `next build` completes successfully
- `output: 'standalone'` produces `.next/standalone/` directory
- No TypeScript errors
- No compilation errors

---

## 6. Pass 5: Docker Validation

### 6.1 Full Rebuild

```bash
docker compose down -v  # destroy stale state
docker compose up --build
```

Wait for all three services to report healthy status.

Verify:
- [ ] `db` service passes healthcheck (`pg_isready`)
- [ ] `backend` service starts without import errors
- [ ] Alembic migrations run successfully (check logs for `001_create_documents.py` and `002_add_embeddings.py`)
- [ ] `frontend` service builds successfully and starts on port 3000
- [ ] `curl http://localhost:8000/health` → `{"status":"ok"}`
- [ ] `curl http://localhost:8000/health/db` → database connected
- [ ] `curl http://localhost:3000` → returns HTML (200 OK)

### 6.2 CORS Verification

```bash
curl -H "Origin: http://localhost:3000" \
     -H "Access-Control-Request-Method: POST" \
     -X OPTIONS \
     -I http://localhost:8000/query
```

Expected: `access-control-allow-origin: *` in response headers.

---

## 7. Pass 6: Manual Smoke Test

### 7.1 Clean-Slate Setup

```bash
docker compose down -v  # ensure no stale documents or state
docker compose up --build
```

### 7.2 Test Steps

1. **Open frontend:** Navigate to `http://localhost:3000`
2. **Verify landing page:** Title "Document Intelligence Platform" visible
3. **Upload document:** Use `sample_technical_document.pdf` (or any test PDF)
4. **Verify upload feedback:**
   - Success message with filename and page count
   - Document appears in Documents list
   - `embedding_status` shows `completed` (may take a moment for FastEmbed model download)
5. **Query — Structured:**
   - Ask "What is the total amount?" (or similar if document has structured fields)
   - Verify answer contains formatted structured data (`**key:** value`)
   - Verify trace shows `strategy: structured`
6. **Query — Semantic:**
   - Ask "Summarize the document"
   - Verify synthesized answer appears
   - Verify sources section is collapsible and shows chunk excerpts
   - Verify trace shows `strategy: semantic`
7. **Query — Hybrid-style:**
   - Ask a question combining concrete filter + semantic request
   - Verify trace shows `strategy: hybrid`
   - Verify both documents and chunks appear in sources
8. **Error handling:**
   - Submit empty query → error message shown
   - Query with backend temporarily stopped → error message shown
9. **Verify no console errors:** Check browser dev tools for JavaScript errors
10. **Verify no backend errors:** Check `docker compose logs backend` for exceptions

---

## 8. Pass 7: Code Quality Review

### 8.1 Unused Imports

Run:
```bash
cd backend
.venv/bin/python -m ruff check . --select F401
```

Fix all `F401` (unused import) violations.

### 8.2 Dead Code

Run:
```bash
cd backend
.venv/bin/python -m ruff check . --select F841
```

Fix all `F841` (unused variable) violations.

### 8.3 TODO / FIXME Audit

Search codebase for `TODO`, `FIXME`, `HACK`, `XXX`:
```bash
grep -r "TODO\|FIXME\|HACK\|XXX" /Users/akshitbansal/Projects/multi-agent-intelligence/backend --include="*.py"
grep -r "TODO\|FIXME\|HACK\|XXX" /Users/akshitbansal/Projects/multi-agent-intelligence/frontend/src --include="*.ts" --include="*.tsx"
```

Resolution rules:
- If it's a quick fix (<5 min), fix it.
- If it requires new features, remove the comment and create a note in `docs/FUTURE.md` (if creating Phase 12 deliverables) or leave for post-submission.
- If it's a known limitation that should be documented, move it to the appropriate `.md` file.

### 8.4 Test Quality Audit

For every test file, verify:

1. **No trivial assertions:** No `isinstance(x, list)` without content checks.
2. **No vacuous passes:** Every test exercises the actual code path (not empty input that bypasses logic).
3. **Mocks at correct boundaries:** External I/O (HTTP, database, file system) is mocked; internal business logic is NOT mocked.
4. **Specific value assertions:** Prefer `assert result == expected` over `assert result is not None`.

High-value tests to review carefully:
- `test_extractor_registry.py` — selection logic
- `test_generic_extractor.py` — threshold behavior, small/large document paths
- `test_query_planner.py` — routing to structured/semantic/hybrid
- `test_structured_retriever.py` — JSONB query behavior
- `test_answer_composer.py` — strategy-aware composition
- `test_evaluation.py` — harness orchestration

### 8.5 Legacy File Verification

> **Phase 11 cleanup:** These legacy files were moved to `legacy/` during cleanup. They are no longer at project root. Kept for reference — not imported or used by the modern application.

The legacy files (`legacy/eval_pipeline.py`, `legacy/agent_graph.py`, `legacy/ingest_and_search.py`) were verified to parse correctly before the move:

```bash
cd /Users/akshitbansal/Projects/multi-agent-intelligence
python -m py_compile eval_pipeline.py
python -m py_compile agent_graph.py
python -m py_compile ingest_and_search.py
```

Expected: All three compile without syntax errors.

**Do NOT** attempt to run them — they require the legacy venv packages and may conflict with the backend's pinned versions.

---

## 9. Known Issues to Address

Based on deviations documented in prior phase plans:

| Issue | Source Phase | Resolution in Phase 11 |
|-------|-------------|----------------------|
| `langchain-community==0.4.1` pin needed in backend requirements | Phase 10 | Verify pin is present and sufficient |
| RAGAS `evaluate()` sync in async harness needs `asyncio.to_thread()` | Phase 10 | Verify wrapper is in place and working |
| `sys.path` manipulation in `alembic/env.py` | Phase 3 | Verify still necessary; remove if alembic now works without it |
| Null-byte sanitization in `pdf_ingester.py` | Phase 3 | Verify still handles `\x00` correctly |
| `pydantic-settings` version bump (2.9.1 → 2.10.1) | Phase 2 | Verify no compatibility issues |
| Frontend proxy uses `app/api/[...path]/route.ts` instead of static rewrites | Phase 9 | Verify proxy works correctly in Docker |
| Frontend Dockerfile uses `node .next/standalone/server.js` | Phase 9 | Verify CMD still works with current Next.js version |
| `embedding_id` column in DB is unused but present | Phase 6 | Leave as-is (breaking change to remove); document in code comment if not already |

---

## 10. Files Summary

### Modified (as-needed during stabilization)

Any file with a type error, lint error, test failure, or code quality issue gets modified. No predetermined file list — discovered during verification passes.

Potential candidates based on prior deviations:

| File | Possible Issue |
|------|---------------|
| `backend/pyproject.toml` | May need additional `ignore_missing_imports` for RAGAS |
| `backend/requirements.txt` | May need version bumps or additional pins |
| Various `__init__.py` | May have unused imports (F401) |
| Various test files | May have vacuous assertions or wrong mock boundaries |
| `backend/alembic/env.py` | May no longer need `sys.path` manipulation |

### Created (1)

| File | Purpose |
|------|---------|
| `docs/PHASE_11_PLAN.md` | This plan document |

### Deleted (as-needed)

Any file that is truly dead (not imported by anything, not documented, not part of the legacy foundation) should be removed. Candidates:
- `__pycache__` directories in tests and backend
- Any temporary files created during development

---

## 11. Deviation Protocol

Phase 11 is the stabilization phase where deviations from ALL prior plans are identified and corrected. Any deviation discovered during Phase 11 must be:

1. Flagged explicitly.
2. Documented with the reason.
3. Fixed if it's a bug or code quality issue.
4. If it's an acceptable architectural choice, updated in the relevant plan document.

No silent deviations are acceptable.

---

## 12. Phase Completion Checklist

Phase 11 is NOT complete until ALL of the following pass in a single clean run:

- [ ] `mypy .` (backend) — zero errors in source files
- [ ] `ruff check .` (backend) — zero issues
- [ ] `pytest -v` (non-DB tests) — all pass
- [ ] `pytest -v` (DB tests, with PostgreSQL running) — all pass
- [ ] `npm run build` (frontend) — zero TypeScript errors
- [ ] `docker compose down -v && docker compose up --build` — all services start
- [ ] `curl /health` and `/health/db` — both return OK
- [ ] CORS preflight from `localhost:3000` to backend — `access-control-allow-origin: *`
- [ ] Manual smoke test (all 10 steps in Section 7.2) — pass
- [ ] Legacy files `eval_pipeline.py`, `agent_graph.py`, `ingest_and_search.py` — all parse without syntax errors
- [ ] No `TODO`/`FIXME`/`HACK` comments remain in production code
- [ ] No unused imports or dead code (per `ruff --select F401,F841`)
- [ ] No import errors when running `python -c "from main import app"` from backend directory

If ANY check fails:

1. **STOP.**
2. Diagnose root cause.
3. Fix the issue.
4. **Re-run the ENTIRE validation pipeline from Pass 1.**
5. Do not proceed to Phase 12 until all checks pass.

---

## 13. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Fixing one issue introduces another | Re-run the full validation pipeline after every fix, not just the failing check |
| Docker volume state corruption | Always start Pass 5/6 with `docker compose down -v` to ensure clean state |
| Test flakiness (timing-dependent async tests) | Run DB tests multiple times; if flaky, add `pytest-rerunfailures` or fix race condition |
| RAGAS dependencies causing import errors in Docker | Verify `langchain-community==0.4.1` pin is present and working in fresh image |
| Frontend build breaks due to Node.js version mismatch | Dockerfile uses `node:20-alpine` which is stable |
| `mypy` strict mode reports false positives in third-party code | Already configured `ignore_missing_imports` for `fastembed`, `pgvector`; add `ragas` if needed |

---

## 14. Success Criteria

After Phase 11, a reviewer should be able to:

1. Clone the repository.
2. `cp .env.example .env`
3. `docker compose up --build`
4. Open `http://localhost:3000`
5. Upload a PDF, wait for processing, ask questions, receive explainable answers.
6. Run `cd backend && .venv/bin/python -m pytest ../tests/ -v` and see all tests pass.
7. See zero type errors, zero lint issues, and zero TODOs in the codebase.
8. Understand that this is a stable, production-ready demonstration of engineering judgment.

Every check must pass. No exceptions. No skipped tests. No ignored errors.
