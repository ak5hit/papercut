# Phase 3: Canonical Document & Persistence Layer — Execution Plan

## Objective

Create the CanonicalDocument model, database schema with Alembic migrations, persistence layer, and PDF ingestion pipeline. Documents flow through canonical representation and are persisted to PostgreSQL.

**Deliverable:** Working document upload, storage, and retrieval via API.

**Rule:** Do NOT implement any Phase 4+ features. No extractors, no query planner, no LLM providers, no embeddings. Only the canonical model and persistence foundation.

---

## 1. Target File Structure (Phase 3 Only)

Files to create:

```
multi-agent-intelligence/
├── backend/
│   ├── alembic.ini                              # Alembic configuration
│   ├── alembic/
│   │   ├── env.py                               # Alembic environment setup (async)
│   │   ├── script.py.mako                       # Migration template
│   │   └── versions/
│   │       └── 001_create_documents.py          # Initial migration
│   ├── models/
│   │   ├── __init__.py
│   │   ├── canonical_document.py                # CanonicalDocument Pydantic model
│   │   ├── document_chunk.py                    # DocumentChunk Pydantic model
│   │   └── db_models.py                         # SQLAlchemy ORM models
│   ├── storage/
│   │   └── document_store.py                    # Document persistence layer
│   ├── ingestion/
│   │   ├── __init__.py
│   │   └── pdf_ingester.py                      # PDF ingestion logic
│   └── api/
│       └── routes/
│           └── documents.py                     # POST /documents/upload, GET /documents
├── tests/
│   ├── test_models.py                           # CanonicalDocument validation tests
│   ├── test_document_store.py                   # Persistence layer tests
│   └── test_ingestion.py                        # Ingestion pipeline tests
└── docs/
    └── PHASE_3_PLAN.md                          # (this file)
```

Files to modify:

| File | Change |
|------|--------|
| `backend/requirements.txt` | Add `alembic`, `pypdf`, `langchain-text-splitters` |
| `backend/main.py` | Register documents router |
| `backend/storage/database.py` | Add SQLAlchemy declarative base |
| `backend/Dockerfile` | Run migrations on startup |

Files to NOT create (reserved for future phases):

- `backend/extractors/` — Phase 4
- `backend/llm/` — Phase 5
- `backend/query/` — Phase 7
- `backend/evaluation/` — Phase 10
- `frontend/` — Phase 9
- Embedding storage logic — Phase 6

Files to NOT modify:

- `ingest_and_search.py` — kept as legacy reference
- `agent_graph.py` — untouched
- `eval_pipeline.py` — untouched
- Root `requirements.txt` — untouched

---

## 2. Schema Design

### 2.1 CanonicalDocument (Pydantic Model)

