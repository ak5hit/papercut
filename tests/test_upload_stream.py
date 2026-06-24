import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.routes.documents import router


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()
    application.include_router(router)
    return application


def _parse_events(body: str) -> list[dict[str, object]]:
    """Parse SSE body into a list of {type, data} dicts."""
    events: list[dict[str, object]] = []
    for part in body.split("\n\n"):
        lines = part.strip().split("\n")
        event_type = ""
        data_line = ""
        for line in lines:
            if line.startswith("event: "):
                event_type = line[7:].strip()
            elif line.startswith("data: "):
                data_line = line[6:].strip()

        if data_line and event_type:
            events.append({"type": event_type, "data": json.loads(data_line), "raw": part})
    return events


@pytest.fixture(autouse=True)
def mock_deps():
    """Mock embedding/llm/settings dependencies for upload tests."""
    with (
        patch("api.routes.documents.create_embedding_provider") as mock_emb,
        patch("api.routes.documents.create_llm_provider") as mock_llm,
        patch("api.routes.documents.app_settings") as mock_set,
    ):
        mock_emb.return_value = MagicMock()
        mock_emb.return_value.embed = MagicMock(return_value=[[0.1, 0.2, 0.3]])
        mock_llm.return_value = MagicMock()
        mock_set.graph_extraction_enabled = False
        mock_set.openai_api_key = ""
        mock_set.llm_provider = "ollama"
        yield


@pytest.mark.asyncio
async def test_upload_stream_returns_sse_content_type(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10) as client:
        files = {"file": ("test.pdf", b"%PDF-1.4 fake content", "application/pdf")}
        resp = await client.post("/documents/upload", files=files)

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_upload_stream_emits_phase_events_before_error(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10) as client:
        files = {"file": ("test.pdf", b"%PDF-1.4 fake content", "application/pdf")}
        resp = await client.post("/documents/upload", files=files)

    assert resp.status_code == 200
    events = _parse_events(resp.text)
    assert len(events) >= 2  # at least one phase + error/done

    # The "reading" phase should fire before the fake PDF fails
    assert events[0]["type"] == "phase"
    assert events[0]["data"]["phase"] == "reading"

    # The last event should be either "done" or "error"
    assert events[-1]["type"] in ("done", "error")


@pytest.mark.asyncio
async def test_upload_stream_ends_with_error_or_done(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10) as client:
        files = {"file": ("test.pdf", b"%PDF-1.4 fake content", "application/pdf")}
        resp = await client.post("/documents/upload", files=files)

    assert resp.status_code == 200
    events = _parse_events(resp.text)
    assert events[-1]["type"] in ("done", "error")


@pytest.mark.asyncio
async def test_upload_stream_rejects_non_pdf(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10) as client:
        files = {"file": ("test.txt", b"not a pdf", "text/plain")}
        resp = await client.post("/documents/upload", files=files)

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_stream_phase_labels_are_human_readable(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10) as client:
        files = {"file": ("test.pdf", b"%PDF-1.4 fake content", "application/pdf")}
        resp = await client.post("/documents/upload", files=files)

    assert resp.status_code == 200
    events = _parse_events(resp.text)

    for ev in events:
        if ev["type"] == "phase":
            label = ev["data"].get("label", "")
            assert isinstance(label, str) and len(label) > 0
            assert not label.startswith("phase_")


@pytest.mark.asyncio
async def test_upload_stream_reading_phase_is_first(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10) as client:
        files = {"file": ("test.pdf", b"%PDF-1.4 fake content", "application/pdf")}
        resp = await client.post("/documents/upload", files=files)

    assert resp.status_code == 200
    events = _parse_events(resp.text)
    assert events[0]["type"] == "phase"
    assert events[0]["data"]["phase"] == "reading"
