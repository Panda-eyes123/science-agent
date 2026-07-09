"""Public package exports for the phase-one SDK skeleton."""

from .core.agent import Agent, AgentConfig
from .core.template import AgentTemplateDefinition, AgentTemplateRegistry
from .core.todo import TodoItem, TodoService
from .infra.providers.base import ModelProvider
from .infra.sandbox import LocalSandbox, SandboxResult
from .infra.store.json_store import JSONStore
from .tools.base import Tool, ToolExecutionContext
from .tools.registry import ToolRegistry
from .types import ModelResponse, ToolCallRequest

try:
    from .infra.providers.openai import OpenAIProvider
except ModuleNotFoundError as exc:  # pragma: no cover

    class OpenAIProvider:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            raise ModuleNotFoundError(
                "OpenAIProvider requires the optional dependency 'httpx'. Install project dependencies first."
            ) from exc


__all__ = [
    "Agent",
    "AgentConfig",
    "AgentTemplateDefinition",
    "AgentTemplateRegistry",
    "JSONStore",
    "LocalSandbox",
    "ModelProvider",
    "ModelResponse",
    "OpenAIProvider",
    "SandboxResult",
    "TodoItem",
    "TodoService",
    "Tool",
    "ToolCallRequest",
    "ToolExecutionContext",
    "ToolRegistry",
]
