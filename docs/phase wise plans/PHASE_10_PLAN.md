# Phase 10: Evaluation — RAGAS Integration with New Architecture

## Objective

Create a new evaluation harness that measures the quality of answers produced by the modern pipeline (QueryPlanner + AnswerComposer) using the **RAGAS** framework. Measure **Faithfulness** and **Context Precision**. Keep the legacy `eval_pipeline.py` intact as foundation code. Document the evaluation methodology.

## Context

- **Phases 1–9** built the complete application: ingestion, extraction, embedding, query planning, answer composition, and a Next.js frontend.
- **Legacy evaluation:** `eval_pipeline.py` (root directory) uses RAGAS with `faithfulness` and `context_precision` metrics, a `ChatOllama` judge, and `FastEmbedEmbeddings`. It runs against the old `agent_graph.py` + `ingest_and_search.py` (Qdrant in-memory) pipeline.
- **New pipeline:** `POST /query` runs `QueryPlanner.execute()` → `AnswerComposer.compose()` and returns `{answer, sources, trace}`.
- **RAGAS requirements:** Needs `question`, `answer`, `contexts` (list of retrieved text passages), and `ground_truth` for each test case.
- **Shared venv:** Root `requirements.txt` already has `ragas`, `langchain-community==0.4.1`, `datasets`, `pandas`. Backend `requirements.txt` does not.

## Scope

### In Scope

- `backend/evaluation/` module with harness, dataset, and reporter
- Run test questions through the internal pipeline (QueryPlanner + AnswerComposer)
- Extract retrieved contexts from `QueryResult` for RAGAS consumption
- Run RAGAS `faithfulness` and `context_precision` metrics
- Judge LLM via LangChain (`ChatOllama` or OpenAI-compatible)
- Judge embeddings via LangChain (`FastEmbedEmbeddings`)
- CLI entry point `run_eval.py`
- Results output: console summary + CSV
- `docs/EVALUATION.md` methodology documentation
- Tests that verify harness assembles the dataset correctly (mock RAGAS)

### Out of Scope

- HTTP API endpoint for triggering evaluation (CLI is sufficient for a demo)
- Streaming evaluation results
- New RAGAS metrics beyond faithfulness and context_precision
- Modifying legacy `eval_pipeline.py`, `agent_graph.py`, or `ingest_and_search.py`
- Automated CI benchmark gates

---

## 1. Architecture

```
CLI: python -m evaluation.run_eval
              │
              ▼
┌─────────────────────────┐
│   EvaluationHarness     │
│   (orchestrator)        │
└──────────┬──────────────┘
           │
     ┌─────┴─────┐
     │           │
     ▼           ▼
QueryPlanner  AnswerComposer
     │           │
     └─────┬─────┘
           │ QueryResult + ComposedAnswer
           ▼
┌─────────────────────────┐
│   Context Extractor     │
│   (text serialization)  │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│   RAGAS evaluate()      │
│   faithfulness          │
│   context_precision     │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│   EvaluationReporter    │
│   console + CSV         │
└─────────────────────────┘
```

**Separation of concerns:**
- `EvaluationHarness` = orchestrates pipeline runs + RAGAS invocation
- `ContextExtractor` = converts `QueryResult` into RAGAS-compatible text contexts
- `EvaluationReporter` = formats and persists results
- `run_eval.py` = CLI entry point

---

## 2. New Module: `backend/evaluation/`

### 2.1 `backend/evaluation/__init__.py`

```python
from evaluation.harness import EvaluationHarness
from evaluation.dataset import EvaluationDataset
from evaluation.reporter import EvaluationReporter

__all__ = ["EvaluationHarness", "EvaluationDataset", "EvaluationReporter"]
```

---

### 2.2 `backend/evaluation/dataset.py`

```python
from dataclasses import dataclass


@dataclass
class EvaluationDataset:
    """A collection of test questions with expected ground-truth answers."""

    questions: list[str]
    ground_truths: list[str]

    def __post_init__(self) -> None:
        if len(self.questions) != len(self.ground_truths):
            raise ValueError(
                f"questions ({len(self.questions)}) and ground_truths "
                f"({len(self.ground_truths)}) must have the same length"
            )

    def __len__(self) -> int:
        return len(self.questions)

    def __iter__(self):
        return iter(zip(self.questions, self.ground_truths))
```

---

### 2.3 `backend/evaluation/context_extractor.py`

