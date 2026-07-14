import asyncio

import pytest

from science_agent import (
    Agent,
    AgentConfig,
    AgentTemplateDefinition,
    AgentTemplateRegistry,
    JSONStore,
    LocalSandbox,
    ModelResponse,
    ToolCallRequest,
    ToolRegistry,
)
from science_agent.tools.base import ToolExecutionContext
from science_agent.tools.builtin import register_builtin_tools
from science_agent.types import AgentEventEnvelope, AgentInfo


class MissingToolProvider:
    async def complete(self, messages, *, tools=None, system_prompt=None):
        return ModelResponse(
            tool_calls=[ToolCallRequest(name="missing_tool", arguments={})]
        )


class InvalidToolArgsProvider:
    async def complete(self, messages, *, tools=None, system_prompt=None):
        return ModelResponse(
            tool_calls=[ToolCallRequest(name="fs_write", arguments={"path": "a.txt"})]
        )


async def _collect_until_done(agent, bucket):
    async for envelope in agent.subscribe(["progress", "monitor"]):
        bucket.append(envelope)
        if envelope.event["type"] == "done":
            break


@pytest.mark.asyncio
async def test_json_store_reads_filters_lists_and_deletes_events(tmp_path):
    store = JSONStore(tmp_path)
    agent_id = "agent-one"
    await store.save_info(
        agent_id,
        AgentInfo(agent_id=agent_id, template_id="science"),
    )
    await store.append_event(
        agent_id,
        AgentEventEnvelope(
            seq=1, timestamp=1.0, channel="progress", event={"type": "text_chunk"}
        ),
    )
    await store.append_event(
        agent_id,
        AgentEventEnvelope(
            seq=2, timestamp=2.0, channel="monitor", event={"type": "state_changed"}
        ),
    )

    progress_events = [
        event async for event in store.read_events(agent_id, channel="progress")
    ]
    since_events = [event async for event in store.read_events(agent_id, since=1)]

    assert [event.seq for event in progress_events] == [1]
    assert [event.seq for event in since_events] == [2]
    assert await store.list() == [agent_id]

    await store.delete(agent_id)
    assert await store.list() == []


@pytest.mark.asyncio
async def test_json_store_round_trips_snapshots(tmp_path):
    store = JSONStore(tmp_path)
    await store.save_snapshot("agent-one", "first", {"round": 1})

    assert await store.load_snapshot("agent-one", "first") == {"round": 1}
    assert await store.list_snapshots("agent-one") == ["first"]


@pytest.mark.asyncio
async def test_unknown_tool_emits_error_and_persists_record(tmp_path):
    templates = AgentTemplateRegistry()
    templates.register(AgentTemplateDefinition(id="science", system_prompt="Use tools."))
    store = JSONStore(tmp_path)
    agent = await Agent.create(
        AgentConfig(
            template_id="science",
            model=MissingToolProvider(),
            tool_registry=ToolRegistry(),
            store=store,
            agent_id="agent-with-error",
        ),
        templates,
    )
    events = []
    consumer = asyncio.create_task(_collect_until_done(agent, events))
    await asyncio.sleep(0)

    with pytest.raises(RuntimeError, match="Unknown tool"):
        await agent.send("try a tool")
    await consumer

    assert any(item.event["type"] == "tool:error" for item in events)
    assert any(item.event["type"] == "error" for item in events)
    records = await store.load_tool_call_records("agent-with-error")
    assert records[0].state == "FAILED"
    assert "Unknown tool" in (records[0].error or "")


@pytest.mark.asyncio
async def test_tool_argument_validation_emits_tool_error(tmp_path):
    templates = AgentTemplateRegistry()
    templates.register(
        AgentTemplateDefinition(
            id="science", system_prompt="Write files.", tools=["fs_write"]
        )
    )
    registry = register_builtin_tools(ToolRegistry())
    agent = await Agent.create(
        AgentConfig(
            template_id="science",
            model=InvalidToolArgsProvider(),
            tool_registry=registry,
            sandbox=LocalSandbox(tmp_path / "workspace"),
        ),
        templates,
    )
    events = []
    consumer = asyncio.create_task(_collect_until_done(agent, events))
    await asyncio.sleep(0)

    with pytest.raises(RuntimeError, match="missing required argument: content"):
        await agent.send("write a file")
    await consumer

    assert any(item.event["type"] == "tool:error" for item in events)


@pytest.mark.asyncio
async def test_sandbox_file_tools_enforce_boundaries(tmp_path):
    sandbox = LocalSandbox(tmp_path / "workspace")
    registry = register_builtin_tools(ToolRegistry())
    write_tool = registry.get("fs_write")
    read_tool = registry.get("fs_read")
    context = ToolExecutionContext(sandbox=sandbox)

    await write_tool.run({"path": "notes/result.txt", "content": "ok"}, context)
    result = await read_tool.run({"path": "notes/result.txt"}, context)

    assert result == {"path": "notes/result.txt", "content": "ok"}
    with pytest.raises(Exception, match="escapes sandbox"):
        await read_tool.run({"path": "..\\outside.txt"}, context)
