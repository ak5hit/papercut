# Phase 13: Upload Pipeline Transparency

## Objective

Show the user exactly what happened during document upload — which extractor ran, what pipeline steps were executed, and what fields were extracted. Replace the opaque spinner with a transparent, step-by-step pipeline trace.

## Context

- **Phases 3–12** built the complete application: extraction pipeline, query pipeline, answer composer, evaluation harness, frontend.
- **The query pipeline** already has a transparency mechanism — `ExecutionTrace` captures every step (classification, retrieval, composition) and renders as an expandable component in the frontend. The query response includes `strategy`, `steps[]`, `structured_results_count`, and `semantic_results_count`.
- **The upload pipeline** has zero transparency. A user uploading a resume sees only a spinner, then a one-line success message: `"Uploaded: resume.pdf (2 pages)"`. They have no idea whether `ResumeExtractor` or `GenericExtractor` ran, what fields were extracted, or how many chunks were created.
- **This is inconsistent** with the query side's execution trace and misses an opportunity to demonstrate the plugin architecture in action.
- **Per AGENTS.md:** "User should never need to understand the architecture. Always prioritize simplicity, transparency, trust." A blank spinner is not transparent.

## Design Decision: Pre-computed Trace vs Streaming

### What we chose

A pre-computed `PipelineTrace` returned in the upload response as a complete object. The frontend renders all steps at once after the upload completes.

### Why

- **Builds on existing pattern.** The query's `ExecutionTrace` already works this way — all steps are available after the query completes. Consistency is valuable.
- **Minimal complexity.** No Server-Sent Events, no WebSockets, no streaming infrastructure. The backend computes the trace as it processes the document, returns it in the final response.
- **FastAPI's SSE support** would require refactoring the upload endpoint to use `StreamingResponse`, managing an async generator, and handling client disconnection. This is an avoidable ~3+ hour complexity cost.
- **In an interview demo**, seeing all steps at once is sufficient to demonstrate the pipeline. Real-time streaming is a production need, not a demo need.

### What we rejected

Server-Sent Events (SSE) for real-time step-by-step streaming during upload.

### Consequences

- Steps appear all-at-once, not one-by-one. The user sees the full trace after upload completes.
- For very large documents (which take 30+ seconds), the user still sees a spinner during processing. This is acceptable per AGENTS.md simplicity guidance.

## Scope

### In Scope

- `PipelineTrace` dataclass — trace model capturing extractor name, steps, and field summary
- `Extractor.extract()` interface change — returns `(CanonicalDocument, PipelineTrace)`
- `ResumeExtractor` — populates PipelineTrace with resume-specific steps
- `GenericExtractor` — populates PipelineTrace with generic steps
- `ExtractorRegistry.process()` — returns `(CanonicalDocument, PipelineTrace)`
- `POST /documents/upload` — includes `pipeline_trace` in JSON response
- `frontend/src/lib/types.ts` — `PipelineTrace` interface
- `frontend/src/components/upload-pipeline.tsx` — new component rendering the trace
- `frontend/src/hooks/use-upload.ts` — store full response including `pipeline_trace`
- `frontend/src/app/page.tsx` — render `UploadPipeline` after successful upload
- All existing tests updated for the new return signature
- New tests for PipelineTrace population

### Out of Scope

- Streaming/SSE for real-time step display
- Persisting pipeline traces to the database (traces are transient)
- Adding pipeline trace visibility to query flow (already has ExecutionTrace)
- Automatic document type detection via content analysis
- Progress percentage or estimated time remaining

---

## Files to Create

| File | Purpose |
|------|---------|
| `backend/extractors/pipeline_trace.py` | `PipelineTrace` dataclass |
| `frontend/src/components/upload-pipeline.tsx` | Frontend component rendering the upload trace |

## Files to Modify

