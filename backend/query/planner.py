from embeddings.base import EmbeddingProvider
from llm.base import LLMProvider
from query.classifier import QueryClassifier
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
        category = await self.classifier.classify(question)

        if category == "STRUCTURED":
            trace = ExecutionTrace(strategy="structured")
            trace.add_step("Routed to Structured Search")
            docs = await self.structured.search()
            trace.structured_results_count = len(docs)
            trace.add_step(f"Retrieved {len(docs)} documents")
            return QueryResult(trace=trace, documents=docs)

        if category == "SEMANTIC":
            trace = ExecutionTrace(strategy="semantic")
            trace.add_step("Routed to Semantic Search")
            chunks = await self.semantic.search(question)
            trace.semantic_results_count = len(chunks)
            trace.add_step(f"Retrieved {len(chunks)} chunks")
            return QueryResult(trace=trace, chunks=chunks)

        docs, chunks, trace = await self.hybrid.search(question)
        return QueryResult(trace=trace, documents=docs, chunks=chunks)
