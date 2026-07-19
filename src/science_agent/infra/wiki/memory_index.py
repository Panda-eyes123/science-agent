"""Small in-memory Wiki index for examples and contract tests."""

from math import sqrt
import re

from science_agent.wiki.service import WikiService
from science_agent.wiki.types import WikiPage, WikiSearchHit


class InMemoryWikiIndex:
    def __init__(self) -> None:
        self._pages: dict[str, WikiPage] = {}
        self._vectors: dict[str, list[float]] = {}

    async def replace_pages(
        self, pages: list[WikiPage], embeddings: list[list[float]]
    ) -> None:
        if len(pages) != len(embeddings):
            raise ValueError("Every Wiki page must have exactly one embedding.")
        for page, vector in zip(pages, embeddings, strict=True):
            self._pages[page.page_id] = page
            self._vectors[page.page_id] = vector

    async def delete_pages(self, page_ids: list[str]) -> None:
        for page_id in page_ids:
            self._pages.pop(page_id, None)
            self._vectors.pop(page_id, None)

    async def search_bm25(self, query: str, *, limit: int) -> list[WikiSearchHit]:
        terms = self._terms(query)
        ranked: list[WikiSearchHit] = []
        for page in self._pages.values():
            text = WikiService.index_text(page)
            normalized = text.lower()
            score = float(sum(normalized.count(term) for term in terms))
            if score:
                ranked.append(self._hit(page, score, text))
        ranked.sort(key=lambda hit: (-hit.score, hit.page_id))
        return ranked[:limit]

    async def search_dense(
        self, vector: list[float], *, limit: int
    ) -> list[WikiSearchHit]:
        ranked = [
            self._hit(page, self._cosine(vector, self._vectors[page_id]))
            for page_id, page in self._pages.items()
        ]
        ranked.sort(key=lambda hit: (-hit.score, hit.page_id))
        return ranked[:limit]

    @staticmethod
    def _terms(value: str) -> list[str]:
        return [term for term in re.findall(r"\w+", value.lower()) if term]

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left:
            return 0.0
        numerator = sum(a * b for a, b in zip(left, right, strict=True))
        denominator = sqrt(sum(a * a for a in left)) * sqrt(
            sum(b * b for b in right)
        )
        return numerator / denominator if denominator else 0.0

    @staticmethod
    def _hit(page: WikiPage, score: float, text: str | None = None) -> WikiSearchHit:
        return WikiSearchHit(
            page_id=page.page_id,
            score=score,
            title=page.title,
            text=text or WikiService.index_text(page),
            page_type=page.page_type,
            status=page.status,
            revision=page.revision,
        )
