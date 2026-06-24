from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from graph.extractor import GraphExtractor
from config import Settings


def _make_node(id: str, type: str, desc: str = ""):
    n = MagicMock()
    n.id = id
    n.type = type
    n.properties = {"description": desc} if desc else {}
    return n


def _make_rel(src, tgt, rel_type):
    r = MagicMock()
    r.source = src
    r.target = tgt
    r.type = rel_type
    r.properties = {}
    return r


def _make_graph_doc(nodes, rels):
    gd = MagicMock()
    gd.nodes = nodes
    gd.relationships = rels
    gd.source = MagicMock()
    gd.source.metadata = {"combined_chunk_ids": [str(uuid4())]}
    return gd


def test_sanitize_strips_backticks():
    settings = Settings()
    extractor = GraphExtractor(settings)

    n = _make_node("`Microsoft`", "`Organization`")
    gd = _make_graph_doc([n], [])
    result = extractor._sanitize([gd])
    assert result[0].nodes[0].type == "Organization"
    assert result[0].nodes[0].id == "Microsoft"


def test_sanitize_drops_empty():
    settings = Settings()
    extractor = GraphExtractor(settings)

    n = MagicMock()
    n.id = ""
    n.type = "Organization"
    n.properties = {}
    gd = _make_graph_doc([n], [])
    result = extractor._sanitize([gd])
    assert len(result[0].nodes) == 0


def test_sanitize_drops_empty_rel():
    settings = Settings()
    extractor = GraphExtractor(settings)

    n = _make_node("MS", "Org")
    r = MagicMock()
    r.type = ""
    r.source = _make_node("A", "Person")
    r.target = _make_node("B", "Org")
    r.properties = {}
    gd = _make_graph_doc([n], [r])
    result = extractor._sanitize([gd])
    assert len(result[0].relationships) == 0
