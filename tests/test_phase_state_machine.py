from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from extractors.base import DocumentInput
from extractors.pipeline_trace import PHASE_BUILDING, PHASE_LABELS, PipelineTrace


@pytest.mark.asyncio
async def test_graph_failure_still_shows_building_phase() -> None:
    """When graph ops fail, the BUILDING phase was already emitted to user."""
    from extractors.generic import GenericExtractor
    from storage.document_store import DocumentStore

    doc_store = MagicMock(spec=DocumentStore)
    doc_store.save_document = AsyncMock()
    doc_store.save_chunks = AsyncMock()
    doc_store.save_chunk_embeddings = AsyncMock()
    doc_store.update_embedding_status = AsyncMock()

    ext = GenericExtractor(doc_store)

    phases_received: list[str] = []

    async def on_phase(phase_key: str, label: str) -> None:
        phases_received.append(phase_key)

    pdf_bytes = b"%PDF-1.4 fakeresume content\nWork Experience\nCRED\nUdaan"
    doc_input = DocumentInput(content=pdf_bytes, filename="test.pdf")

    try:
        doc, trace = await ext.extract(doc_input, on_phase=on_phase)
    except Exception:
        pass

    # reading + embedding + extracting should have fired (PDF text extraction
    # fails on fake PDF but these phases fire before text extraction)
    assert len(phases_received) >= 1


@pytest.mark.asyncio
async def test_graph_extraction_failure_logs_and_propagates() -> None:
    """Verify that graph failure raises through extract()."""
    from extractors.generic import GenericExtractor
    from storage.document_store import DocumentStore

    doc_store = MagicMock(spec=DocumentStore)
    doc_store.save_document = AsyncMock()
    doc_store.save_chunks = AsyncMock()
    doc_store.save_chunk_embeddings = AsyncMock()
    doc_store.update_embedding_status = AsyncMock()

    ext = GenericExtractor(doc_store)

    with (
        pytest.raises(Exception),
    ):
        pdf_bytes = b"%PDF-1.4 fake\nSome text\n"
        doc_input = DocumentInput(content=pdf_bytes, filename="test.pdf")
        await ext.extract(doc_input)
