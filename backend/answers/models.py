from typing import Any

from pydantic import BaseModel


class SourceReference(BaseModel):
    document_id: str
    document_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "document_name": self.document_name,
        }


class ComposedAnswer(BaseModel):
    answer: str
    sources: list[SourceReference]
    trace: dict[str, Any]
    # Keep generated_cypher on the model for server-side debugging/logging.
    # Deliberately excluded from to_dict() — the frontend does not render it.
    generated_cypher: str | None = None
    cypher_context: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "sources": [s.to_dict() for s in self.sources],
            "trace": self.trace,
        }
