"""Ports used by Wiki services; concrete storage stays outside the domain."""

from collections.abc import Callable
from typing import Protocol

from science_agent.rag.types import EvidencePack

from .types import (
    ChangesetDraft,
    ClaimVerification,
    RawSourceSnapshot,
    WikiPage,
)


class WikiPageStore(Protocol):
    async def get(self, page_id: str) -> WikiPage | None: ...

    async def list(self) -> list[WikiPage]: ...

    async def put(self, page: WikiPage, *, expected_version: int) -> WikiPage: ...


class WikiCompiler(Protocol):
    async def compile(
        self,
        *,
        page: WikiPage,
        snapshots: tuple[RawSourceSnapshot, ...],
        instruction: str,
    ) -> ChangesetDraft: ...


class WikiPageSearcher(Protocol):
    async def search(self, query: str) -> list[WikiPage]: ...


class RawEvidenceSearcher(Protocol):
    async def search(self, query: str) -> EvidencePack: ...


class ClaimVerifier(Protocol):
    async def verify(
        self,
        *,
        query: str,
        wiki_pages: tuple[WikiPage, ...],
        evidence: EvidencePack,
    ) -> list[ClaimVerification]: ...


WikiContextFormatter = Callable[[tuple[WikiPage, ...]], str]
