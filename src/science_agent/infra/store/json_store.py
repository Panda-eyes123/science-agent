"""Simple JSON file-backed persistence for local development."""

import json
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from science_agent.config import DEFAULT_STORE_DIR
from science_agent.infra.store.errors import EventSequenceConflictError
from science_agent.infra.store.serialization import (
    dump_agent_info,
    dump_event,
    dump_messages,
    dump_tool_call_records,
    load_agent_info,
    load_event_json,
    load_messages,
    load_tool_call_records,
)
from science_agent.types import (
    AgentChannel,
    AgentEventEnvelope,
    AgentInfo,
    Message,
    ToolCallRecord,
)


class JSONStore:
    def __init__(self, base_dir: str | Path = DEFAULT_STORE_DIR) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _agent_dir(self, agent_id: str) -> Path:
        return self.base_dir / agent_id

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    async def save_agent_state(
        self,
        agent_id: str,
        *,
        messages: list[Message],
        records: list[ToolCallRecord],
        info: AgentInfo,
        todos: list[dict],
    ) -> None:
        """Preserve the Store contract for local development.

        PostgreSQL commits this operation atomically. JSONStore remains a
        compatibility implementation and can only replace its files one by one.
        """
        await self.save_messages(agent_id, messages)
        await self.save_tool_call_records(agent_id, records)
        await self.save_info(agent_id, info)
        await self.save_todos(agent_id, todos)

    async def save_messages(self, agent_id: str, messages: list[Message]) -> None:
        payload = dump_messages(messages)
        self._write_json(self._agent_dir(agent_id) / "messages.json", payload)

    async def load_messages(self, agent_id: str) -> list[Message]:
        rows = self._read_json(self._agent_dir(agent_id) / "messages.json", [])
        return load_messages(rows)

    async def save_tool_call_records(
        self, agent_id: str, records: list[ToolCallRecord]
    ) -> None:
        payload = dump_tool_call_records(records)
        self._write_json(self._agent_dir(agent_id) / "tool_calls.json", payload)

    async def load_tool_call_records(self, agent_id: str) -> list[ToolCallRecord]:
        rows = self._read_json(self._agent_dir(agent_id) / "tool_calls.json", [])
        return load_tool_call_records(rows)

    async def append_event(self, agent_id: str, envelope: AgentEventEnvelope) -> None:
        path = self._agent_dir(agent_id) / "events.jsonl"
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    stored = load_event_json(line)
                    if stored.seq != envelope.seq:
                        continue
                    if stored == envelope:
                        return
                    raise EventSequenceConflictError(
                        f"Event sequence {envelope.seq} for agent {agent_id!r} "
                        "already contains different content."
                    )
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            payload = dump_event(envelope)
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    async def read_events(
        self,
        agent_id: str,
        *,
        since: int | None = None,
        channel: AgentChannel | None = None,
    ) -> AsyncIterator[AgentEventEnvelope]:
        path = self._agent_dir(agent_id) / "events.jsonl"
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                envelope = load_event_json(line)
                if since is not None and envelope.seq <= since:
                    continue
                if channel is not None and envelope.channel != channel:
                    continue
                yield envelope

    async def last_event_seq(self, agent_id: str) -> int:
        last_seq = 0
        async for envelope in self.read_events(agent_id):
            last_seq = max(last_seq, envelope.seq)
        return last_seq

    async def save_info(self, agent_id: str, info: AgentInfo) -> None:
        payload = dump_agent_info(info)
        self._write_json(self._agent_dir(agent_id) / "info.json", payload)

    async def load_info(self, agent_id: str) -> AgentInfo | None:
        row = self._read_json(self._agent_dir(agent_id) / "info.json", None)
        return load_agent_info(row) if row else None

    async def save_todos(self, agent_id: str, todos: list[dict]) -> None:
        self._write_json(self._agent_dir(agent_id) / "todos.json", todos)

    async def load_todos(self, agent_id: str) -> list[dict]:
        return self._read_json(self._agent_dir(agent_id) / "todos.json", [])

    async def save_snapshot(
        self, agent_id: str, snapshot_id: str, snapshot: dict[str, Any]
    ) -> None:
        self._write_json(
            self._agent_dir(agent_id) / "snapshots" / f"{snapshot_id}.json", snapshot
        )

    async def load_snapshot(
        self, agent_id: str, snapshot_id: str
    ) -> dict[str, Any] | None:
        return self._read_json(
            self._agent_dir(agent_id) / "snapshots" / f"{snapshot_id}.json", None
        )

    async def list_snapshots(self, agent_id: str) -> list[str]:
        path = self._agent_dir(agent_id) / "snapshots"
        if not path.exists():
            return []
        return sorted(item.stem for item in path.glob("*.json") if item.is_file())

    async def list(self, prefix: str | None = None) -> list[str]:
        if not self.base_dir.exists():
            return []
        agent_ids = sorted(
            item.name for item in self.base_dir.iterdir() if item.is_dir()
        )
        if prefix is None:
            return agent_ids
        return [agent_id for agent_id in agent_ids if agent_id.startswith(prefix)]

    async def delete(self, agent_id: str) -> None:
        path = self.base_dir / agent_id
        if path.exists():
            shutil.rmtree(path)
