"""Sentence Transformers dense embedding adapter with lazy model loading."""

from typing import Any


class SentenceTransformerEmbeddings:
    def __init__(self, model_name: str = "BAAI/bge-m3") -> None:
        self.model_name = model_name
        self._model: Any | None = None

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._get_model().encode(texts, normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        vector = self._get_model().encode(text, normalize_embeddings=True)
        return vector.tolist()

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ModuleNotFoundError as exc:  # pragma: no cover - dependency boundary
                raise ModuleNotFoundError(
                    "Dense retrieval requires sentence-transformers. "
                    "Install with `pip install science-agent[rag]`."
                ) from exc
            self._model = SentenceTransformer(self.model_name)
        return self._model