```python
from typing import Any

from query.result import QueryResult


class ContextExtractor:
    """Convert QueryResult retrieval output into plain-text contexts for RAGAS.

    RAGAS expects each question to have a list of retrieved text passages
    (strings) that the answer is supposedly grounded in.
    """

    @staticmethod
    def extract(result: QueryResult) -> list[str]:
        contexts: list[str] = []

        # Semantic / Hybrid: chunk texts are primary contexts
        for chunk in result.chunks:
            contexts.append(chunk["text"])

        # Structured / Hybrid: serialize structured fields as text contexts
        for doc in result.documents:
            fields = doc.get("structured_fields", {})
            if fields:
                kv_pairs = ", ".join(f"{k}={v}" for k, v in fields.items())
                contexts.append(f"Structured fields from {doc.get('metadata', {}).get('filename', 'unknown')}: {kv_pairs}")
            entities = doc.get("entities", [])
            if entities:
                entity_texts = ", ".join(
                    f"{e.get('name')} ({e.get('type')})" for e in entities
                )
                contexts.append(f"Entities: {entity_texts}")

        # RAGAS requires non-empty contexts; provide a sentinel if nothing retrieved
        if not contexts:
            contexts = ["No context was retrieved for this query."]

        return contexts
```

**Rationale:** RAGAS `contexts` must be a list of strings. For semantic retrieval, raw chunk text is the natural fit. For structured retrieval, we serialize structured_fields and entities into text so the judge can assess whether the answer is grounded in them.

---

### 2.4 `backend/evaluation/harness.py`

```python
import asyncio
from dataclasses import dataclass
from typing import Any

from datasets import Dataset

from answers.composer import AnswerComposer
from embeddings.base import EmbeddingProvider
from evaluation.context_extractor import ContextExtractor
from evaluation.dataset import EvaluationDataset
from llm.base import LLMProvider
from query.planner import QueryPlanner
from storage.document_store import DocumentStore


@dataclass
class EvaluationResult:
    overall_scores: dict[str, float]
    per_question: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_scores": self.overall_scores,
            "per_question": self.per_question,
        }


class EvaluationHarness:
    """Runs a set of test questions through the full pipeline and scores with RAGAS."""

    def __init__(
        self,
        document_store: DocumentStore,
        llm_provider: LLMProvider,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.planner = QueryPlanner(document_store, llm_provider, embedding_provider)
        self.composer = AnswerComposer(llm_provider)
        self.extractor = ContextExtractor()

    async def evaluate(self, dataset: EvaluationDataset) -> EvaluationResult:
        questions: list[str] = []
        answers: list[str] = []
        contexts: list[list[str]] = []
        ground_truths: list[str] = []

        for question, ground_truth in dataset:
            print(f"[Eval] Running: {question}")
            query_result = await self.planner.execute(question)
            composed = await self.composer.compose(question, query_result)

            questions.append(question)
            answers.append(composed.answer)
            ground_truths.append(ground_truth)
            contexts.append(self.extractor.extract(query_result))

        ragas_dataset = Dataset.from_dict({
            "question": questions,
            "answer": answers,
            "contexts": contexts,
            "ground_truth": ground_truths,
        })

        # Run RAGAS metrics
        # Note: RAGAS requires LangChain LLM / embedding objects.
        # We instantiate these directly; they are independent of the
        # system's LLMProvider abstraction.
        from langchain_community.chat_models import ChatOllama
        from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
        from ragas import evaluate
        from ragas.metrics import context_precision, faithfulness

        judge_llm = ChatOllama(model="llama3", temperature=0)
        judge_embeddings = FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")

        ragas_result = evaluate(
            ragas_dataset,
            metrics=[faithfulness, context_precision],
            llm=judge_llm,
            embeddings=judge_embeddings,
        )

        # Parse RAGAS result
        overall_scores: dict[str, float] = {}
        per_question: list[dict[str, Any]] = []

        df = ragas_result.to_pandas()
        for metric in ("faithfulness", "context_precision"):
            if metric in df.columns:
                overall_scores[metric] = round(float(df[metric].mean()), 3)

        for idx, row in df.iterrows():
            per_question.append({
                "question": row.get("question", ""),
                "answer": row.get("answer", ""),
                "ground_truth": row.get("ground_truth", ""),
                "faithfulness": round(float(row.get("faithfulness", 0)), 3),
                "context_precision": round(float(row.get("context_precision", 0)), 3),
            })

        return EvaluationResult(
            overall_scores=overall_scores,
            per_question=per_question,
        )
```

