"""Example showing a model response that triggers a built-in tool."""

import asyncio

from science_agent import (
    Agent,
    AgentConfig,
    AgentTemplateDefinition,
    AgentTemplateRegistry,
    JSONStore,
    ModelResponse,
    ToolCallRequest,
    ToolRegistry,
)
from science_agent.tools.builtin import register_builtin_tools


class TodoDemoProvider:
    def __init__(self) -> None:
        self._step = 0

    async def complete(self, messages, *, tools=None, system_prompt=None):
        self._step += 1
        if self._step == 1:
            return ModelResponse(
                tool_calls=[
                    ToolCallRequest(
                        name="todo_write",
                        arguments={
                            "id": "lit-review",
                            "content": "Read three papers on CRISPR delivery.",
                            "status": "in_progress",
                        },
                    )
                ]
            )
        return ModelResponse(
            text="Todo item created. You can now continue the literature review."
        )


async def main() -> None:
    templates = AgentTemplateRegistry()
    templates.register(
        AgentTemplateDefinition(
            id="science-assistant",
            system_prompt="You plan and track science workflows.",
            tools=["todo_write", "todo_read"],
        )
    )
    registry = register_builtin_tools(ToolRegistry())
    agent = await Agent.create(
        AgentConfig(
            template_id="science-assistant",
            model=TodoDemoProvider(),
            tool_registry=registry,
            store=JSONStore(".demo_store"),
        ),
        templates,
    )
    print(await agent.send("Track my next literature review task."))
    print(agent.todo_service.snapshot())


if __name__ == "__main__":
    asyncio.run(main())
