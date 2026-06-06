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