**Rationale:**
- Uses internal modules directly (not HTTP API) for direct access to `QueryResult` contexts.
- Instantiates LangChain judge objects directly. RAGAS is tightly coupled to LangChain; trying to adapt our `LLMProvider` would be complex and provide no benefit for an evaluation tool.
- The judge runs locally via Ollama (`llama3`) by default, matching the legacy pipeline's approach.

---

### 2.5 `backend/evaluation/reporter.py`

```python
import csv
from pathlib import Path
from typing import Any

from evaluation.harness import EvaluationResult


class EvaluationReporter:
    def print_summary(self, result: EvaluationResult) -> None:
        print("\n" + "=" * 50)
        print("EVALUATION RESULTS")
        print("=" * 50)

        for metric, score in result.overall_scores.items():
            print(f"  {metric}: {score}")

        print("\nPer-question breakdown:")
        for item in result.per_question:
            print(
                f"  Q: {item['question'][:60]}... "
                f"F={item['faithfulness']} CP={item['context_precision']}"
            )

        print("=" * 50)

    def save_csv(self, result: EvaluationResult, path: str | Path) -> None:
        path = Path(path)
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "question",
                    "answer",
                    "ground_truth",
                    "faithfulness",
                    "context_precision",
                ],
            )
            writer.writeheader()
            for item in result.per_question:
                writer.writerow(item)
        print(f"Saved detailed results to {path}")
```

---

### 2.6 `backend/evaluation/run_eval.py`

```python
"""CLI entry point for running evaluation.

Usage:
    cd backend
    python -m evaluation.run_eval

Requires:
    - PostgreSQL running with seeded documents
    - Ollama running with llama3 model pulled (or OPENAI_API_KEY set)
"""

import asyncio

from evaluation.dataset import EvaluationDataset
from evaluation.harness import EvaluationHarness
from evaluation.reporter import EvaluationReporter

# Internal imports for wiring
from config import settings
from embeddings import create_embedding_provider
from llm import create_llm_provider
from storage.database import async_session_factory
from storage.document_store import DocumentStore


# Demo test dataset — replace with domain-specific questions
# after uploading relevant documents.
DEFAULT_DATASET = EvaluationDataset(
    questions=[
        "What are the characteristics of an attenuated virus?",
        "What are the two main types of currently licensed vaccines?",
    ],
    ground_truths=[
        "An attenuated virus is genetically disabled or killed to prevent replication.",
        "Most licensed vaccines are subunit vaccines or attenuated microorganisms.",
    ],
)


async def main() -> None:
    print("[Eval] Initializing evaluation harness...")

    # Create a DB session for the harness
    async with async_session_factory() as session:
        store = DocumentStore(session)

        # Use the system's configured LLM provider
        llm_provider = None
        if settings.openai_api_key or settings.llm_provider == "ollama":
            llm_provider = create_llm_provider(settings)

        if llm_provider is None:
            raise RuntimeError(
                "No LLM provider configured. Set OPENAI_API_KEY or use Ollama."
            )

        embedding_provider = create_embedding_provider(settings)
        harness = EvaluationHarness(store, llm_provider, embedding_provider)

        print(f"[Eval] Running {len(DEFAULT_DATASET)} test questions...")
        result = await harness.evaluate(DEFAULT_DATASET)

    reporter = EvaluationReporter()
    reporter.print_summary(result)
    reporter.save_csv(result, "evaluation_results.csv")


if __name__ == "__main__":
    asyncio.run(main())
```

**Rationale:** `run_eval.py` is a standalone CLI script, not an API endpoint. It wires together the harness with real DB session and providers. The default test dataset mirrors the legacy `eval_pipeline.py` questions so results are comparable.

---

## 3. Dependencies

Add to `backend/requirements.txt`:

```
# Evaluation (RAGAS)
ragas>=0.1.0
 datasets>=2.14.0
 pandas>=2.0.0
```

**Version note:** The shared project venv already has `langchain-community==0.4.1`, `langgraph`, `fastembed`, etc. from the root `requirements.txt`. RAGAS should be compatible with these. If version conflicts arise during implementation, resolve them and document the fix.

**Rationale:** We add these to `backend/requirements.txt` so the backend Docker image can optionally run evaluation, even though evaluation is primarily a local dev activity.

---

## 4. Documentation

### 4.1 `docs/EVALUATION.md`

