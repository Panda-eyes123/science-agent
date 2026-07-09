"""Provider protocol definitions."""

from typing import Protocol

from science_agent.types import Message, ModelResponse, ToolCallRequest


class ModelProvider(Protocol):
    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
    ) -> ModelResponse: ...


__all__ = ["ModelProvider", "ModelResponse", "ToolCallRequest"]
