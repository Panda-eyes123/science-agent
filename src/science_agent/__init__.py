"""Public package exports for the phase-one SDK skeleton."""

from .core.agent import Agent, AgentConfig
from .core.template import AgentTemplateDefinition, AgentTemplateRegistry
from .core.todo import TodoItem, TodoService
from .infra.providers.base import ModelProvider
from .infra.sandbox import LocalSandbox, SandboxResult
from .infra.store import (
    EventSequenceConflictError,
    JSONStore,
    PostgresStore,
    StoreError,
    migrate_postgres,
)
from .tools.base import Tool, ToolExecutionContext
from .tools.registry import ToolRegistry
from .types import ModelResponse, ToolCallRequest

_openai_provider_import_error: ModuleNotFoundError | None = None

try:
    from .infra.providers.openai import OpenAIProvider, RetryConfig
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
    "Agent",
    "AgentConfig",
    "AgentTemplateDefinition",
    "AgentTemplateRegistry",
    "EventSequenceConflictError",
    "JSONStore",
    "LocalSandbox",
    "ModelProvider",
    "ModelResponse",
    "OpenAIProvider",
    "PostgresStore",
    "RetryConfig",
    "SandboxResult",
    "StoreError",
    "TodoItem",
    "TodoService",
    "Tool",
    "ToolCallRequest",
    "ToolExecutionContext",
    "ToolRegistry",
    "migrate_postgres",
]
