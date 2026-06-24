import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_chat_requires_messages(client: AsyncClient) -> None:
    response = await client.post("/query/chat", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_requires_user_message(client: AsyncClient) -> None:
    response = await client.post(
        "/query/chat",
        json={"messages": [{"role": "assistant", "content": "hello"}]},
    )
    assert response.status_code == 400
    assert "user message" in response.json()["detail"]


@pytest.mark.asyncio
async def test_chat_creates_session_and_returns_answer(client: AsyncClient) -> None:
    response = await client.post(
        "/query/chat",
        json={"messages": [{"role": "user", "content": "What is the capital of France?"}]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"]
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "What is the capital of France?"
    assert data["messages"][1]["role"] == "assistant"
    assert data["messages"][1]["content"]


@pytest.mark.asyncio
async def test_chat_returns_response_struct(client: AsyncClient) -> None:
    response = await client.post(
        "/query/chat",
        json={"messages": [{"role": "user", "content": "What is the capital of Germany?"}]},
    )
    assert response.status_code == 200
    data = response.json()
    resp = data["response"]
    assert "answer" in resp
    assert "sources" in resp
    assert "trace" in resp
    assert "strategy" in resp["trace"]


@pytest.mark.asyncio
async def test_chat_unknown_session(client: AsyncClient) -> None:
    response = await client.post(
        "/query/chat",
        json={
            "messages": [{"role": "user", "content": "hello"}],
            "session_id": "nonexistent",
        },
    )
    assert response.status_code == 404
    assert "Session not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_chat_reuses_session_and_accumulates_history(client: AsyncClient) -> None:
    first = await client.post(
        "/query/chat",
        json={"messages": [{"role": "user", "content": "First question"}]},
    )
    assert first.status_code == 200
    session_id = first.json()["session_id"]
    assert len(first.json()["messages"]) == 2

    second = await client.post(
        "/query/chat",
        json={
            "session_id": session_id,
            "messages": [
                {"role": "user", "content": "First question"},
                {"role": "assistant", "content": first.json()["messages"][1]["content"]},
                {"role": "user", "content": "Second question"},
            ],
        },
    )
    assert second.status_code == 200
    data = second.json()
    assert data["session_id"] == session_id
    assert len(data["messages"]) == 4
    assert data["messages"][-1]["role"] == "assistant"
