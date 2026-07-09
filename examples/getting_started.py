"""Minimal runnable example without external API calls."""

import asyncio

from science_agent import (
    Agent,
    AgentConfig,
    AgentTemplateDefinition,
    AgentTemplateRegistry,
    ModelResponse,
    ToolRegistry,
)


class EchoProvider:
    async def complete(self, messages, *, tools=None, system_prompt=None):
        last_user = next(
            message.content for message in reversed(messages) if message.role == "user"
        )
        return ModelResponse(text=f"Science agent received: {last_user}")


async def main() -> None:
    templates = AgentTemplateRegistry()
    templates.register(
        AgentTemplateDefinition(
            id="science-assistant",
            system_prompt="You are a concise scientific research assistant.",
        )
    )
    agent = await Agent.create(
        AgentConfig(
            template_id="science-assistant",
            model=EchoProvider(),
            tool_registry=ToolRegistry(),
        ),
        templates,
    )

    async def consume() -> None:
        async for envelope in agent.subscribe(["progress"]):
            print(envelope.event)
            if envelope.event["type"] == "done":
                break

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0)
    await agent.send("Summarize the role of controls in a simple experiment.")
    await consumer


if __name__ == "__main__":
    asyncio.run(main())
