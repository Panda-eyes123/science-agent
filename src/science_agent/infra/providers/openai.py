"""Minimal OpenAI-compatible provider implementation."""

import asyncio
import json
import os
from collections.abc import AsyncIterator
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
from science_agent.types import (
    Message,
    ModelResponse,
    ModelStreamEnd,
    ModelStreamEvent,
    ModelTextDelta,
    ToolCallRequest,
)


@dataclass(frozen=True, slots=True)
class RetryConfig:
    max_attempts: int = 3
    backoff_seconds: float = 0.5


class OpenAIProvider:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        retry: RetryConfig | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL") or DEFAULT_MODEL
        self.base_url = (
            base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        ).rstrip("/")
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
        response = await self._post_with_retry(
            self._headers(), self._payload(messages, tools, system_prompt)
        )
        try:
            raw = response.json()
            return _parse_message(raw["choices"][0]["message"], raw=raw)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderResponseError(
                "OpenAI response had an unexpected shape."
            ) from exc

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderError("OPENAI_API_KEY is not set.")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _payload(
        self,
        messages: list[Message],
        tools: list[dict] | None,
        system_prompt: str | None,
    ) -> dict[str, Any]:
        payload_messages: list[dict[str, Any]] = []
        if system_prompt:
            payload_messages.append({"role": "system", "content": system_prompt})
        for message in messages:
            entry: dict[str, Any] = {"role": message.role, "content": message.content}
            if message.role == "tool" and message.tool_call_id:
                entry["tool_call_id"] = message.tool_call_id
            if message.name:
                entry["name"] = message.name
            if message.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": call.call_id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments, ensure_ascii=False),
                        },
                    }
                    for call in message.tool_calls
                ]
            payload_messages.append(entry)

        payload: dict[str, Any] = {"model": self.model, "messages": payload_messages}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        return payload

    async def stream(
        self,
        messages: list[Message],
        *,
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[ModelStreamEvent]:
        payload = self._payload(messages, tools, system_prompt)
        payload["stream"] = True
        headers = self._headers()
        consumed = False
        attempts = max(1, self.retry.max_attempts)
        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout, transport=self.transport
                ) as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    ) as response:
                        if response.status_code >= 400:
                            await response.aread()
                            raise _classify_openai_response(response)
                        text: list[str] = []
                        calls: dict[int, dict[str, Any]] = {}
                        finished = False
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                finished = True
                                break
                            consumed = True
                            try:
                                chunk = json.loads(data)
                                if "error" in chunk:
                                    raise ProviderResponseError(str(chunk["error"]))
                                choices = chunk.get("choices") or []
                                if not choices:
                                    continue
                                choice = choices[0]
                                if choice.get("finish_reason") in {
                                    "length",
                                    "content_filter",
                                }:
                                    raise ProviderResponseError(
                                        f"Model stopped: {choice['finish_reason']}"
                                    )
                                delta = choice.get("delta") or {}
                                if delta.get("content"):
                                    text.append(delta["content"])
                                    yield ModelTextDelta(text=delta["content"])
                                # 按 index 分别拼接工具参数；完整收到后才能解析并执行。
                                for part in delta.get("tool_calls") or []:
                                    call = calls.setdefault(
                                        part["index"],
                                        {
                                            "id": "",
                                            "function": {"name": "", "arguments": ""},
                                        },
                                    )
                                    if part.get("id"):
                                        call["id"] += part["id"]
                                    function = part.get("function") or {}
                                    for key in ("name", "arguments"):
                                        call["function"][key] += function.get(key) or ""
                            except (KeyError, TypeError, ValueError) as exc:
                                raise ProviderResponseError(
                                    "Invalid streaming response."
                                ) from exc
                        if not finished:
                            raise ProviderResponseError(
                                "Model stream ended before [DONE]."
                            )
                        yield ModelStreamEnd(
                            response=_parse_message(
                                {
                                    "content": "".join(text),
                                    "tool_calls": [calls[key] for key in sorted(calls)],
                                }
                            )
                        )
                        return
            except httpx.TimeoutException:
                error = ProviderTimeoutError("OpenAI request timed out.")
            except httpx.RequestError as exc:
                error = ProviderNetworkError(f"OpenAI network request failed: {exc}")
            except ProviderError as exc:
                error = exc
            # 消费流后不重试，避免重复文本或工具副作用。
            if consumed or not error.retryable or attempt == attempts - 1:
                raise error
            await asyncio.sleep(_retry_delay(error, attempt, self.retry))

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


def _parse_message(choice: dict, raw: dict | None = None) -> ModelResponse:
    try:
        calls = []
        for call in choice.get("tool_calls") or []:
            function = call["function"]
            args = function.get("arguments") or "{}"
            calls.append(
                ToolCallRequest(
                    name=function["name"],
                    arguments=json.loads(args) if isinstance(args, str) else args,
                    call_id=call.get("id") or None,
                )
            )
        return ModelResponse(
            text=choice.get("content") or "", tool_calls=calls, raw=raw
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderResponseError("Invalid model message or tool arguments.") from exc


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
