"""Decorator helper for defining tools."""

from collections.abc import Callable
from typing import Any

from science_agent.tools.base import Tool


def tool(
    name: str,
    description: str,
    *,
    readonly: bool = False,
    input_schema: dict[str, Any] | None = None,
) -> Callable:
    def decorator(func: Callable) -> Tool:
        return Tool(
            name=name,
            description=description,
            execute=func,
            readonly=readonly,
            input_schema=input_schema or {"type": "object", "properties": {}},
        )

    return decorator
