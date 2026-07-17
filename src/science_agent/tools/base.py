"""Tool primitives."""

import inspect
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from science_agent.errors import ToolExecutionError

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
        self.validate_arguments(arguments)
        result = self.execute(arguments, context)
        if inspect.isawaitable(result):
            return await result
        return result

    def validate_arguments(self, arguments: dict[str, Any]) -> None:
        if not isinstance(arguments, dict):
            raise ToolExecutionError(f"Tool '{self.name}' arguments must be an object.")
        required = self.input_schema.get("required", [])
        for key in required:
            if key not in arguments:
                raise ToolExecutionError(
                    f"Tool '{self.name}' missing required argument: {key}"
                )
        properties = self.input_schema.get("properties", {})
        for key, schema in properties.items():
            if key not in arguments:
                continue
            expected = schema.get("type")
            if expected and not _matches_json_type(arguments[key], expected):
                raise ToolExecutionError(
                    f"Tool '{self.name}' argument '{key}' must be {expected}."
                )
            allowed = schema.get("enum")
            if allowed is not None and arguments[key] not in allowed:
                raise ToolExecutionError(
                    f"Tool '{self.name}' argument '{key}' must be one of {allowed}."
                )

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


def _matches_json_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True
