from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.documents import router as documents_router
from api.routes.health import router as health_router
from api.routes.query import router as query_router
from config import settings
from embeddings import create_embedding_provider


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    print("[Startup] Warming up embedding model...")
    app.state.ready = False
    embedder = create_embedding_provider(settings)
    embedder.embed(["warmup"])
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
