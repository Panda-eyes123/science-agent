"""Built-in file write tool."""

from science_agent.tools.base import Tool, ToolExecutionContext


def create_fs_write_tool() -> Tool:
    async def execute(arguments: dict, context: ToolExecutionContext) -> dict:
        path = arguments["path"]
        content = arguments["content"]
        if context.sandbox is None:
            raise RuntimeError("Sandbox is not configured.")
        context.sandbox.write_text(path, content)
        return {"path": path, "written": True}

    return Tool(
        name="fs_write",
        description="Write a UTF-8 text file inside the sandbox workspace.",
        execute=execute,
        readonly=False,
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    )
