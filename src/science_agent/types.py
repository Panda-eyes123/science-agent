"""Core data structures shared across the runtime."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

MessageRole = Literal["system", "user", "assistant", "tool"]
AgentChannel = Literal["progress", "control", "monitor"]
AgentRuntimeState = Literal["READY", "WORKING", "PAUSED"]
ToolCallState = Literal[
    "PENDING",
    "APPROVAL_REQUIRED",
    "APPROVED",
    "EXECUTING",
    "COMPLETED",
    "FAILED",
    "DENIED",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Message:
    role: MessageRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    id: str = field(default_factory=lambda: uuid4().hex)
    tool_calls: list["ToolCallRequest"] = field(default_factory=list)
    run_id: str | None = None


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
    run_id: str | None = None


class ModelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = ""
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)
    raw: dict[str, Any] | None = None


class ModelTextDelta(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    text: str


class ModelStreamEnd(BaseModel):
    type: Literal["end"] = "end"
    response: ModelResponse


ModelStreamEvent = ModelTextDelta | ModelStreamEnd


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
    run_id: str | None = None
