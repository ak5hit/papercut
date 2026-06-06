import io
import json
from unittest.mock import MagicMock, patch

import pytest
from httpx import HTTPStatusError, Request, Response
from pypdf import PdfWriter

from extractors.base import DocumentInput
from extractors.generic import ENTITY_EXTRACTION_PROMPT, GenericExtractor
from llm.base import LLMProvider
from storage.document_store import DocumentStore


class MockLLMProvider(LLMProvider):
    def __init__(self, response: str = '{"entities": [], "relationships": []}') -> None:
        self.response = response
        self.prompt_received: str = ""

    async def complete(self, prompt: str, max_tokens: int = 2000) -> str:
        self.prompt_received = prompt
        return self.response


class FailingLLMProvider(LLMProvider):
    async def complete(self, prompt: str, max_tokens: int = 2000) -> str:
        raise HTTPStatusError(
            "Provider error",
            request=Request("POST", "https://api.example.com/v1/chat/completions"),
            response=Response(status_code=500),
        )


def _create_blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _mock_reader(pages_text: list[str]) -> MagicMock:
    reader = MagicMock()
    reader.pages = []
    for text in pages_text:
        page = MagicMock()
        page.extract_text.return_value = text
        reader.pages.append(page)
    return reader


@pytest.mark.asyncio
async def test_generic_extractor_without_llm_provider(session):
    store = DocumentStore(session)
    extractor = GenericExtractor(store, llm_provider=None, size_threshold=10_000_000)

    with patch("extractors.generic.PdfReader", return_value=_mock_reader(["Some text."])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="test.pdf")
        document = await extractor.extract(doc_input)

    assert document.entities == []
    assert document.relationships == []
    assert document.extraction_strategy == "generic_small"


@pytest.mark.asyncio
async def test_generic_extractor_with_llm_provider(session):
    entities_response = json.dumps({
        "entities": [
            {"name": "Acme Corp", "type": "ORGANIZATION", "value": "Acme Corporation"},
            {"name": "2024-01-15", "type": "DATE", "value": "2024-01-15"},
            {"name": "$50,000", "type": "MONEY", "value": "50000.00"},
        ],
        "relationships": [
            {
                "source": "Acme Corp",
                "target": "John Doe",
                "type": "WORKS_AT",
                "description": "CEO of Acme Corp",
            },
        ],
    })

    provider = MockLLMProvider(response=entities_response)
    store = DocumentStore(session)
    extractor = GenericExtractor(store, llm_provider=provider, size_threshold=10_000_000)

    page_text = "Acme Corp invoice. John Doe, CEO. Date: 2024-01-15. Amount: $50,000."
    with patch("extractors.generic.PdfReader", return_value=_mock_reader([page_text])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="test.pdf")
        document = await extractor.extract(doc_input)

    assert len(document.entities) == 3
    assert document.entities[0]["name"] == "Acme Corp"
    assert document.entities[0]["type"] == "ORGANIZATION"
    assert document.entities[1]["name"] == "2024-01-15"
    assert document.entities[1]["type"] == "DATE"
    assert document.entities[2]["name"] == "$50,000"
    assert document.entities[2]["type"] == "MONEY"

    assert len(document.relationships) == 1
    assert document.relationships[0]["source"] == "Acme Corp"
    assert document.relationships[0]["target"] == "John Doe"
    assert document.relationships[0]["type"] == "WORKS_AT"
    assert document.relationships[0]["description"] == "CEO of Acme Corp"

    assert document.extraction_strategy == "generic_small"


@pytest.mark.asyncio
async def test_generic_extractor_llm_failure(session):
    provider = FailingLLMProvider()
    store = DocumentStore(session)
    extractor = GenericExtractor(store, llm_provider=provider, size_threshold=10_000_000)

    with patch("extractors.generic.PdfReader", return_value=_mock_reader(["Some text."])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="test.pdf")
        document = await extractor.extract(doc_input)

    assert document.entities == []
    assert document.relationships == []
    assert document.extraction_strategy == "generic_small"


@pytest.mark.asyncio
async def test_generic_extractor_malformed_json(session):
    provider = MockLLMProvider(response="not valid json [{")
    store = DocumentStore(session)
    extractor = GenericExtractor(store, llm_provider=provider, size_threshold=10_000_000)

    with patch("extractors.generic.PdfReader", return_value=_mock_reader(["Some text."])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="test.pdf")
        document = await extractor.extract(doc_input)

    assert document.entities == []
    assert document.relationships == []


@pytest.mark.asyncio
async def test_generic_extractor_large_document_skips_llm(session):
    entities_response = json.dumps({
        "entities": [{"name": "Test", "type": "OTHER", "value": "test"}],
        "relationships": [],
    })
    provider = MockLLMProvider(response=entities_response)
    store = DocumentStore(session)
    extractor = GenericExtractor(store, llm_provider=provider, size_threshold=0)

    with patch("extractors.generic.PdfReader", return_value=_mock_reader(["Some text."])):
        doc_input = DocumentInput(content=_create_blank_pdf(), filename="test.pdf")
        document = await extractor.extract(doc_input)

    assert document.extraction_strategy == "generic_large"
    assert document.entities == []
    assert document.relationships == []
    assert provider.prompt_received == ""


def test_entity_extraction_prompt_format():
    test_text = "Acme Corp invoice dated 2024-01-15. Amount: $50,000."
    prompt = ENTITY_EXTRACTION_PROMPT.format(text=test_text)

    assert test_text in prompt
    assert '"entities"' in prompt
    assert '"relationships"' in prompt
    assert '"name"' in prompt
    assert '"type"' in prompt
    assert 'PERSON|ORGANIZATION|LOCATION|DATE|MONEY|OTHER' in prompt
    assert 'WORKS_AT|LOCATED_IN|PART_OF|OTHER' in prompt
