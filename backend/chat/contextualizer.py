from typing import Any

from llm.base import LLMProvider


class QueryContextualizer:
    """Rewrites a follow-up question into a standalone question using chat history.

    Only fires when prior user/assistant turns exist. First-turn questions
    pass through unchanged (zero added latency on cold start).
    """

    _PROMPT = (
        "Given the conversation so far and a follow-up question, "
        "rewrite the follow-up into a SINGLE standalone question that can be "
        "understood without the prior conversation. Resolve pronouns (he, she, "
        "they, it, this, that) to their referents. Do NOT answer the question "
        "-- only rewrite it.\n\n"
        "Rules:\n"
        "- Output ONLY the rewritten question. One line. No preamble, no quotes.\n"
        "- If the follow-up is already self-contained, return it unchanged.\n"
        "- If it cannot be disambiguated, return it unchanged.\n\n"
        "CONVERSATION SO FAR:\n{history}\n\n"
        "FOLLOW-UP QUESTION: {question}\n\n"
        "STANDALONE QUESTION:"
    )

    def __init__(self, llm: LLMProvider, max_history_pairs: int = 3) -> None:
        self._llm = llm
        self._max_history_pairs = max_history_pairs

    async def rewrite(self, question: str, history: list[dict[str, Any]]) -> str:
        if not history:
            return question
        last_n = history[-(self._max_history_pairs * 2) :]
        history_lines = [f"{m['role']}: {m['content'][:300]}" for m in last_n]
        history_block = "\n".join(history_lines)
        prompt = self._PROMPT.format(history=history_block, question=question)
        rewritten = await self._llm.complete(prompt, max_tokens=256)
        rewritten = rewritten.strip().strip('"').strip("'").strip()
        if not rewritten or len(rewritten) > len(question) * 4:
            return question
        return rewritten
