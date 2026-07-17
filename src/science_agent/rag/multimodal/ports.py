"""Replaceable ports used by the multimodal domain service."""

from typing import Protocol

from science_agent.rag.multimodal.types import VLMResponse, VisualAsset
from science_agent.rag.types import EvidencePack, PaperDocument, SourceElement


class EvidenceRetriever(Protocol):
    async def search(
        self,
        query: str,
        *,
        limit: int | None = None,
        section_kind: str | None = None,
        chunk_types: tuple[str, ...] | None = None,
    ) -> EvidencePack: ...


class PaperSourceStore(Protocol):
    async def get_papers(self, paper_ids: list[str]) -> list[PaperDocument]: ...


class VisualAssetResolver(Protocol):
    async def resolve(
        self,
        element: SourceElement,
        paper: PaperDocument,
        *,
        context: str = "",
    ) -> VisualAsset | None: ...


class VisionLanguageModel(Protocol):
    async def analyze(self, query: str, assets: list[VisualAsset]) -> VLMResponse: ...
