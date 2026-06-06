import json
import os
import tempfile
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from embeddings.base import EmbeddingProvider
from extractors.base import DocumentInput, Extractor
from llm.base import LLMProvider
from models.canonical_document import CanonicalDocument
from models.document_chunk import DocumentChunk
from storage.document_store import DocumentStore

ENTITY_EXTRACTION_PROMPT = """You are an entity extraction system.
Extract all entities and relationships from this document text.

Return ONLY valid JSON in this exact format:
{{
  "entities": [
    {{"name": "Entity Name", "type": "PERSON|ORGANIZATION|LOCATION|DATE|MONEY|OTHER", "value": "normalized value"}}
  ],
  "relationships": [
    {{"source": "Entity1", "target": "Entity2", "type": "WORKS_AT|LOCATED_IN|PART_OF|OTHER", "description": "optional"}}
  ]
}}

If no entities are found, return {{"entities": [], "relationships": []}}.

DOCUMENT TEXT:
{text}
"""


class GenericExtractor(Extractor):
    DEFAULT_SIZE_THRESHOLD = 100_000

    def __init__(
        self,
        document_store: DocumentStore,
        llm_provider: LLMProvider | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        size_threshold: int = DEFAULT_SIZE_THRESHOLD,
    ) -> None:
        self.document_store = document_store
        self.llm_provider = llm_provider
        self.embedding_provider = embedding_provider
        self.size_threshold = size_threshold

    def supports(self, document: DocumentInput) -> float:
        if document.filename.lower().endswith(".pdf"):
            return 0.1
        return 0.0

    async def extract(self, document: DocumentInput) -> CanonicalDocument:
        text, page_metadata = self._extract_text(document.content)
        is_small = len(text) < self.size_threshold

        metadata = self._build_metadata(document, page_metadata)
        strategy = "generic_small" if is_small else "generic_large"

        doc = CanonicalDocument.create(
            raw_text=text,
            metadata=metadata,
            extraction_strategy=strategy,
        )

        chunks = self._create_chunks(text, doc.id)

        if is_small:
            doc.structured_fields = self._build_structured_fields(text, page_metadata, chunks)

            if self.llm_provider:
                entities, relationships = await self._extract_entities(text, self.llm_provider)
                doc.entities = entities
                doc.relationships = relationships

        await self.document_store.save_document(doc)
        await self.document_store.save_chunks(chunks)

        if self.embedding_provider:
            texts = [chunk.text for chunk in chunks]
            embeddings = self.embedding_provider.embed(texts)
            await self.document_store.save_chunk_embeddings(doc.id, embeddings)
            await self.document_store.update_embedding_status(doc.id, "completed")
            doc.embedding_status = "completed"
        else:
            await self.document_store.update_embedding_status(doc.id, "failed")
            doc.embedding_status = "failed"

        return doc

    async def _extract_entities(
        self,
        text: str,
        llm_provider: LLMProvider,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        prompt = ENTITY_EXTRACTION_PROMPT.format(text=text)

        try:
            response = await llm_provider.complete(prompt, max_tokens=4000)
            data = json.loads(response)
            entities: list[dict[str, Any]] = data.get("entities", [])
            relationships: list[dict[str, Any]] = data.get("relationships", [])
            return entities, relationships
        except (json.JSONDecodeError, KeyError, httpx.HTTPError):
            return [], []

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
            full_text = full_text.replace("\x00", "")
            return full_text, page_metadata
        finally:
            os.unlink(tmp_path)

    def _build_metadata(
        self,
        document: DocumentInput,
        page_metadata: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "filename": document.filename,
            "page_count": len(page_metadata),
            "file_size_bytes": len(document.content),
        }

    def _build_structured_fields(
        self,
        text: str,
        page_metadata: list[dict[str, Any]],
        chunks: list[DocumentChunk],
    ) -> dict[str, Any]:
        total_chunks = len(chunks)
        avg_chunk_size = sum(len(c.text) for c in chunks) // total_chunks if total_chunks else 0
        return {
            "page_count": len(page_metadata),
            "total_characters": len(text),
            "total_chunks": total_chunks,
            "avg_chunk_size": avg_chunk_size,
        }

    def _create_chunks(
        self,
        text: str,
        document_id: UUID,
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
                metadata={"source": "generic_extractor"},
                created_at=now,
            )
            for i, chunk in enumerate(text_chunks)
        ]
