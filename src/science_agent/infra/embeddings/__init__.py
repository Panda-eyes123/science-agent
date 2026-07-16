"""Embedding provider contracts."""

from .base import EmbeddingProvider
from .sentence_transformer import SentenceTransformerEmbeddings

__all__ = ["EmbeddingProvider", "SentenceTransformerEmbeddings"]
