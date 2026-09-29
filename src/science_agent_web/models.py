"""The public web contract. OpenAPI is also the frontend's type source."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from science_agent.core.todo import TodoItem
from science_agent.rag.types import EvidenceView
from science_agent.types import Message, ToolCallRecord

RunStatus = Literal[
    "running",
    "waiting_approval",
    "cancelling",
    "succeeded",
    "failed",
    "cancelled",
    "interrupted",
]
TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}


class Run(BaseModel):
    id: str
    thread_id: str
    status: RunStatus = "running"
    created_at: str
    updated_at: str
    error: str | None = None


class EventBase(BaseModel):
    run_id: str
    seq: int
    timestamp: float


class TextEvent(EventBase):
    type: Literal["message.delta"] = "message.delta"
    message_id: str
    delta: str


class ToolEvent(EventBase):
    type: Literal["tool.started", "tool.completed", "tool.failed"]
    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    error: str | None = None
    evidence_pack: EvidenceView | None = None


class ApprovalEvent(EventBase):
    type: Literal["approval.required", "approval.resolved"]
    call_id: str
    name: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    decision: Literal["allow", "deny"] | None = None


class StateEvent(EventBase):
    type: Literal["run.state"] = "run.state"
    status: RunStatus
    error: str | None = None


RunEvent = Annotated[
    TextEvent | ToolEvent | ApprovalEvent | StateEvent,
    Field(discriminator="type"),
]


class RunDetail(BaseModel):
    run: Run
    events: list[RunEvent]


class ThreadSummary(BaseModel):
    id: str
    title: str
    updated_at: str


class RunEvidence(BaseModel):
    run_id: str
    call_id: str
    evidence_pack: EvidenceView


class ThreadDetail(BaseModel):
    thread: ThreadSummary
    messages: list[Message]
    tool_calls: list[ToolCallRecord]
    todos: list[TodoItem]
    active_run: Run | None
    evidence: list[RunEvidence] = Field(default_factory=list)


class SendMessage(BaseModel):
    text: str = Field(min_length=1, max_length=32000)


class ApprovalDecision(BaseModel):
    decision: Literal["allow", "deny"]


class ServiceInfo(BaseModel):
    model: str
    configured: bool
    rag_configured: bool = False


class PaperSummary(BaseModel):
    paper_id: str
    thread_id: str
    filename: str
    title: str | None = None
    status: Literal["indexing", "ready", "failed", "interrupted"]
    created_at: str
    updated_at: str
    error: str | None = None
