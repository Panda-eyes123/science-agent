"""Deterministic provider for testing the real Docker HTTP/SSE/approval path.

Only used when explicitly mounted into a separate acceptance API container.
"""
import asyncio
import os
from pathlib import Path

from science_agent import ModelResponse, ModelStreamEnd, ModelTextDelta, ToolCallRequest
from science_agent_web.app import create_app as web_app
from science_agent_web.service import RunService


class AcceptanceProvider:
    model = "docker-acceptance"

    async def stream(self, messages, **kwargs):
        if messages[-1].role == "user":
            yield ModelStreamEnd(response=ModelResponse(tool_calls=[
                ToolCallRequest(
                    name="fs_write", call_id="docker-write",
                    arguments={"path": "notes/docker.txt", "content": "docker-persistence-ok"},
                )
            ]))
        else:
            for text in ("Docker ", "验收通过。"):
                yield ModelTextDelta(text=text)
                await asyncio.sleep(0.5)
            yield ModelStreamEnd(response=ModelResponse(text="Docker 验收通过。"))


def create_app():
    # Upload validation must work without external credentials. Acceptance tests
    # only submit invalid/oversized PDFs, so no embedding request is performed.
    os.environ["EMBEDDING_API_KEY"] = "acceptance-unused"
    return web_app(RunService(Path(os.environ["SCIENCE_AGENT_DATA_DIR"]), AcceptanceProvider()))
