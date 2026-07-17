"""Multimodal evidence retrieval for scientific papers."""

from .policy import VLMFallbackPolicy
from .service import FigureSearchService
from .types import (
    FallbackDecision,
    FigureEvidencePack,
    VLMMode,
    VLMObservation,
    VLMResponse,
    VisualAsset,
)

__all__ = [
    "FallbackDecision",
    "FigureEvidencePack",
    "FigureSearchService",
    "VLMFallbackPolicy",
    "VLMMode",
    "VLMObservation",
    "VLMResponse",
    "VisualAsset",
]
