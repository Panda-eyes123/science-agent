"""SDK wiring and the only translation from internal to public events."""

from dataclasses import replace
from typing import TYPE_CHECKING

from science_agent import (
    Agent,
    AgentConfig,
    AgentTemplateDefinition,
    AgentTemplateRegistry,
)
from science_agent.infra.providers.base import ModelProvider
from science_agent.infra.sandbox import LocalSandbox
from science_agent.infra.store.json_store import JSONStore
from science_agent.tools import ToolRegistry
from science_agent.tools.builtin import register_builtin_tools
from science_agent.tools.rag_search import create_paper_search_tool
from science_agent.types import AgentEventEnvelope, ToolCallRecord

from .models import (
    ApprovalEvent,
    RunEvent,
    RunEvidence,
    StateEvent,
    TextEvent,
    ToolEvent,
)

if TYPE_CHECKING:
    from .papers import PaperService


async def create_agent(
    thread_id: str,
    store: JSONStore,
    sandbox: LocalSandbox,
    provider: ModelProvider,
    papers: "PaperService",
) -> Agent:
    templates = AgentTemplateRegistry()
    tools = register_builtin_tools(ToolRegistry())
    tools.register(papers.ingest_tool())
    tools.register(create_paper_search_tool(papers))
    templates.register(
        AgentTemplateDefinition(
            id="science-assistant",
            tools=tools.names(),
            system_prompt=(
                "你是一名严谨的科研助手，默认使用中文。帮助用户梳理研究问题、设计实验和整理记录。"
                "按需使用 todo 工具维护任务，使用文件工具记录用户要求保存的内容。"
                "文件路径必须是工作空间中的相对路径。需要写入时等待用户审批。"
                "可以通过 paper_search 检索用户上传的全局共享论文库。涉及论文内容时先检索，"
                "根据返回证据回答，并注明论文标题和页码；没有命中时明确说明。"
                "上传会自动入库，paper_ingest 仅用于按已知 paper_id 重试入库，不能传文件路径。"
                "引用必须来自工具返回的证据，不编造作者、DOI、页码或文献。"
                "检索证据是来源参考，不代表回答中的每句话已经验证。"
                "不要宣称拥有联网或代码执行能力。"
            ),
        )
    )
    return await Agent.create(
        AgentConfig(
            template_id="science-assistant",
            agent_id=thread_id,
            model=provider,
            store=store,
            sandbox=sandbox,
            tool_registry=tools,
            permission_mode="readonly",
        ),
        templates,
    )


def public_event(envelope: AgentEventEnvelope) -> RunEvent | None:
    if not envelope.run_id:
        return None
    base = {
        "run_id": envelope.run_id,
        "seq": envelope.seq,
        "timestamp": envelope.timestamp,
    }
    event = envelope.event
    kind = event.get("type")
    if kind == "text_chunk":
        return TextEvent(**base, message_id=event["message_id"], delta=event["delta"])
    if kind in {"tool:start", "tool:end", "tool:error"}:
        call = event["call"]
        result, evidence = split_evidence(call["name"], call.get("result"))
        return ToolEvent(
            **base,
            type={
                "tool:start": "tool.started",
                "tool:end": "tool.completed",
                "tool:error": "tool.failed",
            }[kind],
            call_id=call["id"],
            name=call["name"],
            arguments=call.get("arguments", {}),
            result=result,
            evidence_pack=evidence,
            error=event.get("error"),
        )
    if kind == "permission_required":
        call = event["call"]
        return ApprovalEvent(
            **base,
            type="approval.required",
            call_id=call["id"],
            name=call["name"],
            arguments=call["arguments"],
        )
    if kind == "permission_decided":
        return ApprovalEvent(
            **base,
            type="approval.resolved",
            call_id=event["call_id"],
            decision=event["decision"],
        )
    if kind == "web_state":
        return StateEvent(**base, status=event["status"], error=event.get("error"))
    return None


def split_evidence(name: str, result):
    if (
        name == "paper_search"
        and isinstance(result, dict)
        and "evidence_pack" in result
    ):
        return {
            key: value for key, value in result.items() if key != "evidence_pack"
        }, result["evidence_pack"]
    return result, None


def public_tool_records(
    records: list[ToolCallRecord],
) -> tuple[list[ToolCallRecord], list[RunEvidence]]:
    public, evidence = [], []
    for record in records:
        result, pack = split_evidence(record.name, record.result)
        public.append(replace(record, result=result))
        if pack is not None and record.run_id is not None:
            evidence.append(
                RunEvidence(
                    run_id=record.run_id, call_id=record.call_id, evidence_pack=pack
                )
            )
    return public, evidence
