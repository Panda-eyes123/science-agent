"""Core data structures shared across the runtime."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MessageRole = Literal["system", "user", "assistant", "tool"]
AgentChannel = Literal["progress", "control", "monitor"]
AgentRuntimeState = Literal["READY", "WORKING", "PAUSED"]
ToolCallState = Literal["PENDING", "EXECUTING", "COMPLETED", "FAILED", "DENIED"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Message:
    role: MessageRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None


class ToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = None


@dataclass(slots=True)
class ToolCallRecord:
    call_id: str
    name: str
    arguments: dict[str, Any]
    state: ToolCallState
    result: Any | None = None
    error: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


class ModelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = ""
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class AgentInfo:
    agent_id: str
    template_id: str
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    state: AgentRuntimeState = "READY"


@dataclass(slots=True)
class AgentEventEnvelope:
    seq: int
    timestamp: float
    channel: AgentChannel
    event: dict[str, Any]
