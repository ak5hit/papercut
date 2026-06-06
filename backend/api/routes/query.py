from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from answers.composer import AnswerComposer
from config import settings
from embeddings import create_embedding_provider
from llm import create_llm_provider
from query.planner import QueryPlanner
from storage.database import get_session
from storage.document_store import DocumentStore

router = APIRouter(prefix="/query", tags=["query"])


@router.post("")
async def query_documents(
    payload: dict[str, Any],
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    question = payload.get("query", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Query is required")

    store = DocumentStore(session)

    llm_provider = None
    if settings.openai_api_key or settings.llm_provider == "ollama":
        llm_provider = create_llm_provider(settings)

    if llm_provider is None:
        raise HTTPException(status_code=503, detail="LLM provider not configured")

    embedding_provider = create_embedding_provider(settings)
    planner = QueryPlanner(store, llm_provider, embedding_provider)
    composer = AnswerComposer(llm_provider)

    result = await planner.execute(question)
    composed = await composer.compose(question, result)

    return composed.to_dict()