| File | Change |
|------|--------|
| `backend/extractors/base.py` | Change `extract()` return type from `CanonicalDocument` to `tuple[CanonicalDocument, PipelineTrace]` |
| `backend/extractors/resume.py` | Create and populate `PipelineTrace` during extraction |
| `backend/extractors/generic.py` | Create and populate `PipelineTrace` during extraction |
| `backend/extractors/registry.py` | `process()` returns `tuple[CanonicalDocument, PipelineTrace]`; import `PipelineTrace` |
| `backend/api/routes/documents.py` | Destructure the tuple; include `pipeline_trace` in upload response JSON |
| `frontend/src/lib/types.ts` | Add `PipelineTrace` interface |
| `frontend/src/hooks/use-upload.ts` | Store full `DocumentWithTrace` response; add `lastTrace` to return value |
| `frontend/src/app/page.tsx` | Render `UploadPipeline` component after successful upload |
| `tests/test_extractor_registry.py` | Update mocks to return `(doc, trace)` tuples |
| `tests/test_query_planner.py` | Update mocks to return `ClassificationResult` (already done in prior phase) — **no change needed to this file** |

### Files NOT Touched

- `backend/models/canonical_document.py` — PipelineTrace is NOT part of the canonical schema
- `backend/models/db_models.py` — PipelineTrace is NOT persisted
- `backend/query/` — No changes to query pipeline
- `backend/answers/` — No changes to answer composer
- `backend/storage/` — No changes to document store
- `backend/llm/` — No changes to LLM providers
- `backend/embeddings/` — No changes to embedding providers
- `frontend/src/components/upload-dropzone.tsx` — Still passes `(file, documentType)` to `onUpload`
- `frontend/src/components/document-list.tsx` — Already shows `document_type`
- `frontend/src/components/execution-trace.tsx` — Unchanged (used for queries only)
- `frontend/src/lib/api-client.ts` — `uploadDocument()` already returns `Document`, no type change needed at the HTTP layer; the new `pipeline_trace` field is additive in the JSON

---

## Step 1: `PipelineTrace` Dataclass

### File: `backend/extractors/pipeline_trace.py`

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineTrace:
    extractor: str
    steps: list[dict[str, str]] = field(default_factory=list)
    extracted_fields: dict[str, Any] = field(default_factory=dict)

    def add_step(self, description: str, detail: str | None = None) -> None:
        step: dict[str, str] = {"step": description}
        if detail:
            step["detail"] = detail
        self.steps.append(step)

    def set_extracted_fields(self, fields: dict[str, Any]) -> None:
        self.extracted_fields = fields

    def to_dict(self) -> dict[str, Any]:
        return {
            "extractor": self.extractor,
            "steps": self.steps,
            "extracted_fields": self.extracted_fields,
        }
```

### Design rationale

- `steps` is a `list[dict[str, str]]`, not `list[str]`, so each step can carry a `detail` field (e.g., `"detail": "12,345 characters"`). This gives the frontend more rendering flexibility.
- `extracted_fields` is a flat dict of key field names to values. For ResumeExtractor, this contains `name`, `email`, `phone`, `skills`, `experience_count`, `education_count`. For GenericExtractor, it contains `page_count`, `total_characters`, etc.
- `add_step()` and `set_extracted_fields()` are builder methods called inline during extraction.
- `to_dict()` produces the JSON shape the frontend expects.

---

## Step 2: Change the `Extractor` Interface

### File: `backend/extractors/base.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

from models.canonical_document import CanonicalDocument
from extractors.pipeline_trace import PipelineTrace


@dataclass(frozen=True)
class DocumentInput:
    content: bytes
    filename: str
    content_type: str | None = None
    document_type: str | None = None


class Extractor(ABC):
    @abstractmethod
    def supports(self, document: DocumentInput) -> float:
        ...

    @abstractmethod
    async def extract(self, document: DocumentInput) -> tuple[CanonicalDocument, PipelineTrace]:
        ...
```

### Change detail

- `extract()` now returns `tuple[CanonicalDocument, PipelineTrace]` instead of `CanonicalDocument`.
- This is the ONLY interface change. `supports()` and `DocumentInput` are unchanged.
- Every extractor implementation must be updated. Currently two: `GenericExtractor` and `ResumeExtractor`.

---

## Step 3: Update `ResumeExtractor.extract()`

### File: `backend/extractors/resume.py`

The `extract()` method is updated to create a `PipelineTrace` and add steps at each stage.

#### Step trace for ResumeExtractor

```
1. "Selected extractor: ResumeExtractor"
   detail: "score=0.9"
