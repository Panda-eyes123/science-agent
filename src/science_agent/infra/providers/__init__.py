"""Provider exports."""

from science_agent.types import ModelResponse, ToolCallRequest

from .base import ModelProvider

_openai_provider_import_error: ModuleNotFoundError | None = None

try:
    from .openai import OpenAIProvider, RetryConfig
except ModuleNotFoundError as exc:  # pragma: no cover
    _openai_provider_import_error = exc

    class OpenAIProvider:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            raise ModuleNotFoundError(
                "OpenAIProvider requires the optional dependency 'httpx'. Install project dependencies first."
            ) from _openai_provider_import_error

    class RetryConfig:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            raise ModuleNotFoundError(
                "RetryConfig requires the optional dependency 'httpx'. Install project dependencies first."
            ) from _openai_provider_import_error


__all__ = [
    "ModelProvider",
    "ModelResponse",
    "OpenAIProvider",
    "RetryConfig",
    "ToolCallRequest",
]
