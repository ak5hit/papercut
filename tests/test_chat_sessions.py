import time

import pytest

from chat.sessions import ChatMessage, ChatSessionStore


@pytest.fixture
def empty_store() -> ChatSessionStore:
    store = ChatSessionStore()
    store._sessions = {}
    return store


@pytest.mark.asyncio
async def test_create_and_get(empty_store: ChatSessionStore) -> None:
    session = await empty_store.create()
    assert session.id
    assert len(session.messages) == 0

    retrieved = await empty_store.get(session.id)
    assert retrieved is not None
    assert retrieved.id == session.id


@pytest.mark.asyncio
async def test_get_unknown_id(empty_store: ChatSessionStore) -> None:
    retrieved = await empty_store.get("nonexistent")
    assert retrieved is None


@pytest.mark.asyncio
async def test_append_message(empty_store: ChatSessionStore) -> None:
    session = await empty_store.create()
    msg = ChatMessage(role="user", content="hello")
    result = await empty_store.append(session.id, msg)
    assert result is not None
    assert len(result.messages) == 1
    assert result.messages[0].content == "hello"
    assert result.messages[0].role == "user"

    msg2 = ChatMessage(role="assistant", content="world")
    await empty_store.append(session.id, msg2)
    assert len(result.messages) == 2
    assert result.messages[1].content == "world"


@pytest.mark.asyncio
async def test_append_unknown_session(empty_store: ChatSessionStore) -> None:
    msg = ChatMessage(role="user", content="hello")
    result = await empty_store.append("nonexistent", msg)
    assert result is None


@pytest.mark.asyncio
async def test_eviction_on_access(empty_store: ChatSessionStore) -> None:
    empty_store.ttl_seconds = 0
    session = await empty_store.create()
    assert await empty_store.get(session.id) is None


@pytest.mark.asyncio
async def test_eviction_skips_active(empty_store: ChatSessionStore) -> None:
    session = await empty_store.create()
    msg = ChatMessage(role="user", content="ping")
    await empty_store.append(session.id, msg)
    assert await empty_store.get(session.id) is not None


@pytest.mark.asyncio
async def test_last_activity_updates_on_get(empty_store: ChatSessionStore) -> None:
    session = await empty_store.create()
    original = session.last_activity
    time.sleep(0.01)
    await empty_store.get(session.id)
    assert session.last_activity > original


@pytest.mark.asyncio
async def test_last_activity_updates_on_append(empty_store: ChatSessionStore) -> None:
    session = await empty_store.create()
    original = session.last_activity
    time.sleep(0.01)
    msg = ChatMessage(role="user", content="x")
    await empty_store.append(session.id, msg)
    assert session.last_activity > original


@pytest.mark.asyncio
async def test_concurrent_create(empty_store: ChatSessionStore) -> None:
    import asyncio

    async def create_one() -> str:
        s = await empty_store.create()
        return s.id

    ids = await asyncio.gather(*[create_one() for _ in range(10)])
    assert len(set(ids)) == 10
