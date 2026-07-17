"""Deterministic policy deciding when visual model analysis is warranted."""

from dataclasses import dataclass

from science_agent.rag.multimodal.types import FallbackDecision, VLMMode, VisualAsset

_VISUAL_QUERY_HINTS = (
    "figure",
    "fig.",
    "plot",
    "curve",
    "chart",
    "diagram",
    "architecture",
    "table",
    "image",
    "图",
    "曲线",
    "图表",
    "架构图",
    "流程图",
    "表格",
    "图中",
)


@dataclass(slots=True)
class VLMFallbackPolicy:
    min_caption_chars: int = 80

    def decide(
        self,
        query: str,
        assets: list[VisualAsset],
        *,
        mode: VLMMode = "auto",
    ) -> FallbackDecision:
        if mode == "never":
            return FallbackDecision(use_vlm=False, reasons=["vlm_disabled"])
        if not assets:
            return FallbackDecision(use_vlm=False, reasons=["no_visual_assets"])
        if mode == "always":
            return FallbackDecision(use_vlm=True, reasons=["vlm_forced"])

        reasons: list[str] = []
        normalized = query.lower()
        if any(hint in normalized for hint in _VISUAL_QUERY_HINTS):
            reasons.append("explicit_visual_query")
        if all(len(asset.caption.strip()) < self.min_caption_chars for asset in assets):
            reasons.append("insufficient_visual_text")
        return FallbackDecision(use_vlm=bool(reasons), reasons=reasons)
