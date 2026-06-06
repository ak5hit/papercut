from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.canonical_document import CanonicalDocument
from models.db_models import DocumentChunkModel, DocumentModel
from models.document_chunk import DocumentChunk


@dataclass
class ChunkSearchResult:
    chunk: DocumentChunk
    score: float


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

    async def update_embedding_status(
        self, document_id: UUID, status: Literal["pending", "completed", "failed"]
    ) -> None:
        result = await self.session.execute(
            select(DocumentModel).where(DocumentModel.id == document_id)
        )
        model = result.scalar_one_or_none()
        if model:
            model.embedding_status = status
            await self.session.commit()

    async def save_chunk_embeddings(
        self, document_id: UUID, embeddings: list[list[float]]
    ) -> None:
        result = await self.session.execute(
            select(DocumentChunkModel)
            .where(DocumentChunkModel.document_id == document_id)
            .order_by(DocumentChunkModel.chunk_index)
        )
        models = result.scalars().all()
        for model, embedding in zip(models, embeddings, strict=True):
            model.embedding = embedding
        await self.session.commit()

    async def delete_document(self, document_id: UUID) -> bool:
        result = await self.session.execute(
            select(DocumentModel).where(DocumentModel.id == document_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return False
        await self.session.delete(model)
        await self.session.commit()
        return True

    async def semantic_search(
        self, query_embedding: list[float], limit: int = 5
    ) -> list[ChunkSearchResult]:
        result = await self.session.execute(
            select(
                DocumentChunkModel,
                DocumentChunkModel.embedding.cosine_distance(query_embedding).label("distance"),
            )
            .where(DocumentChunkModel.embedding.is_not(None))
            .order_by("distance")
            .limit(limit)
        )
        rows = result.all()
        return [
            ChunkSearchResult(
                chunk=model.to_model(),
                score=round(1.0 - distance, 4),
            )
            for model, distance in rows
        ]
