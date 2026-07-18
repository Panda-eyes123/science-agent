"""Store protocol used by the runtime."""

from collections.abc import AsyncIterator
from typing import Any, Protocol

from science_agent.types import (
    AgentChannel,
    AgentEventEnvelope,
    AgentInfo,
    Message,
    ToolCallRecord,
)


class Store(Protocol):
    """Persistence contract used by the agent runtime.

    Event writes must be idempotent for identical ``(agent_id, seq)`` values and
    must raise ``EventSequenceConflictError`` when the stored content differs.
    Implementations should return events ordered by ascending sequence number.
    The runtime expects one active writer for each agent id; conflict detection
    is a safety boundary, not a distributed scheduling mechanism.
    """

    async def save_agent_state(
        self,
        agent_id: str,
        *,
        messages: list[Message],
        records: list[ToolCallRecord],
        info: AgentInfo,
        todos: list[dict],
    ) -> None: ...
    async def save_messages(self, agent_id: str, messages: list[Message]) -> None: ...
    async def load_messages(self, agent_id: str) -> list[Message]: ...
    async def save_tool_call_records(
        self, agent_id: str, records: list[ToolCallRecord]
    ) -> None: ...
    async def load_tool_call_records(self, agent_id: str) -> list[ToolCallRecord]: ...
    async def append_event(
        self, agent_id: str, envelope: AgentEventEnvelope
    ) -> None: ...
    def read_events(
        self,
        agent_id: str,
        *,
        since: int | None = None,
        channel: AgentChannel | None = None,
    ) -> AsyncIterator[AgentEventEnvelope]: ...
    async def last_event_seq(self, agent_id: str) -> int: ...
    async def save_info(self, agent_id: str, info: AgentInfo) -> None: ...
    async def load_info(self, agent_id: str) -> AgentInfo | None: ...
    async def save_todos(self, agent_id: str, todos: list[dict]) -> None: ...
    async def load_todos(self, agent_id: str) -> list[dict]: ...
    async def save_snapshot(
        self, agent_id: str, snapshot_id: str, snapshot: dict[str, Any]
    ) -> None: ...
    async def load_snapshot(
        self, agent_id: str, snapshot_id: str
    ) -> dict[str, Any] | None: ...
    async def list_snapshots(self, agent_id: str) -> list[str]: ...
    async def list(self, prefix: str | None = None) -> list[str]: ...
    async def delete(self, agent_id: str) -> None: ...
