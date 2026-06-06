from unittest.mock import AsyncMock

import pytest

from query.classifier import QueryClassifier


class TestQueryClassifier:
    @pytest.mark.asyncio
    async def test_classifies_structured(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "STRUCTURED"
        classifier = QueryClassifier(llm)
        result = await classifier.classify("What is the total AWS spend?")
        assert result == "STRUCTURED"

    @pytest.mark.asyncio
    async def test_classifies_semantic(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "SEMANTIC"
        classifier = QueryClassifier(llm)
        result = await classifier.classify("Summarize payment obligations")
        assert result == "SEMANTIC"

    @pytest.mark.asyncio
    async def test_classifies_hybrid(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "HYBRID"
        classifier = QueryClassifier(llm)
        result = await classifier.classify("Show AWS contracts with invoices above 1 lakh")
        assert result == "HYBRID"

    @pytest.mark.asyncio
    async def test_defaults_to_semantic_on_garbage(self) -> None:
        llm = AsyncMock()
        llm.complete.return_value = "something weird"
        classifier = QueryClassifier(llm)
        result = await classifier.classify("???")
        assert result == "SEMANTIC"