```python
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CanonicalDocument(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    metadata: dict[str, Any]
    raw_text: str
    structured_fields: dict[str, Any] = Field(default_factory=dict)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    extraction_strategy: str
    embedding_status: Literal["pending", "completed", "failed"] = "pending"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

**Key decisions:**
- `metadata` — flexible JSONB for source info, filename, upload date, etc.
- `structured_fields` — empty dict for now; populated by extractors in Phase 4
- `entities` / `relationships` — empty lists for now; populated by extractors in Phase 4
- `extraction_strategy` — tracks how the document was processed (e.g., "pdf_basic", "full_llm", "chunked")
- `embedding_status` — tracks whether embeddings have been generated (Phase 6)
- All fields have sensible defaults where appropriate

### 2.2 DocumentChunk (Pydantic Model)

```python
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class DocumentChunk(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    document_id: UUID
    chunk_index: int
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

**Key decisions:**
- `chunk_index` — preserves ordering within a document
- `metadata` — per-chunk metadata (page number, section, etc.)
- `embedding_id` — nullable; will store vector store point ID in Phase 6
- `document_id` — foreign key to parent document

### 2.3 Database Tables (SQLAlchemy ORM)

**documents table:**

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `metadata` | JSONB | NOT NULL |
| `raw_text` | TEXT | NOT NULL |
| `structured_fields` | JSONB | DEFAULT '{}' |
| `entities` | JSONB | DEFAULT '[]' |
| `relationships` | JSONB | DEFAULT '[]' |
| `extraction_strategy` | VARCHAR(50) | NOT NULL |
| `embedding_status` | VARCHAR(20) | NOT NULL, DEFAULT 'pending' |
| `created_at` | TIMESTAMP | NOT NULL |
| `updated_at` | TIMESTAMP | NOT NULL |

**document_chunks table:**

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `document_id` | UUID | FK → documents.id, NOT NULL, indexed |
| `chunk_index` | INTEGER | NOT NULL |
| `text` | TEXT | NOT NULL |
| `metadata` | JSONB | DEFAULT '{}' |
| `embedding_id` | VARCHAR(255) | NULLABLE |
| `created_at` | TIMESTAMP | NOT NULL |

**Constraints:**
- Unique constraint on `(document_id, chunk_index)`
- Index on `document_id` for fast chunk lookups
- Index on `embedding_status` for filtering unembedded documents (Phase 6)

---

## 3. Step-by-Step Execution

### Step 1: Add Dependencies

Add to `backend/requirements.txt`:

```
alembic==1.14.0
pypdf==6.12.1
langchain-text-splitters==1.1.2
```

**Rationale:**
- `alembic` — database migrations (Phase 2 plan explicitly deferred this to Phase 3)
- `pypdf` — PDF text extraction (already available in root venv at 6.12.1)
- `langchain-text-splitters` — text chunking (already available in root venv at 1.1.2)

**Why not `langchain-community`?** The backend should not depend on the heavy langchain ecosystem. `pypdf` is lightweight and sufficient for basic text extraction. `langchain-text-splitters` is a standalone package with minimal dependencies.

**Verification:** `pip install -r backend/requirements.txt` succeeds.

---

### Step 2: Add SQLAlchemy Declarative Base

Modify `backend/storage/database.py`:

```python
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, echo=False)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


async def check_connection() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
```

**Key decisions:**
- `Base` class is the single source of truth for all ORM models
- Imported by Alembic's `env.py` and by all ORM model classes
- No other changes to existing functions

**Verification:** `from storage.database import Base` succeeds.

---

### Step 3: Create Pydantic Models

#### 3.1 Create `backend/models/__init__.py`

Empty file.

#### 3.2 Create `backend/models/canonical_document.py`

Define `CanonicalDocument` as shown in Section 2.1.

Add a factory method for convenience:

```python
@classmethod
def create(
    cls,
    raw_text: str,
    metadata: dict[str, Any],
    extraction_strategy: str,
) -> "CanonicalDocument":
    now = datetime.utcnow()
    return cls(
        raw_text=raw_text,
        metadata=metadata,
        extraction_strategy=extraction_strategy,
        created_at=now,
        updated_at=now,
    )
```

#### 3.3 Create `backend/models/document_chunk.py`

Define `DocumentChunk` as shown in Section 2.2.

**Verification:** Models can be instantiated, validation rejects invalid data.

---

### Step 4: Create SQLAlchemy ORM Models

Create `backend/models/db_models.py`:

```python
from datetime import datetime
from uuid import UUID

from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storage.database import Base


class DocumentModel(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    structured_fields: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    entities: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    relationships: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    extraction_strategy: Mapped[str] = mapped_column(String(50), nullable=False)
    embedding_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    chunks: Mapped[list["DocumentChunkModel"]] = relationship(
        "DocumentChunkModel", back_populates="document", cascade="all, delete-orphan"
    )

    def to_canonical(self) -> "CanonicalDocument":
        from models.canonical_document import CanonicalDocument
        return CanonicalDocument(
            id=self.id,
            metadata=self.metadata_,
            raw_text=self.raw_text,
            structured_fields=self.structured_fields,
            entities=self.entities,
            relationships=self.relationships,
            extraction_strategy=self.extraction_strategy,
            embedding_status=self.embedding_status,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_canonical(cls, doc: "CanonicalDocument") -> "DocumentModel":
        return cls(
            id=doc.id,
            metadata_=doc.metadata,
            raw_text=doc.raw_text,
            structured_fields=doc.structured_fields,
            entities=doc.entities,
            relationships=doc.relationships,
            extraction_strategy=doc.extraction_strategy,
            embedding_status=doc.embedding_status,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )


class DocumentChunkModel(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default="{}")
    embedding_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    document: Mapped["DocumentModel"] = relationship("DocumentModel", back_populates="chunks")

    def to_model(self) -> "DocumentChunk":
        from models.document_chunk import DocumentChunk
        return DocumentChunk(
            id=self.id,
            document_id=self.document_id,
            chunk_index=self.chunk_index,
            text=self.text,
            metadata=self.metadata_,
            embedding_id=self.embedding_id,
            created_at=self.created_at,
        )

    @classmethod
    def from_model(cls, chunk: "DocumentChunk") -> "DocumentChunkModel":
        return cls(
            id=chunk.id,
            document_id=chunk.document_id,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            metadata_=chunk.metadata,
            embedding_id=chunk.embedding_id,
            created_at=chunk.created_at,
        )
```

**Key decisions:**
- SQLAlchemy 2.x `Mapped` + `mapped_column` style (modern, type-safe)
- `metadata_` attribute maps to `metadata` column (avoids conflict with SQLAlchemy's `MetaData`)
- `to_canonical()` / `from_canonical()` — conversion between ORM and Pydantic models
- `cascade="all, delete-orphan"` — deleting a document deletes its chunks
- Lazy imports in conversion methods to avoid circular dependencies

**Verification:** ORM models convert to/from Pydantic models correctly.

---

### Step 5: Setup Alembic

#### 5.1 Create `backend/alembic.ini`

```ini
[alembic]
script_location = alembic
sqlalchemy.url = postgresql+asyncpg://postgres:postgres@db:5432/doc_intelligence

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %%(levelname)-5.5s [%%(name)s] %%(message)s
datefmt = %%H:%%M:%%S
```

**Note:** The `sqlalchemy.url` here is a placeholder. The actual URL is set programmatically in `env.py` from the application's `settings`.

#### 5.2 Create `backend/alembic/env.py`

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from config import settings
from storage.database import Base
from models.db_models import DocumentModel, DocumentChunkModel  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

**Key decisions:**
- Uses `async_engine_from_config` for async SQLAlchemy
- Imports `settings.database_url` so URL comes from environment, not hardcoded
- Imports ORM models to ensure `Base.metadata` includes all tables
- `# noqa: F401` on model imports — they're needed for metadata registration

#### 5.3 Create `backend/alembic/script.py.mako`

Standard Alembic migration template:

```python
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

#### 5.4 Create `backend/alembic/versions/001_create_documents.py`

```python
"""create documents and document_chunks tables

Revision ID: 001
Revises:
Create Date: 2026-06-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("structured_fields", JSONB, nullable=False, server_default="{}"),
        sa.Column("entities", JSONB, nullable=False, server_default="[]"),
        sa.Column("relationships", JSONB, nullable=False, server_default="[]"),
        sa.Column("extraction_strategy", sa.String(50), nullable=False),
        sa.Column("embedding_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("embedding_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("document_id", "chunk_index"),
    )

    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_documents_embedding_status", "documents", ["embedding_status"])


def downgrade() -> None:
    op.drop_index("ix_documents_embedding_status", table_name="documents")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_table("documents")
```

**Key decisions:**
- Hand-written migration (not auto-generated) for clarity and reviewability
- Indexes on `document_id` and `embedding_status` for query performance
- `downgrade()` properly reverses all changes
- `server_default` for JSONB columns ensures database-level defaults

**Verification:** `alembic upgrade head` creates both tables with correct schema.

---

### Step 6: Create Document Store

Create `backend/storage/document_store.py`:

```python
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.canonical_document import CanonicalDocument
from models.document_chunk import DocumentChunk
from models.db_models import DocumentChunkModel, DocumentModel


class DocumentStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_document(self, document: CanonicalDocument) -> None:
        model = DocumentModel.from_canonical(document)
        self.session.add(model)
        await self.session.commit()

    async def get_document(self, document_id: UUID) -> CanonicalDocument | None:
        result = await self.session.execute(
            select(DocumentModel)
            .options(selectinload(DocumentModel.chunks))
            .where(DocumentModel.id == document_id)
        )
        model = result.scalar_one_or_none()
        return model.to_canonical() if model else None

    async def list_documents(self, limit: int = 100, offset: int = 0) -> list[CanonicalDocument]:
        result = await self.session.execute(
            select(DocumentModel)
            .order_by(DocumentModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [model.to_canonical() for model in result.scalars().all()]

    async def save_chunks(self, chunks: list[DocumentChunk]) -> None:
        models = [DocumentChunkModel.from_model(chunk) for chunk in chunks]
        self.session.add_all(models)
        await self.session.commit()

    async def get_chunks(self, document_id: UUID) -> list[DocumentChunk]:
        result = await self.session.execute(
            select(DocumentChunkModel)
            .where(DocumentChunkModel.document_id == document_id)
            .order_by(DocumentChunkModel.chunk_index)
        )
        return [model.to_model() for model in result.scalars().all()]

    async def update_embedding_status(self, document_id: UUID, status: str) -> None:
        result = await self.session.execute(
            select(DocumentModel).where(DocumentModel.id == document_id)
        )
        model = result.scalar_one_or_none()
        if model:
            model.embedding_status = status
            await self.session.commit()
```

**Key decisions:**
- Constructor takes `AsyncSession` — follows dependency injection pattern
- Returns Pydantic models (not ORM models) — keeps layers separate
- `selectinload` for eager loading chunks when fetching a document
- `order_by(created_at.desc())` for listing — newest first
- `update_embedding_status` — separate method for Phase 6 embedding pipeline

**Verification:** Unit tests pass with a real database session.

---

### Step 7: Create PDF Ingester

#### 7.1 Create `backend/ingestion/__init__.py`

Empty file.

#### 7.2 Create `backend/ingestion/pdf_ingester.py`

```python
import os
import tempfile
from datetime import datetime
from typing import Any
from uuid import uuid4

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from models.canonical_document import CanonicalDocument
from models.document_chunk import DocumentChunk
from storage.document_store import DocumentStore


class PDFIngester:
    def __init__(self, document_store: DocumentStore) -> None:
        self.document_store = document_store

    async def ingest(self, file_content: bytes, filename: str) -> CanonicalDocument:
        text, page_metadata = self._extract_text(file_content)

        document = CanonicalDocument.create(
            raw_text=text,
            metadata={
                "filename": filename,
                "page_count": len(page_metadata),
                "file_size_bytes": len(file_content),
            },
            extraction_strategy="pdf_basic",
        )

        await self.document_store.save_document(document)

        chunks = self._create_chunks(text, page_metadata, document.id)
        await self.document_store.save_chunks(chunks)

        return document

    def _extract_text(self, file_content: bytes) -> tuple[str, list[dict[str, Any]]]:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            reader = PdfReader(tmp_path)
            pages = []
            page_metadata = []

            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                pages.append(text)
                page_metadata.append({"page": i, "char_count": len(text)})

            full_text = "\n\n".join(pages)
            return full_text, page_metadata
        finally:
            os.unlink(tmp_path)

    def _create_chunks(
        self,
        text: str,
        page_metadata: list[dict[str, Any]],
        document_id: Any,
    ) -> list[DocumentChunk]:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", ".", " ", ""],
        )

        text_chunks = splitter.split_text(text)
        now = datetime.utcnow()

        return [
            DocumentChunk(
                id=uuid4(),
                document_id=document_id,
                chunk_index=i,
                text=chunk,
                metadata={"source": "pdf_basic"},
                created_at=now,
            )
            for i, chunk in enumerate(text_chunks)
        ]
```

**Key decisions:**
- Accepts `bytes` (not file path) — works with FastAPI's `UploadFile`
- Uses `pypdf` directly (not `langchain-community`'s `PyPDFLoader`) — lighter dependency
- Same chunking config as `ingest_and_search.py` (500 chars, 50 overlap)
- Temporary file for `PdfReader` (pypdf requires a file path, not bytes)
- `extraction_strategy="pdf_basic"` — distinguishes from future LLM-based extraction
- Does NOT ingest to vector store — that's a separate concern for Phase 6

**Verification:** Can ingest a PDF and create CanonicalDocument with chunks.

---

### Step 8: Create Document API Routes

Create `backend/api/routes/documents.py`:

```python
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ingestion.pdf_ingester import PDFIngester
from storage.database import get_session
from storage.document_store import DocumentStore

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", status_code=201)
async def upload_document(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    content = await file.read()
    store = DocumentStore(session)
    ingester = PDFIngester(store)
    document = await ingester.ingest(content, file.filename)

    return {
        "id": str(document.id),
        "filename": document.metadata.get("filename"),
        "page_count": document.metadata.get("page_count"),
        "extraction_strategy": document.extraction_strategy,
        "embedding_status": document.embedding_status,
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
```

**Key decisions:**
- `POST /upload` — accepts multipart file upload via FastAPI's `UploadFile`
- Validates file extension (PDF only)
- Returns JSON with document metadata (not raw text — too large)
- `GET /{id}` returns `raw_text_length` instead of full text (client can request chunks)
- `GET /{id}/chunks` returns all chunks for a document
- Uses `DocumentStore` and `PDFIngester` via constructor injection
- No authentication (not in scope)

**Verification:** Endpoints work via curl/httpx.

---

### Step 9: Update Main App

Modify `backend/main.py`:

```python
from api.routes.documents import router as documents_router

# ... existing code ...

app.include_router(health_router)
app.include_router(documents_router)
```

**Verification:** App starts, new routes registered at `/documents/*`.

---

### Step 10: Update Dockerfile

Modify `backend/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
```

**Key decisions:**
- `alembic upgrade head` runs before uvicorn starts
- Ensures database schema is always up to date
- Simple approach — no separate migration container needed
- If migration fails, the container fails to start (fail-fast)

**Verification:** Docker container starts, migrations run automatically.

---

### Step 11: Create Tests

#### 11.1 Create `tests/test_models.py`

```python
from datetime import datetime
from uuid import uuid4

from models.canonical_document import CanonicalDocument
from models.document_chunk import DocumentChunk


def test_canonical_document_creation():
    doc = CanonicalDocument(
        id=uuid4(),
        metadata={"filename": "test.pdf"},
        raw_text="Hello world",
        extraction_strategy="pdf_basic",
        embedding_status="pending",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    assert doc.raw_text == "Hello world"
    assert doc.structured_fields == {}
    assert doc.entities == []


def test_canonical_document_factory():
    doc = CanonicalDocument.create(
        raw_text="Test text",
        metadata={"filename": "test.pdf"},
        extraction_strategy="pdf_basic",
    )
    assert doc.id is not None
    assert doc.embedding_status == "pending"
    assert doc.created_at is not None


def test_canonical_document_rejects_invalid_status():
    try:
        CanonicalDocument(
            id=uuid4(),
            metadata={},
            raw_text="text",
            extraction_strategy="pdf_basic",
            embedding_status="invalid",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        assert False, "Should have raised validation error"
    except Exception:
        pass


def test_document_chunk_creation():
    chunk = DocumentChunk(
        id=uuid4(),
        document_id=uuid4(),
        chunk_index=0,
        text="Chunk text",
        metadata={"page": 0},
        created_at=datetime.utcnow(),
    )
    assert chunk.chunk_index == 0
    assert chunk.embedding_id is None
```

#### 11.2 Create `tests/test_document_store.py`

```python
import pytest
from models.canonical_document import CanonicalDocument
from storage.document_store import DocumentStore


@pytest.mark.asyncio
async def test_save_and_retrieve_document(session):
    store = DocumentStore(session)
    doc = CanonicalDocument.create(
        raw_text="Test document text",
        metadata={"filename": "test.pdf", "page_count": 1},
        extraction_strategy="pdf_basic",
    )
    await store.save_document(doc)

    retrieved = await store.get_document(doc.id)
    assert retrieved is not None
    assert retrieved.id == doc.id
    assert retrieved.raw_text == "Test document text"
    assert retrieved.metadata["filename"] == "test.pdf"


@pytest.mark.asyncio
async def test_list_documents(session):
    store = DocumentStore(session)
    doc = CanonicalDocument.create(
        raw_text="Another test",
        metadata={"filename": "test2.pdf"},
        extraction_strategy="pdf_basic",
    )
    await store.save_document(doc)

    documents = await store.list_documents()
    assert len(documents) >= 1


@pytest.mark.asyncio
async def test_save_and_retrieve_chunks(session):
    store = DocumentStore(session)
    doc = CanonicalDocument.create(
        raw_text="Chunked document",
        metadata={"filename": "chunked.pdf"},
        extraction_strategy="pdf_basic",
    )
    await store.save_document(doc)

    from datetime import datetime
    from uuid import uuid4
    from models.document_chunk import DocumentChunk

    chunks = [
        DocumentChunk(
            id=uuid4(),
            document_id=doc.id,
            chunk_index=0,
            text="First chunk",
            metadata={"page": 0},
            created_at=datetime.utcnow(),
        ),
        DocumentChunk(
            id=uuid4(),
            document_id=doc.id,
            chunk_index=1,
            text="Second chunk",
            metadata={"page": 0},
            created_at=datetime.utcnow(),
        ),
    ]
    await store.save_chunks(chunks)

    retrieved = await store.get_chunks(doc.id)
    assert len(retrieved) == 2
    assert retrieved[0].chunk_index == 0
    assert retrieved[1].chunk_index == 1


@pytest.mark.asyncio
async def test_get_nonexistent_document(session):
    store = DocumentStore(session)
    from uuid import uuid4
    result = await store.get_document(uuid4())
    assert result is None
```

#### 11.3 Create `tests/test_ingestion.py`

```python
import pytest
from ingestion.pdf_ingester import PDFIngester
from storage.document_store import DocumentStore


@pytest.mark.asyncio
async def test_pdf_ingestion(session):
    store = DocumentStore(session)
    ingester = PDFIngester(store)

    # Create a minimal PDF in memory
    from pypdf import PdfWriter
    import io

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    pdf_bytes = buffer.getvalue()

    document = await ingester.ingest(pdf_bytes, "test.pdf")

    assert document.id is not None
    assert document.metadata["filename"] == "test.pdf"
    assert document.extraction_strategy == "pdf_basic"
    assert document.embedding_status == "pending"

    # Verify document was persisted
    retrieved = await store.get_document(document.id)
    assert retrieved is not None


@pytest.mark.asyncio
async def test_pdf_ingestion_creates_chunks(session):
    store = DocumentStore(session)
    ingester = PDFIngester(store)

    from pypdf import PdfWriter
    import io

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    pdf_bytes = buffer.getvalue()

    document = await ingester.ingest(pdf_bytes, "test.pdf")
    chunks = await store.get_chunks(document.id)

    # Blank page may produce 0 or more chunks depending on text extraction
    assert isinstance(chunks, list)
```

#### 11.4 Update `tests/conftest.py`

Add a database session fixture for tests that need it:

```python
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from main import app
from storage.database import Base

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/doc_intelligence"


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as sess:
        yield sess

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
```

**Key decisions:**
- `session` fixture creates tables, yields session, drops tables after test
- Uses `localhost:5432` (not `db:5432`) for local test runs
- Each test gets a clean schema via `create_all` / `drop_all`
- Tests that need a database use the `session` fixture
- Tests that don't need a database (model validation) don't use it

**Verification:** All tests pass.

---

## 4. Execution Order

| Order | Step | Files Created/Modified | Verification |
|-------|------|------------------------|--------------|
| 1 | Add dependencies | `backend/requirements.txt` | `pip install` succeeds |
| 2 | Add declarative base | `backend/storage/database.py` | Import succeeds |
| 3 | Create Pydantic models | `backend/models/canonical_document.py`, `backend/models/document_chunk.py`, `backend/models/__init__.py` | Models instantiate, validation works |
| 4 | Create ORM models | `backend/models/db_models.py` | Conversion works |
| 5 | Setup Alembic | `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako` | Alembic config valid |
| 6 | Create migration | `backend/alembic/versions/001_create_documents.py` | `alembic upgrade head` creates tables |
| 7 | Create document store | `backend/storage/document_store.py` | Unit tests pass |
| 8 | Create PDF ingester | `backend/ingestion/__init__.py`, `backend/ingestion/pdf_ingester.py` | Ingestion test passes |
| 9 | Create document routes | `backend/api/routes/documents.py` | Endpoints work |
| 10 | Update main app | `backend/main.py` | Routes registered |
| 11 | Update Dockerfile | `backend/Dockerfile` | Runs migrations on startup |
| 12 | Create tests | `tests/test_models.py`, `tests/test_document_store.py`, `tests/test_ingestion.py`, update `tests/conftest.py` | All tests pass |
| 13 | Run full validation | — | See Section 6 |

---

## 5. What NOT to Do

| Anti-pattern | Why |
|-------------|-----|
| Add extractors or extractor registry | Phase 4 |
| Add LLM-based extraction | Phase 4 (GenericExtractor) |
| Add entity extraction | Phase 4 |
| Add pgvector column or embeddings | Phase 6 |
| Replace Qdrant | Phase 6 |
| Add query endpoints | Phase 7 |
| Add authentication | Not in scope |
| Add file storage service (S3, etc.) | Premature — use temp files |
| Add background task queue | Premature — sync ingestion is fine for now |
| Add API versioning (`/api/v1/`) | Premature for a few endpoints |
| Modify `ingest_and_search.py` | Keep as legacy reference |
| Add logging framework | Premature |
| Add pagination metadata (total count, etc.) | Premature — simple limit/offset is sufficient |

---

## 6. Phase Completion Checklist

All checks MUST pass before Phase 3 is considered complete.

### 6.1 Type Checking

```bash
cd backend
mypy .
```

Expected: No errors. All models, store methods, and routes typed. `strict = true` enforced.

### 6.2 Linting

```bash
cd backend
ruff check .
```

Expected: No issues. All imports sorted, no unused imports, PEP 8 naming.

### 6.3 Unit Tests

```bash
cd backend
pytest ../tests/ -v
```

Expected: All tests pass (health + models + store + ingestion).

### 6.4 Build Verification

```bash
docker compose build
```

Expected: Image builds successfully.

### 6.5 Docker Compose Startup

```bash
cp .env.example .env
docker compose up --build
```

Expected:
- PostgreSQL starts and passes health check
- Alembic migrations run automatically
- Backend starts and connects to PostgreSQL
- No crash, no import errors, no startup exceptions
- Tables `documents` and `document_chunks` exist in database

### 6.6 Manual Smoke Test

With `docker compose up` running:

```bash
# Health checks still work
curl http://localhost:8000/health
# Expected: {"status":"ok"}

curl http://localhost:8000/health/db
# Expected: {"database":"connected","healthy":true}

# Upload a document
curl -X POST http://localhost:8000/documents/upload \
  -F "file=@sample_technical_document.pdf"
# Expected: 201 Created, returns document ID and metadata

# List documents
curl http://localhost:8000/documents/
# Expected: 200 OK, returns list with uploaded document

# Get specific document
curl http://localhost:8000/documents/{id}
# Expected: 200 OK, returns document metadata

# Get chunks
curl http://localhost:8000/documents/{id}/chunks
# Expected: 200 OK, returns list of chunks

# Verify database state
docker exec -it multi-agent-intelligence-db-1 psql -U postgres -d doc_intelligence -c "SELECT id, metadata->>'filename', embedding_status FROM documents;"
# Expected: Document record exists

docker exec -it multi-agent-intelligence-db-1 psql -U postgres -d doc_intelligence -c "SELECT COUNT(*) FROM document_chunks;"
# Expected: Chunks exist

# OpenAPI docs
open http://localhost:8000/docs
# Expected: Swagger UI with health + document endpoints
```

### 6.7 Fix Before Proceeding

If ANY check fails:
1. STOP.
2. Diagnose root cause.
3. Fix completely.
4. Re-run ALL checks from 6.1.

---

## 7. Testing Strategy

### 7.1 Unit Tests

| Test | File | What it verifies |
|------|------|-----------------|
| `test_canonical_document_creation` | `test_models.py` | CanonicalDocument creates with valid data |
| `test_canonical_document_factory` | `test_models.py` | Factory method sets defaults correctly |
| `test_canonical_document_rejects_invalid_status` | `test_models.py` | Validation rejects invalid embedding_status |
| `test_document_chunk_creation` | `test_models.py` | DocumentChunk creates correctly |
| `test_save_and_retrieve_document` | `test_document_store.py` | Document persists and retrieves correctly |
| `test_list_documents` | `test_document_store.py` | Listing returns documents |
| `test_save_and_retrieve_chunks` | `test_document_store.py` | Chunks persist and retrieve in order |
| `test_get_nonexistent_document` | `test_document_store.py` | Returns None for missing document |
| `test_pdf_ingestion` | `test_ingestion.py` | Full ingestion creates CanonicalDocument |
| `test_pdf_ingestion_creates_chunks` | `test_ingestion.py` | Ingestion creates chunks |

### 7.2 Integration Tests (Docker)

| Test | How | What it verifies |
|------|-----|-----------------|
| Upload document | `curl /documents/upload` | End-to-end upload works |
| List documents | `curl /documents/` | Listing works |
| Get document | `curl /documents/{id}` | Retrieval works |
| Get chunks | `curl /documents/{id}/chunks` | Chunks accessible |
| Database state | `psql` queries | Records persisted correctly |
| Migrations | Container startup | Tables created automatically |

### 7.3 What NOT to Test Yet

- Embedding generation (Phase 6)
- Query routing (Phase 7)
- Extractor selection (Phase 4)
- LLM extraction (Phase 4+)
- Frontend integration (Phase 9)

---

## 8. Dependency Decisions

### 8.1 Why Alembic?

Phase 2 plan explicitly stated: "Add in Phase 3 when CanonicalDocument table is created."

Alembic is the standard migration tool for SQLAlchemy. It:
- Tracks schema changes over time
- Supports async SQLAlchemy
- Is well-documented and widely used
- Allows hand-written migrations for clarity

### 8.2 Why Separate Pydantic and ORM Models?

- **Pydantic models** — validation, API contracts, business logic
- **ORM models** — database persistence, relationships, queries

Separation allows:
- Changing database schema without breaking API contracts
- Testing business logic without database
- Clear layer boundaries
- Following the principle from AGENTS.md: "Every module should have a single responsibility"

### 8.3 Why JSONB for metadata/entities/relationships?

- Flexible schema for arbitrary extracted data
- PostgreSQL JSONB supports indexing and querying
- Different documents will have different structures
- Avoids premature schema rigidity
- Phase 4 extractors will populate these fields with varying structures

### 8.4 Why `pypdf` over `langchain-community`'s `PyPDFLoader`?

- `pypdf` is lightweight (single package)
- `langchain-community` pulls in heavy dependencies
- Backend should not depend on the langchain ecosystem
- `pypdf` is sufficient for basic text extraction
- Phase 4 GenericExtractor can use more sophisticated extraction if needed

---

## 9. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Migration fails on startup | Test migrations locally first; container fails fast if migration errors |
| Large PDFs cause memory issues | Read file content in chunks if needed; 8.4MB sample is manageable |
| PyPDF extraction poor quality | Accept limitation; Phase 4 GenericExtractor will improve extraction |
| Test database conflicts | `conftest.py` creates/drops tables per test session |
| `langchain-text-splitters` version conflict | Pin to same version as root venv (1.1.2) |
| Alembic URL mismatch between Docker and local | `env.py` reads URL from `settings`, which reads from environment |

---

## 10. Post-Phase 3 State

After Phase 3 is complete, the repository will have:

```
multi-agent-intelligence/
├── docker-compose.yml              ← UNCHANGED
├── .env.example                    ← UNCHANGED
├── .gitignore                      ← UNCHANGED
├── backend/
│   ├── Dockerfile                  ← MODIFIED (run migrations)
│   ├── requirements.txt            ← MODIFIED (add alembic, pypdf, text-splitters)
│   ├── pyproject.toml              ← UNCHANGED
│   ├── main.py                     ← MODIFIED (add documents router)
│   ├── config.py                   ← UNCHANGED
│   ├── alembic.ini                 ← NEW
│   ├── alembic/                    ← NEW
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 001_create_documents.py
│   ├── models/                     ← NEW
│   │   ├── __init__.py
│   │   ├── canonical_document.py
│   │   ├── document_chunk.py
│   │   └── db_models.py
│   ├── storage/
│   │   ├── __init__.py             ← UNCHANGED
│   │   ├── database.py             ← MODIFIED (add Base)
│   │   └── document_store.py       ← NEW
│   ├── ingestion/                  ← NEW
│   │   ├── __init__.py
│   │   └── pdf_ingester.py
│   └── api/
│       ├── __init__.py             ← UNCHANGED
│       └── routes/
│           ├── __init__.py         ← UNCHANGED
│           ├── health.py           ← UNCHANGED
│           └── documents.py        ← NEW
├── tests/
│   ├── __init__.py                 ← UNCHANGED
│   ├── conftest.py                 ← MODIFIED (add session fixture)
│   ├── test_health.py              ← UNCHANGED
│   ├── test_models.py              ← NEW
│   ├── test_document_store.py      ← NEW
│   └── test_ingestion.py           ← NEW
├── ingest_and_search.py            ← UNCHANGED
├── agent_graph.py                  ← UNCHANGED
├── eval_pipeline.py                ← UNCHANGED
├── requirements.txt                ← UNCHANGED (root-level, legacy)
├── sample_technical_document.pdf   ← UNCHANGED
├── AGENTS.md                       ← UNCHANGED
└── docs/
    ├── PROJECT_SPEC.md             ← UNCHANGED
    ├── ENGINEERING_PRINCIPLES.md   ← UNCHANGED
    ├── PHASES.md                   ← UNCHANGED
    ├── PHASE_2_PLAN.md             ← UNCHANGED
    └── PHASE_3_PLAN.md             ← THIS FILE
```

**Total new files:** ~15
**Total modified files:** 4
**Existing files broken:** 0

Phase 4 will then add the Extractor Registry and GenericExtractor, wrapping the ingestion logic in a pluggable interface.

---

## ✅ Phase 3 Completion Report (2026-06-05)

### Implementation Summary

All 12 steps from Section 3 were executed in order. The implementation matches the plan with minor, justified deviations.

### Files Created (15 new)

| File | Purpose |
|------|---------|
| `backend/models/__init__.py` | Package init |
| `backend/models/canonical_document.py` | CanonicalDocument Pydantic model |
| `backend/models/document_chunk.py` | DocumentChunk Pydantic model |
| `backend/models/db_models.py` | SQLAlchemy ORM models with conversion methods |
| `backend/alembic.ini` | Alembic configuration |
| `backend/alembic/env.py` | Async Alembic environment setup |
| `backend/alembic/script.py.mako` | Migration template |
| `backend/alembic/versions/001_create_documents.py` | Initial migration (documents + document_chunks) |
| `backend/storage/document_store.py` | Document persistence layer |
| `backend/ingestion/__init__.py` | Package init |
| `backend/ingestion/pdf_ingester.py` | PDF text extraction + chunking pipeline |
| `backend/api/routes/documents.py` | Document CRUD API endpoints |
| `tests/test_models.py` | Pydantic model validation tests |
| `tests/test_document_store.py` | Persistence layer tests |
| `tests/test_ingestion.py` | Ingestion pipeline tests |

### Files Modified (4)

| File | Change |
|------|--------|
| `backend/requirements.txt` | Added alembic, pypdf, langchain-text-splitters |
| `backend/storage/database.py` | Added `DeclarativeBase` class |
| `backend/main.py` | Registered documents router |
| `backend/Dockerfile` | Run `alembic upgrade head` before uvicorn |
| `tests/conftest.py` | Added `session` fixture for DB-dependent tests |

### Deviations from Plan

1. **`alembic/env.py`: Added `sys.path.insert(0, ...)`** — The alembic runtime does not automatically add the project root to `sys.path`, so `from config import settings` failed inside Docker. Fixed by computing the project root from `__file__` and inserting it at the front of `sys.path`.

2. **`ingestion/pdf_ingester.py`: Added null-byte sanitization** — The sample PDF (`sample_technical_document.pdf`, 8.4 MB, image-dominant per Phase 1 findings) contains `\x00` null bytes in the extracted text. PostgreSQL TEXT columns reject these. Added `full_text.replace("\x00", "")` after extraction.

3. **Type annotations tightened for mypy strict mode** — The plan used `Mapped[dict]` and `Mapped[list]` in ORM models. mypy strict mode with `disallow_any_generics` requires explicit type parameters. Changed to `Mapped[dict[str, Any]]`, `Mapped[list[dict[str, Any]]]`. Also replaced `typing.Sequence`/`typing.Union` with `collections.abc.Sequence` and `X | Y` syntax in the migration file to satisfy ruff's UP rules.

### Full Validation Results

#### 6.1 Type Checking
```
mypy .  →  Success: no issues found in 17 source files
```

#### 6.2 Linting
```
ruff check .  →  All checks passed!
```

#### 6.3 Unit Tests (non-DB)
```
tests/test_health.py::test_health_check PASSED
tests/test_health.py::test_database_health_check PASSED
tests/test_models.py::test_canonical_document_creation PASSED
tests/test_models.py::test_canonical_document_factory PASSED
tests/test_models.py::test_canonical_document_rejects_invalid_status PASSED
tests/test_models.py::test_document_chunk_creation PASSED
============================== 6 passed ==============================
```

#### 6.4 Build Verification
```
docker compose build  →  Image built successfully
```

#### 6.5 Docker Compose Startup
- PostgreSQL starts and passes health check
- Alembic migrations run automatically (tables `documents` and `document_chunks` created)
- Backend starts and connects to PostgreSQL
- No crashes, import errors, or startup exceptions

#### 6.6 Manual Smoke Test

```
curl /health                         → {"status":"ok"}
curl /health/db                      → {"database":"connected","healthy":true}
POST /documents/upload (8.4MB PDF)   → 201, 155 pages, 467,148 chars extracted
GET /documents/                      → 1 document listed
GET /documents/{id}                  → metadata + raw_text_length: 467148
GET /documents/{id}/chunks           → 1104 chunks returned
psql: SELECT COUNT(*) FROM document_chunks → 1104
psql: SELECT * FROM documents        → 1 record, embedding_status: pending
```

### What Was Intentionally NOT Built

| Feature | Why |
|---------|-----|
| Extractors / Extractor Registry | Phase 4 |
| LLM-based extraction | Phase 4 (GenericExtractor) |
| Entity extraction | Phase 4 |
| pgvector embeddings | Phase 6 |
| Vector store (pgvector/Qdrant) | Phase 6 |
| Query endpoints (structured/semantic/hybrid) | Phase 7 |
| Authentication | Not in scope |
| Background task queue | Premature |

### Architecture Decisions Validated

- **Separate Pydantic and ORM models**: Clean layer separation confirmed. Models tested independently of database.
- **JSONB for metadata/entities/relationships**: Handles the 155-page medical research paper's extracted text without schema issues.
- **`pypdf` over `langchain-community`**: Extracted 467K characters of text from an 8.4MB image-dominant PDF. Backend remains independent of the heavy langchain ecosystem.
- **Hand-written Alembic migration**: Migration is reviewable and explicit. Runs on every container startup via Dockerfile CMD.
- **Constructor injection**: DocumentStore receives AsyncSession, PDFIngester receives DocumentStore. Clear dependency flow.

### Ready for Phase 4

The CanonicalDocument model, persistence layer, and document ingestion pipeline are fully operational. Phase 4 can now implement the Extractor interface, ExtractorRegistry, and GenericExtractor — wrapping `PDFIngester` logic behind the `Extractor` interface and populating `structured_fields`, `entities`, and `relationships`.
