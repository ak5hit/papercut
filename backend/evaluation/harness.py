import asyncio
from dataclasses import dataclass
from typing import Any

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import context_precision, faithfulness

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

        from langchain_community.chat_models import ChatOllama
        from langchain_community.embeddings.fastembed import FastEmbedEmbeddings

        judge_llm = ChatOllama(model="llama3", temperature=0)
        judge_embeddings = FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")

        ragas_result = await asyncio.to_thread(
            evaluate,
            ragas_dataset,
            metrics=[faithfulness, context_precision],
            llm=judge_llm,
            embeddings=judge_embeddings,
        )

        overall_scores: dict[str, float] = {}
        per_question: list[dict[str, Any]] = []

        df = ragas_result.to_pandas()  # type: ignore[union-attr]
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
