from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from llm.base import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=self.timeout)

    async def complete(self, prompt: str, max_tokens: int = 2000) -> str:
        response = await self._client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.0,
                "thinking": {"type": "disabled"},
            },
        )
        response.raise_for_status()
        data = response.json()
        content: str = data["choices"][0]["message"].get("content") or ""
        return content

    async def stream_complete(self, prompt: str, max_tokens: int = 2000) -> AsyncIterator[str]:
        async with self._client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.0,
                "thinking": {"type": "disabled"},
                "stream": True,
            },
        ) as response:
            response.raise_for_status()
            buffer = ""
            async for chunk in response.aiter_bytes():
                buffer += chunk.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if line.startswith("data: "):
                        raw = line[6:]
                        if raw == "[DONE]":
                            return
                        try:
                            evt = json.loads(raw)
                            delta = evt.get("choices", [{}])[0].get("delta", {})
                            content_text = delta.get("content")
                            if content_text:
                                yield content_text
                        except json.JSONDecodeError:
                            pass

    async def close(self) -> None:
        await self._client.aclose()
