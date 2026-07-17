"""Compatibility name for an API-served cross-encoder reranker."""

from science_agent.infra.rerankers.api import APIReranker


class CrossEncoderReranker(APIReranker):
    """Backward-compatible constructor; inference is always remote."""

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3", **kwargs) -> None:
        super().__init__(model=model_name, **kwargs)
