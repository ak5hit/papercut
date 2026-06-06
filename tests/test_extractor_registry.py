import pytest

from extractors.base import DocumentInput, Extractor
from extractors.generic import GenericExtractor
from extractors.pipeline_trace import PipelineTrace
from extractors.registry import ExtractorRegistry, create_default_registry
from models.canonical_document import CanonicalDocument
from storage.document_store import DocumentStore


class _MockExtractor(Extractor):
    def __init__(self, score: float, name: str = "Mock") -> None:
        self._score = score
        self._name = name

    def supports(self, document: DocumentInput) -> float:
        return self._score

    async def extract(self, document: DocumentInput) -> tuple[CanonicalDocument, PipelineTrace]:
        doc = CanonicalDocument.create(
            raw_text="mock",
            metadata={"mock": True},
            extraction_strategy="mock",
        )
        trace = PipelineTrace(extractor=self._name)
        trace.add_step("Mock extraction")
        return doc, trace


class TestRegistrySelection:
    def test_selects_highest_scoring_extractor(self) -> None:
        low = _MockExtractor(0.5)
        high = _MockExtractor(0.8)
        registry = ExtractorRegistry([low, high])
        doc = DocumentInput(content=b"", filename="test.pdf")
        selected = registry.select(doc)
        assert selected is high

    def test_raises_when_no_extractor_matches(self) -> None:
        no_match = _MockExtractor(0.0)
        registry = ExtractorRegistry([no_match])
        doc = DocumentInput(content=b"", filename="test.pdf")
        with pytest.raises(ValueError, match="No extractor available"):
            registry.select(doc)

    def test_falls_back_to_single_extractor(self) -> None:
        generic = _MockExtractor(0.1)
        registry = ExtractorRegistry([generic])
        doc = DocumentInput(content=b"", filename="test.pdf")
        selected = registry.select(doc)
        assert selected is generic


class TestRegistryProcess:
    @pytest.mark.asyncio
    async def test_process_delegates_to_selected_extractor(self) -> None:
        mock = _MockExtractor(0.9)
        registry = ExtractorRegistry([mock])
        doc = DocumentInput(content=b"", filename="test.pdf")
        result, trace = await registry.process(doc)
        assert result.extraction_strategy == "mock"
        assert trace.extractor == "Mock"


class TestGenericExtractorSupports:
    def test_supports_pdf(self) -> None:
        store = DocumentStore(None)  # type: ignore[arg-type]
        extractor = GenericExtractor(store)
        doc = DocumentInput(content=b"", filename="report.PDF")
        assert extractor.supports(doc) == 0.1

    def test_rejects_non_pdf(self) -> None:
        store = DocumentStore(None)  # type: ignore[arg-type]
        extractor = GenericExtractor(store)
        doc = DocumentInput(content=b"", filename="data.txt")
        assert extractor.supports(doc) == 0.0

    def test_rejects_no_extension(self) -> None:
        store = DocumentStore(None)  # type: ignore[arg-type]
        extractor = GenericExtractor(store)
        doc = DocumentInput(content=b"", filename="noextension")
        assert extractor.supports(doc) == 0.0


class TestCreateDefaultRegistry:
    def test_creates_registry_with_generic_extractor(self) -> None:
        store = DocumentStore(None)  # type: ignore[arg-type]
        registry = create_default_registry(store)
        doc = DocumentInput(content=b"", filename="test.pdf")
        selected = registry.select(doc)
        assert isinstance(selected, GenericExtractor)