2. "Extracted text from N pages"
   detail: "12,345 characters"
3. "Extracted deterministic fields"
   detail: "email, phone, linkedin_url"
4. "Extracted semantic fields via LLM"
   detail: "name, skills, experience, education"  (only if llm_provider is available; skipped otherwise)
5. "Created N chunks"
   detail: "1000 chars, 100 overlap"
6. "Generated N embeddings"
   detail: "384-dim, BAAI/bge-small-en-v1.5"  (only if embedding_provider is available)
7. "Saved to database"
```

#### Extracted fields summary

```python
{
    "name": "John Doe",          # or None
    "email": "john@example.com", # or None
    "phone": "+91-9876543210",   # or None
    "skills": ["Python", "JavaScript", "SQL"],
    "experience_count": 3,
    "education_count": 2,
    "total_experience_years": 5, # or None
}
```

#### Code changes in `extract()`

The method structure becomes:

```python
async def extract(self, document: DocumentInput) -> tuple[CanonicalDocument, PipelineTrace]:
    trace = PipelineTrace(extractor="ResumeExtractor")
    trace.add_step("Selected extractor: ResumeExtractor", "score=0.9")

    text, page_metadata, pages = self._extract_text(document.content)
    trace.add_step(f"Extracted text from {len(page_metadata)} pages", f"{len(text)} characters")

    metadata = self._build_metadata(document, page_metadata)
    doc = CanonicalDocument.create(raw_text=text, metadata=metadata, extraction_strategy="resume")

    deterministic_fields = self._extract_deterministic(text)
    present_fields = [k for k, v in deterministic_fields.items() if v]
    if present_fields:
        trace.add_step("Extracted deterministic fields", ", ".join(present_fields))

    semantic_fields = await self._extract_semantic(text)
    semantic_present = [k for k, v in semantic_fields.items() if v and v != []]
    if semantic_present:
        trace.add_step("Extracted semantic fields via LLM", ", ".join(semantic_present))

    doc.structured_fields = self._merge_fields(deterministic_fields, semantic_fields)
    doc.entities = self._build_entities(doc.structured_fields)

    chunks = self._create_chunks(pages, doc.id)
    trace.add_step(f"Created {len(chunks)} chunks", "1000 chars, 100 overlap")

    await self.document_store.save_document(doc)
    await self.document_store.save_chunks(chunks)

    if self.embedding_provider:
        texts = [chunk.text for chunk in chunks]
        embeddings = self.embedding_provider.embed(texts)
        await self.document_store.save_chunk_embeddings(doc.id, embeddings)
        await self.document_store.update_embedding_status(doc.id, "completed")
        doc.embedding_status = "completed"
        trace.add_step(f"Generated {len(chunks)} embeddings", "384-dim, bge-small-en-v1.5")
    else:
        await self.document_store.update_embedding_status(doc.id, "failed")
        doc.embedding_status = "failed"

    trace.add_step("Saved to database")

    # Build extracted fields summary
    fields_summary = {
        "name": doc.structured_fields.get("name"),
        "email": doc.structured_fields.get("email"),
        "phone": doc.structured_fields.get("phone"),
        "skills": doc.structured_fields.get("skills", []),
        "experience_count": len(doc.structured_fields.get("experience", [])),
        "education_count": len(doc.structured_fields.get("education", [])),
        "total_experience_years": doc.structured_fields.get("total_experience_years"),
    }
    trace.set_extracted_fields(fields_summary)

    return doc, trace
```

---

## Step 4: Update `GenericExtractor.extract()`

### File: `backend/extractors/generic.py`

#### Step trace for GenericExtractor (small document)

```
1. "Selected extractor: GenericExtractor"
   detail: "score=0.1"
2. "Extracted text from N pages"
   detail: "45,678 characters"
3. "Document classified as small"
   detail: "< 100K characters"
