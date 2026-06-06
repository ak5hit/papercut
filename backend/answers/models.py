from typing import Any

from pydantic import BaseModel


class SourceReference(BaseModel):
    document_id: str
    document_name: str
    chunk_index: int | None = None
    page: int | None = None
    excerpt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "document_name": self.document_name,
            "chunk_index": self.chunk_index,
            "page": self.page,
            "excerpt": self.excerpt,
        }


class ComposedAnswer(BaseModel):
    answer: str
    sources: list[SourceReference]
    trace: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "sources": [s.to_dict() for s in self.sources],
            "trace": self.trace,
        }
