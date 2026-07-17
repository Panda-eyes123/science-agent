"""OpenAI-compatible vision adapter for structured figure analysis."""

import asyncio
import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

import httpx

from science_agent.rag.multimodal.types import (
    VLMObservation,
    VLMResponse,
    VisualAsset,
)

_SYSTEM_PROMPT = """You analyze figures, tables, formulas, and plots from scientific papers.
Answer only from the supplied images and context. Return a JSON object with:
answer: string; observations: an array of objects containing element_id, summary,
key_values (array of strings), and confidence (number from 0 to 1 or null).
Do not invent unreadable labels or values."""


class OpenAIVisionProvider:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 90.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("VLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("VLM_MODEL") or "gpt-4.1-mini"
        self.base_url = (
            base_url
            or os.getenv("VLM_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        self.timeout = timeout
        self.transport = transport

    async def analyze(self, query: str, assets: list[VisualAsset]) -> VLMResponse:
        if not self.api_key:
            raise ValueError("VLM API key is not set. Set VLM_API_KEY or OPENAI_API_KEY.")
        if not assets:
            return VLMResponse(answer="No visual evidence was supplied.")
        content: list[dict[str, Any]] = [
            {"type": "text", "text": f"Research question: {query}"}
        ]
        asset_blocks = await asyncio.gather(
            *(asyncio.to_thread(self._asset_content, asset) for asset in assets)
        )
        for blocks in asset_blocks:
            content.extend(blocks)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(
            timeout=self.timeout, transport=self.transport
        ) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if response.status_code >= 400:
            raise ValueError(
                f"VLM request failed: {response.status_code} {response.text}"
            )
        raw = response.json()
        try:
            content_text = raw["choices"][0]["message"]["content"]
            parsed = json.loads(self._strip_json_fence(content_text))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("VLM response did not contain valid structured JSON.") from exc
        observations = [
            VLMObservation(
                element_id=str(item.get("element_id", "")),
                summary=str(item.get("summary", "")),
                key_values=[str(value) for value in item.get("key_values", [])],
                confidence=self._confidence(item.get("confidence")),
            )
            for item in parsed.get("observations", [])
            if isinstance(item, dict)
        ]
        return VLMResponse(
            answer=str(parsed.get("answer", "")),
            observations=observations,
            raw=raw,
        )

    @staticmethod
    def _asset_content(asset: VisualAsset) -> list[dict[str, Any]]:
        description = (
            f"element_id={asset.element_id}\n"
            f"paper_id={asset.paper_id}\n"
            f"page={asset.page_no}\n"
            f"caption={asset.caption}\n"
            f"surrounding_context={asset.context}"
        )
        path = Path(asset.image_path)
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return [
            {"type": "text", "text": description},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{encoded}"},
            },
        ]

    @staticmethod
    def _strip_json_fence(value: str) -> str:
        stripped = value.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            lines = lines[1:-1] if len(lines) >= 3 else lines
            return "\n".join(lines)
        return stripped

    @staticmethod
    def _confidence(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return min(1.0, max(0.0, float(value)))
        except (TypeError, ValueError):
            return None
