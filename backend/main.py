from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from api.routes.documents import router as documents_router
from api.routes.health import router as health_router
from api.routes.query import router as query_router
from config import settings
from embeddings import create_embedding_provider
from storage.database import Base, engine


async def _ensure_tables_exist() -> None:
    """Verify core tables exist; create them if alembic stamp is stale."""
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT to_regclass('public.documents')"))
        documents_exists = result.scalar() is not None

        result = await conn.execute(text("SELECT to_regclass('public.document_chunks')"))
        chunks_exists = result.scalar() is not None

        if not documents_exists or not chunks_exists:
            print("[Startup] Core tables missing despite alembic stamp. Creating tables...")
            await conn.run_sync(Base.metadata.create_all)
            print("[Startup] Tables created.")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    print("[Startup] Warming up embedding model...")
    app.state.ready = False
    embedder = create_embedding_provider(settings)
    embedder.embed(["warmup"])

    print("[Startup] Verifying database tables...")
    await _ensure_tables_exist()

    app.state.ready = True
    print("[Startup] Embedding model ready.")
    yield
    app.state.ready = False


app = FastAPI(
    title="Document Intelligence Platform",
    description="Universal document intelligence platform with structured and semantic retrieval.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(documents_router)
app.include_router(query_router)
