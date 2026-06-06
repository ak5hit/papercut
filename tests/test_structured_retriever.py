import pytest

from models.canonical_document import CanonicalDocument
from query.structured_retriever import StructuredRetriever
from storage.document_store import DocumentStore


@pytest.mark.asyncio
async def test_search_by_structured_field(session):
    store = DocumentStore(session)
    retriever = StructuredRetriever(session)

    doc = CanonicalDocument.create(
        raw_text="Invoice data",
        metadata={"filename": "inv.pdf"},
        extraction_strategy="generic_small",
    )
    doc.structured_fields = {"total_amount": 150000, "currency": "INR"}
    await store.save_document(doc)

    results = await retriever.search(field_filters={"total_amount": 150000})
    assert len(results) == 1
    assert results[0]["structured_fields"]["total_amount"] == 150000


@pytest.mark.asyncio
async def test_search_by_entity_name(session):
    store = DocumentStore(session)
    retriever = StructuredRetriever(session)

    doc = CanonicalDocument.create(
        raw_text="AWS contract",
        metadata={"filename": "aws.pdf"},
        extraction_strategy="generic_small",
    )
    doc.entities = [{"name": "Amazon Web Services", "type": "ORGANIZATION", "value": "AWS"}]
    await store.save_document(doc)

    results = await retriever.search(entity_name="Amazon Web Services")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_no_match_returns_empty(session):
    retriever = StructuredRetriever(session)
    results = await retriever.search(field_filters={"nonexistent": "value"})
    assert results == []
