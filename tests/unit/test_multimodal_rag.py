import json
from pathlib import Path

import httpx
import pytest

from science_agent.infra.visual_assets.region_renderer import normalize_pdf_bbox
from science_agent.infra.vlm.openai_vision import OpenAIVisionProvider
from science_agent.rag.multimodal.policy import VLMFallbackPolicy
from science_agent.rag.multimodal.service import FigureSearchService
from science_agent.rag.multimodal.types import (
    VLMObservation,
    VLMResponse,
    VisualAsset,
)
from science_agent.rag.types import (
    EvidencePack,
    PaperDocument,
    ParentChunk,
    RetrievalHit,
    SourceElement,
)
from science_agent.tools.base import ToolExecutionContext
from science_agent.errors import ToolExecutionError
from science_agent.tools.rag_figure_search import create_paper_figure_search_tool


def _asset(*, caption: str = "") -> VisualAsset:
    return VisualAsset(
        element_id="figure-1",
        paper_id="paper-1",
        image_path="figure.png",
        source="pdf_crop",
        caption=caption,
    )


def test_normalize_pdf_bbox_converts_bottom_left_coordinates():
    result = normalize_pdf_bbox(
        (10, 180, 110, 80),
        page_width=200,
        page_height=200,
        coord_origin="bottom_left",
        padding=5,
    )

    assert result == (5, 15, 115, 125)


def test_vlm_policy_respects_modes_and_visual_intent():
    policy = VLMFallbackPolicy(min_caption_chars=20)

    assert policy.decide("What does this figure show?", [_asset()]).use_vlm is True
    assert (
        policy.decide("Summarize", [_asset(caption="a" * 30)]).use_vlm is False
    )
    assert policy.decide("Summarize", [_asset()], mode="always").reasons == [
        "vlm_forced"
    ]
    assert policy.decide("figure", [_asset()], mode="never").use_vlm is False


class FakeRetriever:
    def __init__(self) -> None:
        self.chunk_types = None

    async def search(
        self, query, *, limit=None, section_kind=None, chunk_types=None
    ):
        self.chunk_types = chunk_types
        parent = ParentChunk(
            chunk_id="parent-1",
            paper_id="paper-1",
            section_kind="result",
            text="Figure 1 compares accuracy across methods.",
            source_element_ids=["figure-1"],
            chunk_type="figure",
        )
        element = SourceElement(
            element_id="figure-1",
            paper_id="paper-1",
            page_no=2,
            bbox=(10, 20, 200, 180),
            element_type="figure",
            section_kind="result",
            text="Figure 1",
            raw_payload={"caption": "Accuracy comparison"},
        )
        return EvidencePack(
            query=query,
            hits=[
                RetrievalHit(
                    chunk_id="child-1",
                    score=0.9,
                    text="Figure 1",
                    paper_id="paper-1",
                    parent_chunk_id="parent-1",
                    section_kind="result",
                )
            ],
            parents={"parent-1": parent},
            source_elements={"figure-1": element},
            route="result",
        )


class FakePaperStore:
    async def get_papers(self, paper_ids):
        return [PaperDocument("paper-1", "paper.pdf", "Paper")]


class FakeAssetResolver:
    async def resolve(self, element, paper, *, context=""):
        return VisualAsset(
            element_id=element.element_id,
            paper_id=paper.paper_id,
            image_path="crop.png",
            source="pdf_crop",
            page_no=element.page_no,
            bbox=element.bbox,
            caption=element.raw_payload["caption"],
            context=context,
            width=640,
            height=480,
        )


class FakeVLM:
    async def analyze(self, query, assets):
        return VLMResponse(
            answer="Method A has the highest accuracy.",
            observations=[
                VLMObservation(
                    element_id=assets[0].element_id,
                    summary="Method A leads the comparison.",
                    key_values=["Method A: 91%"],
                    confidence=0.9,
                )
            ],
        )


class FailingVLM:
    async def analyze(self, query, assets):
        raise ValueError("vision endpoint unavailable")


@pytest.mark.asyncio
async def test_figure_service_filters_resolves_and_calls_vlm():
    retriever = FakeRetriever()
    service = FigureSearchService(
        retrieval=retriever,
        paper_store=FakePaperStore(),
        asset_resolver=FakeAssetResolver(),
        vlm=FakeVLM(),
    )

    result = await service.search("What does Figure 1 show?")

    assert retriever.chunk_types == ("figure", "table", "formula", "mixed")
    assert result.vlm_used is True
    assert result.assets[0].context.startswith("Figure 1 compares")
    assert result.vlm_response.answer == "Method A has the highest accuracy."


@pytest.mark.asyncio
async def test_figure_service_reports_missing_vlm_provider():
    service = FigureSearchService(
        retrieval=FakeRetriever(),
        paper_store=FakePaperStore(),
        asset_resolver=FakeAssetResolver(),
    )

    result = await service.search("Inspect the figure", vlm_mode="always")

    assert result.vlm_used is False
    assert result.decision.reasons == [
        "vlm_forced",
        "vlm_provider_unavailable",
    ]


@pytest.mark.asyncio
async def test_figure_service_isolates_vlm_failures():
    service = FigureSearchService(
        retrieval=FakeRetriever(),
        paper_store=FakePaperStore(),
        asset_resolver=FakeAssetResolver(),
        vlm=FailingVLM(),
    )

    result = await service.search("Inspect the figure", vlm_mode="always")

    assert result.assets
    assert result.vlm_used is False
    assert result.vlm_error == "ValueError: vision endpoint unavailable"
    assert result.decision.reasons[-1] == "vlm_failed"


@pytest.mark.asyncio
async def test_figure_search_tool_returns_compact_visual_evidence():
    service = FigureSearchService(
        retrieval=FakeRetriever(),
        paper_store=FakePaperStore(),
        asset_resolver=FakeAssetResolver(),
        vlm=FakeVLM(),
    )
    tool = create_paper_figure_search_tool(service)

    result = await tool.run(
        {"query": "Inspect the figure", "vlm_mode": "always"},
        ToolExecutionContext(),
    )

    assert result["vlm_used"] is True
    assert result["assets"][0]["element_id"] == "figure-1"
    assert result["vlm_response"]["observations"][0]["confidence"] == 0.9

    with pytest.raises(ToolExecutionError, match="must be one of"):
        await tool.run(
            {"query": "Inspect the figure", "vlm_mode": "sometimes"},
            ToolExecutionContext(),
        )


@pytest.mark.asyncio
async def test_openai_vision_provider_sends_images_and_parses_json(tmp_path):
    image_path = tmp_path / "figure.png"
    image_path.write_bytes(b"fake-png")

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        user_content = payload["messages"][1]["content"]
        image_url = next(
            item["image_url"]["url"]
            for item in user_content
            if item["type"] == "image_url"
        )
        assert image_url.startswith("data:image/png;base64,")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "answer": "The curve rises.",
                                    "observations": [
                                        {
                                            "element_id": "figure-1",
                                            "summary": "Rising curve",
                                            "key_values": ["peak=0.9"],
                                            "confidence": 1.4,
                                        }
                                    ],
                                }
                            )
                        }
                    }
                ]
            },
            request=request,
        )

    provider = OpenAIVisionProvider(
        api_key="test",
        transport=httpx.MockTransport(handler),
    )

    response = await provider.analyze(
        "Describe the curve",
        [
            VisualAsset(
                element_id="figure-1",
                paper_id="paper-1",
                image_path=str(Path(image_path)),
                source="pdf_crop",
            )
        ],
    )

    assert response.answer == "The curve rises."
    assert response.observations[0].confidence == 1.0