```markdown
# Evaluation Methodology

## Overview

We evaluate the document intelligence pipeline using [RAGAS](https://docs.ragas.io/)
(Retrieval-Augmented Generation Assessment).

## Metrics

### Faithfulness

Measures whether the generated answer is factually consistent with the
retrieved contexts. A score of 1.0 means every claim in the answer is supported
by the context. A score of 0.0 means no claims are supported.

### Context Precision

Measures the proportion of retrieved contexts that are relevant to answering
the question. A score of 1.0 means all retrieved passages contain information
needed for the ground-truth answer.

## Test Dataset

The default test dataset (`evaluation/run_eval.py`) contains two questions
about vaccine biology, matching the legacy evaluation pipeline for comparability.

Replace this with domain-specific questions after uploading your own documents.

## Running Evaluation

### Prerequisites

1. Documents uploaded and processed (embedding_status = completed)
2. PostgreSQL running
3. LLM provider configured (OpenAI API key or Ollama with `llama3`)

### Command

```bash
cd backend
python -m evaluation.run_eval
```

### Output

Console summary with average scores, plus `evaluation_results.csv` with
per-question breakdown.

## Architecture

```
Test Questions + Ground Truths
         │
         ▼
   QueryPlanner → AnswerComposer
         │
         ▼
   ContextExtractor (QueryResult → text)
         │
         ▼
   RAGAS evaluate(faithfulness, context_precision)
         │
         ▼
   EvaluationReporter (console + CSV)
```

## Limitations

- **Structured queries:** Context precision is less meaningful when answers
  come from exact database matches rather than ranked retrieval. The harness
  serializes structured fields into text for RAGAS, but the metric was designed
  for passage retrieval.
- **Judge LLM:** Scores depend on the judge model (default: `llama3` via Ollama).
  Different judges may produce different scores.
- **Single-turn only:** Multi-turn conversation evaluation is not supported.

## Legacy Comparison

The original `eval_pipeline.py` (root directory) evaluated the old
Qdrant-in-memory + LangGraph pipeline. The new harness evaluates the
PostgreSQL + QueryPlanner pipeline. Scores are not directly comparable
because the retrieval backend, chunking strategy, and answer generation
pipeline have all changed.
```

---

## 5. Test Plan

### `tests/test_evaluation.py`

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from evaluation.context_extractor import ContextExtractor
from evaluation.dataset import EvaluationDataset
from evaluation.harness import EvaluationHarness, EvaluationResult


