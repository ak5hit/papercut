from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from graph.postprocessing import GraphPostProcessor


@pytest.fixture
def age_graph() -> MagicMock:
    g = MagicMock()
    labels_rows = [
        {"labels": ["Person"]},
        {"labels": ["Technology"]},
        {"labels": ["ProgrammingLanguage"]},
        {"labels": ["Skill"]},
        {"labels": ["Chunk"]},
        {"labels": ["Document"]},
    ]
    types_rows = [
        {"types": "WORKS_FOR"},
        {"types": "EMPLOYED_BY"},
    ]

    def query(cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if "labels(n)" in cypher:
            return labels_rows
        if "type(r)" in cypher:
            return types_rows
        return []

    g.query = query
    return g


@pytest.fixture
def llm_provider() -> AsyncMock:
    llm = AsyncMock()
    llm.complete.return_value = (
        '{"nodes": {"Skill": ["Technology", "ProgrammingLanguage"]}, '
        '"relationships": {"WORKS_FOR": ["EMPLOYED_BY"]}}'
    )
    return llm


@pytest.fixture
def post_processor(age_graph: MagicMock, llm_provider: AsyncMock) -> GraphPostProcessor:
    from config import Settings

    settings = Settings()
    return GraphPostProcessor(age_graph, llm_provider, settings)


@pytest.mark.asyncio
async def test_consolidate_labels_skips_chunk_and_document(post_processor: GraphPostProcessor, age_graph: MagicMock) -> None:
    original_query = age_graph.query

    call_count: int = 0
    captured_prompt: str | None = None

    async def track_complete(prompt: str, max_tokens: int = 1000) -> str:
        nonlocal captured_prompt
        captured_prompt = prompt
        return (
            '{"nodes": {"Skill": ["Technology", "ProgrammingLanguage"]}, '
            '"relationships": {}}'
        )

    post_processor.llm.complete = track_complete

    await post_processor.consolidate_labels()

    assert captured_prompt is not None
    assert "Technology" in captured_prompt
    assert "ProgrammingLanguage" in captured_prompt
    assert "Chunk" not in captured_prompt
    assert "Document" not in captured_prompt


@pytest.mark.asyncio
async def test_consolidate_labels_emits_rewrite_cypher(post_processor: GraphPostProcessor, age_graph: MagicMock) -> None:
    executed: list[str] = []
    original_query = age_graph.query

    def track_query(cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        executed.append(cypher)
        return original_query(cypher, params)

    age_graph.query = track_query

    await post_processor.consolidate_labels()

    set_statements = [c for c in executed if "SET" in c.upper() and "REMOVE" in c.upper()]
    assert len(set_statements) == 2

    tech_rewrite = [c for c in set_statements if "Technology" in c]
    assert len(tech_rewrite) == 1
    assert "SET n:`Skill`" in tech_rewrite[0]
    assert "REMOVE n:`Technology`" in tech_rewrite[0]

    prog_rewrite = [c for c in set_statements if "ProgrammingLanguage" in c]
    assert len(prog_rewrite) == 1
    assert "SET n:`Skill`" in prog_rewrite[0]
    assert "REMOVE n:`ProgrammingLanguage`" in prog_rewrite[0]


@pytest.mark.asyncio
async def test_consolidate_labels_rewrites_relationship_types(post_processor: GraphPostProcessor, age_graph: MagicMock) -> None:
    executed: list[str] = []
    original_query = age_graph.query

    def track_query(cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        executed.append(cypher)
        return original_query(cypher, params)

    age_graph.query = track_query

    await post_processor.consolidate_labels()

    rel_rewrites = [c for c in executed if "CREATE" in c.upper() and "DELETE r" in c]
    assert len(rel_rewrites) == 1
    assert "EMPLOYED_BY" in rel_rewrites[0]
    assert "WORKS_FOR" in rel_rewrites[0]


@pytest.mark.asyncio
async def test_consolidate_labels_returns_counts(post_processor: GraphPostProcessor) -> None:
    result = await post_processor.consolidate_labels()
    assert isinstance(result, dict)
    assert "labels_consolidated" in result
    assert "types_consolidated" in result
    assert result["labels_consolidated"] == 2
    assert result["types_consolidated"] == 1


@pytest.mark.asyncio
async def test_consolidate_labels_graceful_degradation(post_processor: GraphPostProcessor, age_graph: MagicMock) -> None:
    async def fail_complete(prompt: str, max_tokens: int = 1000) -> str:
        msg = "not json"
        return msg

    post_processor.llm.complete = fail_complete

    result = await post_processor.consolidate_labels()
    assert result == {"labels_consolidated": 0, "types_consolidated": 0}


@pytest.mark.asyncio
async def test_consolidate_labels_empty_graph(age_graph: MagicMock, llm_provider: AsyncMock) -> None:
    from config import Settings

    def empty_query(cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return []

    age_graph.query = empty_query
    settings = Settings()
    pp = GraphPostProcessor(age_graph, llm_provider, settings)

    result = await pp.consolidate_labels()
    assert result == {"labels_consolidated": 0, "types_consolidated": 0}
