from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ChatRequestMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatRequestMessage]
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    messages: list[ChatRequestMessage]
    response: dict[str, Any]
