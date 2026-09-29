"""Select the top fused hits without a learned reranking model."""

from science_agent.rag.types import RetrievalHit


class FusionRanker:
    async def rerank(
        self, query: str, hits: list[RetrievalHit], *, limit: int
    ) -> list[RetrievalHit]:
        # RetrievalService 已完成 RRF；本地模式只截取结果，不伪造新的相关性分数。
        return hits[: max(0, limit)]
