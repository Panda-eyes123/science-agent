"""Reusable behavioral contract for Store implementations."""

import pytest

from science_agent.infra.store.errors import EventSequenceConflictError
from science_agent.types import (
    AgentEventEnvelope,
    AgentInfo,
    Message,
    ToolCallRecord,
)


async def assert_store_contract(store, agent_id: str) -> None:
    """Exercise every Store method against one isolated agent id."""
    assert await store.load_messages(agent_id) == []
    assert await store.load_tool_call_records(agent_id) == []
    assert await store.load_info(agent_id) is None
    assert await store.load_todos(agent_id) == []
    assert await store.load_snapshot(agent_id, "missing") is None
    assert agent_id not in await store.list(prefix=agent_id)

    messages = [Message(role="user", content="persist this")]
    records = [
        ToolCallRecord(
            call_id="call-1",
            name="paper_search",
            arguments={"query": "controls"},
            state="COMPLETED",
            result={"hits": 2},
        )
    ]
    info = AgentInfo(agent_id=agent_id, template_id="science")
    todos = [{"id": "todo-1", "content": "Review evidence", "status": "pending"}]
    await store.save_agent_state(
        agent_id,
        messages=messages,
        records=records,
        info=info,
        todos=todos,
    )

    assert await store.load_messages(agent_id) == messages
    assert await store.load_tool_call_records(agent_id) == records
    assert await store.load_info(agent_id) == info
    assert await store.load_todos(agent_id) == todos

    replacement_messages = [Message(role="assistant", content="updated")]
    await store.save_messages(agent_id, replacement_messages)
    await store.save_tool_call_records(agent_id, [])
    await store.save_todos(agent_id, [])
    assert await store.load_messages(agent_id) == replacement_messages
    assert await store.load_tool_call_records(agent_id) == []
    assert await store.load_todos(agent_id) == []

    progress = AgentEventEnvelope(
        seq=1,
        timestamp=1.0,
        channel="progress",
        event={"type": "text_chunk", "delta": "result"},
    )
    monitor = AgentEventEnvelope(
        seq=2,
        timestamp=2.0,
        channel="monitor",
        event={"type": "state_changed", "state": "READY"},
    )
    await store.append_event(agent_id, progress)
    await store.append_event(agent_id, progress)
    await store.append_event(agent_id, monitor)

    events = [event async for event in store.read_events(agent_id)]
    progress_events = [
        event async for event in store.read_events(agent_id, channel="progress")
    ]
    since_events = [event async for event in store.read_events(agent_id, since=1)]
    assert events == [progress, monitor]
    assert progress_events == [progress]
    assert since_events == [monitor]
    assert await store.last_event_seq(agent_id) == 2

    with pytest.raises(EventSequenceConflictError):
        await store.append_event(
            agent_id,
            AgentEventEnvelope(
                seq=1,
                timestamp=1.0,
                channel="progress",
                event={"type": "text_chunk", "delta": "different"},
            ),
        )

    await store.save_snapshot(agent_id, "second", {"round": 2})
    await store.save_snapshot(agent_id, "first", {"round": 1})
    await store.save_snapshot(agent_id, "first", {"round": 3})
    assert await store.load_snapshot(agent_id, "first") == {"round": 3}
    assert await store.list_snapshots(agent_id) == ["first", "second"]
    assert agent_id in await store.list(prefix=agent_id[:-1])

    await store.delete(agent_id)
    assert agent_id not in await store.list(prefix=agent_id)
    assert await store.load_messages(agent_id) == []
    assert [event async for event in store.read_events(agent_id)] == []
    assert await store.list_snapshots(agent_id) == []