4. "Extracted structured fields"
   detail: "page_count, total_characters, detected_emails, detected_phone_numbers"
5. "Created N chunks"
   detail: "1000 chars, 100 overlap"
6. "Generated N embeddings"
   detail: "384-dim, bge-small-en-v1.5"
7. "Saved to database"
```

#### Step trace for GenericExtractor (large document)

```
1. "Selected extractor: GenericExtractor"
   detail: "score=0.1"
2. "Extracted text from N pages"
   detail: "450,678 characters"
3. "Document classified as large"
   detail: ">= 100K characters"
4. "Skipped structured field extraction"
   detail: "large documents use lightweight metadata only"
5. "Created N chunks"
   detail: "500 chars, 50 overlap"
6. "Generated N embeddings"
   detail: "384-dim, bge-small-en-v1.5"
7. "Saved to database"
```

#### Code changes

Same pattern as ResumeExtractor — create `PipelineTrace` at the top, add steps as each stage completes, return `(doc, trace)`.

For small documents:
```python
trace.set_extracted_fields({
    "page_count": len(page_metadata),
    "total_characters": len(text),
    "total_chunks": len(chunks),
    "detected_emails": doc.structured_fields.get("detected_emails", []),
    "detected_phone_numbers": doc.structured_fields.get("detected_phone_numbers", []),
})
```

For large documents:
```python
trace.set_extracted_fields({
    "page_count": len(page_metadata),
    "total_characters": len(text),
    "total_chunks": len(chunks),
})
```

---

## Step 5: Update `ExtractorRegistry.process()`

### File: `backend/extractors/registry.py`

```python
from extractors.pipeline_trace import PipelineTrace

async def process(self, document: DocumentInput) -> tuple[CanonicalDocument, PipelineTrace]:
    extractor = self.select(document)
    return await extractor.extract(document)
```

This is a one-line change. The `process()` method now destructures and returns the tuple from `extract()`.

---

## Step 6: Update Upload Endpoint

### File: `backend/api/routes/documents.py`

```python
@router.post("/upload", status_code=201)
async def upload_document(
    file: UploadFile,
    document_type: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
    _ready: None = Depends(_require_ready),
) -> dict[str, Any]:
    ...
    document, pipeline_trace = await registry.process(document_input)

    return {
        "id": str(document.id),
        "filename": document.metadata.get("filename"),
        "page_count": document.metadata.get("page_count"),
        "extraction_strategy": document.extraction_strategy,
        "embedding_status": document.embedding_status,
        "entities_count": len(document.entities),
        "relationships_count": len(document.relationships),
        "document_type": document.structured_fields.get("document_type"),
        "pipeline_trace": pipeline_trace.to_dict(),
        "created_at": document.created_at.isoformat(),
    }
```

The `pipeline_trace` field is added to the existing response JSON. All existing fields remain unchanged — this is purely additive.

---

## Step 7: Frontend Types

### File: `frontend/src/lib/types.ts`

Add new interfaces:

```typescript
export interface PipelineTraceStep {
  step: string;
  detail?: string;
}

export interface PipelineTrace {
  extractor: string;
  steps: PipelineTraceStep[];
  extracted_fields: Record<string, unknown>;
}

export interface Document {
  id: string;
  filename: string;
  page_count: number;
  extraction_strategy: string;
  embedding_status: "pending" | "completed" | "failed";
  document_type: string | null;
  pipeline_trace?: PipelineTrace;   // NEW
  created_at: string;
}
```

`pipeline_trace` is optional on `Document` because it only appears in the upload response, not in the list documents response.

---

## Step 8: Frontend Component — `UploadPipeline`

### File: `frontend/src/components/upload-pipeline.tsx` (NEW)

Similar to `ExecutionTrace` but with key UX differences:

1. **Always expanded.** After upload completes, the user wants to see the trace immediately. No collapse toggle.
2. **Green checkmarks** for each step to convey success.
3. **Extracted fields section** at the bottom showing a preview of what was extracted.
4. **Extractor badge** prominently displayed at the top.

```tsx
"use client";

