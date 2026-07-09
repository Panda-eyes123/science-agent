"""Provider exports."""

from science_agent.types import ModelResponse, ToolCallRequest

from .base import ModelProvider

try:
    from .openai import OpenAIProvider
except ModuleNotFoundError as exc:  # pragma: no cover

    class OpenAIProvider:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            raise ModuleNotFoundError(
                "OpenAIProvider requires the optional dependency 'httpx'. Install project dependencies first."
            ) from exc


__all__ = ["ModelProvider", "ModelResponse", "OpenAIProvider", "ToolCallRequest"]
