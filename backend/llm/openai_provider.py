import httpx

from llm.base import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def complete(self, prompt: str, max_tokens: int = 2000) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
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
                },
            )
            response.raise_for_status()
            data = response.json()
            content: str = data["choices"][0]["message"].get("content") or ""
            if not content:
                reasoning = data["choices"][0]["message"].get("reasoning_content") or ""
                if reasoning:
                    import re

                    match = re.search(r"\{[\s\S]*\}", reasoning)
                    if match:
                        return match.group(0)
                    return reasoning
            return content
