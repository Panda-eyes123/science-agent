"""Orchestrate visual retrieval, asset resolution, and optional VLM analysis."""

import asyncio
from collections.abc import Awaitable

from science_agent.rag.multimodal.policy import VLMFallbackPolicy
from science_agent.rag.multimodal.ports import (
    EvidenceRetriever,
    PaperSourceStore,
    VisionLanguageModel,
    VisualAssetResolver,
)
from science_agent.rag.multimodal.types import FigureEvidencePack, VLMMode, VisualAsset
from science_agent.rag.types import EvidencePack, SourceElement

_VISUAL_ELEMENT_TYPES = {"figure", "table", "formula"}
_VISUAL_CHUNK_TYPES = ("figure", "table", "formula", "mixed")


class FigureSearchService:
    def __init__(
        self,
        *,
        retrieval: EvidenceRetriever,
        paper_store: PaperSourceStore,
        asset_resolver: VisualAssetResolver,
        vlm: VisionLanguageModel | None = None,
        policy: VLMFallbackPolicy | None = None,
        max_assets: int = 4,
        context_chars: int = 2_000,
    ) -> None:
        self.retrieval = retrieval
        self.paper_store = paper_store
        self.asset_resolver = asset_resolver
        self.vlm = vlm
        self.policy = policy or VLMFallbackPolicy()
        self.max_assets = max_assets
        self.context_chars = context_chars

    async def search(
        self,
        query: str,
        *,
        limit: int | None = None,
        section_kind: str | None = None,
        vlm_mode: VLMMode = "auto",
    ) -> FigureEvidencePack:
        asset_limit = limit or self.max_assets
        evidence = await self.retrieval.search(
            query,
            limit=max(asset_limit * 2, asset_limit),
            section_kind=section_kind,
            chunk_types=_VISUAL_CHUNK_TYPES,
        )
        assets, asset_errors = await self._resolve_assets(
            evidence, limit=asset_limit
        )
        decision = self.policy.decide(query, assets, mode=vlm_mode)
        response = None
        vlm_error = None
        if decision.use_vlm and self.vlm is not None:
            try:
                response = await self.vlm.analyze(query, assets)
            except Exception as exc:  # noqa: BLE001 - isolate replaceable provider failures
                vlm_error = f"{type(exc).__name__}: {exc}"
                decision.reasons.append("vlm_failed")
        elif decision.use_vlm:
            decision.use_vlm = False
            decision.reasons.append("vlm_provider_unavailable")
        return FigureEvidencePack(
            query=query,
            retrieval=evidence,
            assets=assets,
            decision=decision,
            vlm_response=response,
            asset_errors=asset_errors,
            vlm_error=vlm_error,
        )

    async def _resolve_assets(
        self, evidence: EvidencePack, *, limit: int
    ) -> tuple[list[VisualAsset], dict[str, str]]:
        elements = self._ranked_visual_elements(evidence)[:limit]
        paper_ids = list(dict.fromkeys(element.paper_id for element in elements))
        papers = await self.paper_store.get_papers(paper_ids)
        papers_by_id = {paper.paper_id: paper for paper in papers}
        resolutions: list[tuple[str, Awaitable[VisualAsset | None]]] = []
        for element in elements:
            paper = papers_by_id.get(element.paper_id)
            if paper is None:
                continue
            resolutions.append(
                (
                    element.element_id,
                    self.asset_resolver.resolve(
                        element,
                        paper,
                        context=self._context_for(element, evidence),
                    ),
                )
            )
        resolved = await asyncio.gather(
            *(resolution for _, resolution in resolutions),
            return_exceptions=True,
        )
        assets: list[VisualAsset] = []
        errors: dict[str, str] = {}
        for (element_id, _), result in zip(resolutions, resolved, strict=True):
            if isinstance(result, Exception):
                errors[element_id] = f"{type(result).__name__}: {result}"
            elif result is not None:
                assets.append(result)
        return assets, errors

    @staticmethod
    def _ranked_visual_elements(evidence: EvidencePack) -> list[SourceElement]:
        ranked: list[SourceElement] = []
        seen: set[str] = set()
        for hit in evidence.hits:
            parent = evidence.parents.get(hit.parent_chunk_id or "")
            if parent is None:
                continue
            for element_id in parent.source_element_ids:
                element = evidence.source_elements.get(element_id)
                if (
                    element is not None
                    and element.element_type in _VISUAL_ELEMENT_TYPES
                    and element.element_id not in seen
                ):
                    ranked.append(element)
                    seen.add(element.element_id)
        return ranked

    def _context_for(self, element: SourceElement, evidence: EvidencePack) -> str:
        for parent in evidence.parents.values():
            if element.element_id in parent.source_element_ids:
                return parent.text[: self.context_chars]
        return ""
