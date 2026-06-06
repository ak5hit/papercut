from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from embeddings import create_embedding_provider
from extractors import DocumentInput, create_default_registry
from llm import create_llm_provider
from storage.database import get_session
from storage.document_store import DocumentStore

router = APIRouter(prefix="/documents", tags=["documents"])


def _require_ready(request: Request) -> None:
    if not getattr(request.app.state, "ready", True):
        raise HTTPException(
            status_code=503,
            detail="System is still initializing. Please wait a moment and try again.",
        )


@router.post("/upload", status_code=201)
async def upload_document(
    file: UploadFile,
    document_type: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
    _ready: None = Depends(_require_ready),
) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    content = await file.read()
    store = DocumentStore(session)

    llm_provider = None
    if settings.openai_api_key or settings.llm_provider == "ollama":
        llm_provider = create_llm_provider(settings)

    embedding_provider = create_embedding_provider(settings)

    registry = create_default_registry(store, llm_provider, embedding_provider)
    document_input = DocumentInput(
        content=content,
        filename=file.filename,
        content_type=file.content_type,
        document_type=document_type,
    )
    document, pipeline_trace = await registry.process(document_input)

    return {
        "id": str(document.id),
        "filename": document.metadata.get("filename"),
        "page_count": document.metadata.get("page_count"),
        "extraction_strategy": document.extraction_strategy,
        "embedding_status": document.embedding_status,
        "entities_count": len(document.entities),
        "relationships_count": len(document.relationships),
        "document_type": document.structured_fields.get("document_type"),
        "pipeline_trace": pipeline_trace.to_dict(),
        "created_at": document.created_at.isoformat(),
    }


@router.get("/")
async def list_documents(
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    store = DocumentStore(session)
    documents = await store.list_documents(limit=limit, offset=offset)
    return [
        {
            "id": str(doc.id),
            "filename": doc.metadata.get("filename"),
            "page_count": doc.metadata.get("page_count"),
            "extraction_strategy": doc.extraction_strategy,
            "embedding_status": doc.embedding_status,
            "created_at": doc.created_at.isoformat(),
        }
        for doc in documents
    ]


@router.get("/{document_id}")
async def get_document(
    document_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    store = DocumentStore(session)
    document = await store.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": str(document.id),
        "metadata": document.metadata,
        "raw_text_length": len(document.raw_text),
        "extraction_strategy": document.extraction_strategy,
        "embedding_status": document.embedding_status,
        "created_at": document.created_at.isoformat(),
        "updated_at": document.updated_at.isoformat(),
    }


@router.delete("/{document_id}")
async def delete_document(
    document_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    store = DocumentStore(session)
    deleted = await store.delete_document(document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": True}


@router.get("/{document_id}/chunks")
async def get_document_chunks(
    document_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    store = DocumentStore(session)
    document = await store.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = await store.get_chunks(document_id)
    return [
        {
            "id": str(chunk.id),
            "chunk_index": chunk.chunk_index,
            "text": chunk.text,
            "metadata": chunk.metadata,
        }
        for chunk in chunks
    ]


@router.post("/search/semantic")
async def semantic_search(
    query: str,
    limit: int = 5,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    provider = create_embedding_provider(settings)
    query_embedding = provider.embed([query])[0]

    store = DocumentStore(session)
    results = await store.semantic_search(query_embedding, limit=limit)

    return [
        {
            "chunk_id": str(result.chunk.id),
            "document_id": str(result.chunk.document_id),
            "chunk_index": result.chunk.chunk_index,
            "text": result.chunk.text,
            "score": result.score,
            "metadata": result.chunk.metadata,
        }
        for result in results
    ]
