from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from answers.composer import AnswerComposer
from api.sse import sse_event as _sse
from chat.contextualizer import QueryContextualizer
from chat.schemas import ChatRequest, ChatRequestMessage, ChatResponse
from chat.sessions import ChatMessage
from chat.sessions import store as chat_store
from config import settings
from embeddings import create_embedding_provider
from llm import create_llm_provider
from query.planner import QueryPlanner
from storage.database import get_session
from storage.document_store import DocumentStore

router = APIRouter(prefix="/query", tags=["query"])


def _get_llm_provider() -> Any:
    llm_provider = None
    if settings.openai_api_key or settings.llm_provider == "ollama":
        llm_provider = create_llm_provider(settings)
    if llm_provider is None:
        raise HTTPException(status_code=503, detail="LLM provider not configured")
    return llm_provider


async def _build_planner_and_composer(
    session: AsyncSession,
) -> tuple[QueryPlanner, AnswerComposer]:
    store = DocumentStore(session)
    llm_provider = _get_llm_provider()
    embedding_provider = create_embedding_provider(settings)
    planner = QueryPlanner(store, llm_provider, embedding_provider, settings=settings)
    composer = AnswerComposer(llm_provider)
    return planner, composer


@router.post("")
async def query_documents(
    payload: dict[str, Any],
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    question = payload.get("query", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Query is required")

    planner, composer = await _build_planner_and_composer(session)
    result = await planner.execute(question)
    composed = await composer.compose(question, result)

    return composed.to_dict()


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    if not payload.messages:
        raise HTTPException(status_code=400, detail="At least one message is required")

    user_messages = [m for m in payload.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="At least one user message is required")

    question = user_messages[-1].content

    if payload.session_id:
        existing = await chat_store.get(payload.session_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Session not found")
        session_id = payload.session_id
    else:
        session_obj = await chat_store.create()
        session_id = session_obj.id

    await chat_store.append(session_id, ChatMessage(role="user", content=question))

    # Contextualize follow-up questions so the pipeline resolves pronouns correctly
    history = [m for m in payload.messages[:-1]]
    standalone = question
    if history:
        ctx_llm = _get_llm_provider()
        ctx = QueryContextualizer(ctx_llm)
        history_dicts = [m.model_dump() for m in history]
        standalone = await ctx.rewrite(question, history_dicts)

    planner, composer = await _build_planner_and_composer(session)
    result = await planner.execute(standalone)
    if standalone != question:
        result.trace.add_step(f"Contextualized: '{question}' -> '{standalone}'")
    composed = await composer.compose(
        standalone, result,
        history=[m.model_dump() for m in history] if history else None,
    )

    await chat_store.append(session_id, ChatMessage(role="assistant", content=composed.answer))

    response_messages = list(payload.messages) + [
        ChatRequestMessage(role="assistant", content=composed.answer)
    ]

    return ChatResponse(
        session_id=session_id,
        messages=response_messages,
        response=composed.to_dict(),
    )


async def _stream_events(
    payload: ChatRequest,
    session: AsyncSession,
) -> AsyncIterator[str]:
    """SSE event generator for the streaming chat endpoint."""
    try:
        if not payload.messages:
            yield _sse("error", {"message": "At least one message is required"})
            return

        user_messages = [m for m in payload.messages if m.role == "user"]
        if not user_messages:
            yield _sse("error", {"message": "At least one user message is required"})
            return

        question = user_messages[-1].content

        if payload.session_id:
            existing = await chat_store.get(payload.session_id)
            if existing is None:
                yield _sse("error", {"message": "Session not found"})
                return
            session_id = payload.session_id
        else:
            session_obj = await chat_store.create()
            session_id = session_obj.id

        await chat_store.append(session_id, ChatMessage(role="user", content=question))

        yield _sse("progress", {"stage": "understand", "message": "Understanding your question..."})

        # Contextualize follow-up questions so the pipeline resolves pronouns correctly
        history = [m for m in payload.messages[:-1]]
        standalone = question
        if history:
            ctx_llm = _get_llm_provider()
            ctx = QueryContextualizer(ctx_llm)
            history_dicts = [m.model_dump() for m in history]
            standalone = await ctx.rewrite(question, history_dicts)

        yield _sse("progress", {"stage": "search", "message": "Searching your documents and knowledge graph..."})

        planner, composer = await _build_planner_and_composer(session)
        result = await planner.execute(standalone)
        if standalone != question:
            result.trace.add_step(f"Contextualized: '{question}' -> '{standalone}'")

        yield _sse("meta", {"session_id": session_id})
        yield _sse("contextualize", {"original": question, "standalone": standalone})

        trace_dict = (
            result.trace.to_dict()
            if hasattr(result.trace, "to_dict")
            else {"strategy": result.trace.strategy, "steps": result.trace.steps}
        )
        yield _sse("trace", trace_dict)

        seen: set[str] = set()
        sources: list[dict[str, Any]] = []
        for chunk in result.chunks or []:
            doc_id = chunk.get("document_id") or chunk.get("id", "")
            if str(doc_id) not in seen:
                seen.add(str(doc_id))
                sources.append({
                    "document_id": str(doc_id),
                    "document_name": chunk.get("filename", "Unknown"),
                })

        # Also add structured-document sources
        for doc in result.documents or []:
            doc_id = doc.get("id", "")
            if doc_id not in seen:
                seen.add(doc_id)
                sources.append({
                    "document_id": doc_id,
                    "document_name": doc.get("metadata", {}).get("filename", "Unknown"),
                })

        # Add graph-direct source documents from the Cypher context
        for src_doc in (result.graph_result or {}).get("source_documents") or []:
            doc_id = src_doc.get("document_id", "")
            if doc_id and doc_id not in seen:
                seen.add(doc_id)
                sources.append(src_doc)

        yield _sse("sources", {"sources": sources})

        yield _sse("progress", {"stage": "synthesize", "message": "Synthesizing the answer..."})

        full_answer = ""
        comp_history = [m.model_dump() for m in history] if history else None
        async for token in composer.compose_stream(standalone, result, history=comp_history):
            full_answer += token
            yield _sse("token", {"text": token})

        stripped = full_answer.strip()
        await chat_store.append(session_id, ChatMessage(role="assistant", content=stripped))

        response_messages = list(payload.messages) + [
            ChatRequestMessage(role="assistant", content=stripped)
        ]
        yield _sse("done", {"session_id": session_id, "messages": [m.model_dump() for m in response_messages]})

    except Exception as exc:
        yield _sse("error", {"message": str(exc)})


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    return StreamingResponse(
        _stream_events(payload, session),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
