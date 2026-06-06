"""CLI entry point for running evaluation.

Usage:
    cd backend
    python -m evaluation.run_eval

Requires:
    - PostgreSQL running with seeded documents
    - Ollama running with llama3 model pulled (or OPENAI_API_KEY set)
"""

import asyncio

from config import settings
from embeddings import create_embedding_provider
from evaluation.dataset import EvaluationDataset
from evaluation.harness import EvaluationHarness
from evaluation.reporter import EvaluationReporter
from llm import create_llm_provider
from storage.database import async_session_factory
from storage.document_store import DocumentStore

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

    try:
        llm_provider = create_llm_provider(settings)
    except ValueError as e:
        raise RuntimeError(
            f"No LLM provider configured: {e}. "
            "Set OPENAI_API_KEY for OpenAI or configure Ollama."
        ) from e

    embedding_provider = create_embedding_provider(settings)

    async with async_session_factory() as session:
        store = DocumentStore(session)
        harness = EvaluationHarness(store, llm_provider, embedding_provider)

        print(f"[Eval] Running {len(DEFAULT_DATASET)} test questions...")
        result = await harness.evaluate(DEFAULT_DATASET)

    reporter = EvaluationReporter()
    reporter.print_summary(result)
    reporter.save_csv(result, "evaluation_results.csv")


if __name__ == "__main__":
    asyncio.run(main())
