from typing import Any

from langchain_core.documents import Document
from langchain_experimental.graph_transformers import LLMGraphTransformer

from config import Settings
from graph.llm_bridge import build_langchain_chat


class GraphExtractor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._transformer: LLMGraphTransformer | None = None

    def _get_transformer(self) -> LLMGraphTransformer:
        if self._transformer is not None:
            return self._transformer
        llm = build_langchain_chat(self.settings)
        kwargs: dict[str, Any] = {"llm": llm}

        allowed_nodes = [n.strip() for n in self.settings.graph_allowed_nodes.split(",") if n.strip()]
        allowed_rels_raw = [
            r.strip() for r in self.settings.graph_allowed_relationships.split(",") if r.strip()
        ]
        if allowed_nodes:
            kwargs["allowed_nodes"] = allowed_nodes
        if len(allowed_rels_raw) % 3 == 0 and allowed_rels_raw:
            kwargs["allowed_relationships"] = [
                (allowed_rels_raw[i], allowed_rels_raw[i + 1], allowed_rels_raw[i + 2])
                for i in range(0, len(allowed_rels_raw), 3)
            ]

        kwargs["node_properties"] = False
        kwargs["relationship_properties"] = False
        kwargs["ignore_tool_usage"] = True
        kwargs["additional_instructions"] = (
            "Your goal is to identify and categorize entities while ensuring that specific data "
            "types such as dates, numbers, revenues, and other non-entity information are not "
            "extracted as separate nodes. Instead, treat these as properties associated with the "
            "relevant entities. "
            "Extract email addresses as nodes with label 'Email' and the email as the id. "
            "Extract phone numbers as nodes with label 'Phone' and the phone number as the id. "
            "Extract URLs as nodes with label 'URL' and the URL as the id."
        )

        self._transformer = LLMGraphTransformer(**kwargs)
        return self._transformer

    async def extract(self, chunks: list[dict[str, Any]]) -> list[Any]:
        transformer = self._get_transformer()
        combine = max(1, self.settings.graph_chunks_to_combine)

        combined: list[Document] = []
        for i in range(0, len(chunks), combine):
            batch = chunks[i : i + combine]
            text = "".join(c["text"] for c in batch)
            ids = [c["id"] for c in batch]
            combined.append(Document(page_content=text, metadata={"combined_chunk_ids": ids}))

        graph_docs = await transformer.aconvert_to_graph_documents(combined)
        return self._sanitize(graph_docs)

    def _sanitize(self, graph_docs: list[Any]) -> list[Any]:
        for gd in graph_docs:
            cleaned_nodes = []
            for node in gd.nodes:
                node.type = _strip(node.type)
                node.id = _strip(node.id)
                if node.type and node.id:
                    cleaned_nodes.append(node)
            gd.nodes = cleaned_nodes

            cleaned_rels = []
            for rel in gd.relationships:
                rel.type = _strip(rel.type)
                if rel.source:
                    rel.source.type = _strip(rel.source.type)
                    rel.source.id = _strip(rel.source.id)
                if rel.target:
                    rel.target.type = _strip(rel.target.type)
                    rel.target.id = _strip(rel.target.id)
                if rel.type and rel.source and rel.target:
                    if rel.source.type and rel.source.id and rel.target.type and rel.target.id:
                        cleaned_rels.append(rel)
            gd.relationships = cleaned_rels

        return graph_docs


def _strip(value: str | None) -> str:
    if not value:
        return ""
    return str(value).strip().replace("`", "")
