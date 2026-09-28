"""Provider protocol definitions."""

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from science_agent.types import (
    Message,
    ModelResponse,
    ModelStreamEvent,
    ToolCallRequest,
)


class ModelProvider(Protocol):
    async def complete(
        self,
        messages: list[Message],
        *,
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
    ) -> ModelResponse: ...


@runtime_checkable
class StreamingModelProvider(Protocol):
    def stream(
        self,
        messages: list[Message],
        *,
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[ModelStreamEvent]: ...


__all__ = [
    "ModelProvider",
    "StreamingModelProvider",
    "ModelResponse",
    "ToolCallRequest",
]
