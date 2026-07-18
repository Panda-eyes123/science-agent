import asyncio

import pytest

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
from science_agent.types import AgentEventEnvelope


class EchoProvider:
    async def complete(self, messages, *, tools=None, system_prompt=None):
        return ModelResponse(text="ready")


class TodoProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages, *, tools=None, system_prompt=None):
        self.calls += 1
        if self.calls == 1:
            return ModelResponse(
                tool_calls=[
                    ToolCallRequest(
                        name="todo_write",
                        arguments={
                            "id": "task-1",
                            "content": "Draft hypothesis",
                            "status": "pending",
                        },
                    )
                ]
            )
        return ModelResponse(text="todo saved")


async def _collect_until_done(agent, bucket):
    async for envelope in agent.subscribe(["progress", "monitor"]):
        bucket.append(envelope)
        if envelope.event["type"] == "done":
            break


@pytest.mark.asyncio
async def test_agent_emits_text_and_done_events():
    templates = AgentTemplateRegistry()
    templates.register(
        AgentTemplateDefinition(id="science", system_prompt="Be concise.")
    )
    agent = await Agent.create(
        AgentConfig(
            template_id="science", model=EchoProvider(), tool_registry=ToolRegistry()
        ),
        templates,
    )
    events = []
    consumer = asyncio.create_task(_collect_until_done(agent, events))
    await asyncio.sleep(0)
    result = await agent.send("hello")
    await consumer
    assert result == "ready"
    assert any(item.event["type"] == "text_chunk" for item in events)
    assert any(item.event["type"] == "done" for item in events)


@pytest.mark.asyncio
async def test_agent_can_execute_builtin_todo_tool():
    templates = AgentTemplateRegistry()
    templates.register(
        AgentTemplateDefinition(
            id="science",
            system_prompt="Track tasks.",
            tools=["todo_write", "todo_read"],
        )
    )
    registry = register_builtin_tools(ToolRegistry())
    agent = await Agent.create(
        AgentConfig(
            template_id="science", model=TodoProvider(), tool_registry=registry
        ),
        templates,
    )
    result = await agent.send("track this")
    assert result == "todo saved"
    assert agent.todo_service.list_items()[0].content == "Draft hypothesis"


@pytest.mark.asyncio
async def test_json_store_round_trips_agent_state(tmp_path):
    templates = AgentTemplateRegistry()
    templates.register(
        AgentTemplateDefinition(id="science", system_prompt="Persist state.")
    )
    store = JSONStore(tmp_path)
    config = AgentConfig(
        template_id="science",
        model=EchoProvider(),
        store=store,
        tool_registry=ToolRegistry(),
        agent_id="persisted-agent",
    )

    agent = await Agent.create(config, templates)
    await agent.send("remember this")

    restored = await Agent.create(config, templates)
    assert [message.content for message in restored.messages] == [
        "remember this",
        "ready",
    ]
    assert restored.info.agent_id == "persisted-agent"


@pytest.mark.asyncio
async def test_restored_agent_continues_persisted_event_sequence(tmp_path):
    templates = AgentTemplateRegistry()
    templates.register(
        AgentTemplateDefinition(id="science", system_prompt="Persist events.")
    )
    store = JSONStore(tmp_path)
    await store.append_event(
        "event-agent",
        AgentEventEnvelope(
            seq=7,
            timestamp=1.0,
            channel="monitor",
            event={"type": "restored"},
        ),
    )
    agent = await Agent.create(
        AgentConfig(
            template_id="science",
            model=EchoProvider(),
            store=store,
            tool_registry=ToolRegistry(),
            agent_id="event-agent",
        ),
        templates,
    )

    await agent.send("continue")

    events = [event async for event in store.read_events("event-agent")]
    sequences = [event.seq for event in events]
    assert sequences[0] == 7
    assert sequences[1] == 8
    assert sequences == sorted(set(sequences))
