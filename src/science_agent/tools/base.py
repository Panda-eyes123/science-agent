"""Tool primitives."""

import inspect
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from science_agent.core.agent import Agent
    from science_agent.infra.sandbox import LocalSandbox

ToolHandler = Callable[[dict[str, Any], "ToolExecutionContext"], Any | Awaitable[Any]]


@dataclass(slots=True)
class ToolExecutionContext:
    agent: "Agent | None" = None
    sandbox: "LocalSandbox | None" = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Tool:
    name: str
    description: str
    execute: ToolHandler
    readonly: bool = False
    input_schema: dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )

    async def run(
        self, arguments: dict[str, Any], context: ToolExecutionContext
    ) -> Any:
        result = self.execute(arguments, context)
        if inspect.isawaitable(result):
            return await result
        return result

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }
