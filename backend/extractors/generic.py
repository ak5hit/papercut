import json
import os
import re
import tempfile
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from embeddings.base import EmbeddingProvider
from extractors.base import DocumentInput, Extractor
from extractors.pipeline_trace import PipelineTrace
from llm.base import LLMProvider
from models.canonical_document import CanonicalDocument
from models.document_chunk import DocumentChunk
from storage.document_store import DocumentStore

# NOTE: Entity/relationship extraction is temporarily disabled to speed up uploads.
# The _extract_entities method is preserved below for future re-activation.
# To re-enable, uncomment lines 75-78 in extract().
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

    async def extract(self, document: DocumentInput) -> tuple[CanonicalDocument, PipelineTrace]:
        trace = PipelineTrace(extractor="GenericExtractor")
        if document.document_type:
            trace.add_step("Selected extractor: GenericExtractor", f"document_type={document.document_type}")
        else:
            trace.add_step("Selected extractor: GenericExtractor", f"score={self.supports(document)}")

        text, page_metadata, pages = self._extract_text(document.content)
        trace.add_step(f"Extracted text from {len(page_metadata)} pages", f"{len(text)} characters")

        is_small = len(text) < self.size_threshold

        if is_small:
            trace.add_step("Document classified as small", f"< {self.size_threshold:,} characters")
        else:
            trace.add_step("Document classified as large", f">= {self.size_threshold:,} characters")

        metadata = self._build_metadata(document, page_metadata)
        strategy = "generic_small" if is_small else "generic_large"

        doc = CanonicalDocument.create(
            raw_text=text,
            metadata=metadata,
            extraction_strategy=strategy,
        )

        chunks = self._create_chunks(pages, doc.id, is_small)

        if is_small:
            doc.structured_fields = self._build_structured_fields(text, page_metadata, chunks)
            trace.add_step("Extracted structured fields",
                           "page_count, total_characters, detected_emails, detected_phone_numbers")

            # NOTE: Entity/relationship extraction disabled for upload speed.
            # Re-enable by uncommenting the block below.
            # if self.llm_provider:
            #     entities, relationships = await self._extract_entities(text, self.llm_provider)
            #     doc.entities = entities
            #     doc.relationships = relationships
        else:
            trace.add_step("Skipped structured field extraction", "large documents use lightweight metadata only")

        await self.document_store.save_document(doc)
        await self.document_store.save_chunks(chunks)

        chunk_size = 1000 if is_small else 500
        chunk_overlap = 100 if is_small else 50
        trace.add_step(f"Created {len(chunks)} chunks", f"{chunk_size} chars, {chunk_overlap} overlap")

        if self.embedding_provider:
            texts = [chunk.text for chunk in chunks]
            embeddings = self.embedding_provider.embed(texts)
            await self.document_store.save_chunk_embeddings(doc.id, embeddings)
            await self.document_store.update_embedding_status(doc.id, "completed")
            doc.embedding_status = "completed"
            trace.add_step(f"Generated {len(chunks)} embeddings", "384-dim, bge-small-en-v1.5")
        else:
            await self.document_store.update_embedding_status(doc.id, "failed")
            doc.embedding_status = "failed"

        trace.add_step("Saved to database")

        if is_small:
            trace.set_extracted_fields({
                "page_count": len(page_metadata),
                "total_characters": len(text),
                "total_chunks": len(chunks),
                "detected_emails": doc.structured_fields.get("detected_emails", []) if doc.structured_fields else [],
                "detected_phone_numbers": (
                    doc.structured_fields.get("detected_phone_numbers", [])
                    if doc.structured_fields else []
                ),
            })
        else:
            trace.set_extracted_fields({
                "page_count": len(page_metadata),
                "total_characters": len(text),
                "total_chunks": len(chunks),
            })

        return doc, trace

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

    def _extract_text(self, file_content: bytes) -> tuple[str, list[dict[str, Any]], list[str]]:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            reader = PdfReader(tmp_path)
            pages: list[str] = []
            page_metadata = []

            for i, page in enumerate(reader.pages):
                text = (page.extract_text() or "").replace("\x00", "")
                pages.append(text)
                page_metadata.append({"page": i, "char_count": len(text)})

            full_text = "\n\n".join(pages)
            return full_text, page_metadata, pages
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

    def _extract_emails(self, text: str) -> list[str]:
        pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        return list(set(re.findall(pattern, text)))

    def _extract_phone_numbers(self, text: str) -> list[str]:
        # Indian mobile numbers: +91 prefix optional, 10 digits starting with 6-9
        patterns = [
            r"\+91[\s-]?\d{5}[\s-]?\d{5}",      # +91 88728 00037 or +91-88728-00037
            r"\+91[\s-]?\d{10}",                  # +91 8872800037 or +918872800037
            r"[6789]\d{9}",                        # 8872800037 (10 digits, starts with 6-9)
        ]
        found: set[str] = set()
        for pattern in patterns:
            found.update(re.findall(pattern, text))
        return list(found)

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
            "detected_emails": self._extract_emails(text),
            "detected_phone_numbers": self._extract_phone_numbers(text),
        }

    def _create_chunks(
        self,
        pages: list[str],
        document_id: UUID,
        is_small: bool,
    ) -> list[DocumentChunk]:
        chunk_size = 1000 if is_small else 500
        chunk_overlap = 100 if is_small else 50
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ".", " ", ""],
        )

        now = datetime.utcnow()
        all_chunks: list[DocumentChunk] = []
        chunk_index = 0

        for page_num, page_text in enumerate(pages):
            if not page_text.strip():
                continue
            page_chunks = splitter.split_text(page_text)
            for chunk in page_chunks:
                all_chunks.append(
                    DocumentChunk(
                        id=uuid4(),
                        document_id=document_id,
                        chunk_index=chunk_index,
                        text=chunk,
                        metadata={"page": page_num, "source": "generic_extractor"},
                        created_at=now,
                    )
                )
                chunk_index += 1

        return all_chunks
