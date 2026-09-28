"""Single-process run ownership. JSONStore remains the persistence boundary."""

import asyncio
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from uuid import uuid4

from science_agent import Agent, JSONStore, LocalSandbox, OpenAIProvider
from science_agent.infra.providers.base import ModelProvider
from science_agent.types import AgentEventEnvelope, utc_now_iso

from .adapter import create_agent, public_event
from .models import (
    TERMINAL,
    Run,
    RunDetail,
    RunEvent,
    RunStatus,
    ServiceInfo,
    ThreadDetail,
    ThreadSummary,
)


class ServiceError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status


class RunService:
    def __init__(self, data_dir: Path, provider: ModelProvider | None = None):
        self.store = JSONStore(data_dir / "store")
        self.workspace = data_dir / "workspaces"
        self.provider = provider if provider is not None else OpenAIProvider()
        self.agents: dict[str, Agent] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.runs: dict[str, Run] = {}
        self.approvals: dict[tuple[str, str], Callable[..., Awaitable[None]]] = {}
        self._lock = asyncio.Lock()

    def info(self) -> ServiceInfo:
        return ServiceInfo(
            model=getattr(self.provider, "model", "test-provider"),
            configured=not isinstance(self.provider, OpenAIProvider)
            or bool(self.provider.api_key),
        )

    async def startup(self) -> None:
        for thread_id in await self.store.list():
            for name in await self.store.list_snapshots(thread_id):
                if not name.startswith("run_"):
                    continue
                row = await self.store.load_snapshot(thread_id, name)
                run = Run.model_validate(row)
                self.runs[run.id] = run
                if run.status not in TERMINAL:
                    agent = await self.agent(thread_id)
                    agent.events.run_id = run.id
                    await self._state(
                        run, "interrupted", "服务已重启，本次运行未继续执行。"
                    )

    async def shutdown(self) -> None:
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def agent(self, thread_id: str) -> Agent:
        if thread_id not in self.agents:
            # JSONStore 是文件存储；只接受本服务生成且已经存在的 ID。
            if (
                not re.fullmatch(r"[a-f0-9]{32}", thread_id)
                or thread_id not in await self.store.list()
            ):
                raise ServiceError(404, "会话不存在。")
            self.agents[thread_id] = await create_agent(
                thread_id,
                self.store,
                LocalSandbox(self.workspace / thread_id),
                self.provider,
            )
        return self.agents[thread_id]

    async def create_thread(self) -> ThreadSummary:
        thread_id = uuid4().hex
        agent = await create_agent(
            thread_id,
            self.store,
            LocalSandbox(self.workspace / thread_id),
            self.provider,
        )
        self.agents[thread_id] = agent
        await self.store.save_info(thread_id, agent.info)
        return self._summary(agent)

    def _summary(self, agent: Agent) -> ThreadSummary:
        title = next(
            (
                message.content[:36]
                for message in agent.messages
                if message.role == "user"
            ),
            "新的探索",
        )
        return ThreadSummary(
            id=agent.agent_id, title=title, updated_at=agent.info.updated_at
        )

    async def threads(self) -> list[ThreadSummary]:
        result = [
            self._summary(await self.agent(thread))
            for thread in await self.store.list()
        ]
        return sorted(result, key=lambda item: item.updated_at, reverse=True)

    async def thread(self, thread_id: str) -> ThreadDetail:
        agent = await self.agent(thread_id)
        active = next(
            (
                run
                for run in self.runs.values()
                if run.thread_id == thread_id and run.status not in TERMINAL
            ),
            None,
        )
        return ThreadDetail(
            thread=self._summary(agent),
            messages=agent.messages,
            tool_calls=agent.tool_records,
            todos=agent.todo_service.list_items(),
            active_run=active,
        )

    async def history(self, thread_id: str) -> list[Run]:
        await self.agent(thread_id)
        return sorted(
            (run for run in self.runs.values() if run.thread_id == thread_id),
            key=lambda run: run.created_at,
            reverse=True,
        )

    def require_run(self, thread_id: str, run_id: str) -> Run:
        run = self.runs.get(run_id)
        if run is None or run.thread_id != thread_id:
            raise ServiceError(404, "运行不存在。")
        return run

    async def detail(self, thread_id: str, run_id: str) -> RunDetail:
        run = self.require_run(thread_id, run_id)
        events = []
        async for envelope in self.store.read_events(thread_id):
            if (
                envelope.run_id == run_id
                and (event := public_event(envelope)) is not None
            ):
                events.append(event)
        return RunDetail(run=run, events=events)

    async def start(self, thread_id: str, text: str) -> Run:
        if not text.strip():
            raise ServiceError(422, "消息不能为空。")
        if not self.info().configured:
            raise ServiceError(503, "尚未配置 OPENAI_API_KEY，请在服务端配置后重启。")
        async with self._lock:
            agent = await self.agent(thread_id)
            if any(
                run.thread_id == thread_id and run.status not in TERMINAL
                for run in self.runs.values()
            ):
                raise ServiceError(409, "当前会话仍在运行，请等待结束或停止后再发送。")
            run = Run(
                id=uuid4().hex,
                thread_id=thread_id,
                created_at=utc_now_iso(),
                updated_at=utc_now_iso(),
            )
            self.runs[run.id] = run
            agent.events.run_id = run.id
            await self._state(run, "running")
            ready = asyncio.Event()
            self.tasks[run.id] = asyncio.create_task(
                self._execute(run, agent, text.strip(), ready)
            )
            # 首条用户消息已被 SDK 接收后再返回，前端随后读取历史不会漏掉它。
            await ready.wait()
            return run

    async def _execute(
        self, run: Run, agent: Agent, text: str, ready: asyncio.Event
    ) -> None:
        work: asyncio.Task | None = None
        pending: asyncio.Task | None = None
        try:
            async with agent.events.listen(["progress", "control", "monitor"]) as queue:
                work = asyncio.create_task(agent.send(text, stream=True, run_id=run.id))
                # 同时观察执行任务和事件，避免模型提前报错时只等 done 而永久挂起。
                while True:
                    if work.done() and queue.empty():
                        break
                    pending = asyncio.create_task(queue.get())
                    done, _ = await asyncio.wait(
                        [pending, work], return_when=asyncio.FIRST_COMPLETED
                    )
                    if pending in done:
                        await self._handle(run, pending.result())
                        ready.set()
                    else:
                        pending.cancel()
                        await asyncio.gather(pending, return_exceptions=True)
                        break
                await work
            await self._state(run, "succeeded")
        except asyncio.CancelledError:
            if work is not None:
                work.cancel()
                await asyncio.gather(work, return_exceptions=True)
            user_cancel = run.status == "cancelling"
            await self._state(
                run,
                "cancelled" if user_cancel else "interrupted",
                None if user_cancel else "服务已停止，本次运行未继续执行。",
            )
        except Exception as exc:
            await self._state(run, "failed", str(exc))
        finally:
            if pending is not None and not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
            for key in list(self.approvals):
                if key[0] == run.id:
                    del self.approvals[key]
            ready.set()
            self.tasks.pop(run.id, None)

    async def _handle(self, run: Run, envelope: AgentEventEnvelope) -> None:
        event = envelope.event
        if event.get("type") == "permission_required":
            self.approvals[(run.id, event["call"]["id"])] = event["respond"]
            await self._state(run, "waiting_approval")
        elif event.get("type") == "permission_decided" and run.status != "cancelling":
            await self._state(run, "running")

    async def _state(
        self, run: Run, status: RunStatus, error: str | None = None
    ) -> None:
        run.status, run.error, run.updated_at = status, error, utc_now_iso()
        await self.store.save_snapshot(
            run.thread_id, f"run_{run.id}", run.model_dump(mode="json")
        )
        await self.agents[run.thread_id].events.emit_monitor(
            {"type": "web_state", "status": status, "error": error}
        )

    async def cancel(self, thread_id: str, run_id: str) -> Run:
        run = self.require_run(thread_id, run_id)
        if run.status not in TERMINAL and run.status != "cancelling":
            await self._state(run, "cancelling")
            self.tasks[run.id].cancel()
        return run

    async def approve(
        self, thread_id: str, run_id: str, call_id: str, decision: str
    ) -> Run:
        run = self.require_run(thread_id, run_id)
        if run.status != "waiting_approval":
            raise ServiceError(409, "本次运行已不在等待审批。")
        callback = self.approvals.pop((run_id, call_id), None)
        if callback is None:
            raise ServiceError(409, "此审批已处理或已失效。")
        await callback(decision)
        return run

    async def events(
        self, thread_id: str, run_id: str, after: int
    ) -> AsyncIterator[RunEvent | None]:
        run = self.require_run(thread_id, run_id)
        agent = await self.agent(thread_id)
        async with agent.events.listen(["progress", "control", "monitor"]) as queue:
            # 先注册实时订阅，再读磁盘；重叠事件用 seq 去重，无需另建事件缓存。
            async for envelope in self.store.read_events(thread_id, since=after):
                if envelope.run_id == run_id:
                    after = max(after, envelope.seq)
                    if (event := public_event(envelope)) is not None:
                        yield event
            if run.status in TERMINAL:
                return
            while True:
                try:
                    envelope = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield None
                    continue
                if envelope.run_id != run_id or envelope.seq <= after:
                    continue
                after = envelope.seq
                event = public_event(envelope)
                if event is not None:
                    yield event
                    if event.type == "run.state" and event.status in TERMINAL:
                        return
