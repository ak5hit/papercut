from unittest.mock import AsyncMock

import pytest

from query.classifier import ClassificationResult, QueryClassifier


class TestQueryClassifier:
    @pytest.mark.asyncio
    async def test_classifies_structured(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = '{"category": "STRUCTURED", "document_type": null, "field_filters": null, "entity_name": null}'
        classifier = QueryClassifier(llm)
        result = await classifier.classify("What is the total AWS spend?")
        assert isinstance(result, ClassificationResult)
        assert result.category == "STRUCTURED"

    @pytest.mark.asyncio
    async def test_classifies_semantic(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = '{"category": "SEMANTIC", "document_type": null, "field_filters": null, "entity_name": null}'
        classifier = QueryClassifier(llm)
        result = await classifier.classify("Summarize payment obligations")
        assert isinstance(result, ClassificationResult)
        assert result.category == "SEMANTIC"

    @pytest.mark.asyncio
    async def test_classifies_hybrid(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = '{"category": "HYBRID", "document_type": null, "field_filters": null, "entity_name": null}'
        classifier = QueryClassifier(llm)
        result = await classifier.classify("Show AWS contracts with invoices above 1 lakh")
        assert isinstance(result, ClassificationResult)
        assert result.category == "HYBRID"

    @pytest.mark.asyncio
    async def test_defaults_to_semantic_on_garbage(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "something weird"
        classifier = QueryClassifier(llm)
        result = await classifier.classify("???")
        assert isinstance(result, ClassificationResult)
        assert result.category == "SEMANTIC"

    @pytest.mark.asyncio
    async def test_classifies_structured_with_filters(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = (
            '{"category": "STRUCTURED", "document_type": "resume", '
            '"field_filters": {"skills": "Python"}, "entity_name": null}'
        )
        classifier = QueryClassifier(llm)
        result = await classifier.classify("Show me candidates with Python experience")
        assert result.category == "STRUCTURED"
        assert result.document_type == "resume"
        assert result.field_filters == {"skills": "Python"}

    @pytest.mark.asyncio
    async def test_classifies_hybrid_with_entity_name(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = (
            '{"category": "HYBRID", "document_type": "resume", '
            '"field_filters": {"current_role": "senior"}, "entity_name": "Google"}'
        )
        classifier = QueryClassifier(llm)
        result = await classifier.classify("Find senior engineers who worked at Google")
        assert result.category == "HYBRID"
        assert result.document_type == "resume"
        assert result.field_filters == {"current_role": "senior"}
        assert result.entity_name == "Google"
