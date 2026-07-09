"""Simple JSON file-backed persistence for local development."""

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from science_agent.config import DEFAULT_STORE_DIR
from science_agent.types import AgentEventEnvelope, AgentInfo, Message, ToolCallRecord

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
