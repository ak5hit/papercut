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
