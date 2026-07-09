"""Built-in todo read tool."""

from dataclasses import asdict

from science_agent.tools.base import Tool, ToolExecutionContext


def create_todo_read_tool() -> Tool:
    async def execute(arguments: dict, context: ToolExecutionContext) -> dict:
        if context.agent is None:
            raise RuntimeError("Agent is not configured.")
        return {
            "items": [asdict(item) for item in context.agent.todo_service.list_items()]
        }

    return Tool(
        name="todo_read",
        description="Read the current todo list.",
        execute=execute,
        readonly=True,
    )
