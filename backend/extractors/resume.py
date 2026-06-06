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

RESUME_EXTRACTION_PROMPT = """Extract structured data from this resume. Return ONLY valid JSON:
{{
  "name": "full name",
  "location": "city, state/country",
  "summary": "2-3 sentence professional summary",
  "skills": ["skill1", "skill2", ...],
  "total_experience_years": <int or null>,
  "current_role": "current job title",
  "experience": [
    {{
      "company": "...",
      "role": "...",
      "start_date": "YYYY-MM",
      "end_date": "YYYY-MM or Present",
      "responsibilities": ["bullet point 1", "bullet point 2", ...]
    }}
  ],
  "education": [
    {{"institution": "...", "degree": "...", "field": "...", "year": "YYYY"}}
  ]
}}
If a field cannot be determined, use null.

RESUME TEXT:
{text}
"""


class ResumeExtractor(Extractor):
    def __init__(
        self,
        document_store: DocumentStore,
        llm_provider: LLMProvider | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.document_store = document_store
        self.llm_provider = llm_provider
        self.embedding_provider = embedding_provider

    def supports(self, document: DocumentInput) -> float:
        if not document.filename.lower().endswith(".pdf"):
            return 0.0
        if document.document_type == "resume":
            return 0.9
        return 0.0

    async def extract(self, document: DocumentInput) -> tuple[CanonicalDocument, PipelineTrace]:
        trace = PipelineTrace(extractor="ResumeExtractor")
        if document.document_type == "resume":
            trace.add_step("Selected extractor: ResumeExtractor", f"document_type={document.document_type}")
        else:
            trace.add_step("Selected extractor: ResumeExtractor", f"score={self.supports(document)}")

        text, page_metadata, pages = self._extract_text(document.content)
        trace.add_step(f"Extracted text from {len(page_metadata)} pages", f"{len(text)} characters")

        metadata = self._build_metadata(document, page_metadata)

        doc = CanonicalDocument.create(
            raw_text=text,
            metadata=metadata,
            extraction_strategy="resume",
        )

        deterministic_fields = self._extract_deterministic(text)
        present_fields = [k for k, v in deterministic_fields.items() if v]
        if present_fields:
            trace.add_step("Extracted deterministic fields", ", ".join(present_fields))
        else:
            trace.add_step("Extracted deterministic fields", "none found")

        semantic_fields, semantic_status = await self._extract_semantic(text)
        if self.llm_provider:
            trace.add_step("Extracted semantic fields via LLM", semantic_status)

        doc.structured_fields = self._merge_fields(deterministic_fields, semantic_fields)
        doc.entities = self._build_entities(doc.structured_fields)

        chunks = self._create_chunks(pages, doc.id)
        trace.add_step(f"Created {len(chunks)} chunks", "1000 chars, 100 overlap")

        await self.document_store.save_document(doc)
        await self.document_store.save_chunks(chunks)

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

        fields_summary = {
            "name": doc.structured_fields.get("name"),
            "email": doc.structured_fields.get("email"),
            "phone": doc.structured_fields.get("phone"),
            "skills": doc.structured_fields.get("skills", []),
            "experience_count": len(doc.structured_fields.get("experience", [])),
            "education_count": len(doc.structured_fields.get("education", [])),
            "total_experience_years": doc.structured_fields.get("total_experience_years"),
        }
        trace.set_extracted_fields(fields_summary)

        return doc, trace

    def _extract_deterministic(self, text: str) -> dict[str, Any]:
        return {
            "email": self._extract_email(text),
            "phone": self._extract_phone(text),
            "linkedin_url": self._extract_linkedin(text),
            "urls": self._extract_urls(text),
        }

    def _extract_email(self, text: str) -> str | None:
        pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        matches = re.findall(pattern, text)
        return matches[0] if matches else None

    def _extract_phone(self, text: str) -> str | None:
        patterns = [
            r"\+91[\s-]?\d{5}[\s-]?\d{5}",
            r"\+91[\s-]?\d{10}",
            r"[6789]\d{9}",
            r"\+1[\s-]?\d{3}[\s-]?\d{3}[\s-]?\d{4}",
            r"\(\d{3}\)\s*\d{3}[\s-]?\d{4}",
            r"\d{3}[\s-]?\d{3}[\s-]?\d{4}",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text)
            if matches:
                return matches[0]
        return None

    def _extract_linkedin(self, text: str) -> str | None:
        pattern = r"linkedin\.com/in/[\w-]+"
        matches = re.findall(pattern, text, re.IGNORECASE)
        return matches[0] if matches else None

    def _extract_urls(self, text: str) -> list[str]:
        pattern = r"https?://[^\s)]+"
        return list(set(re.findall(pattern, text)))

    async def _extract_semantic(self, text: str) -> tuple[dict[str, Any], str]:
        if not self.llm_provider:
            return {}, "skipped (no LLM provider)"

        prompt = RESUME_EXTRACTION_PROMPT.format(text=text)

        try:
            response = await self.llm_provider.complete(prompt, max_tokens=8000)
            data = json.loads(response)
            fields = {
                "name": data.get("name"),
                "location": data.get("location"),
                "summary": data.get("summary"),
                "skills": data.get("skills") or [],
                "total_experience_years": data.get("total_experience_years"),
                "current_role": data.get("current_role"),
                "experience": data.get("experience") or [],
                "education": data.get("education") or [],
            }
            present = [k for k, v in fields.items() if v and v != []]
            if present:
                return fields, f"{len(present)} fields extracted ({', '.join(present)})"
            return fields, "LLM returned no data"
        except json.JSONDecodeError:
            return {}, "LLM response was not valid JSON"
        except httpx.HTTPError:
            return {}, "LLM request failed"

    def _merge_fields(
        self, deterministic: dict[str, Any], semantic: dict[str, Any]
    ) -> dict[str, Any]:
        merged = {"document_type": "resume"}
        merged.update(deterministic)
        merged.update(semantic)
        return merged

    def _build_entities(self, fields: dict[str, Any]) -> list[dict[str, Any]]:
        entities = []

        if fields.get("name"):
            entities.append({"name": fields["name"], "type": "PERSON", "value": fields["name"]})

        if fields.get("email"):
            entities.append({"name": fields["email"], "type": "EMAIL", "value": fields["email"]})

        if fields.get("phone"):
            entities.append({"name": fields["phone"], "type": "PHONE", "value": fields["phone"]})

        if fields.get("linkedin_url"):
            entities.append(
                {"name": fields["linkedin_url"], "type": "URL", "value": fields["linkedin_url"]}
            )

        if fields.get("location"):
            entities.append(
                {"name": fields["location"], "type": "LOCATION", "value": fields["location"]}
            )

        for skill in fields.get("skills", []):
            entities.append({"name": skill, "type": "SKILL", "value": skill})

        for exp in fields.get("experience", []):
            if exp.get("company"):
                entities.append(
                    {
                        "name": exp["company"],
                        "type": "ORGANIZATION",
                        "value": exp["company"],
                    }
                )

        for edu in fields.get("education", []):
            if edu.get("institution"):
                entities.append(
                    {
                        "name": edu["institution"],
                        "type": "ORGANIZATION",
                        "value": edu["institution"],
                    }
                )

        seen: set[tuple[str, str]] = set()
        unique_entities = []
        for e in entities:
            key = (e["name"], e["type"])
            if key not in seen:
                seen.add(key)
                unique_entities.append(e)

        return unique_entities

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

    def _create_chunks(
        self,
        pages: list[str],
        document_id: UUID,
    ) -> list[DocumentChunk]:
        chunk_size = 1000
        chunk_overlap = 100
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
                        metadata={"page": page_num, "source": "resume_extractor"},
                        created_at=now,
                    )
                )
                chunk_index += 1

        return all_chunks