class TestEvaluationDataset:
    def test_valid_dataset(self) -> None:
        ds = EvaluationDataset(
            questions=["Q1", "Q2"],
            ground_truths=["A1", "A2"],
        )
        assert len(ds) == 2

    def test_mismatched_lengths_raises(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            EvaluationDataset(questions=["Q1"], ground_truths=["A1", "A2"])


class TestContextExtractor:
    def test_extracts_chunk_text(self) -> None:
        from query.result import QueryResult
        from query.execution_trace import ExecutionTrace

        result = QueryResult(
            trace=ExecutionTrace(strategy="semantic"),
            chunks=[{"text": "Chunk one text."}, {"text": "Chunk two text."}],
        )
        contexts = ContextExtractor.extract(result)
        assert contexts == ["Chunk one text.", "Chunk two text."]

    def test_extracts_structured_fields(self) -> None:
        from query.result import QueryResult
        from query.execution_trace import ExecutionTrace

        result = QueryResult(
            trace=ExecutionTrace(strategy="structured"),
            documents=[{
                "id": "d1",
                "metadata": {"filename": "inv.pdf"},
                "structured_fields": {"total": 100},
                "entities": [{"name": "AWS", "type": "ORG"}],
                "extraction_strategy": "",
            }],
        )
        contexts = ContextExtractor.extract(result)
        assert any("total=100" in ctx for ctx in contexts)
        assert any("AWS (ORG)" in ctx for ctx in contexts)

    def test_fallback_for_empty_result(self) -> None:
        from query.result import QueryResult
        from query.execution_trace import ExecutionTrace

        result = QueryResult(trace=ExecutionTrace(strategy="structured"))
        contexts = ContextExtractor.extract(result)
        assert contexts == ["No context was retrieved for this query."]


class TestEvaluationHarness:
    @pytest.mark.asyncio
    async def test_evaluate_returns_scores(self) -> None:
        mock_store = MagicMock()
        mock_llm = AsyncMock()
        mock_embedder = MagicMock()

        harness = EvaluationHarness(mock_store, mock_llm, mock_embedder)

        dataset = EvaluationDataset(
            questions=["What is X?"],
            ground_truths=["X is Y."],
        )

        # Mock pipeline steps
        with patch.object(harness.planner, "execute", return_value=MagicMock()) as mock_plan:
            with patch.object(harness.composer, "compose", return_value=MagicMock(answer="X is Y.")) as mock_comp:
                with patch.object(harness.extractor, "extract", return_value=["ctx"]) as mock_ext:
                    with patch("evaluation.harness.evaluate") as mock_ragas:
                        # Build a mock RAGAS result DataFrame
                        import pandas as pd
                        mock_df = pd.DataFrame({
                            "question": ["What is X?"],
                            "answer": ["X is Y."],
                            "ground_truth": ["X is Y."],
                            "faithfulness": [0.85],
                            "context_precision": [0.90],
                        })
                        mock_ragas.return_value = MagicMock(to_pandas=lambda: mock_df)

                        result = await harness.evaluate(dataset)

        assert isinstance(result, EvaluationResult)
        assert result.overall_scores["faithfulness"] == 0.85
        assert result.overall_scores["context_precision"] == 0.90
        assert len(result.per_question) == 1
        mock_plan.assert_awaited_once()
        mock_comp.assert_awaited_once()
```

**Rationale:** Tests verify:
- Dataset validation behavior
- Context extraction for all three query strategies (semantic, structured, empty)
- Harness orchestration: pipeline called once per question, RAGAS called once overall
- Score parsing from the mock RAGAS result

No real LLM calls in tests — mocks at the RAGAS boundary.

---

## 6. Files Summary

### Created (7)

| File | Purpose |
|------|---------|
| `backend/evaluation/__init__.py` | Package init, re-exports |
| `backend/evaluation/dataset.py` | `EvaluationDataset` dataclass |
| `backend/evaluation/context_extractor.py` | Converts `QueryResult` → RAGAS text contexts |
| `backend/evaluation/harness.py` | `EvaluationHarness` — orchestrates pipeline + RAGAS |
| `backend/evaluation/reporter.py` | `EvaluationReporter` — console + CSV output |
| `backend/evaluation/run_eval.py` | CLI entry point |
| `docs/EVALUATION.md` | Evaluation methodology documentation |
| `tests/test_evaluation.py` | Unit tests for dataset, extractor, harness |

### Modified (1)

| File | Changes |
|------|---------|
| `backend/requirements.txt` | Add `ragas`, `datasets`, `pandas` |

### Untouched (legacy foundation)

| File | Note |
|------|------|
| `eval_pipeline.py` | Legacy Qdrant-based evaluation — preserved as foundation code |
| `agent_graph.py` | Legacy LangGraph pipeline — preserved |
| `ingest_and_search.py` | Legacy Qdrant ingestion — preserved |

---

## 7. Deviation Protocol

Any deviation from the above during implementation must be:

1. Flagged explicitly in the phase review.
2. Documented with the reason for deviation.
3. Reflected in an updated plan document.

No silent deviations are acceptable.

### 7.1 Actual Deviations During Implementation (2026-06-05)

| # | Deviation | Plan Specified | Implemented | Reason |
|---|-----------|----------------|-------------|--------|
| 1 | Dependency pinning | `ragas>=0.1.0`, `datasets>=2.14.0`, `pandas>=2.0.0` | `ragas==0.4.3`, `datasets==4.8.5`, `pandas==3.0.3` | Pinned to versions installed in shared project venv for deterministic Docker builds. These versions are proven compatible with `langchain-community==0.4.1`. |
| 2 | LLM provider guard in `run_eval.py` | `if settings.openai_api_key or settings.llm_provider == "ollama":` | `try: llm_provider = create_llm_provider(settings) except ValueError as e: raise RuntimeError(...)` | The plan's condition short-circuits incorrectly when `llm_provider=="openai"` with no key set. The factory already validates config; wrapping in try/except lets the factory own validation (single-responsibility principle). |
| 3 | Sync RAGAS in async harness | RAGAS `evaluate()` called directly from `async def evaluate()` | Wrapped in `asyncio.to_thread()` | RAGAS `evaluate()` is synchronous; calling it directly from an async method blocks the event loop. `asyncio.to_thread()` runs it in a thread pool without blocking. |
| 4 | RAGAS imports location | `from ragas import evaluate` inside `async def evaluate()` method body | Moved to module-level imports | The method-local import made `evaluate` invisible to `unittest.mock.patch("evaluation.harness.evaluate")` at test setup time. Module-level import enables testability without changing behavior. LangChain imports (`ChatOllama`, `FastEmbedEmbeddings`) remain method-local as the plan intended. |
| 5 | RAGAS deprecation warnings | `from ragas.metrics import faithfulness, context_precision` | Kept as specified | RAGAS 0.4.3 emits `DeprecationWarning` that these imports will move to `ragas.metrics.collections` in v1.0. The legacy import path still works and matches `eval_pipeline.py`. Not changed to avoid unnecessary divergence from the plan. |
| 6 | `langchain-community` not pinned in backend requirements | Not specified in plan (plan assumed shared venv's `langchain-community==0.4.1` would carry over) | Added `langchain-community==0.4.1` to `backend/requirements.txt` | Without an explicit pin, pip resolves `langchain-community` to `0.4.2` as a transitive dep of `ragas==0.4.3`. Version `0.4.2` removed the `vertexai` submodule that RAGAS 0.4.3 still imports, causing `ModuleNotFoundError` at runtime inside Docker. The pin matches the root `requirements.txt` and shared venv, where the import works correctly. |

---

## 8. Phase Completion Checklist

Before Phase 11 begins, ALL of the following must pass:

- [x] `mypy .` — zero new errors (pre-existing library stub warnings only)
- [x] `ruff check .` — zero issues
- [x] `pytest -v` — 56/56 passed (6 new evaluation tests + 50 existing; 6 DB-dependent tests skipped — PostgreSQL not running locally)
- [x] `docker compose build` — succeeds (ragas 0.4.3, datasets 4.8.5, pandas 3.0.3 installed)
- [x] `docker compose up --build` — all three services start, health endpoints return OK
- [ ] Manual smoke test:
  - [ ] Upload `sample_technical_document.pdf` (or any test PDF)
  - [ ] Wait for `embedding_status` = `completed`
  - [ ] `cd backend && python -m evaluation.run_eval` (with Ollama running or OpenAI key set)
  - [ ] Verify console shows faithfulness and context_precision scores
  - [ ] Verify `evaluation_results.csv` is created with per-question breakdown
  - [ ] Verify `docs/EVALUATION.md` accurately describes the methodology
- [x] Legacy `eval_pipeline.py` still runs independently (parses without errors)
- [x] No import errors or runtime crashes on startup

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| RAGAS version conflict with `langchain-community==0.4.1` | Pin compatible RAGAS version in `requirements.txt`; test in fresh venv |
| Ollama not running → evaluation fails | Print clear prerequisite message; support OpenAI fallback via config |
| No documents in DB → all scores are zero / meaningless | Print warning if no documents found; require pre-seeded corpus |
| Structured queries produce misleading context_precision | Document limitation in `EVALUATION.md`; metric designed for passage retrieval |
| Evaluation takes a long time (LLM judge per question) | Cap test dataset to 2–5 questions for demo; document that full eval requires more time |
| `async` RAGAS integration issues | RAGAS `evaluate()` is sync; call it from async harness with care (run in thread if needed) |

---

## 10. Design Decisions & Tradeoffs

### Why use LangChain directly for the judge?

RAGAS is tightly coupled to LangChain's `BaseLanguageModel` and `Embeddings` interfaces. Adapting our `LLMProvider` abstraction to satisfy these interfaces would require implementing ~10 abstract methods with no business value. The judge is an evaluation concern, not production logic, so direct LangChain usage is pragmatic.

### Why a CLI script instead of an API endpoint?

Evaluation is an offline, dev/testing activity. An API endpoint would require async job handling, result storage, and authentication. A CLI script is simpler, requires no new infrastructure, and is sufficient for a reviewer to verify system quality.

### Why keep the legacy `eval_pipeline.py`?

Per `ENGINEERING_PRINCIPLES.md`: "Build On Existing Components" and "Reuse working components whenever possible." The legacy file is part of the existing foundation. Deleting it would erase the baseline. We create a NEW harness for the new architecture while preserving the old one.

### Why serialize structured fields into text for RAGAS?

RAGAS `faithfulness` requires text contexts to compare against the answer. Structured data (JSON key-value pairs) must be serialized into strings for the judge LLM to assess. This is an inherent limitation of text-based evaluation frameworks — documented in `EVALUATION.md`.

### Why default to the legacy test questions?

Using the same questions as `eval_pipeline.py` (`attenuated virus`, `vaccine types`) means the reviewer can compare the old and new evaluation outputs if desired. The questions are domain-specific to the sample PDF, so they serve as a consistent benchmark.
