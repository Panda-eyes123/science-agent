"""Thin HTTP routes; lifecycle decisions belong to RunService."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, Header, Query, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from science_agent.config import DEFAULT_DATA_DIR

from .models import (
    ApprovalDecision,
    PaperSummary,
    Run,
    RunDetail,
    SendMessage,
    ServiceInfo,
    ThreadDetail,
    ThreadSummary,
)
from .service import RunService, ServiceError


def create_app(service: RunService | None = None) -> FastAPI:
    load_dotenv()
    runtime = service or RunService(
        Path(os.getenv("SCIENCE_AGENT_DATA_DIR", DEFAULT_DATA_DIR))
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await runtime.startup()
        yield
        await runtime.shutdown()

    app = FastAPI(title="Science Agent Local API", version="0.1.0", lifespan=lifespan)
    app.state.runtime = runtime

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError):
        return JSONResponse(status_code=exc.status, content={"detail": str(exc)})

    @app.get("/api/v1/info", response_model=ServiceInfo)
    async def info():
        return runtime.info()

    @app.get("/api/v1/threads", response_model=list[ThreadSummary])
    async def threads():
        return await runtime.threads()

    @app.post("/api/v1/threads", response_model=ThreadSummary, status_code=201)
    async def create_thread():
        return await runtime.create_thread()

    @app.get("/api/v1/papers", response_model=list[PaperSummary])
    async def papers():
        return runtime.papers.list()

    @app.post(
        "/api/v1/threads/{thread_id}/papers",
        response_model=PaperSummary,
        status_code=202,
    )
    async def upload_paper(thread_id: str, file: UploadFile):
        try:
            await runtime.agent(thread_id)

            async def chunks():
                while chunk := await file.read(1024 * 1024):
                    yield chunk

            return await runtime.papers.upload(thread_id, file.filename or "", chunks())
        finally:
            await file.close()

    @app.get("/api/v1/threads/{thread_id}", response_model=ThreadDetail)
    async def thread(thread_id: str):
        return await runtime.thread(thread_id)

    @app.post("/api/v1/threads/{thread_id}/runs", response_model=Run, status_code=202)
    async def start(thread_id: str, body: SendMessage):
        return await runtime.start(thread_id, body.text)

    @app.get("/api/v1/threads/{thread_id}/runs", response_model=list[Run])
    async def runs(thread_id: str):
        return await runtime.history(thread_id)

    @app.get("/api/v1/threads/{thread_id}/runs/{run_id}", response_model=RunDetail)
    async def run(thread_id: str, run_id: str):
        return await runtime.detail(thread_id, run_id)

    @app.get("/api/v1/threads/{thread_id}/runs/{run_id}/events")
    async def events(
        thread_id: str,
        run_id: str,
        after: Annotated[int, Query(ge=0)] = 0,
        last_event_id: Annotated[int | None, Header(ge=0)] = None,
    ):
        runtime.require_run(thread_id, run_id)

        async def stream():
            async for event in runtime.events(
                thread_id, run_id, max(after, last_event_id or 0)
            ):
                if event is None:
                    yield ": heartbeat\n\n"
                else:
                    yield f"id: {event.seq}\ndata: {event.model_dump_json()}\n\n"

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/v1/threads/{thread_id}/runs/{run_id}/cancel", response_model=Run)
    async def cancel(thread_id: str, run_id: str):
        return await runtime.cancel(thread_id, run_id)

    @app.post(
        "/api/v1/threads/{thread_id}/runs/{run_id}/approvals/{call_id}",
        response_model=Run,
    )
    async def approve(
        thread_id: str, run_id: str, call_id: str, body: ApprovalDecision
    ):
        return await runtime.approve(thread_id, run_id, call_id, body.decision)

    return app
