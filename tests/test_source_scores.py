from typing import Any
from unittest.mock import MagicMock

import pytest

from answers.composer import AnswerComposer, SourceReference


class TestSourceReference:
    def test_accepts_score(self) -> None:
        sr = SourceReference(document_id="d1", document_name="test.pdf", score=0.85)
        assert sr.score == 0.85

    def test_score_optional(self) -> None:
        sr = SourceReference(document_id="d1", document_name="test.pdf")
        assert sr.score is None

    def test_to_dict_omits_score_when_none(self) -> None:
        sr = SourceReference(document_id="d1", document_name="test.pdf")
        d = sr.to_dict()
        assert "score" not in d

    def test_to_dict_rounds_score(self) -> None:
        sr = SourceReference(document_id="d1", document_name="test.pdf", score=0.8567)
        d = sr.to_dict()
        assert d["score"] == 0.8567


class TestBuildSourceList:
    def test_returns_empty_when_no_chunks_or_docs(self) -> None:
        result = AnswerComposer._build_source_list(None)
        assert result == []

    def test_attaches_score_from_chunk(self) -> None:
        chunks = [{"document_id": "d1", "filename": "test.pdf", "score": 0.92}]
        sources = AnswerComposer._build_source_list(chunks)
        assert len(sources) == 1
        assert sources[0].score == 0.92

    def test_uses_max_score_per_doc(self) -> None:
        chunks = [
            {"document_id": "d1", "filename": "test.pdf", "score": 0.92},
            {"document_id": "d1", "filename": "test.pdf", "score": 0.88},
        ]
        sources = AnswerComposer._build_source_list(chunks)
        assert len(sources) == 1
        assert sources[0].score == 0.92

    def test_sorts_sources_by_score_descending(self) -> None:
        chunks = [
            {"document_id": "d2", "filename": "b.pdf", "score": 0.60},
            {"document_id": "d1", "filename": "a.pdf", "score": 0.95},
            {"document_id": "d3", "filename": "c.pdf", "score": 0.75},
        ]
        sources = AnswerComposer._build_source_list(chunks)
        assert [s.document_id for s in sources] == ["d1", "d3", "d2"]

    def test_none_scores_come_last(self) -> None:
        chunks = [
            {"document_id": "d2", "filename": "b.pdf", "score": None},
            {"document_id": "d1", "filename": "a.pdf", "score": 0.95},
        ]
        sources = AnswerComposer._build_source_list(chunks)
        assert sources[0].document_id == "d1"
        assert sources[1].document_id == "d2"

    def test_docs_have_no_score_chunks_have_score(self) -> None:
        docs = [{"id": "d1", "metadata": {"filename": "doc.pdf"}}]
        chunks = [{"document_id": "d2", "filename": "chunk.pdf", "score": 0.88}]
        sources = AnswerComposer._build_source_list(chunks, docs)
        assert len(sources) == 2
        assert sources[0].document_id == "d2"  # has score, comes first
        assert sources[0].score == 0.88
        assert sources[1].document_id == "d1"
        assert sources[1].score is None

    def test_dedup_across_docs_and_chunks(self) -> None:
        docs = [{"id": "d1", "metadata": {"filename": "same.pdf"}}]
        chunks = [{"document_id": "d1", "filename": "same.pdf", "score": 0.95}]
        sources = AnswerComposer._build_source_list(chunks, docs)
        assert len(sources) == 1  # deduped
        assert sources[0].score == 0.95  # score from chunk wins
