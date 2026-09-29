"""Typed records exchanged by paper parsing, indexing, and retrieval."""

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

SectionKind = Literal[
    "background", "method", "experiment", "result", "discussion", "other"
]
ElementType = Literal[
    "title",
    "section_heading",
    "paragraph",
    "list",
    "table",
    "figure",
    "caption",
    "formula",
    "code",
    "reference",
    "other",
]
ChunkType = Literal["text", "table", "figure", "formula", "mixed"]


@dataclass(slots=True)
class PaperDocument:
    paper_id: str
    source_path: str
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SourceElement:
    """A faithful, page-addressable item emitted by a document parser."""

    element_id: str
    paper_id: str
    page_no: int | None
    bbox: tuple[float, float, float, float] | None
    element_type: ElementType
    section_kind: SectionKind
    text: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)
    image_path: str | None = None
    table_markdown: str | None = None
    parent_element_id: str | None = None


@dataclass(slots=True)
class ParentChunk:
    chunk_id: str
    paper_id: str
    section_kind: SectionKind
    text: str
    source_element_ids: list[str]
    chunk_type: ChunkType = "text"
    page_start: int | None = None
    page_end: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChildChunk:
    chunk_id: str
    parent_chunk_id: str
    paper_id: str
    section_kind: SectionKind
    text: str
    source_element_ids: list[str]
    chunk_type: ChunkType = "text"
    ordinal: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RetrievalHit:
    chunk_id: str
    score: float
    text: str = ""
    paper_id: str | None = None
    parent_chunk_id: str | None = None
    section_kind: SectionKind | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EvidencePack:
    query: str
    hits: list[RetrievalHit]
    parents: dict[str, ParentChunk]
    source_elements: dict[str, SourceElement]
    route: SectionKind | None = None
    papers: dict[str, PaperDocument] = field(default_factory=dict)


class EvidenceSource(BaseModel):
    element_id: str
    page_no: int | None
    element_type: ElementType
    text: str


class EvidenceItem(BaseModel):
    chunk_id: str
    paper_id: str | None
    title: str | None
    section_kind: SectionKind | None
    score: float
    excerpt: str
    sources: list[EvidenceSource]


class EvidenceView(BaseModel):
    """可供模型和前端共享的证据摘要，不包含文件路径或解析器内部载荷。"""

    query: str
    route: SectionKind | None
    items: list[EvidenceItem]
