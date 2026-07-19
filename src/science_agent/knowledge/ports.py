"""Ports required by the knowledge application layer."""

from pathlib import Path
from typing import Protocol

from science_agent.rag.types import EvidencePack, PaperIngestionResult


class DetailedPaperIngestor(Protocol):
    async def ingest_detailed(
        self, path: str | Path, *, paper_id: str | None = None
    ) -> PaperIngestionResult: ...


class RawEvidenceRetriever(Protocol):
    async def search(
        self,
        query: str,
        *,
        limit: int | None = None,
        section_kind: str | None = None,
        chunk_types: tuple[str, ...] | None = None,
    ) -> EvidencePack: ...
