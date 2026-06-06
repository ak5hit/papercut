from answers.models import ComposedAnswer, SourceReference


class TestSourceReference:
    def test_to_dict_omits_none_gracefully(self) -> None:
        ref = SourceReference(document_id="id-1", document_name="file.pdf")
        d = ref.to_dict()
        assert d["document_id"] == "id-1"
        assert d["document_name"] == "file.pdf"
        assert d["chunk_index"] is None
        assert d["page"] is None

    def test_excerpt_truncation_not_built_in(self) -> None:
        ref = SourceReference(document_id="id", document_name="f", excerpt="a" * 1000)
        assert len(ref.excerpt) == 1000


class TestComposedAnswer:
    def test_to_dict_roundtrip(self) -> None:
        answer = ComposedAnswer(
            answer="Hello",
            sources=[SourceReference(document_id="d1", document_name="a.pdf")],
            trace={"strategy": "test"},
        )
        d = answer.to_dict()
        assert d["answer"] == "Hello"
        assert d["sources"][0]["document_name"] == "a.pdf"
        assert d["trace"]["strategy"] == "test"
