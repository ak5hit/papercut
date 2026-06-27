import hashlib
import logging
import os
import tempfile
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from langchain_text_splitters import TokenTextSplitter
from pypdf import PdfReader

from config import Settings
from embeddings.base import EmbeddingProvider
from extractors.base import DocumentInput, Extractor, OnPhaseCallback
from extractors.pipeline_trace import (
    PHASE_BUILDING,
    PHASE_EMBEDDING,
    PHASE_EXTRACTING,
    PHASE_LABELS,
    PHASE_READING,
    PipelineTrace,
)
from llm.base import LLMProvider
from models.canonical_document import CanonicalDocument
from models.document_chunk import DocumentChunk
from storage.document_store import DocumentStore


class GenericExtractor(Extractor):
    DEFAULT_SIZE_THRESHOLD = 100_000

    def __init__(
        self,
        document_store: DocumentStore,
        llm_provider: LLMProvider | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        size_threshold: int = DEFAULT_SIZE_THRESHOLD,
        settings: Settings | None = None,
    ) -> None:
        self.document_store = document_store
        self.llm_provider = llm_provider
        self.embedding_provider = embedding_provider
        self.size_threshold = size_threshold
        self.settings = settings

    def supports(self, document: DocumentInput) -> float:
        if document.filename.lower().endswith(".pdf"):
            return 0.1
        return 0.0

    async def extract(
        self,
        document: DocumentInput,
        on_phase: OnPhaseCallback | None = None,
    ) -> tuple[CanonicalDocument, PipelineTrace]:
        trace = PipelineTrace(extractor="GenericExtractor")
        if document.document_type:
            trace.add_step("Selected extractor: GenericExtractor", f"document_type={document.document_type}")
        else:
            trace.add_step("Selected extractor: GenericExtractor", f"score={self.supports(document)}")

        trace.set_phase(PHASE_READING)
        if on_phase:
            await on_phase(PHASE_READING, PHASE_LABELS[PHASE_READING])

        text, page_metadata, pages = self._extract_text(document.content)
        trace.add_step(f"Extracted text from {len(page_metadata)} pages", f"{len(text)} characters")

        is_small = len(text) < self.size_threshold
        trace.add_step(f"Extracted text: {len(text)} chars", f"small={is_small}")

        metadata = self._build_metadata(document, page_metadata)
        strategy = "generic_small" if is_small else "generic_large"

        doc = CanonicalDocument.create(
            raw_text=text,
            metadata=metadata,
            extraction_strategy=strategy,
        )

        chunks = self._create_chunks(pages, doc.id, document.filename)
        trace.add_step(f"Created {len(chunks)} chunks")

        await self.document_store.save_document(doc)
        await self.document_store.save_chunks(chunks)
        trace.add_step("Saved document and chunks")

        trace.set_phase(PHASE_EMBEDDING)
        if on_phase:
            await on_phase(PHASE_EMBEDDING, PHASE_LABELS[PHASE_EMBEDDING])

        if self.embedding_provider:
            texts = [chunk.text for chunk in chunks]
            embeddings = self.embedding_provider.embed(texts)
            await self.document_store.save_chunk_embeddings(doc.id, embeddings)
            await self.document_store.update_embedding_status(doc.id, "completed")
            doc.embedding_status = "completed"
            trace.add_step(f"Generated {len(chunks)} embeddings")
        else:
            await self.document_store.update_embedding_status(doc.id, "failed")
            doc.embedding_status = "failed"

        if self.settings and self.settings.graph_extraction_enabled and self.llm_provider:
            from graph.age_connection import create_age_graph
            from graph.extractor import GraphExtractor
            from graph.store import GraphStore

            chunks_for_graph = [
                {"id": str(c.id), "text": c.text, "position": c.chunk_index}
                for c in chunks
            ]

            graph_ext = GraphExtractor(self.settings)
            graph_docs = await graph_ext.extract(chunks_for_graph)
            trace.add_step(f"Extracted {len(graph_docs)} graph documents")
            trace.set_phase(PHASE_EXTRACTING)
            if on_phase:
                await on_phase(PHASE_EXTRACTING, PHASE_LABELS[PHASE_EXTRACTING])

            # === BUILDING PHASE: graph persistence and postprocessing ===
            trace.set_phase(PHASE_BUILDING)
            if on_phase:
                await on_phase(PHASE_BUILDING, PHASE_LABELS[PHASE_BUILDING])

            try:
                age_graph = create_age_graph(self.settings)
                graph_store = GraphStore(age_graph, self.settings)

                chunks_created = await graph_store.add_document_and_chunks(
                    doc.id, document.filename, chunks_for_graph
                )
                trace.add_step(f"Created Document + {chunks_created}/{len(chunks)} chunks in AGE")

                await graph_store.add_graph_documents(graph_docs)

                link_result = await graph_store.link_chunks_to_entities(
                    graph_docs, {str(c.id): c.id for c in chunks}
                )
                trace.add_step(
                    f"Linked chunks→entities: {link_result['linked']} linked, "
                    f"{link_result['failed']} failed"
                    + (f" (first error: {link_result['errors'][0]})" if link_result['errors'] else "")
                )

                if self.settings.graph_auto_postprocess and self.llm_provider:
                    from graph.postprocessing import GraphPostProcessor
                    post = GraphPostProcessor(age_graph, self.llm_provider, self.settings)
                    try:
                        if self.settings.graph_auto_consolidate_labels:
                            res = await post.consolidate_labels()
                            trace.add_step("Consolidated graph labels", str(res))
                    except Exception as exc:
                        trace.add_step(f"Label consolidation failed: {exc}")

                node_count = await graph_store.count_nodes(doc.id)
                edge_count = await graph_store.count_edges(doc.id)
                trace.add_step(f"Built graph: {node_count} nodes, {edge_count} edges")

            except Exception as exc:
                trace.add_step(f"Graph building failed: {exc}")
                logging.exception("Graph building failed for document %s", doc.id)
                raise

        trace.add_step("Saved to database")

        trace.set_extracted_fields({
            "page_count": len(page_metadata),
            "total_characters": len(text),
            "total_chunks": len(chunks),
        })

        return doc, trace

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
        filename: str,
    ) -> list[DocumentChunk]:
        splitter = TokenTextSplitter(
            chunk_size=self.settings.chunk_token_size if self.settings else 512,
            chunk_overlap=self.settings.chunk_token_overlap if self.settings else 50,
        )

        now = datetime.utcnow()
        all_chunks: list[DocumentChunk] = []
        chunk_index = 0
        offset = 0

        for page_num, page_text in enumerate(pages):
            if not page_text.strip():
                continue
            page_chunks = splitter.split_text(page_text)
            for chunk_text in page_chunks:
                content_hash = hashlib.sha1(chunk_text.encode()).hexdigest()
                all_chunks.append(
                    DocumentChunk(
                        id=uuid4(),
                        document_id=document_id,
                        chunk_index=chunk_index,
                        text=chunk_text,
                        metadata={"page": page_num, "source": "generic_extractor", "filename": filename},
                        content_hash=content_hash,
                        position=chunk_index,
                        length=len(chunk_text),
                        content_offset=offset,
                        page_number=page_num,
                        created_at=now,
                    )
                )
                offset += len(chunk_text)
                chunk_index += 1

        return all_chunks
