"""Application records that combine Wiki knowledge with raw RAG evidence."""

from dataclasses import dataclass, field
from typing import Literal

from science_agent.rag.types import EvidencePack, PaperIngestionResult
from science_agent.wiki.types import SourceRef, WikiChangeSet, WikiEvidence

KnowledgeQueryMode = Literal["wiki_guided", "raw_first", "raw_only"]
KnowledgeIngestionStatus = Literal[
    "drafted",
    "applied",
    "unchanged",
    "maintenance_failed",
    "compiler_failed",
    "apply_failed",
]


@dataclass(slots=True)
class KnowledgeQueryPlan:
    mode: KnowledgeQueryMode
    reasons: list[str] = field(default_factory=list)
    expand_links: bool = True
    raw_required: bool = True


@dataclass(frozen=True, slots=True)
class KnowledgeCitation:
    reference: SourceRef
    page_id: str
    claim_id: str
    verified_in_raw_results: bool


@dataclass(slots=True)
class KnowledgeEvidence:
    query: str
    plan: KnowledgeQueryPlan
    wiki: WikiEvidence
    raw: EvidencePack
    citations: list[KnowledgeCitation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class KnowledgeIngestionResult:
    raw: PaperIngestionResult
    status: KnowledgeIngestionStatus
    changeset: WikiChangeSet | None = None
    stale_changeset: WikiChangeSet | None = None
    error: str | None = None
