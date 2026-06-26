from collections.abc import AsyncIterator
from typing import Any

from answers.models import ComposedAnswer, SourceReference
from llm.base import LLMProvider
from query.result import QueryResult


class AnswerComposer:
    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    @staticmethod
    def _strip_reasoning(answer: str) -> str:
        """Defensive fallback in case the model emits reasoning despite thinking:disabled."""
        import re
        reasoning_pattern = r'^(?:\d+\.\s+\*\*[^*]+\*\*[\s\S]*?\n\n)+'
        match = re.match(reasoning_pattern, answer)
        if match:
            return answer[match.end():]
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

    @staticmethod
    def _history_block(history: list[dict[str, Any]] | None) -> str:
        if not history:
            return ""
        lines = [f"{m['role']}: {m['content'][:300]}" for m in history[-6:]]
        return "CONVERSATION SO FAR:\n" + "\n".join(lines) + "\n\n"

    async def compose(
        self, question: str, result: QueryResult, history: list[dict[str, Any]] | None = None
    ) -> ComposedAnswer:
        strategy = result.trace.strategy

        if strategy == "graph":
            return await self._compose_graph(question, result, history=history)
        if strategy == "semantic":
            return await self._compose_semantic(question, result, history=history)
        return await self._compose_hybrid(question, result, history=history)

    async def compose_stream(
        self, question: str, result: QueryResult, history: list[dict[str, Any]] | None = None
    ) -> AsyncIterator[str]:
        """Yield answer text tokens from the LLM. Trace/sources are already in result."""
        hb = self._history_block(history)
        strategy = result.trace.strategy

        if strategy == "graph":
            if result.graph_result:
                answer = result.graph_result.get("answer", "No answer generated")
                yield answer.strip()
                return
            context = result.graph_context
            chunks = result.chunks
            if not context and not chunks:
                yield "I could not find relevant data to answer this question."
                return
            prompt = self._build_semantic_prompt(
                question, context or self._build_context(chunks), history_block=hb
            )
            async for chunk in self._llm.stream_complete(prompt, max_tokens=2000):
                yield chunk
            return

        if strategy == "semantic":
            chunks = result.chunks
            if not chunks:
                yield "I could not find relevant text in the documents."
                return
            context = result.graph_context or self._build_context(chunks)
            prompt = self._build_semantic_prompt(question, context, history_block=hb)
            async for chunk in self._llm.stream_complete(prompt, max_tokens=2000):
                yield chunk
            return

        if strategy == "hybrid":
            docs = result.documents
            chunks = result.chunks
            structured_context = ""
            if docs:
                lines = []
                for doc in docs[:10]:
                    filename = doc.get("metadata", {}).get("filename", "Unknown")
                    fields = doc.get("structured_fields", {})
                    field_str = ", ".join(f"{k}={v}" for k, v in fields.items())
                    lines.append(f"Document {filename}: {field_str}")
                structured_context = "\n".join(lines)
            semantic_context = result.graph_context or (
                self._build_context(chunks) if chunks else ""
            )
            prompt = self._build_hybrid_prompt(
                question, structured_context, semantic_context, history_block=hb
            )
            async for chunk in self._llm.stream_complete(prompt, max_tokens=2000):
                yield chunk
            return

    async def _compose_graph(
        self, question: str, result: QueryResult, history: list[dict[str, Any]] | None = None
    ) -> ComposedAnswer:
        # If Cypher result is available, use it
        if result.graph_result:
            answer = result.graph_result.get("answer", "No answer generated")
            cypher = result.graph_result.get("cypher", "")
            context = result.graph_result.get("context", [])

            result.trace.add_step("Generated graph answer via Cypher")
            result.trace.graph_results_count = len(context)

            return ComposedAnswer(
                answer=self._strip_reasoning(answer.strip()),
                sources=[],
                trace=result.trace.to_dict(),
                generated_cypher=cypher,
                cypher_context=context,
            )

        # Fallback: use graph-enriched context
        context = result.graph_context
        chunks = result.chunks

        if not context and not chunks:
            return ComposedAnswer(
                answer="I could not find relevant data to answer this question.",
                sources=[],
                trace=result.trace.to_dict(),
            )

        hb = self._history_block(history)
        prompt = self._build_semantic_prompt(question, context or self._build_context(chunks), history_block=hb)
        answer_text = await self._llm.complete(prompt, max_tokens=2000)

        seen: set[str] = set()
        sources: list[SourceReference] = []
        for chunk in chunks or []:
            doc_id = chunk.get("document_id") or chunk.get("id", "")
            if str(doc_id) not in seen:
                seen.add(str(doc_id))
                sources.append(
                    SourceReference(
                        document_id=str(doc_id),
                        document_name=chunk.get("filename", "Unknown"),
                    )
                )

        result.trace.add_step("Generated graph answer via enriched context")
        return ComposedAnswer(
            answer=self._strip_reasoning(answer_text.strip()),
            sources=sources,
            trace=result.trace.to_dict(),
        )

    async def _compose_semantic(
        self, question: str, result: QueryResult, history: list[dict[str, Any]] | None = None
    ) -> ComposedAnswer:
        chunks = result.chunks
        if not chunks:
            return ComposedAnswer(
                answer="I could not find relevant text in the documents.",
                sources=[],
                trace=result.trace.to_dict(),
            )

        context = result.graph_context or self._build_context(chunks)
        if result.graph_context:
            result.trace.add_step("Using graph-enriched context")
        hb = self._history_block(history)
        prompt = self._build_semantic_prompt(question, context, history_block=hb)
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
                        document_name=chunk.get("filename") or chunk.get("metadata", {}).get("filename", "Unknown"),
                    )
                )

        result.trace.add_step("Generated semantic answer via LLM")
        return ComposedAnswer(
            answer=self._strip_reasoning(answer_text.strip()),
            sources=sources,
            trace=result.trace.to_dict(),
        )

    async def _compose_hybrid(
        self, question: str, result: QueryResult, history: list[dict[str, Any]] | None = None
    ) -> ComposedAnswer:
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

        semantic_context = result.graph_context or (self._build_context(chunks) if chunks else "")
        if result.graph_context:
            result.trace.add_step("Using graph-enriched context for hybrid")

        hb = self._history_block(history)
        prompt = self._build_hybrid_prompt(
            question, structured_context, semantic_context, history_block=hb
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
                        document_name=chunk.get("filename") or chunk.get("metadata", {}).get("filename", "Unknown"),
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

    def _build_semantic_prompt(self, question: str, context: str, history_block: str = "") -> str:
        return (
            "Answer concisely using ONLY the provided document excerpts. "
            "Begin with a one-line factual answer, then add brief supporting "
            "detail from the excerpts if it exists. Do NOT include private "
            "reasoning, chained calculations, or 'let me think' prose.\n\n"
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
            "- Be thorough — include all relevant details from the excerpts. "
            "Do not compress multiple facts or entries into a single sentence.\n"
            "- Use the full context provided — do not omit details.\n\n"
            f"{history_block}"
            "DOCUMENT EXCERPTS:\n"
            f"{context}\n\n"
            f"QUESTION: {question}\n\n"
            "Provide a thorough, factual answer."
        )

    def _build_hybrid_prompt(
        self, question: str, structured_context: str, semantic_context: str, history_block: str = ""
    ) -> str:
        parts = [
            "Answer concisely using ONLY the provided structured data and "
            "document excerpts. Begin with a one-line factual answer, then add "
            "brief supporting detail from the data if it exists. Do NOT include "
            "private reasoning, chained calculations, or 'let me think' prose.\n\n",
            "You are a precise document intelligence assistant. "
            "Answer the user's question using ONLY the provided structured data and document excerpts. "
            "If the answer is not in the provided data, say "
            "'The documents do not contain enough information to answer this question.'\n\n",
        ]
        if history_block:
            parts.append(history_block)
        if structured_context:
            parts.append(f"STRUCTURED DATA:\n{structured_context}\n\n")
        if semantic_context:
            parts.append(f"DOCUMENT EXCERPTS:\n{semantic_context}\n\n")
        parts.append(
            "RULES:\n"
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
