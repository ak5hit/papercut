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
    embedding: list[float] | None = None
    content_hash: str | None = None
    position: int = 0
    length: int = 0
    content_offset: int = 0
    page_number: int | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
