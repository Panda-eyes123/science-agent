"""Built-in file read tool."""

from science_agent.tools.base import Tool, ToolExecutionContext


def create_fs_read_tool() -> Tool:
    async def execute(arguments: dict, context: ToolExecutionContext) -> dict:
        path = arguments["path"]
        if context.sandbox is None:
            raise RuntimeError("Sandbox is not configured.")
        return {"path": path, "content": context.sandbox.read_text(path)}

    return Tool(
        name="fs_read",
        description="Read a UTF-8 text file from the sandbox workspace.",
        execute=execute,
        readonly=True,
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )
