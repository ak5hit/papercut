from typing import Any

from llm.base import LLMProvider


class QueryContextualizer:
    """Rewrites a follow-up question into a standalone question using chat history.

    Only fires when prior user/assistant turns exist. First-turn questions
    pass through unchanged (zero added latency on cold start).
    """

    _PROMPT = (
        "You are a query contextualizer for a document Q&A system. "
        "Rewrite the follow-up question into a single standalone question "
        "that can be understood without the prior conversation.\n\n"
        "Rules:\n"
        "- If the follow-up continues the same topic as the previous turn, "
        "expand implicit references to make the topic explicit.\n"
        "- If the follow-up asks about a new topic or is already self-contained, "
        "return it unchanged.\n"
        "- Resolve pronouns (he, she, they, it, this, that, them) and vague "
        "references (\"those points\", \"the above\", \"it\", \"them\") "
        "to their referents.\n"
        "- Output ONLY the rewritten question. One line. No preamble, no quotes.\n"
        "- Do NOT answer the question; only rewrite it.\n"
        "- If you cannot determine the topic, return the follow-up unchanged.\n\n"
        "Examples:\n\n"
        "User: What qualifications does the job require?\n"
        "Assistant: The job requires a bachelor's degree in computer science, "
        "5 years of experience, and knowledge of Python.\n"
        "Follow-up: give me top 3 points\n"
        "Standalone: What are the top 3 qualifications required for the job?\n\n"
        "User: What is the distance between Earth and Mars?\n"
        "Assistant: The average distance is about 225 million kilometers.\n"
        "Follow-up: What is the capital of France?\n"
        "Standalone: What is the capital of France?\n\n"
        "User: What is the email of John Smith?\n"
        "Assistant: john@example.com\n"
        "Follow-up: What is his phone number?\n"
        "Standalone: What is the phone number of John Smith?\n\n"
        "CONVERSATION SO FAR:\n{history}\n\n"
        "FOLLOW-UP QUESTION: {question}\n\n"
        "STANDALONE QUESTION:"
    )

    def __init__(self, llm: LLMProvider, max_history_pairs: int = 6) -> None:
        self._llm = llm
        self._max_history_pairs = max_history_pairs

    async def rewrite(self, question: str, history: list[dict[str, Any]]) -> str:
        if not history:
            return question
        last_n = history[-(self._max_history_pairs * 2) :]
        history_lines = []
        for m in last_n:
            limit = 1200 if m["role"] == "assistant" else 300
            history_lines.append(f"{m['role']}: {m['content'][:limit]}")
        history_block = "\n".join(history_lines)
        prompt = self._PROMPT.format(history=history_block, question=question)
        rewritten = await self._llm.complete(prompt, max_tokens=256)
        rewritten = rewritten.strip().strip('"').strip("'").strip()
        if not rewritten or len(rewritten) > len(question) * 4:
            return question
        return rewritten
