from unittest.mock import AsyncMock, patch

import pytest
from httpx import Request, Response

from config import Settings
from llm.factory import create_llm_provider, get_llm_provider
from llm.ollama_provider import OllamaProvider
from llm.openai_provider import OpenAICompatibleProvider


@pytest.mark.asyncio
async def test_get_llm_provider_returns_cached_instance() -> None:
    """get_llm_provider should return the same instance on repeated calls."""
    s = Settings(
        llm_provider="openai",
        openai_api_key="test-key",
        llm_model="gpt-4o-mini",
        openai_base_url="https://api.openai.com/v1",
    )
    p1 = await get_llm_provider(s)
    p2 = await get_llm_provider(s)
    assert p1 is p2


class TestOpenAIProvider:
    def test_initialization(self) -> None:
        provider = OpenAICompatibleProvider(
            api_key="test-key",
            model="gpt-4o",
            base_url="https://custom.api.com/v1",
            timeout=30.0,
        )
        assert provider.api_key == "test-key"
        assert provider.model == "gpt-4o"
        assert provider.base_url == "https://custom.api.com/v1"
        assert provider.timeout == 30.0

    def test_base_url_trailing_slash_stripped(self) -> None:
        provider = OpenAICompatibleProvider(
            api_key="test-key",
            base_url="https://api.openai.com/v1/",
        )
        assert provider.base_url == "https://api.openai.com/v1"

    def test_default_values(self) -> None:
        provider = OpenAICompatibleProvider(api_key="test-key")
        assert provider.model == "gpt-4o-mini"
        assert provider.base_url == "https://api.openai.com/v1"
        assert provider.timeout == 60.0

    @pytest.mark.asyncio
    async def test_complete_returns_response_text(self) -> None:
        mock_response = Response(
            status_code=200,
            json={
                "choices": [{"message": {"content": "extracted entities here"}}],
            },
            request=Request("POST", "https://api.openai.com/v1/chat/completions"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            provider = OpenAICompatibleProvider(api_key="test-key")
            result = await provider.complete("extract entities", max_tokens=500)

        assert result == "extracted entities here"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["json"]["model"] == "gpt-4o-mini"
        assert call_kwargs["json"]["temperature"] == 0.0
        assert call_kwargs["json"]["max_tokens"] == 500
        assert call_kwargs["json"]["thinking"] == {"type": "disabled"}

    @pytest.mark.asyncio
    async def test_thinking_disabled_via_parameter(self) -> None:
        """Verify that thinking: {type: disabled} is sent in the request body."""
        mock_response = Response(
            status_code=200,
            json={
                "choices": [{"message": {"content": "test"}}],
            },
            request=Request("POST", "https://api.openai.com/v1/chat/completions"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            provider = OpenAICompatibleProvider(api_key="test-key")
            await provider.complete("test prompt")

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["thinking"] == {"type": "disabled"}

    @pytest.mark.asyncio
    async def test_reasoning_content_not_fallback(self) -> None:
        """Reasoning content is NOT extracted when content is empty.
        reasoning_effort: none prevents the model from emitting it, so
        there is no fallback."""
        mock_response = Response(
            status_code=200,
            json={
                "choices": [{
                    "message": {
                        "content": None,
                        "reasoning_content": "Some thinking text.",
                    },
                }],
            },
            request=Request("POST", "https://api.openai.com/v1/chat/completions"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            provider = OpenAICompatibleProvider(api_key="test-key")
            result = await provider.complete("extract", max_tokens=500)

        assert result == ""


class TestOllamaProvider:
    def test_initialization(self) -> None:
        provider = OllamaProvider(
            model="mistral",
            base_url="http://localhost:11435",
            timeout=90.0,
        )
        assert provider.model == "mistral"
        assert provider.base_url == "http://localhost:11435"
        assert provider.timeout == 90.0

    def test_default_values(self) -> None:
        provider = OllamaProvider()
        assert provider.model == "llama3"
        assert provider.base_url == "http://localhost:11434"
        assert provider.timeout == 120.0

    @pytest.mark.asyncio
    async def test_complete_returns_response_text(self) -> None:
        mock_response = Response(
            status_code=200,
            json={"response": "extracted entities here"},
            request=Request("POST", "http://localhost:11434/api/generate"),
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            provider = OllamaProvider()
            result = await provider.complete("extract entities", max_tokens=500)

        assert result == "extracted entities here"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["json"]["model"] == "llama3"
        assert call_kwargs["json"]["stream"] is False
        assert call_kwargs["json"]["options"]["num_predict"] == 500


class TestProviderFactory:
    def test_creates_openai_provider(self) -> None:
        s = Settings(
            llm_provider="openai",
            openai_api_key="test-key",
            llm_model="gpt-4o",
            openai_base_url="https://api.openai.com/v1",
        )
        provider = create_llm_provider(s)
        assert isinstance(provider, OpenAICompatibleProvider)

    def test_creates_openai_compatible_provider(self) -> None:
        s = Settings(
            llm_provider="openai-compatible",
            openai_api_key="test-key",
            llm_model="gpt-4o",
            openai_base_url="https://api.openai.com/v1",
        )
        provider = create_llm_provider(s)
        assert isinstance(provider, OpenAICompatibleProvider)

    def test_creates_ollama_provider(self) -> None:
        s = Settings(
            llm_provider="ollama",
            llm_model="llama3",
            ollama_base_url="http://localhost:11434",
        )
        provider = create_llm_provider(s)
        assert isinstance(provider, OllamaProvider)

    def test_raises_on_unknown_provider(self) -> None:
        s = Settings(
            llm_provider="anthropic",
            openai_api_key="test-key",
            llm_model="claude",
            openai_base_url="https://api.anthropic.com",
        )
        with pytest.raises(ValueError, match="Unknown LLM provider: anthropic"):
            create_llm_provider(s)

    def test_validates_openai_api_key(self) -> None:
        s = Settings(
            llm_provider="openai",
            openai_api_key="",
            llm_model="gpt-4o-mini",
        )
        with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
            create_llm_provider(s)

    def test_provider_name_case_insensitive(self) -> None:
        s = Settings(
            llm_provider="OPENAI",
            openai_api_key="test-key",
            llm_model="gpt-4o-mini",
        )
        provider = create_llm_provider(s)
        assert isinstance(provider, OpenAICompatibleProvider)
