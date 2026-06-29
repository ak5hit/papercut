import pytest

from chat.contextualizer import QueryContextualizer
from tests.fixtures.document_snippets import CRED_PROJECTS, F1_DATABASE, ZAMP_EXPECTATIONS


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
    prompt = llm.last_prompt
    conv_section = prompt[prompt.index("CONVERSATION SO FAR:"):]
    msg_count = conv_section.count("user:") + conv_section.count("assistant:")
    assert msg_count <= 4, f"Expected <=4 message lines in prompt, got {msg_count}"


@pytest.mark.asyncio
async def test_rewrite_expands_implicit_topic_continuation_with_real_doc() -> None:
    """Follow-up with implicit reference is expanded to include the topic from a real document."""
    llm = _mock_llm(
        "What are the top 5 things Zamp expects from candidates in the project round?"
    )
    ctx = QueryContextualizer(llm)
    history = [
        {"role": "user", "content": "What does Zamp expect from candidates?"},
        {"role": "assistant", "content": ZAMP_EXPECTATIONS},
    ]
    result = await ctx.rewrite("give me top 5 points", history)
    assert "top 5" in result.lower()
    assert "zamp" in result.lower()


@pytest.mark.asyncio
async def test_rewrite_detects_new_topic_pivot() -> None:
    """Follow-up about a completely different topic is returned unchanged."""
    llm = _mock_llm("What is the capital of France?")
    ctx = QueryContextualizer(llm)
    history = [
        {"role": "user", "content": "What does Zamp expect from candidates?"},
        {"role": "assistant", "content": ZAMP_EXPECTATIONS},
    ]
    result = await ctx.rewrite("What is the capital of France?", history)
    assert "zamp" not in result.lower()
    assert "france" in result.lower()


@pytest.mark.asyncio
async def test_rewrite_resolves_pronoun_with_real_doc() -> None:
    """Pronoun references are resolved to entities mentioned in real document content."""
    llm = _mock_llm("What problem does F1 database solve?")
    ctx = QueryContextualizer(llm)
    history = [
        {"role": "user", "content": "What is F1 database?"},
        {"role": "assistant", "content": F1_DATABASE},
    ]
    result = await ctx.rewrite("What problem does it solve?", history)
    assert "f1" in result.lower()


@pytest.mark.asyncio
async def test_prompt_includes_real_doc_context() -> None:
    """The prompt sent to the LLM contains the actual document excerpt and the follow-up."""
    llm = _mock_llm("some rewrite")
    ctx = QueryContextualizer(llm)
    history = [
        {"role": "user", "content": "What did Akshit build at CRED?"},
        {"role": "assistant", "content": CRED_PROJECTS},
    ]
    await ctx.rewrite("give me top 5 projects", history)
    assert "Datalens" in llm.last_prompt
    assert "Mixpanel" in llm.last_prompt
    assert "top 5" in llm.last_prompt


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
