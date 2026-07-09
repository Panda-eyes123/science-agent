"""Registry for runtime tools."""

from science_agent.tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def export_openai_tools(self, names: list[str]) -> list[dict]:
        return [
            self._tools[name].to_openai_tool() for name in names if name in self._tools
        ]
