"""Registry for runtime tools."""

from science_agent.errors import ToolExecutionError
from science_agent.tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ToolExecutionError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolExecutionError(f"Unknown tool: {name}") from exc

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def export_openai_tools(self, names: list[str]) -> list[dict]:
        return [self.get(name).to_openai_tool() for name in names]
