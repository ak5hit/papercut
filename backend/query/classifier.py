from llm.base import LLMProvider


class QueryClassifier:
    _PROMPT = """You are a query routing engine.
Classify the user question into exactly one of: STRUCTURED, SEMANTIC, HYBRID.

Definitions:
- STRUCTURED: Asks for concrete facts answerable from structured fields,
  entities, or metadata (e.g. totals, counts, dates, amounts).
- SEMANTIC: Asks for explanation, summary, or meaning that requires
  reading document text (e.g. "summarize", "explain").
- HYBRID: Combines a concrete filter with a semantic request
  (e.g. "Show AWS contracts with invoices above 1 lakh").

Respond with ONLY the single word: STRUCTURED, SEMANTIC, or HYBRID.

Question: {question}
"""

    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    async def classify(self, question: str) -> str:
        prompt = self._PROMPT.format(question=question)
        response = await self._llm.complete(prompt, max_tokens=20)
        cleaned = response.strip().upper()
        if cleaned in ("STRUCTURED", "SEMANTIC", "HYBRID"):
            return cleaned
        return "SEMANTIC"
