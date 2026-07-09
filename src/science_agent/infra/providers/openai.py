"""Minimal OpenAI-compatible provider implementation."""

import json
import os
from typing import Any

import httpx

from science_agent.config import DEFAULT_MODEL
from science_agent.errors import ProviderError
from science_agent.types import Message, ModelResponse, ToolCallRequest


class OpenAIProvider:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

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

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions", headers=headers, json=payload
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"OpenAI request failed: {response.status_code} {response.text}"
            )

        raw = response.json()
        choice = raw["choices"][0]["message"]
        text = choice.get("content") or ""
        tool_calls: list[ToolCallRequest] = []
        for tool_call in choice.get("tool_calls", []) or []:
            raw_args = tool_call.get("function", {}).get("arguments", "{}")
            arguments = (
                json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            )
            tool_calls.append(
                ToolCallRequest(
                    name=tool_call["function"]["name"],
                    arguments=arguments,
                    call_id=tool_call.get("id"),
                )
            )
        return ModelResponse(text=text, tool_calls=tool_calls, raw=raw)
