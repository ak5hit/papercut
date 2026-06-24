from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Literal

from config import settings


@dataclass
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str
    created_at: float = field(default_factory=time.time)


@dataclass
class ChatSession:
    id: str
    messages: list[ChatMessage] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)


class ChatSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}
        self._lock = asyncio.Lock()
        self.ttl_seconds = settings.chat_session_ttl_hours * 3600

    async def create(self) -> ChatSession:
        import uuid

        async with self._lock:
            self._evict_expired()
            session_id = uuid.uuid4().hex
            session = ChatSession(id=session_id)
            self._sessions[session_id] = session
            return session

    async def get(self, session_id: str) -> ChatSession | None:
        async with self._lock:
            self._evict_expired()
            session = self._sessions.get(session_id)
            if session is not None:
                session.last_activity = time.time()
            return session

    async def append(self, session_id: str, message: ChatMessage) -> ChatSession | None:
        async with self._lock:
            self._evict_expired()
            session = self._sessions.get(session_id)
            if session is None:
                return None
            session.messages.append(message)
            session.last_activity = time.time()
            return session

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [
            sid
            for sid, s in self._sessions.items()
            if now - s.last_activity > self.ttl_seconds
        ]
        for sid in expired:
            del self._sessions[sid]


store = ChatSessionStore()
