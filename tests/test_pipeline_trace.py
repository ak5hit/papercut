import pytest

from extractors.pipeline_trace import PipelineTrace


class TestPipelineTrace:
    def test_trace_creation(self) -> None:
        trace = PipelineTrace(extractor="TestExtractor")
        assert trace.extractor == "TestExtractor"
        assert trace.steps == []
        assert trace.extracted_fields == {}

    def test_add_step(self) -> None:
        trace = PipelineTrace(extractor="TestExtractor")
        trace.add_step("Opened document", "3 pages")
        assert len(trace.steps) == 1
        assert trace.steps[0] == {"step": "Opened document", "detail": "3 pages"}

    def test_add_step_without_detail(self) -> None:
        trace = PipelineTrace(extractor="TestExtractor")
        trace.add_step("Saved to database")
        assert len(trace.steps) == 1
        assert trace.steps[0] == {"step": "Saved to database"}
        assert "detail" not in trace.steps[0]

    def test_add_multiple_steps(self) -> None:
        trace = PipelineTrace(extractor="TestExtractor")
        trace.add_step("Step 1")
        trace.add_step("Step 2", "detail 2")
        trace.add_step("Step 3")
        assert len(trace.steps) == 3
        assert trace.steps[1]["detail"] == "detail 2"

    def test_set_extracted_fields(self) -> None:
        trace = PipelineTrace(extractor="TestExtractor")
        trace.set_extracted_fields({"name": "John", "age": 30})
        assert trace.extracted_fields == {"name": "John", "age": 30}

    def test_to_dict_serialization(self) -> None:
        trace = PipelineTrace(extractor="ResumeExtractor")
        trace.add_step("Extracted text", "100 chars")
        trace.add_step("Created chunks", "3 chunks")
        trace.set_extracted_fields({"name": "Jane", "email": "jane@example.com"})

        result = trace.to_dict()
        assert result["extractor"] == "ResumeExtractor"
        assert len(result["steps"]) == 2
        assert result["steps"][0] == {"step": "Extracted text", "detail": "100 chars"}
        assert result["steps"][1] == {"step": "Created chunks", "detail": "3 chunks"}
        assert result["extracted_fields"] == {"name": "Jane", "email": "jane@example.com"}

    def test_to_dict_with_no_fields(self) -> None:
        trace = PipelineTrace(extractor="GenericExtractor")
        trace.add_step("Extracted text")

        result = trace.to_dict()
        assert result["extracted_fields"] == {}

    def test_to_dict_shares_mutable_references(self) -> None:
        trace = PipelineTrace(extractor="TestExtractor")
        trace.add_step("Step 1")
        trace.set_extracted_fields({"key": "value"})

        result = trace.to_dict()
        assert "extractor" in result
        assert "steps" in result
        assert "extracted_fields" in result

        trace.add_step("Step 2")
        assert len(result["steps"]) == 2
