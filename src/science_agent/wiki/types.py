"""Stable records for the review-first Wiki workflow."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from science_agent.rag.types import EvidencePack, SourceElement

WikiPageStatus = Literal["fresh", "stale"]
ChangesetStatus = Literal["pending", "applied", "rejected"]
WikiQueryMode = Literal["wiki_guided", "raw_first", "raw_only"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class RawSourceSnapshot:
    """Immutable raw evidence captured from one source revision.

    A new parser result creates a new snapshot. Existing snapshots remain valid
    evidence for old Wiki versions and can be used to explain stale status.
    """

    snapshot_id: str
    paper_id: str
    source_path: str
    content_hash: str
    version: int
    elements: tuple[SourceElement, ...]
    captured_at: str = field(default_factory=utc_now_iso)

    def citation_keys(self) -> frozenset[str]:
        return frozenset(
            f"{self.snapshot_id}:{element.element_id}" for element in self.elements
        )


@dataclass(slots=True)
class WikiPage:
    page_id: str
    title: str
    markdown: str
    version: int = 0
    source_snapshot_ids: list[str] = field(default_factory=list)
    status: WikiPageStatus = "fresh"
    stale_sources: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True, slots=True)
class ChangesetDraft:
    markdown: str
    summary: str
    citation_keys: tuple[str, ...]


@dataclass(slots=True)
class WikiChangeset:
    changeset_id: str
    page_id: str
    base_version: int
    base_markdown: str
    proposed_markdown: str
    summary: str
    citation_keys: tuple[str, ...]
    status: ChangesetStatus = "pending"
    created_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True, slots=True)
class ClaimVerification:
    claim: str
    citation_keys: tuple[str, ...]
    verified: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class WikiQueryResult:
    query: str
    mode: WikiQueryMode
    wiki_pages: tuple[WikiPage, ...]
    raw_evidence: EvidencePack | None
    claim_verifications: tuple[ClaimVerification, ...] = ()
    context: str = ""
    raw_first: bool = False
