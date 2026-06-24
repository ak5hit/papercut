import asyncio
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api.sse import sse_event
from config import settings as app_settings
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


@router.post("/upload")
async def upload_document(
    file: UploadFile,
    request: Request,
    _ready: None = Depends(_require_ready),
) -> StreamingResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    content = await file.read()

    queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

    async def on_phase(phase_key: str, label: str) -> None:
        await queue.put((phase_key, label))

    async def run_extraction() -> tuple[Any, Any]:
        from storage.database import async_session_factory

        async with async_session_factory() as session:
            llm_provider = None
            if app_settings.openai_api_key or app_settings.llm_provider == "ollama":
                llm_provider = create_llm_provider(app_settings)

            embedding_provider = create_embedding_provider(app_settings)
            store = DocumentStore(session)
            registry = create_default_registry(store, llm_provider, embedding_provider, settings=app_settings)
            document_input = DocumentInput(
                content=content,
                filename=file.filename or "document.pdf",
                content_type=file.content_type,
            )
            doc, trace = await registry.process(document_input, on_phase=on_phase)
            return doc, trace

    extract_task = asyncio.create_task(run_extraction())

    async def event_stream() -> Any:
        nonlocal extract_task
        doc = None
        trace = None

        while True:
            get_queue = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait(
                [get_queue, extract_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                if task is get_queue:
                    phase_key, label = task.result()
                    yield sse_event("phase", {"phase": phase_key, "label": label})
                    break

            if extract_task.done():
                # Drain any remaining events from the queue
                while not queue.empty():
                    try:
                        phase_key, label = queue.get_nowait()
                        yield sse_event("phase", {"phase": phase_key, "label": label})
                    except asyncio.QueueEmpty:
                        break
                break

        try:
            doc, trace = extract_task.result()
        except Exception as exc:
            yield sse_event("error", {"message": str(exc)})
            return

        yield sse_event("done", {
            "id": str(doc.id),
            "filename": doc.metadata.get("filename"),
            "page_count": doc.metadata.get("page_count"),
            "embedding_status": doc.embedding_status,
            "pipeline_trace": trace.to_dict(),
            "created_at": doc.created_at.isoformat(),
        })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
    if app_settings.graph_extraction_enabled:
        try:
            from graph.age_connection import create_age_graph
            from graph.store import GraphStore
            age_graph = create_age_graph(app_settings)
            graph_store = GraphStore(age_graph, app_settings)
            await graph_store.delete_document(document_id)
        except Exception:
            import logging
            logging.warning("AGE cleanup failed for document %s", document_id)

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
    provider = create_embedding_provider(app_settings)
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
