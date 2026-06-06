from embeddings.base import EmbeddingProvider
from llm.base import LLMProvider
from query.classifier import ClassificationResult, QueryClassifier
from query.execution_trace import ExecutionTrace
from query.hybrid_retriever import HybridRetriever
from query.result import QueryResult
from query.semantic_retriever import SemanticRetriever
from query.structured_retriever import StructuredRetriever
from storage.document_store import DocumentStore


class QueryPlanner:
    def __init__(
        self,
        document_store: DocumentStore,
        llm_provider: LLMProvider,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.classifier = QueryClassifier(llm_provider)
        self.structured = StructuredRetriever(document_store.session)
        self.semantic = SemanticRetriever(document_store, embedding_provider)
        self.hybrid = HybridRetriever(self.structured, self.semantic)
        self.store = document_store

    async def execute(self, question: str) -> QueryResult:
        classification: ClassificationResult = await self.classifier.classify(question)
        category = classification.category

        field_filters = classification.field_filters or {}
        if classification.document_type:
            field_filters["document_type"] = classification.document_type

        if category == "STRUCTURED":
            trace = ExecutionTrace(strategy="structured")
            if field_filters or classification.entity_name:
                trace.add_step(
                    f"Classified as STRUCTURED — "
                    f"filters: {field_filters}, entity: {classification.entity_name}"
                )
            else:
                trace.add_step("Classified as STRUCTURED")
            trace.add_step("Routed to Structured Search")
            docs = await self.structured.search(
                field_filters=field_filters or None,
                entity_name=classification.entity_name,
            )
            chunks = await self.semantic.search(question, limit=10)
            trace.structured_results_count = len(docs)
            trace.semantic_results_count = len(chunks)
            trace.add_step(f"Retrieved {len(docs)} documents, {len(chunks)} chunks")
            return QueryResult(trace=trace, documents=docs, chunks=chunks)

        if category == "SEMANTIC":
            trace = ExecutionTrace(strategy="semantic")
            if field_filters or classification.entity_name:
                trace.add_step(
                    f"Classified as SEMANTIC — "
                    f"filters: {field_filters}, entity: {classification.entity_name}"
                )
            else:
                trace.add_step("Classified as SEMANTIC")
            trace.add_step("Routed to Semantic Search")
            chunks = await self.semantic.search(question)
            trace.semantic_results_count = len(chunks)
            trace.add_step(f"Retrieved {len(chunks)} chunks")
            return QueryResult(trace=trace, chunks=chunks)

        docs, chunks, trace = await self.hybrid.search(
            question,
            field_filters=field_filters or None,
            entity_name=classification.entity_name,
        )
        if field_filters or classification.entity_name:
            trace.steps.insert(
                0,
                f"Classified as HYBRID — "
                f"filters: {field_filters}, entity: {classification.entity_name}",
            )
        else:
            trace.steps.insert(0, "Classified as HYBRID")
        return QueryResult(trace=trace, documents=docs, chunks=chunks)
