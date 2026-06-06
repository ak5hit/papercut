from typing import Any

from answers.models import ComposedAnswer, SourceReference
from llm.base import LLMProvider
from query.result import QueryResult


class AnswerComposer:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    async def compose(self, question: str, result: QueryResult) -> ComposedAnswer:
        strategy = result.trace.strategy

        if strategy == "structured":
            return self._compose_structured(question, result)
        if strategy == "semantic":
            return await self._compose_semantic(question, result)
        return await self._compose_hybrid(question, result)

    def _compose_structured(self, question: str, result: QueryResult) -> ComposedAnswer:
        docs = result.documents
        if not docs:
            answer = "No matching documents found."
        elif len(docs) == 1:
            doc = docs[0]
            fields = doc.get("structured_fields", {})
            lines = [f"**{k}:** {v}" for k, v in fields.items()]
            answer = "\n".join(lines) if lines else "Document found but no structured fields available."
        else:
            lines = [f"- **{doc.get('metadata', {}).get('filename', doc['id'])}**" for doc in docs]
            answer = f"Found {len(docs)} matching documents:\n" + "\n".join(lines)

        sources = [
            SourceReference(
                document_id=doc["id"],
                document_name=doc.get("metadata", {}).get("filename", "Unknown"),
            )
            for doc in docs
        ]

        result.trace.add_step("Formatted structured answer")
        return ComposedAnswer(
            answer=answer,
            sources=sources,
            trace=result.trace.to_dict(),
        )

    async def _compose_semantic(self, question: str, result: QueryResult) -> ComposedAnswer:
        chunks = result.chunks
        if not chunks:
            return ComposedAnswer(
                answer="I could not find relevant text in the documents.",
                sources=[],
                trace=result.trace.to_dict(),
            )

        context = self._build_context(chunks)
        prompt = self._build_semantic_prompt(question, context)
        answer_text = await self._llm.complete(prompt, max_tokens=1500)

        sources = [
            SourceReference(
                document_id=chunk["document_id"],
                document_name=chunk.get("metadata", {}).get("filename", "Unknown"),
                chunk_index=chunk["chunk_index"],
                page=chunk.get("metadata", {}).get("page"),
                excerpt=chunk["text"][:300],
            )
            for chunk in chunks
        ]

        result.trace.add_step("Generated semantic answer via LLM")
        return ComposedAnswer(
            answer=answer_text.strip(),
            sources=sources,
            trace=result.trace.to_dict(),
        )

    async def _compose_hybrid(self, question: str, result: QueryResult) -> ComposedAnswer:
        docs = result.documents
        chunks = result.chunks

        structured_context = ""
        if docs:
            structured_lines = []
            for doc in docs[:10]:
                filename = doc.get("metadata", {}).get("filename", "Unknown")
                fields = doc.get("structured_fields", {})
                field_str = ", ".join(f"{k}={v}" for k, v in fields.items())
                structured_lines.append(f"Document {filename}: {field_str}")
            structured_context = "\n".join(structured_lines)

        semantic_context = self._build_context(chunks) if chunks else ""

        prompt = self._build_hybrid_prompt(
            question, structured_context, semantic_context
        )
        answer_text = await self._llm.complete(prompt, max_tokens=1500)

        seen: set[str] = set()
        sources: list[SourceReference] = []

        for doc in docs:
            doc_id = doc["id"]
            if doc_id not in seen:
                seen.add(doc_id)
                sources.append(
                    SourceReference(
                        document_id=doc_id,
                        document_name=doc.get("metadata", {}).get("filename", "Unknown"),
                    )
                )

        for chunk in chunks:
            chunk_doc_id = chunk["document_id"]
            if chunk_doc_id not in seen:
                seen.add(chunk_doc_id)
                sources.append(
                    SourceReference(
                        document_id=chunk_doc_id,
                        document_name=chunk.get("metadata", {}).get("filename", "Unknown"),
                        chunk_index=chunk["chunk_index"],
                        page=chunk.get("metadata", {}).get("page"),
                        excerpt=chunk["text"][:300],
                    )
                )

        result.trace.add_step("Generated hybrid answer via LLM")
        return ComposedAnswer(
            answer=answer_text.strip(),
            sources=sources,
            trace=result.trace.to_dict(),
        )

    def _build_context(self, chunks: list[dict[str, Any]]) -> str:
        lines = []
        for i, chunk in enumerate(chunks, 1):
            text = chunk["text"]
            meta = chunk.get("metadata", {})
            page = meta.get("page")
            source = f"[Chunk {chunk['chunk_index']}" + (f", Page {page}]" if page else "]")
            lines.append(f"{source}\n{text}")
        return "\n\n".join(lines)

    def _build_semantic_prompt(self, question: str, context: str) -> str:
        return (
            "You are a precise document intelligence assistant. "
            "Answer the user's question using ONLY the provided document excerpts. "
            "If the answer is not in the excerpts, say "
            "'The documents do not contain enough information to answer this question.'\n\n"
            "DOCUMENT EXCERPTS:\n"
            f"{context}\n\n"
            f"QUESTION: {question}\n\n"
            "Provide a concise, factual answer."
        )

    def _build_hybrid_prompt(
        self, question: str, structured_context: str, semantic_context: str
    ) -> str:
        parts = [
            "You are a precise document intelligence assistant. "
            "Answer the user's question using ONLY the provided structured data and document excerpts. "
            "If the answer is not in the provided data, say "
            "'The documents do not contain enough information to answer this question.'\n\n",
        ]
        if structured_context:
            parts.append(f"STRUCTURED DATA:\n{structured_context}\n\n")
        if semantic_context:
            parts.append(f"DOCUMENT EXCERPTS:\n{semantic_context}\n\n")
        parts.append(f"QUESTION: {question}\n\nProvide a concise, factual answer.")
        return "".join(parts)
