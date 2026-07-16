"""Scientific paper RAG contracts and orchestration helpers."""

from .chunking import PaperChunker
from .retrieval import RetrievalService, reciprocal_rank_fusion
from .routing import classify_section, route_query
from .service import PaperIngestionService
from .types import (
    ChildChunk,
    EvidencePack,
    PaperDocument,
    ParentChunk,
    RetrievalHit,
    SourceElement,
)

__all__ = [
    "ChildChunk",
    "EvidencePack",
    "PaperChunker",
    "PaperDocument",
    "PaperIngestionService",
    "ParentChunk",
    "RetrievalHit",
    "RetrievalService",
    "SourceElement",
    "classify_section",
    "reciprocal_rank_fusion",
    "route_query",
]
