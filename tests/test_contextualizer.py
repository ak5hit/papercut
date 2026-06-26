import pytest

from chat.contextualizer import QueryContextualizer


@pytest.mark.asyncio
async def test_rewrite_skipped_when_no_history() -> None:
    """When history is empty, the question passes through unchanged and LLM is never called."""
    llm = _mock_llm("should not be called")
    ctx = QueryContextualizer(llm)
    result = await ctx.rewrite("how much tax does Akshit owe", [])
    assert result == "how much tax does Akshit owe"
    # _mock_llm raises if complete() is called, proving zero LLM invocations


@pytest.mark.asyncio
async def test_rewrite_resolves_pronoun() -> None:
    """History provides the referent; the LLM rewrite resolves it."""
    llm = _mock_llm("How much TDS does Akshit Bansal owe?")
    ctx = QueryContextualizer(llm)
    history = [{"role": "user", "content": "how much tax does Akshit Bansal have"}]
    result = await ctx.rewrite("how much TDS does he owe", history)
    assert result == "How much TDS does Akshit Bansal owe?"


@pytest.mark.asyncio
async def test_rewrite_falls_back_on_empty_llm_output() -> None:
    """Empty string from LLM → original question preserved."""
    llm = _mock_llm("")
    ctx = QueryContextualizer(llm)
    history = [{"role": "user", "content": "what is the tax"}]
    result = await ctx.rewrite("how much TDS", history)
    assert result == "how much TDS"


@pytest.mark.asyncio
async def test_rewrite_falls_back_on_overlong_llm_output() -> None:
    """An essay response exceeds len(original)*4 → fallback to original."""
    llm = _mock_llm(
        "I cannot rewrite this question because it is too vague. "
        "Please provide more context about what exactly you are looking for. "
        "Was this helpful? Let me know if you need more assistance."
    )
    ctx = QueryContextualizer(llm)
    history = [{"role": "user", "content": "hi"}]
    original = "hello"
    result = await ctx.rewrite(original, history)
    assert result == original


@pytest.mark.asyncio
async def test_rewrite_strips_surrounding_quotes() -> None:
    """Double quotes and single quotes around the LLM output are removed."""
    llm = _mock_llm('"How much tax does Akshit owe?"')
    ctx = QueryContextualizer(llm)
    history = [{"role": "user", "content": "what is the tax for Akshit"}]
    result = await ctx.rewrite("how much does he owe", history)
    assert result == "How much tax does Akshit owe?"


@pytest.mark.asyncio
async def test_rewrite_returns_self_contained_unchanged() -> None:
    """When the follow-up is already self-contained, return it unchanged."""
    llm = _mock_llm("What is the email of Akshit Bansal?")
    ctx = QueryContextualizer(llm)
    history = [{"role": "user", "content": "previous question"}]
    result = await ctx.rewrite("What is the email of Akshit Bansal?", history)
    assert result == "What is the email of Akshit Bansal?"


@pytest.mark.asyncio
async def test_history_truncates_to_max_pairs() -> None:
    """Only the last max_history_pairs * 2 messages are included in the prompt."""
    llm = _mock_llm("Standalone question")
    ctx = QueryContextualizer(llm, max_history_pairs=2)
    history = [
        {"role": "user", "content": f"msg{i}"}
        for i in range(10)
    ]
    await ctx.rewrite("follow-up", history)
    # The prompt sent to the LLM should contain at most 4 "role:" lines
    prompt = llm.last_prompt
    role_count = prompt.count("role:")
    assert role_count <= 4, f"Expected <=4 role: lines, got {role_count}"


class _mock_llm:
    """LLMProvider-compatible mock that records the prompt and returns a canned answer."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.last_prompt = ""

    async def complete(self, prompt: str, **kwargs: object) -> str:
        if self.answer == "should not be called":
            msg = "LLM.complete() was called but should not have been (no history)"
            raise RuntimeError(msg)
        self.last_prompt = prompt
        return self.answer

    async def stream_complete(self, prompt: str, **kwargs: object) -> object:
        async def _gen() -> object:
            yield ""
        return _gen()
