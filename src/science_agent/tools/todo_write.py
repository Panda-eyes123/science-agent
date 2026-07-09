"""Built-in todo write tool."""

from dataclasses import asdict

from science_agent.tools.base import Tool, ToolExecutionContext


def create_todo_write_tool() -> Tool:
    async def execute(arguments: dict, context: ToolExecutionContext) -> dict:
        if context.agent is None:
            raise RuntimeError("Agent is not configured.")
        item = context.agent.todo_service.upsert(
            item_id=arguments["id"],
            content=arguments["content"],
            status=arguments.get("status", "pending"),
        )
        return {"item": asdict(item)}

    return Tool(
        name="todo_write",
        description="Create or update a todo item.",
        execute=execute,
        readonly=False,
        input_schema={
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "content": {"type": "string"},
                "status": {"type": "string"},
            },
            "required": ["id", "content"],
        },
    )
