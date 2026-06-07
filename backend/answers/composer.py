import json
from typing import Any

from answers.models import ComposedAnswer, SourceReference
from llm.base import LLMProvider
from query.result import QueryResult


class AnswerComposer:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    @staticmethod
    def _strip_reasoning(answer: str) -> str:
        import re
        prefixes = [
            r"^We are asked:[\s\S]*?\n\n",
            r"^Let me [\s\S]*?\n\n",
            r"^First,[\s\S]*?\n\n",
            r"^I need to [\s\S]*?\n\n",
            r"^The user asks[\s\S]*?\n\n",
            r"^The question[\s\S]*?\n\n",
        ]
        for pattern in prefixes:
            match = re.match(pattern, answer)
            if match:
                return answer[match.end():]
        return answer

    async def compose(self, question: str, result: QueryResult) -> ComposedAnswer:
        strategy = result.trace.strategy

        if strategy == "structured":
            return await self._compose_structured(question, result)
        if strategy == "semantic":
            return await self._compose_semantic(question, result)
        return await self._compose_hybrid(question, result)

    async def _compose_structured(self, question: str, result: QueryResult) -> ComposedAnswer:
        docs = result.documents
        if not docs:
            answer = "No matching documents found."
        elif len(docs) == 1:
            doc = docs[0]
            fields = doc.get("structured_fields", {})
            prompt = (
                f"Answer this question using the structured fields below.\n"
                f"If the question asks for a specific field (phone, email, name), "
                f"return ONLY that value — no extra text.\n"
                f"If asked to show the full resume or all details, "
                f"format all fields clearly with labels.\n"
                f"If the structured data contains list/array fields, "
                f"include ALL items from those lists as bullet points. "
                f"Do not summarize or skip items — present every entry "
                f"unless the user explicitly asks for a subset "
                f"(e.g., 'top 2', 'the last 3', 'oldest').\n"
                f"If the field is not found, say so briefly.\n\n"
                f"FIELDS:\n{json.dumps(fields, indent=2)}\n\n"
                f"QUESTION: {question}"
            )
            answer = await self._llm.complete(prompt, max_tokens=500)
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
            answer=self._strip_reasoning(answer.strip()),
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
        answer_text = await self._llm.complete(prompt, max_tokens=2000)

        seen: set[str] = set()
        sources: list[SourceReference] = []
        for chunk in chunks:
            doc_id = chunk["document_id"]
            if doc_id not in seen:
                seen.add(doc_id)
                sources.append(
                    SourceReference(
                        document_id=doc_id,
                        document_name=chunk.get("metadata", {}).get("filename", "Unknown"),
                        excerpt=chunk["text"][:300],
                    )
                )

        result.trace.add_step("Generated semantic answer via LLM")
        return ComposedAnswer(
            answer=self._strip_reasoning(answer_text.strip()),
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
        answer_text = await self._llm.complete(prompt, max_tokens=2000)

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
            doc_id = chunk["document_id"]
            if doc_id not in seen:
                seen.add(doc_id)
                sources.append(
                    SourceReference(
                        document_id=doc_id,
                        document_name=chunk.get("metadata", {}).get("filename", "Unknown"),
                        excerpt=chunk["text"][:300],
                    )
                )

        result.trace.add_step("Generated hybrid answer via LLM")
        return ComposedAnswer(
            answer=self._strip_reasoning(answer_text.strip()),
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
            "IMPORTANT: Output ONLY the final answer. Do NOT write any reasoning, "
            "analysis, or thought process. Start directly with the answer.\n\n"
            "You are a precise document intelligence assistant. "
            "Answer the user's question using ONLY the provided document excerpts. "
            "If the answer is truly not in the excerpts, say "
            "'The documents do not contain enough information to answer this question.' "
            "However, if relevant information IS present, always provide it — do not refuse to answer "
            "questions that can be answered from the excerpts.\n\n"
            "IMPORTANT: If the question asks about duration, timeline, 'how long', 'since when', "
            "or dates, examine ALL provided excerpts for start and end dates, then calculate the total span. "
            "For date ranges like 'Mar. 2024 - Present', treat the current date as the end. "
            "For questions about a person's total experience or time at a company, look at the earliest "
            "and latest dates across all experience entries.\n\n"
            "RULES:\n"
            "- Give ONLY the final answer. Do NOT include your internal reasoning, calculations, or thought process.\n"
            "- Be thorough — include all relevant details from the excerpts. "
            "Do not compress multiple facts or entries into a single sentence.\n"
            "- Use the full context provided — do not omit details.\n\n"
            "DOCUMENT EXCERPTS:\n"
            f"{context}\n\n"
            f"QUESTION: {question}\n\n"
            "Provide a thorough, factual answer."
        )

    def _build_hybrid_prompt(
        self, question: str, structured_context: str, semantic_context: str
    ) -> str:
        parts = [
            "IMPORTANT: Output ONLY the final answer. Do NOT write any reasoning, "
            "analysis, or thought process. Start directly with the answer.\n\n",
            "You are a precise document intelligence assistant. "
            "Answer the user's question using ONLY the provided structured data and document excerpts. "
            "If the answer is not in the provided data, say "
            "'The documents do not contain enough information to answer this question.'\n\n",
        ]
        if structured_context:
            parts.append(f"STRUCTURED DATA:\n{structured_context}\n\n")
        if semantic_context:
            parts.append(f"DOCUMENT EXCERPTS:\n{semantic_context}\n\n")
        parts.append(
            "RULES:\n"
            "- Give ONLY the final answer. Do NOT include your internal reasoning, calculations, or thought process.\n"
            "- Be thorough — include all relevant details from the provided data. "
            "Do not compress multiple facts or entries into a single sentence.\n"
            "- If the structured data contains list/array fields, "
            "include ALL items from those lists as bullet points. "
            "Do not summarize or skip items unless the user explicitly asks for a subset.\n"
            "- Use the full context provided — do not omit details.\n\n"
            f"QUESTION: {question}\n\n"
            "Provide a thorough, factual answer."
        )
        return "".join(parts)
