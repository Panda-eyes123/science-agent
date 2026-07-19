"""Scientific paper RAG contracts and orchestration helpers."""

from .chunking import PaperChunker
from .ports import CorpusStore
from .retrieval import RetrievalService, reciprocal_rank_fusion
from .routing import classify_section, route_query
from .service import PaperIngestionService
from .multimodal import (
    FigureEvidencePack,
    FigureSearchService,
    VLMFallbackPolicy,
    VLMObservation,
    VLMResponse,
    VisualAsset,
)
from .types import (
    ChildChunk,
    EvidencePack,
    PaperDocument,
    PaperIngestionResult,
    ParentChunk,
    RetrievalHit,
    SourceElement,
)

__all__ = [
    "ChildChunk",
    "CorpusStore",
    "EvidencePack",
    "FigureEvidencePack",
    "FigureSearchService",
    "PaperChunker",
    "PaperDocument",
    "PaperIngestionResult",
    "PaperIngestionService",
    "ParentChunk",
    "RetrievalHit",
    "RetrievalService",
    "SourceElement",
    "VLMFallbackPolicy",
    "VLMObservation",
    "VLMResponse",
    "VisualAsset",
    "classify_section",
    "reciprocal_rank_fusion",
    "route_query",
]
