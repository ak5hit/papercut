import json

import pytest
from httpx import AsyncClient

VALID_STAGES = {"understand", "search", "synthesize"}


def _parse_sse_events(text: str) -> list[tuple[str, dict]]:
    """Parse raw SSE text into list of (event_name, data_dict) tuples."""
    events: list[tuple[str, dict]] = []
    for part in text.strip().split("\n\n"):
        lines = part.strip().split("\n")
        if not lines:
            continue
        event_name = ""
        data_str = ""
        for line in lines:
            if line.startswith("event: "):
                event_name = line[7:]
            elif line.startswith("data: "):
                data_str = line[6:]
        if data_str:
            try:
                data = json.loads(data_str)
                events.append((event_name, data))
            except json.JSONDecodeError:
                pass
    return events


@pytest.mark.asyncio
async def test_chat_stream_requires_messages(client: AsyncClient) -> None:
    async with client.stream("POST", "/query/chat/stream", json={}) as response:
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_stream_requires_user_message(client: AsyncClient) -> None:
    async with client.stream(
        "POST",
        "/query/chat/stream",
        json={"messages": [{"role": "assistant", "content": "hello"}]},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = await response.aread()
        assert b"error" in body
        assert b"user message" in body


@pytest.mark.asyncio
async def test_chat_stream_unknown_session(client: AsyncClient) -> None:
    async with client.stream(
        "POST",
        "/query/chat/stream",
        json={
            "messages": [{"role": "user", "content": "hello"}],
            "session_id": "nonexistent",
        },
    ) as response:
        assert response.status_code == 200
        body = await response.aread()
        assert b"error" in body
        assert b"Session not found" in body


@pytest.mark.asyncio
async def test_chat_stream_content_type(client: AsyncClient) -> None:
    async with client.stream(
        "POST",
        "/query/chat/stream",
        json={"messages": [{"role": "user", "content": "test"}], "session_id": "nonexistent"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")


@pytest.mark.asyncio
async def test_chat_stream_progress_events(client: AsyncClient) -> None:
    """Progress events are emitted before the pipeline runs, even if the query later fails."""
    async with client.stream(
        "POST",
        "/query/chat/stream",
        json={
            "messages": [{"role": "user", "content": "what is email"}],
        },
    ) as response:
        assert response.status_code == 200
        body = await response.aread()
        text = body.decode("utf-8")

    events = _parse_sse_events(text)
    progress_events = [(name, data) for name, data in events if name == "progress"]

    assert len(progress_events) >= 1, "Expected at least one progress event"
    for _name, data in progress_events:
        assert "stage" in data, f"Progress event missing 'stage': {data}"
        assert "message" in data, f"Progress event missing 'message': {data}"
        assert isinstance(data["stage"], str) and data["stage"], f"Invalid stage: {data['stage']}"
        assert isinstance(data["message"], str) and data["message"], f"Invalid message: {data['message']}"
        assert data["stage"] in VALID_STAGES, f"Unexpected stage '{data['stage']}', expected one of {VALID_STAGES}"

    # If the query completed successfully, all 3 stages should appear
    # If it errored mid-pipeline, only understand/search may appear.
    # Either way, at least understand must be the first progress event.
    assert progress_events[0][1]["stage"] == "understand", "First progress stage must be 'understand'"


@pytest.mark.asyncio
async def test_chat_stream_sse_format(client: AsyncClient) -> None:
    async with client.stream(
        "POST",
        "/query/chat/stream",
        json={
            "messages": [{"role": "user", "content": "what is email"}],
        },
    ) as response:
        assert response.status_code == 200
        body = await response.aread()
        text = body.decode("utf-8")

    # The response may be an error if AGE is unreachable (test env without Docker),
    # but it must be valid SSE: event: + data: lines
    for event in text.strip().split("\n\n"):
        lines = event.strip().split("\n")
        if not lines:
            continue
        event_name = ""
        data_str = ""
        for line in lines:
            if line.startswith("event: "):
                event_name = line[7:]
            elif line.startswith("data: "):
                data_str = line[6:]
        if data_str:
            try:
                json.loads(data_str)
            except json.JSONDecodeError:
                pytest.fail(f"Invalid JSON in SSE event: {data_str}")
