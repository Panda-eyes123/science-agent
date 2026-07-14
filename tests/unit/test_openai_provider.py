import httpx
import pytest

from science_agent.errors import (
    ProviderAuthenticationError,
    ProviderNetworkError,
    ProviderRateLimitError,
)
from science_agent.infra.providers.openai import OpenAIProvider, RetryConfig
from science_agent.types import Message


def _success_response(request: httpx.Request, text: str = "ok") -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": text}}]},
        request=request,
    )


@pytest.mark.asyncio
async def test_openai_provider_retries_server_errors_then_succeeds():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                500,
                json={"error": {"message": "temporary outage"}},
                request=request,
            )
        return _success_response(request, "recovered")

    provider = OpenAIProvider(
        api_key="test",
        retry=RetryConfig(max_attempts=2, backoff_seconds=0),
        transport=httpx.MockTransport(handler),
    )

    result = await provider.complete([Message(role="user", content="hello")])

    assert result.text == "recovered"
    assert calls == 2


@pytest.mark.asyncio
async def test_openai_provider_does_not_retry_authentication_errors():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            401,
            json={"error": {"message": "bad key"}},
            request=request,
        )

    provider = OpenAIProvider(
        api_key="test",
        retry=RetryConfig(max_attempts=3, backoff_seconds=0),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderAuthenticationError) as error:
        await provider.complete([Message(role="user", content="hello")])

    assert error.value.status_code == 401
    assert calls == 1


@pytest.mark.asyncio
async def test_openai_provider_retries_rate_limits_until_exhausted():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            429,
            json={"error": {"message": "slow down"}},
            headers={"retry-after": "0"},
            request=request,
        )

    provider = OpenAIProvider(
        api_key="test",
        retry=RetryConfig(max_attempts=2, backoff_seconds=0),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderRateLimitError) as error:
        await provider.complete([Message(role="user", content="hello")])

    assert error.value.retryable is True
    assert error.value.retry_after == 0
    assert calls == 2


@pytest.mark.asyncio
async def test_openai_provider_retries_network_errors_then_succeeds():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("connection reset", request=request)
        return _success_response(request, "network recovered")

    provider = OpenAIProvider(
        api_key="test",
        retry=RetryConfig(max_attempts=2, backoff_seconds=0),
        transport=httpx.MockTransport(handler),
    )

    result = await provider.complete([Message(role="user", content="hello")])

    assert result.text == "network recovered"
    assert calls == 2


@pytest.mark.asyncio
async def test_openai_provider_raises_network_error_after_retry_exhaustion():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection reset", request=request)

    provider = OpenAIProvider(
        api_key="test",
        retry=RetryConfig(max_attempts=2, backoff_seconds=0),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderNetworkError) as error:
        await provider.complete([Message(role="user", content="hello")])

    assert error.value.retryable is True
