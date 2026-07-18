"""Serialization shared by persistence implementations."""

from typing import Any

from pydantic import TypeAdapter

from science_agent.types import AgentEventEnvelope, AgentInfo, Message, ToolCallRecord

_AGENT_INFO_ADAPTER = TypeAdapter(AgentInfo)
_EVENT_ENVELOPE_ADAPTER = TypeAdapter(AgentEventEnvelope)
_MESSAGES_ADAPTER = TypeAdapter(list[Message])
_TOOL_CALL_RECORDS_ADAPTER = TypeAdapter(list[ToolCallRecord])


def dump_agent_info(info: AgentInfo) -> dict[str, Any]:
    return _AGENT_INFO_ADAPTER.dump_python(info, mode="json")


def load_agent_info(payload: Any) -> AgentInfo:
    return _AGENT_INFO_ADAPTER.validate_python(payload)


def dump_event(envelope: AgentEventEnvelope) -> dict[str, Any]:
    return _EVENT_ENVELOPE_ADAPTER.dump_python(envelope, mode="json")


def load_event(payload: Any) -> AgentEventEnvelope:
    return _EVENT_ENVELOPE_ADAPTER.validate_python(payload)


def load_event_json(payload: str) -> AgentEventEnvelope:
    return _EVENT_ENVELOPE_ADAPTER.validate_json(payload)


def dump_messages(messages: list[Message]) -> list[dict[str, Any]]:
    return _MESSAGES_ADAPTER.dump_python(messages, mode="json")


def load_messages(payload: Any) -> list[Message]:
    return _MESSAGES_ADAPTER.validate_python(payload)


def dump_tool_call_records(records: list[ToolCallRecord]) -> list[dict[str, Any]]:
    return _TOOL_CALL_RECORDS_ADAPTER.dump_python(records, mode="json")


def load_tool_call_records(payload: Any) -> list[ToolCallRecord]:
    return _TOOL_CALL_RECORDS_ADAPTER.validate_python(payload)
