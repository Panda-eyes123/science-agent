"""Domain records for visual evidence and VLM analysis."""

from dataclasses import dataclass, field
from typing import Any, Literal

from science_agent.rag.types import EvidencePack

VLMMode = Literal["auto", "always", "never"]
VisualSource = Literal["docling_export", "pdf_crop"]


@dataclass(slots=True)
class VisualAsset:
    element_id: str
    paper_id: str
    image_path: str
    source: VisualSource
    page_no: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    element_type: str = "figure"
    caption: str = ""
    context: str = ""
    width: int | None = None
    height: int | None = None


@dataclass(slots=True)
class VLMObservation:
    element_id: str
    summary: str
    key_values: list[str] = field(default_factory=list)
    confidence: float | None = None


@dataclass(slots=True)
class VLMResponse:
    answer: str
    observations: list[VLMObservation] = field(default_factory=list)
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class FallbackDecision:
    use_vlm: bool
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FigureEvidencePack:
    query: str
    retrieval: EvidencePack
    assets: list[VisualAsset]
    decision: FallbackDecision
    vlm_response: VLMResponse | None = None
    asset_errors: dict[str, str] = field(default_factory=dict)
    vlm_error: str | None = None

    @property
    def vlm_used(self) -> bool:
        return self.vlm_response is not None
