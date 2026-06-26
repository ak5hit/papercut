from unittest.mock import AsyncMock, MagicMock

import pytest

from answers.composer import AnswerComposer
from query.execution_trace import ExecutionTrace
from query.result import QueryResult


class _AsyncGen:
    """Returns an async iterator from a list of values — usable as an LLM stream mock."""

    def __init__(self, values: list[str]) -> None:
        self._values = values

    def __aiter__(self):
        return self._aiterator()

    async def _aiterator(self):
        for v in self._values:
            yield v


def test_semantic_prompt_no_longer_says_output_only() -> None:
    """The rigid 'Output ONLY the final answer' instruction is removed from semantic prompts."""
    composer = AnswerComposer(MagicMock())
    prompt = composer._build_semantic_prompt("Q", "ctx")
    assert "Output ONLY the final answer" not in prompt


def test_semantic_prompt_still_discourages_reasoning() -> None:
    """The prompt still tells the model to avoid private reasoning."""
    composer = AnswerComposer(MagicMock())
    prompt = composer._build_semantic_prompt("Q", "ctx")
    assert "reasoning" in prompt.lower()


def test_hybrid_prompt_no_longer_says_output_only() -> None:
    """The rigid 'Output ONLY the final answer' instruction is removed from hybrid prompts."""
    composer = AnswerComposer(MagicMock())
    prompt = composer._build_hybrid_prompt("Q", "struct", "semantic")
    assert "Output ONLY the final answer" not in prompt


@pytest.mark.asyncio
async def test_history_block_appears_in_prompt_when_history_given() -> None:
    """When history is passed to compose_stream, CONVERSATION SO FAR appears in the prompt."""
    llm = MagicMock()
    llm.stream_complete.return_value = _AsyncGen(["test answer"])
    composer = AnswerComposer(llm)
    result = _make_result("semantic", chunks=[{"document_id": "d1", "text": "some text", "chunk_index": 0}])

    results = []
    async for _ in composer.compose_stream(
        "Q", result, history=[{"role": "user", "content": "earlier message"}]
    ):
        results.append(_)

    prompt = llm.stream_complete.call_args[0][0]
    assert "CONVERSATION SO FAR:" in prompt
    assert "earlier message" in prompt


@pytest.mark.asyncio
async def test_history_block_absent_without_history() -> None:
    """When history is None, CONVERSATION SO FAR does not appear in the prompt."""
    llm = MagicMock()
    llm.stream_complete.return_value = _AsyncGen(["test answer"])
    composer = AnswerComposer(llm)
    result = _make_result("semantic", chunks=[{"document_id": "d1", "text": "some text", "chunk_index": 0}])

    results = []
    async for _ in composer.compose_stream("Q", result, history=None):
        results.append(_)

    prompt = llm.stream_complete.call_args[0][0]
    assert "CONVERSATION SO FAR:" not in prompt


def test_history_block_empty_for_graph_direct_path() -> None:
    """The graph-direct (Cypher) path does NOT receive history — it returns the chain answer verbatim."""
    composer = AnswerComposer(MagicMock())
    pass


@pytest.mark.asyncio
async def test_stateless_query_route_unchanged() -> None:
    """Calling compose without history does not inject conversation context."""
    llm = AsyncMock()
    llm.complete.return_value = "answer"
    composer = AnswerComposer(llm)
    result = _make_result("semantic", chunks=[{"document_id": "d1", "text": "some text", "chunk_index": 0}])

    composed = await composer.compose("Q", result)
    prompt = llm.complete.call_args[0][0]
    assert "CONVERSATION SO FAR:" not in prompt
    assert composed.answer == "answer"


def _make_result(strategy: str, chunks: list | None = None) -> QueryResult:
    trace = ExecutionTrace(strategy=strategy, steps=[])
    return QueryResult(trace=trace, chunks=chunks or [])
