import sys
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from main import app
from storage.database import Base

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/doc_intelligence_test"
ADMIN_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"


async def _ensure_test_database() -> None:
    admin_engine = create_async_engine(ADMIN_DATABASE_URL, echo=False, isolation_level="AUTOCOMMIT")
    async with admin_engine.begin() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'doc_intelligence_test'")
        )
        exists = result.scalar() is not None
        if not exists:
            await conn.execute(text("CREATE DATABASE doc_intelligence_test"))
    await admin_engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def session():
    await _ensure_test_database()
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as sess:
        yield sess

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
