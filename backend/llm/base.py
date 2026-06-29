from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, max_tokens: int = 2000) -> str:
        ...

    @abstractmethod
    async def stream_complete(self, prompt: str, max_tokens: int = 2000) -> AsyncIterator[str]:
        """Yield text chunks as the model generates them."""
        ...
        yield ""  # pragma: no cover

    async def close(self) -> None:
        """Optional cleanup hook. Override if the provider holds resources."""
        pass
