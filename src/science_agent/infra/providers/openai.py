"""Minimal OpenAI-compatible provider implementation."""

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

from science_agent.config import DEFAULT_MODEL
from science_agent.errors import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderInvalidRequestError,
    ProviderNetworkError,
    ProviderNotFoundError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderServerError,
    ProviderTimeoutError,
)
from science_agent.types import Message, ModelResponse, ToolCallRequest


@dataclass(frozen=True, slots=True)
class RetryConfig:
    max_attempts: int = 3
    backoff_seconds: float = 0.5


class OpenAIProvider:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
        retry: RetryConfig | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retry = retry or RetryConfig()
        self.transport = transport

    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
    ) -> ModelResponse:
        if not self.api_key:
            raise ProviderError("OPENAI_API_KEY is not set.")

        payload_messages: list[dict[str, Any]] = []
        if system_prompt:
            payload_messages.append({"role": "system", "content": system_prompt})
        for message in messages:
            entry: dict[str, Any] = {"role": message.role, "content": message.content}
            if message.role == "tool" and message.tool_call_id:
                entry["tool_call_id"] = message.tool_call_id
            if message.name:
                entry["name"] = message.name
            payload_messages.append(entry)

        payload: dict[str, Any] = {"model": self.model, "messages": payload_messages}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        response = await self._post_with_retry(headers, payload)

        try:
            raw = response.json()
            choice = raw["choices"][0]["message"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderResponseError("OpenAI response had an unexpected shape.") from exc
        text = choice.get("content") or ""
        tool_calls: list[ToolCallRequest] = []
        for tool_call in choice.get("tool_calls", []) or []:
            raw_args = tool_call.get("function", {}).get("arguments", "{}")
            try:
                arguments = (
                    json.loads(raw_args)
                    if isinstance(raw_args, str)
                    else (raw_args or {})
                )
            except json.JSONDecodeError as exc:
                raise ProviderResponseError(
                    f"OpenAI returned invalid tool arguments for {tool_call.get('id')}."
                ) from exc
            tool_calls.append(
                ToolCallRequest(
                    name=tool_call["function"]["name"],
                    arguments=arguments,
                    call_id=tool_call.get("id"),
                )
            )
        return ModelResponse(text=text, tool_calls=tool_calls, raw=raw)

    async def _post_with_retry(
        self, headers: dict[str, str], payload: dict[str, Any]
    ) -> httpx.Response:
        attempts = max(1, self.retry.max_attempts)
        last_error: ProviderError | None = None

        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout, transport=self.transport
                ) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                if response.status_code < 400:
                    return response
                raise _classify_openai_response(response)
            except httpx.TimeoutException:
                last_error = ProviderTimeoutError("OpenAI request timed out.")
            except httpx.NetworkError as exc:
                last_error = ProviderNetworkError(
                    f"OpenAI network request failed: {exc}"
                )
            except ProviderError as exc:
                last_error = exc

            if not last_error.retryable or attempt == attempts - 1:
                raise last_error
            await asyncio.sleep(_retry_delay(last_error, attempt, self.retry))

        raise last_error or ProviderError("OpenAI request failed.")


def _classify_openai_response(response: httpx.Response) -> ProviderError:
    message = _extract_error_message(response)
    status_code = response.status_code
    retry_after = _parse_retry_after(response.headers.get("retry-after"))
    detail = f"OpenAI request failed: {status_code} {message}"

    if status_code in {401, 403}:
        return ProviderAuthenticationError(detail, status_code=status_code)
    if status_code == 404:
        return ProviderNotFoundError(detail, status_code=status_code)
    if status_code in {400, 422}:
        return ProviderInvalidRequestError(detail, status_code=status_code)
    if status_code == 408:
        return ProviderTimeoutError(
            detail, status_code=status_code, retry_after=retry_after
        )
    if status_code == 429:
        return ProviderRateLimitError(
            detail, status_code=status_code, retry_after=retry_after
        )
    if status_code == 409 or status_code >= 500:
        return ProviderServerError(
            detail, status_code=status_code, retry_after=retry_after
        )
    return ProviderError(detail, status_code=status_code)


def _extract_error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except json.JSONDecodeError:
        return response.text
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(body)


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _retry_delay(error: ProviderError, attempt: int, retry: RetryConfig) -> float:
    if error.retry_after is not None:
        return error.retry_after
    return retry.backoff_seconds * (2**attempt)
