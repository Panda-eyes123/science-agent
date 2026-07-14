"""Simple JSON file-backed persistence for local development."""

import json
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from science_agent.config import DEFAULT_STORE_DIR
from science_agent.types import AgentChannel, AgentEventEnvelope, AgentInfo, Message, ToolCallRecord

_AGENT_INFO_ADAPTER = TypeAdapter(AgentInfo)
_EVENT_ENVELOPE_ADAPTER = TypeAdapter(AgentEventEnvelope)
_MESSAGES_ADAPTER = TypeAdapter(list[Message])
_TOOL_CALL_RECORDS_ADAPTER = TypeAdapter(list[ToolCallRecord])


class JSONStore:
    def __init__(self, base_dir: str | Path = DEFAULT_STORE_DIR) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _agent_dir(self, agent_id: str) -> Path:
        path = self.base_dir / agent_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    async def save_messages(self, agent_id: str, messages: list[Message]) -> None:
        payload = _MESSAGES_ADAPTER.dump_python(messages, mode="json")
        self._write_json(self._agent_dir(agent_id) / "messages.json", payload)

    async def load_messages(self, agent_id: str) -> list[Message]:
        rows = self._read_json(self._agent_dir(agent_id) / "messages.json", [])
        return _MESSAGES_ADAPTER.validate_python(rows)

    async def save_tool_call_records(
        self, agent_id: str, records: list[ToolCallRecord]
    ) -> None:
        payload = _TOOL_CALL_RECORDS_ADAPTER.dump_python(records, mode="json")
        self._write_json(self._agent_dir(agent_id) / "tool_calls.json", payload)

    async def load_tool_call_records(self, agent_id: str) -> list[ToolCallRecord]:
        rows = self._read_json(self._agent_dir(agent_id) / "tool_calls.json", [])
        return _TOOL_CALL_RECORDS_ADAPTER.validate_python(rows)

    async def append_event(self, agent_id: str, envelope: AgentEventEnvelope) -> None:
        path = self._agent_dir(agent_id) / "events.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            payload = _EVENT_ENVELOPE_ADAPTER.dump_python(envelope, mode="json")
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
                envelope = _EVENT_ENVELOPE_ADAPTER.validate_json(line)
                if since is not None and envelope.seq <= since:
                    continue
                if channel is not None and envelope.channel != channel:
                    continue
                yield envelope

    async def save_info(self, agent_id: str, info: AgentInfo) -> None:
        payload = _AGENT_INFO_ADAPTER.dump_python(info, mode="json")
        self._write_json(self._agent_dir(agent_id) / "info.json", payload)

    async def load_info(self, agent_id: str) -> AgentInfo | None:
        row = self._read_json(self._agent_dir(agent_id) / "info.json", None)
        return _AGENT_INFO_ADAPTER.validate_python(row) if row else None

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
        agent_ids = sorted(item.name for item in self.base_dir.iterdir() if item.is_dir())
        if prefix is None:
            return agent_ids
        return [agent_id for agent_id in agent_ids if agent_id.startswith(prefix)]

    async def delete(self, agent_id: str) -> None:
        path = self.base_dir / agent_id
        if path.exists():
            shutil.rmtree(path)
