"""Compose raw paper ingestion with reviewable Wiki compilation."""

from pathlib import Path

from science_agent.knowledge.ports import DetailedPaperIngestor
from science_agent.knowledge.types import KnowledgeIngestionResult
from science_agent.rag.types import PaperIngestionResult
from science_agent.wiki.errors import WikiNotFoundError
from science_agent.wiki.maintenance import WikiMaintenanceService
from science_agent.wiki.ports import (
    WikiCompiler,
    WikiDraftStore,
)
from science_agent.wiki.retrieval import WikiRetrievalService
from science_agent.wiki.service import WikiService
from science_agent.wiki.types import (
    SourceRef,
    WikiApplyResult,
    WikiChangeSet,
    WikiSourceSnapshot,
)


class KnowledgeIngestionService:
    def __init__(
        self,
        *,
        raw_ingestion: DetailedPaperIngestor,
        compiler: WikiCompiler,
        retrieval: WikiRetrievalService,
        wiki: WikiService,
        drafts: WikiDraftStore,
        maintenance: WikiMaintenanceService,
        related_limit: int = 6,
        max_source_chars: int = 40_000,
    ) -> None:
        self.raw_ingestion = raw_ingestion
        self.compiler = compiler
        self.retrieval = retrieval
        self.wiki = wiki
        self.drafts = drafts
        self.maintenance = maintenance
        self.related_limit = related_limit
        self.max_source_chars = max_source_chars

    async def ingest(
        self,
        path: str | Path,
        *,
        paper_id: str | None = None,
        apply: bool = False,
        force_recompile: bool = False,
    ) -> KnowledgeIngestionResult:
        raw = await self.raw_ingestion.ingest_detailed(path, paper_id=paper_id)
        if raw.status == "unchanged" and not force_recompile:
            return KnowledgeIngestionResult(raw=raw, status="unchanged")
        content_hash = raw.paper.content_hash
        if content_hash is None:
            return KnowledgeIngestionResult(
                raw=raw,
                status="compiler_failed",
                error="raw ingestion did not provide a content hash",
            )

        stale_changeset: WikiChangeSet | None = None
        try:
            stale_changeset = await self.maintenance.plan_source_refresh(
                raw.paper.paper_id, content_hash
            )
            if stale_changeset is not None:
                await self.wiki.apply(stale_changeset)
        except Exception as exc:  # noqa: BLE001 - raw ingestion must remain usable
            return KnowledgeIngestionResult(
                raw=raw,
                status="maintenance_failed",
                stale_changeset=stale_changeset,
                error=f"{type(exc).__name__}: {exc}",
            )

        snapshot = self._snapshot(raw)
        try:
            related = await self.retrieval.search(
                raw.paper.title or snapshot.text[:1_000],
                limit=self.related_limit,
                expand_links=False,
            )
            related_pages = [
                related.pages[hit.page_id]
                for hit in related.hits
                if hit.page_id in related.pages
            ]
            changeset = await self.compiler.plan(snapshot, related_pages)
            await self.drafts.save(changeset)
        except Exception as exc:  # noqa: BLE001 - isolate replaceable compiler failures
            return KnowledgeIngestionResult(
                raw=raw,
                status="compiler_failed",
                stale_changeset=stale_changeset,
                error=f"{type(exc).__name__}: {exc}",
            )

        if not apply:
            return KnowledgeIngestionResult(
                raw=raw,
                status="drafted",
                changeset=changeset,
                stale_changeset=stale_changeset,
            )
        try:
            await self.wiki.apply(changeset)
            await self.drafts.delete(changeset.change_id)
        except Exception as exc:  # noqa: BLE001 - preserve draft for retry/review
            return KnowledgeIngestionResult(
                raw=raw,
                status="apply_failed",
                changeset=changeset,
                stale_changeset=stale_changeset,
                error=f"{type(exc).__name__}: {exc}",
            )
        return KnowledgeIngestionResult(
            raw=raw,
            status="applied",
            changeset=changeset,
            stale_changeset=stale_changeset,
        )

    async def apply_draft(self, change_id: str) -> WikiApplyResult:
        changeset = await self.drafts.get(change_id)
        if changeset is None:
            raise WikiNotFoundError(f"Wiki draft '{change_id}' does not exist")
        result = await self.wiki.apply(changeset)
        await self.drafts.delete(change_id)
        return result

    def _snapshot(self, raw: PaperIngestionResult) -> WikiSourceSnapshot:
        content_hash = raw.paper.content_hash
        assert content_hash is not None
        parts: list[str] = []
        references: list[SourceRef] = []
        remaining = self.max_source_chars
        for element in raw.elements:
            text = element.table_markdown or element.text
            if not text or element.element_type in {"section_heading", "reference"}:
                continue
            marker = (
                f"[source element={element.element_id} "
                f"page={element.page_no if element.page_no is not None else 'unknown'}]\n"
            )
            block = f"{marker}{text.strip()}"
            if len(block) > remaining:
                block = block[:remaining]
            if not block:
                break
            parts.append(block)
            references.append(
                SourceRef(
                    paper_id=raw.paper.paper_id,
                    element_id=element.element_id,
                    page_no=element.page_no,
                    content_hash=content_hash,
                )
            )
            remaining -= len(block)
            if remaining <= 0:
                break
        return WikiSourceSnapshot(
            source_id=raw.paper.paper_id,
            title=raw.paper.title,
            content_hash=content_hash,
            text="\n\n".join(parts),
            references=references,
        )
