"""Strict JSON adapter that turns model output into Wiki changesets."""

from dataclasses import asdict
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from science_agent.infra.providers.base import ModelProvider
from science_agent.types import Message
from science_agent.wiki.types import (
    SourceRef,
    WikiChangeSet,
    WikiClaim,
    WikiLink,
    WikiOperation,
    WikiPage,
    WikiSourceSnapshot,
)
from science_agent.wiki.validation import ensure_valid_changeset


class _SourceRefModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_id: str
    element_id: str
    page_no: int | None = None
    content_hash: str | None = None


class _ClaimModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    text: str
    sources: list[_SourceRefModel]
    status: Literal[
        "established", "tentative", "conflicting", "stale", "needs_review"
    ] = "tentative"
    confidence: float | None = None


class _LinkModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_page_id: str
    relation: str = "related"


class _PageModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str
    title: str
    page_type: Literal["index", "topic", "concept", "entity", "source", "query"]
    body: str
    aliases: list[str] = Field(default_factory=list)
    claims: list[_ClaimModel] = Field(default_factory=list)
    links: list[_LinkModel] = Field(default_factory=list)
    status: Literal[
        "draft",
        "established",
        "tentative",
        "conflicting",
        "stale",
        "needs_review",
    ] = "tentative"


class _OperationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal[
        "create_page", "update_page", "link_pages", "mark_conflict", "mark_stale"
    ]
    page_id: str
    page: _PageModel | None = None
    target_page_id: str | None = None
    relation: str = "related"
    expected_revision: int | None = None
    reason: str = ""


class _PlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operations: list[_OperationModel] = Field(min_length=1)


class LLMWikiCompiler:
    def __init__(
        self,
        model: ModelProvider,
        *,
        compiler_version: str = "wiki-compiler-v1",
    ) -> None:
        self.model = model
        self.compiler_version = compiler_version

    async def plan(
        self,
        source: WikiSourceSnapshot,
        related_pages: list[WikiPage],
    ) -> WikiChangeSet:
        response = await self.model.complete(
            [Message(role="user", content=self._prompt(source, related_pages))],
            system_prompt=(
                "You maintain an evidence-backed personal Wiki. Return only JSON. "
                "Never invent source references and never rewrite unrelated pages."
            ),
        )
        plan = _PlanModel.model_validate_json(self._json_text(response.text))
        changeset = WikiChangeSet(
            change_id=self._change_id(source, related_pages),
            operations=[self._operation(item) for item in plan.operations],
            source_hashes=[source.content_hash],
            compiler_version=self.compiler_version,
        )
        self._canonicalize_sources(changeset, source, related_pages)
        ensure_valid_changeset(changeset)
        return changeset

    def _prompt(
        self, source: WikiSourceSnapshot, related_pages: list[WikiPage]
    ) -> str:
        schema = _PlanModel.model_json_schema()
        pages = [asdict(page) for page in related_pages]
        return json.dumps(
            {
                "task": (
                    "Create a minimal Wiki update plan. Prefer updating an existing "
                    "page over creating duplicates. Claims require supplied references."
                ),
                "source": asdict(source),
                "related_pages": pages,
                "output_schema": schema,
            },
            ensure_ascii=False,
        )

    def _change_id(
        self, source: WikiSourceSnapshot, related_pages: list[WikiPage]
    ) -> str:
        revisions = ",".join(
            f"{page.page_id}:{page.revision}" for page in sorted(
                related_pages, key=lambda item: item.page_id
            )
        )
        value = f"{source.content_hash}|{self.compiler_version}|{revisions}"
        return f"wiki-{sha256(value.encode('utf-8')).hexdigest()[:24]}"

    @staticmethod
    def _json_text(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()
        return stripped

    @staticmethod
    def _operation(item: _OperationModel) -> WikiOperation:
        page = None
        if item.page is not None:
            page = WikiPage(
                page_id=item.page.page_id,
                title=item.page.title,
                page_type=item.page.page_type,
                body=item.page.body,
                aliases=item.page.aliases,
                claims=[
                    WikiClaim(
                        claim_id=claim.claim_id,
                        text=claim.text,
                        sources=[SourceRef(**source.model_dump()) for source in claim.sources],
                        status=claim.status,
                        confidence=claim.confidence,
                    )
                    for claim in item.page.claims
                ],
                links=[WikiLink(**link.model_dump()) for link in item.page.links],
                status=item.page.status,
            )
        return WikiOperation(
            operation=item.operation,
            page_id=item.page_id,
            page=page,
            target_page_id=item.target_page_id,
            relation=item.relation,
            expected_revision=item.expected_revision,
            reason=item.reason,
        )

    @staticmethod
    def _canonicalize_sources(
        changeset: WikiChangeSet,
        source: WikiSourceSnapshot,
        related_pages: list[WikiPage],
    ) -> None:
        allowed = {
            (reference.paper_id, reference.element_id): reference
            for reference in source.references
        }
        for page in related_pages:
            for claim in page.claims:
                for reference in claim.sources:
                    allowed[(reference.paper_id, reference.element_id)] = reference
        for operation in changeset.operations:
            if operation.page is None:
                continue
            for claim in operation.page.claims:
                claim.sources = [
                    allowed[(reference.paper_id, reference.element_id)]
                    for reference in claim.sources
                    if (reference.paper_id, reference.element_id) in allowed
                ]
