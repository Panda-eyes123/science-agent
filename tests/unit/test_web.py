import asyncio
import json

import httpx
import pytest

from science_agent import ModelResponse, ModelStreamEnd, ModelTextDelta, ToolCallRequest
from science_agent_web.models import TERMINAL
from science_agent_web.service import RunService, ServiceError

# Web 是可选安装项；仅安装 SDK 的环境继续运行原有核心测试。
create_app = pytest.importorskip(
    "science_agent_web.app", exc_type=ModuleNotFoundError
).create_app


class WriteProvider:
    async def complete(self, messages, **kwargs):
        raise AssertionError("Web must use streaming")

    async def stream(self, messages, **kwargs):
        if messages[-1].role == "user":
            yield ModelStreamEnd(
                response=ModelResponse(
                    tool_calls=[
                        ToolCallRequest(
                            name="fs_write",
                            call_id="write-file",
                            arguments={"path": "notes/test.md", "content": "研究记录"},
                        )
                    ]
                )
            )
        else:
            yield ModelTextDelta(text="文件")
            yield ModelTextDelta(text="已保存。")
            yield ModelStreamEnd(response=ModelResponse(text="文件已保存。"))


async def until(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0.005)


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["allow", "deny"])
async def test_http_approval_replay_and_history(tmp_path, decision):
    service = RunService(tmp_path, WriteProvider())
    app = create_app(service)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            assert (await client.get("/healthz")).json() == {"status": "ok"}
            thread = (await client.post("/api/v1/threads")).json()["id"]
            path = f"/api/v1/threads/{thread}"
            response = await client.post(f"{path}/runs", json={"text": "保存记录"})
            assert response.status_code == 202
            run_id = response.json()["id"]
            run_path = f"{path}/runs/{run_id}"
            run = service.runs[run_id]
            await until(lambda: run.status == "waiting_approval")
            assert (
                await client.post(f"{path}/runs", json={"text": "duplicate"})
            ).status_code == 409
            snapshot = (await client.get(run_path)).json()
            assert any(
                event["type"] == "approval.required" for event in snapshot["events"]
            )
            # 刷新只读取快照，不会丢失待审批回调，也不会产生第二次工具调用。
            assert (await client.get(path)).json()["active_run"]["id"] == run_id
            approval = f"{run_path}/approvals/write-file"
            assert (
                await client.post(approval, json={"decision": decision})
            ).status_code == 200
            assert (
                await client.post(approval, json={"decision": decision})
            ).status_code == 409
            await until(lambda: run.status in TERMINAL)
            assert run.status == ("succeeded" if decision == "allow" else "failed")
            assert (tmp_path / "workspaces" / thread / "notes/test.md").exists() == (
                decision == "allow"
            )
            stream = await client.get(f"{run_path}/events")
            events = [
                json.loads(line[6:])
                for line in stream.text.splitlines()
                if line.startswith("data: ")
            ]
            sequences = [event["seq"] for event in events]
            assert sequences == sorted(set(sequences))
            assert events[-1]["status"] == run.status
            after = sequences[1]
            resumed = await client.get(
                f"{run_path}/events", headers={"Last-Event-ID": str(after)}
            )
            assert all(
                int(line[4:]) > after
                for line in resumed.text.splitlines()
                if line.startswith("id: ")
            )
            assert "respond" not in stream.text
            if decision == "allow":
                assert (await client.get(path)).json()["messages"][-1][
                    "content"
                ] == "文件已保存。"


@pytest.mark.asyncio
async def test_live_subscription_cancel_and_restart(tmp_path):
    service = RunService(tmp_path, WriteProvider())
    await service.startup()
    thread = await service.create_thread()
    run = await service.start(thread.id, "write")
    await until(lambda: run.status == "waiting_approval")
    collected = []

    async def collect():
        async for event in service.events(thread.id, run.id, 0):
            if event is not None:
                collected.append(event)

    consumer = asyncio.create_task(collect())
    await until(lambda: bool(collected))
    await service.cancel(thread.id, run.id)
    await asyncio.wait_for(consumer, 3)
    assert run.status == "cancelled"
    assert collected[-1].status == "cancelled"
    assert not service.approvals
    with pytest.raises(ServiceError):
        await service.approve(thread.id, run.id, "write-file", "allow")
    # 模拟进程意外退出时遗留的非终态快照；启动仅标记中断，绝不重放写文件。
    row = run.model_dump(mode="json")
    row["status"] = "running"
    await service.store.save_snapshot(thread.id, f"run_{run.id}", row)
    await service.shutdown()
    restored = RunService(tmp_path, WriteProvider())
    await restored.startup()
    assert restored.runs[run.id].status == "interrupted"
    assert (await restored.thread(thread.id)).messages[0].content == "write"
    assert not (tmp_path / "workspaces" / thread.id / "notes/test.md").exists()
    assert (await restored.detail(thread.id, run.id)).events[-1].status == "interrupted"
    await restored.shutdown()
