"""Opt-in HTTP checks against docker_fixture behind the actual Nginx image.

SCIENCE_AGENT_TEST_DOCKER_URL must point to an isolated acceptance deployment,
never the user's API. Mount its data volume read-only at /acceptance-data.
Run the persistence check separately after recreating the acceptance API.
"""
import json
import os
import time
from pathlib import Path

import httpx
import pytest

BASE_URL = os.getenv("SCIENCE_AGENT_TEST_DOCKER_URL")
pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not BASE_URL, reason="Docker acceptance only")]


async def test_proxy_sse_approval_and_upload_limits():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        assert (await client.get("/api/v1/info")).json()["model"] == "docker-acceptance"
        assert (await client.get("/")).status_code == 200
        thread = (await client.post("/api/v1/threads", json={})).json()["id"]
        path = f"/api/v1/threads/{thread}"
        started = await client.post(f"{path}/runs", json={"text": "Docker acceptance"})
        assert started.status_code == 202
        run_path = f'{path}/runs/{started.json()["id"]}'
        deltas, finished, approved = [], None, False
        async with client.stream("GET", f"{run_path}/events") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                if event["type"] == "approval.required":
                    decision = await client.post(
                        f'{run_path}/approvals/{event["call_id"]}', json={"decision": "allow"}
                    )
                    assert decision.status_code == 200
                    approved = True
                if "delta" in event:
                    deltas.append((event["delta"], time.monotonic()))
                if event["type"] == "run.state" and event["status"] in ("succeeded", "failed"):
                    assert event["status"] == "succeeded"
                    finished = time.monotonic()
        assert approved and len(deltas) == 2 and finished is not None
        assert finished - deltas[0][1] >= 0.7, "SSE was buffered until completion"
        assert "".join(delta for delta, _ in deltas) == "Docker 验收通过。"
        stored = Path("/acceptance-data/workspaces") / thread / "notes/docker.txt"
        assert stored.read_text() == "docker-persistence-ok"

        # Nginx's default 1 MiB limit must not reject a request intended for the API.
        invalid = await client.post(
            f"{path}/papers", files={"file": ("invalid.pdf", b"x" * (2 * 1024 * 1024))}
        )
        assert invalid.status_code == 415
        assert "detail" in invalid.json()
        too_large = await client.post(
            f"{path}/papers",
            files={"file": ("large.pdf", b"%PDF-" + b"x" * (51 * 1024 * 1024))},
        )
        assert too_large.status_code == 413
        assert "50 MB" in too_large.json()["detail"]


@pytest.mark.skipif(
    os.getenv("SCIENCE_AGENT_TEST_DOCKER_RECREATED") != "1", reason="Run after API recreation"
)
async def test_persistence_after_container_recreation():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        assert (await client.get("/api/v1/info")).json()["model"] == "docker-acceptance"
        threads = (await client.get("/api/v1/threads")).json()
        assert len(threads) == 1
        thread = threads[0]["id"]
        detail = (await client.get(f"/api/v1/threads/{thread}")).json()
        assert detail["messages"][-1]["content"] == "Docker 验收通过。"
        assert detail["active_run"] is None
        stored = Path("/acceptance-data/workspaces") / thread / "notes/docker.txt"
        assert stored.read_text() == "docker-persistence-ok"
