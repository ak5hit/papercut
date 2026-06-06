from abc import ABC, abstractmethod
from dataclasses import dataclass

from models.canonical_document import CanonicalDocument


@dataclass(frozen=True)
class DocumentInput:
    content: bytes
    filename: str
    content_type: str | None = None


class Extractor(ABC):
    @abstractmethod
    def supports(self, document: DocumentInput) -> float:
        ...

    @abstractmethod
    async def extract(self, document: DocumentInput) -> CanonicalDocument:
        ...
