import json

import pytest
from httpx import AsyncClient


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
