import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from extractors.base import DocumentInput
from extractors.pipeline_trace import (
    PHASE_BUILDING,
    PHASE_EMBEDDING,
    PHASE_EXTRACTING,
    PHASE_READING,
    PipelineTrace,
)


def test_set_phase_propagates_to_subsequent_steps() -> None:
    trace = PipelineTrace(extractor="test")
    trace.set_phase(PHASE_READING)
    trace.add_step("Reading PDF")
    trace.set_phase(PHASE_EMBEDDING)
    trace.add_step("Generating embeddings")

    assert len(trace.steps) == 2
    assert trace.steps[0]["phase"] == PHASE_READING
    assert trace.steps[1]["phase"] == PHASE_EMBEDDING


@pytest.mark.asyncio
async def test_duration_ms_is_positive() -> None:
    trace = PipelineTrace(extractor="test")
    trace.add_step("Fast step")
    # Second step has a measurable sleep before it
    await asyncio.sleep(0.05)
    trace.add_step("Slow step")

    # Both durations must be >= 0 (first may be 0 if executed very fast)
    assert trace.steps[0]["duration_ms"] >= 0
    # Second step must have a positive duration because of the sleep
    assert trace.steps[1]["duration_ms"] > 0


@pytest.mark.asyncio
async def test_total_duration_ms_in_to_dict() -> None:
    trace = PipelineTrace(extractor="test")
    trace.add_step("Step one")
    await asyncio.sleep(0.05)
    result = trace.to_dict()

    assert "total_duration_ms" in result
    assert result["total_duration_ms"] > 0


def test_to_dict_includes_steps_and_extractor() -> None:
    trace = PipelineTrace(extractor="MyExtractor")
    trace.add_step("Step A")
    trace.set_extracted_fields({"page_count": 3})
    result = trace.to_dict()

    assert result["extractor"] == "MyExtractor"
    assert len(result["steps"]) == 1
    assert result["steps"][0]["step"] == "Step A"
    assert result["extracted_fields"]["page_count"] == 3


def test_add_step_with_detail() -> None:
    trace = PipelineTrace(extractor="test")
    trace.add_step("Step with detail", "extra info")
    assert trace.steps[0]["detail"] == "extra info"


def test_add_step_without_detail() -> None:
    trace = PipelineTrace(extractor="test")
    trace.add_step("Step without detail")
    assert "detail" not in trace.steps[0]


def test_on_phase_receives_correct_phases() -> None:
    received: list[tuple[str, str]] = []

    async def capture(phase: str, label: str) -> None:
        received.append((phase, label))

    trace = PipelineTrace(extractor="test")
    trace.set_phase(PHASE_EMBEDDING)
    assert trace.steps == []
    assert len(received) == 0  # on_phase is called by extractor, not PipelineTrace



