"""Convenience registration for the built-in tool set."""

from science_agent.tools.fs_read import create_fs_read_tool
from science_agent.tools.fs_write import create_fs_write_tool
from science_agent.tools.registry import ToolRegistry
from science_agent.tools.todo_read import create_todo_read_tool
from science_agent.tools.todo_write import create_todo_write_tool


def register_builtin_tools(registry: ToolRegistry) -> ToolRegistry:
    registry.register(create_fs_read_tool())
    registry.register(create_fs_write_tool())
    registry.register(create_todo_read_tool())
    registry.register(create_todo_write_tool())
    return registry
