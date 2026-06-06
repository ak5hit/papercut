from embeddings.base import EmbeddingProvider
from extractors.base import DocumentInput, Extractor
from extractors.generic import GenericExtractor
from extractors.pipeline_trace import PipelineTrace
from extractors.resume import ResumeExtractor
from llm.base import LLMProvider
from models.canonical_document import CanonicalDocument
from storage.document_store import DocumentStore


class ExtractorRegistry:
    def __init__(self, extractors: list[Extractor]) -> None:
        self._extractors = extractors

    def select(self, document: DocumentInput) -> Extractor:
        best_extractor: Extractor | None = None
        best_score = 0.0

        for extractor in self._extractors:
            score = extractor.supports(document)
            if score > best_score:
                best_score = score
                best_extractor = extractor

        if best_extractor is None or best_score == 0.0:
            raise ValueError("No extractor available for this document type")

        return best_extractor

    async def process(self, document: DocumentInput) -> tuple[CanonicalDocument, PipelineTrace]:
        extractor = self.select(document)
        return await extractor.extract(document)


def create_default_registry(
    document_store: DocumentStore,
    llm_provider: LLMProvider | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> ExtractorRegistry:
    return ExtractorRegistry(
        [
            ResumeExtractor(document_store, llm_provider, embedding_provider),
            GenericExtractor(document_store, llm_provider, embedding_provider),
        ]
    )
