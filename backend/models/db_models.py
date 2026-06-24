from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storage.database import Base

if TYPE_CHECKING:
    from models.canonical_document import CanonicalDocument
    from models.document_chunk import DocumentChunk


class DocumentModel(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    structured_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    entities: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default="[]")
    relationships: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default="[]")
    extraction_strategy: Mapped[str] = mapped_column(String(50), nullable=False)
    embedding_status: Mapped[Literal["pending", "completed", "failed"]] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="completed")
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    token_usage: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    processed_chunk: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    node_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rel_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    chunks: Mapped[list[DocumentChunkModel]] = relationship(
        "DocumentChunkModel", back_populates="document", cascade="all, delete-orphan"
    )

    def to_canonical(self) -> CanonicalDocument:
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
    def from_canonical(cls, doc: CanonicalDocument) -> DocumentModel:
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
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, server_default="{}")
    embedding_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(40), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    length: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    content_offset: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    document: Mapped[DocumentModel] = relationship("DocumentModel", back_populates="chunks")

    def to_model(self) -> DocumentChunk:
        from models.document_chunk import DocumentChunk

        return DocumentChunk(
            id=self.id,
            document_id=self.document_id,
            chunk_index=self.chunk_index,
            text=self.text,
            metadata=self.metadata_,
            embedding_id=self.embedding_id,
            embedding=self.embedding,
            content_hash=self.content_hash,
            position=self.position,
            length=self.length,
            content_offset=self.content_offset,
            page_number=self.page_number,
            created_at=self.created_at,
        )

    @classmethod
    def from_model(cls, chunk: DocumentChunk) -> DocumentChunkModel:
        return cls(
            id=chunk.id,
            document_id=chunk.document_id,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            metadata_=chunk.metadata,
            embedding_id=chunk.embedding_id,
            embedding=chunk.embedding,
            content_hash=chunk.content_hash,
            position=chunk.position,
            length=chunk.length,
            content_offset=chunk.content_offset,
            page_number=chunk.page_number,
            created_at=chunk.created_at,
        )
