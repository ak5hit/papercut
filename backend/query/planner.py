from config import Settings
from embeddings.base import EmbeddingProvider
from graph.retriever import GraphRetriever
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
        settings: Settings | None = None,
    ) -> None:
        self.classifier = QueryClassifier(llm_provider)
        self.structured = StructuredRetriever(document_store.session)
        self.semantic = SemanticRetriever(document_store, embedding_provider, settings=settings)
        self.hybrid = HybridRetriever(self.structured, self.semantic)
        self.store = document_store
        self.settings = settings
        self.graph = None
        if settings and settings.graph_extraction_enabled and llm_provider:
            from graph.age_connection import get_age_graph
            age_graph = get_age_graph(settings)
            self.graph = GraphRetriever(
                session=document_store.session,
                age_graph=age_graph,
                embedding_provider=embedding_provider,
                llm_provider=llm_provider,
                settings=settings,
            )

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
            trace.structured_results_count = len(docs)
            trace.add_step(f"Retrieved {len(docs)} documents")
            return QueryResult(trace=trace, documents=docs, chunks=[])

        if category == "GRAPH":
            trace = ExecutionTrace(strategy="graph")
            trace.add_step("Classified as GRAPH — generating Cypher query")
            if self.graph and await self.graph.has_graph_data():
                graph_result = await self.graph.graph_query(question)
                cypher = graph_result.get("cypher", "")
                answer = graph_result.get("answer", "")
                context = graph_result.get("context", [])
                is_error = any(w in answer.lower() for w in ["failed", "could not", "no answer", "not generate"])
                if cypher and not is_error and context:
                    trace.add_step(f"Cypher: {cypher[:200]}")
                    trace.add_step(f"Answer: {answer[:200]}")
                    trace.graph_results_count = len(context)
                    return QueryResult(trace=trace, graph_result=graph_result)
                trace.add_step("Cypher query returned no results — falling back to enriched search")
                enriched = await self.graph.enriched_search(question)
                chunks = enriched["chunks"]
                graph_context = enriched["context"]
                ec = enriched["entities"]
                rc = enriched["relationships"]
                trace.add_step(f"Graph-enriched: {len(ec)} entities, {len(rc)} relationships")
                return QueryResult(trace=trace, chunks=chunks, graph_context=graph_context)
            trace.add_step("Graph retriever not available — falling back to semantic")
            chunks = await self.semantic.search(question)
            trace.semantic_results_count = len(chunks)
            return QueryResult(trace=trace, chunks=chunks)

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
            if self.graph and await self.graph.has_graph_data():
                enriched = await self.graph.enriched_search(question)
                chunks = enriched["chunks"]
                graph_context = enriched["context"]
                ec = enriched["entities"]
                rc = enriched["relationships"]
                trace.add_step(f"Graph-enriched: {len(ec)} entities, {len(rc)} relationships")
            else:
                chunks = await self.semantic.search(question)
                graph_context = None
            trace.semantic_results_count = len(chunks)
            trace.add_step(f"Retrieved {len(chunks)} chunks")
            return QueryResult(trace=trace, chunks=chunks, graph_context=graph_context)

        docs, chunks, trace = await self.hybrid.search(
            question,
            field_filters=field_filters or None,
            entity_name=classification.entity_name,
        )
        graph_context = None
        if self.graph and await self.graph.has_graph_data():
            enriched = await self.graph.enriched_search(question)
            graph_context = enriched["context"]
            ec = enriched["entities"]
            rc = enriched["relationships"]
            trace.add_step(f"Graph-enriched hybrid: {len(ec)} entities, {len(rc)} relationships")
        if field_filters or classification.entity_name:
            trace.steps.insert(
                0,
                f"Classified as HYBRID — "
                f"filters: {field_filters}, entity: {classification.entity_name}",
            )
        else:
            trace.steps.insert(0, "Classified as HYBRID")
        return QueryResult(trace=trace, documents=docs, chunks=chunks, graph_context=graph_context)