import { CheckCircle2, Cpu, Hash, Mail, Phone, Briefcase } from "lucide-react";
import type { PipelineTrace as PipelineTraceType } from "@/lib/types";

interface UploadPipelineProps {
  trace: PipelineTraceType;
}

export function UploadPipeline({ trace }: UploadPipelineProps) {
  return (
    <div className="bg-white border rounded-lg shadow-sm overflow-hidden">
      {/* Extractor badge header */}
      <div className="bg-blue-50 border-b px-4 py-3 flex items-center gap-2">
        <Cpu className="h-4 w-4 text-blue-600" />
        <span className="font-medium text-sm text-blue-800">
          Extractor: {trace.extractor}
        </span>
      </div>

      {/* Pipeline steps */}
      <div className="px-4 py-3 space-y-2">
        {trace.steps.map((step, i) => (
          <div key={i} className="flex items-start gap-2">
            <CheckCircle2 className="h-4 w-4 text-green-600 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm text-gray-700">{step.step}</p>
              {step.detail && (
                <p className="text-xs text-gray-500">{step.detail}</p>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Extracted fields section */}
      {trace.extracted_fields && Object.keys(trace.extracted_fields).length > 0 && (
        <div className="border-t px-4 py-3">
          <p className="text-xs font-semibold text-gray-500 uppercase mb-2">
            Extracted Fields
          </p>
          <div className="grid grid-cols-2 gap-2 text-sm">
            {Object.entries(trace.extracted_fields).map(([key, value]) => (
              <div key={key} className="flex items-start gap-1">
                <span className="text-gray-500 shrink-0">{key}:</span>
                <span className="text-gray-800 font-medium truncate">
                  {Array.isArray(value)
                    ? value.join(", ")
                    : value !== null && value !== undefined
                    ? String(value)
                    : "—"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

---

## Step 9: Update `useUpload` Hook

### File: `frontend/src/hooks/use-upload.ts`

Add `lastTrace` to the return value, alongside `lastUploaded`:

```typescript
import type { Document, PipelineTrace } from "@/lib/types";

export function useUpload() {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUploaded, setLastUploaded] = useState<Document | null>(null);
  const [lastTrace, setLastTrace] = useState<PipelineTrace | null>(null);

  const upload = useCallback(async (file: File, documentType?: string) => {
    setUploading(true);
    setError(null);
    setLastTrace(null);
    try {
      const doc = await uploadDocument(file, documentType);
      setLastUploaded(doc);
      setLastTrace(doc.pipeline_trace || null);
      return doc;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Upload failed";
      setError(msg);
      throw err;
    } finally {
      setUploading(false);
    }
  }, []);

  return { upload, uploading, error, lastUploaded, lastTrace };
}
```

---

## Step 10: Update `page.tsx`

### File: `frontend/src/app/page.tsx`

Import `UploadPipeline` and render it after a successful upload:

```tsx
import { UploadPipeline } from "@/components/upload-pipeline";
```

Change the `useUpload` destructuring:
```tsx
const { upload, uploading, error: uploadError, lastUploaded, lastTrace } = useUpload();
```

In the Upload section, replace the simple success message with the pipeline component:

```tsx
// Before:
{lastUploaded && (
  <p className="text-sm text-green-600">
    Uploaded: {lastUploaded.filename} ({lastUploaded.page_count} pages)
  </p>
)}

// After:
{lastUploaded && lastTrace && (
  <>
    <p className="text-sm text-green-600 font-medium">
      Uploaded: {lastUploaded.filename} ({lastUploaded.page_count} pages)
    </p>
    <UploadPipeline trace={lastTrace} />
  </>
)}
```

The simple success message stays (it's a quick confirmation), and the pipeline trace appears below it with full detail.

---

## Step 11: Test Updates

### 11.1 Existing Test Changes

The interface change from `extract() -> CanonicalDocument` to `extract() -> tuple[CanonicalDocument, PipelineTrace]` requires updating ALL tests that mock `extract()`:

| Test File | Affected Tests | Change |
|-----------|---------------|--------|
| `test_extractor_registry.py` | `test_process_delegates_to_selected_extractor` | Mock `extract()` returns `(doc, PipelineTrace(...))` instead of `doc` |
| `test_entity_extraction.py` | `test_generic_extractor_with_llm_provider`, `test_generic_extractor_llm_failure`, `test_generic_extractor_malformed_json` | These call `extract()` on the GenericExtractor. The test assertions verify the `CanonicalDocument` — destructure `doc, _ = await extractor.extract(...)` |

Files NOT requiring changes:
- `test_generic_extractor.py` — Tests already call `extract()` and assert on `CanonicalDocument`. Just destructure the tuple: `doc, trace = await ...`.
- `test_query_planner.py` — Already updated in the ResumeExtractor phase to use `ClassificationResult`. No further changes needed.
- `test_query_classifier.py` — Already updated. No changes.
- `test_answer_composer.py` — Does not call extractors. No changes.
- `test_structured_retriever.py` — No changes.

### 11.2 New Test File: `tests/test_pipeline_trace.py`

| Test | What It Verifies |
|------|-----------------|
| `test_trace_creation` | `PipelineTrace` created with extractor name and empty steps |
| `test_add_step` | Steps are appended correctly with description and optional detail |
| `test_add_step_without_detail` | Step without detail has no `detail` key in dict |
| `test_set_extracted_fields` | Fields dict is stored and accessible |
| `test_to_dict_serialization` | `to_dict()` produces correct JSON-serializable shape with all keys |
| `test_no_mutation_of_returned_dict` | Calling `add_step()` after `to_dict()` does NOT affect previously returned dict (or does — we just test the current behavior) |

### 11.3 New Test File: `tests/test_resume_pipeline_trace.py`

| Test | What It Verifies |
|------|-----------------|
| `test_resume_extractor_populates_trace` | `extract()` returns a `PipelineTrace` with 6-8 steps |
| `test_trace_contains_extractor_name` | `trace.extractor == "ResumeExtractor"` |
| `test_trace_contains_deterministic_step` | One step mentions "deterministic fields" |
| `test_trace_contains_llm_step` | One step mentions "semantic fields via LLM" (when LLM available) |
| `test_trace_extracted_fields_populated` | `trace.extracted_fields` contains `name`, `email`, `phone`, `skills`, experience/education counts |
| `test_trace_skip_llm_step_when_no_provider` | When `llm_provider=None`, the LLM step is absent |
| `test_trace_skip_embedding_step_when_no_provider` | When `embedding_provider=None`, the embedding step is absent |

### 11.4 New Test File: `tests/test_generic_pipeline_trace.py`

| Test | What It Verifies |
|------|-----------------|
| `test_generic_small_trace_steps` | Small doc trace includes "classified as small" step |
| `test_generic_small_trace_fields` | `extracted_fields` includes `page_count`, `total_characters`, `detected_emails` |
| `test_generic_large_trace_steps` | Large doc trace includes "classified as large" and "skipped structured" steps |
| `test_generic_large_trace_fields` | Large doc `extracted_fields` does NOT include `detected_emails` |
| `test_trace_title_mentions_generic` | `trace.extractor == "GenericExtractor"` |

---

## Step 12: Verification Checklist

### 12.1 Type Checking

```bash
cd backend
.venv/bin/python -m mypy .
```

Expected: zero errors. The `tuple[CanonicalDocument, PipelineTrace]` return type must pass strict type checking.

### 12.2 Linting

```bash
cd backend
.venv/bin/python -m ruff check .
```

Expected: zero issues.

### 12.3 Unit Tests

```bash
.venv/bin/python -m pytest ../tests/ -v
```

Expected: all existing tests pass, plus ~15 new tests.

### 12.4 Frontend Build

```bash
cd frontend
npm run build
```

Expected: TypeScript compiles with zero errors. The `UploadPipeline` component renders without type issues.

### 12.5 Docker Validation

```bash
docker compose down -v && docker compose up --build
```

Verify:
- Application starts without errors
- Database connects successfully
- Upload a PDF with `document_type=resume` — response includes `pipeline_trace` with steps
- Upload a PDF with auto-detect — response includes `pipeline_trace` from GenericExtractor

### 12.6 Manual Smoke Test

1. Open `http://localhost:3000`
2. Wait for embedding model to load (readiness indicator disappears)
3. Upload a PDF with **Resume / CV** document type
4. **Verify:** After upload, the `UploadPipeline` component appears showing:
   - Extractor: "ResumeExtractor" badge
   - All pipeline steps with green checkmarks
   - Extracted fields summary (name, email, phone, skills, etc.)
5. Upload a PDF with **Auto-detect** document type
6. **Verify:** `UploadPipeline` shows "GenericExtractor"
7. Ask a question — verify query flow still works exactly as before

---

## Deviation Log

None at plan time. Deviations made during implementation must be documented here with rationale.

---

## Risk Mitigation

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Interface change breaks existing tests | High | Update all test mocks to return tuples. A mechanical change — run tests first to find every failure, then fix systematically. |
| Frontend type mismatch (`pipeline_trace` missing from list endpoint) | Medium | Make `pipeline_trace` optional in `Document` interface. The list endpoint doesn't return it — it's only in the upload response. |
| Large extracted fields (e.g., 20 skills) overflow the grid layout | Low | Use `truncate` CSS and allow expansion. The fields section is a grid — long arrays are joined by comma. |
| LLM extraction failure produces misleading trace | Low | The trace reports what WAS attempted, not whether it succeeded. If LLM fails, the "Extracted semantic fields" step still appears with present fields only. Graceful degradation is already handled. |

---

## What NOT to Do

| Don't | Because |
|-------|---------|
| Add `pipeline_trace` to `CanonicalDocument` | `CanonicalDocument` is the universal data output. Pipeline trace is transient metadata about the extraction process. Mixing them violates separation of concerns. |
| Persist `PipelineTrace` to the database | Traces are ephemeral. Storing them adds a table, migration, and cleanup burden with no query-time value. |
| Use SSE/WebSockets for real-time streaming | Adds ~3 hours of complexity (async generators, StreamingResponse, client-side event handling, error recovery). Not justified for this phase. |
| Show `null` as a string in extracted fields | Filter out `None`/`null` values in the frontend — show "—" instead. |
| Change the `upload-dropzone.tsx` component signature | The dropzone already passes `(file, documentType)` to `onUpload`. The pipeline trace is rendered AFTER upload completes — no change needed here. |
| Change the `Document` interface to require `pipeline_trace` | The list endpoint response doesn't include pipeline traces. Making it required would break the document list rendering. |

---

## Post-Phase State

After Phase 13:

```
backend/
├── extractors/
│   ├── base.py              MODIFIED (extract() return type changed)
│   ├── generic.py           MODIFIED (populates PipelineTrace)
│   ├── pipeline_trace.py    NEW
│   ├── registry.py          MODIFIED (process() returns tuple)
│   ├── resume.py            MODIFIED (populates PipelineTrace)
│   └── __init__.py          UNCHANGED
├── api/routes/
│   └── documents.py         MODIFIED (includes pipeline_trace in response)

frontend/src/
├── components/
│   ├── upload-pipeline.tsx  NEW
│   └── execution-trace.tsx  UNCHANGED (used only for queries)
├── hooks/
│   └── use-upload.ts        MODIFIED (returns lastTrace)
├── lib/
│   └── types.ts             MODIFIED (PipelineTrace, PipelineTraceStep interfaces)
├── app/
│   └── page.tsx             MODIFIED (renders UploadPipeline on success)

tests/
├── conftest.py              UNCHANGED
├── test_extractor_registry.py        MODIFIED (mocks return tuples)
├── test_generic_extractor.py         MODIFIED (destructure trace from extract())
├── test_entity_extraction.py         MODIFIED (destructure trace from extract())
├── test_pipeline_trace.py            NEW (~6 tests)
├── test_resume_pipeline_trace.py     NEW (~7 tests)
├── test_generic_pipeline_trace.py    NEW (~5 tests)
└── (all other test files)   UNCHANGED
```
