"""Embedding provider contracts."""

from .base import EmbeddingProvider
from .openai_embeddings import OpenAIEmbeddingProvider

__all__ = ["EmbeddingProvider", "OpenAIEmbeddingProvider"]
