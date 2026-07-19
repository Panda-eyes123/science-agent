"""Stable records for Wiki pages, claims, links, and change operations."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

WikiPageType = Literal["index", "topic", "concept", "entity", "source", "query"]
WikiPageStatus = Literal[
    "draft",
    "established",
    "tentative",
    "conflicting",
    "stale",
    "needs_review",
]
WikiClaimStatus = Literal[
    "established", "tentative", "conflicting", "stale", "needs_review"
]
WikiOperationType = Literal[
    "create_page", "update_page", "link_pages", "mark_conflict", "mark_stale"
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class SourceRef:
    paper_id: str
    element_id: str
    page_no: int | None = None
    content_hash: str | None = None


@dataclass(slots=True)
class WikiClaim:
    claim_id: str
    text: str
    sources: list[SourceRef]
    status: WikiClaimStatus = "tentative"
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class WikiLink:
    target_page_id: str
    relation: str = "related"


@dataclass(slots=True)
class WikiPage:
    page_id: str
    title: str
    page_type: WikiPageType
    body: str
    aliases: list[str] = field(default_factory=list)
    claims: list[WikiClaim] = field(default_factory=list)
    links: list[WikiLink] = field(default_factory=list)
    status: WikiPageStatus = "draft"
    revision: int = 0
    content_hash: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class WikiOperation:
    operation: WikiOperationType
    page_id: str
    page: WikiPage | None = None
    target_page_id: str | None = None
    relation: str = "related"
    expected_revision: int | None = None
    reason: str = ""


@dataclass(slots=True)
class WikiChangeSet:
    change_id: str
    operations: list[WikiOperation]
    source_hashes: list[str] = field(default_factory=list)
    compiler_version: str = "manual"
    created_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class WikiApplyResult:
    change_id: str
    changed_pages: list[WikiPage]
    deleted_page_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class WikiSearchHit:
    page_id: str
    score: float
    title: str = ""
    text: str = ""
    page_type: WikiPageType | None = None
    status: WikiPageStatus | None = None
    revision: int | None = None


@dataclass(slots=True)
class WikiEvidence:
    query: str
    hits: list[WikiSearchHit]
    pages: dict[str, WikiPage]
    expanded_page_ids: list[str] = field(default_factory=list)
    coverage: bool = False


@dataclass(slots=True)
class WikiSourceSnapshot:
    source_id: str
    title: str | None
    content_hash: str
    text: str
    references: list[SourceRef] = field(default_factory=list)
