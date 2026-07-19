"""Deterministic stale detection and Wiki linting."""

from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256

from science_agent.wiki.ports import WikiRepository
from science_agent.wiki.types import WikiChangeSet, WikiOperation
from science_agent.wiki.validation import validate_page


@dataclass(frozen=True, slots=True)
class WikiLintIssue:
    code: str
    message: str
    page_id: str | None = None


@dataclass(slots=True)
class WikiLintReport:
    page_count: int
    issues: list[WikiLintIssue] = field(default_factory=list)


class WikiMaintenanceService:
    def __init__(self, repository: WikiRepository) -> None:
        self.repository = repository

    async def plan_source_refresh(
        self, paper_id: str, current_hash: str
    ) -> WikiChangeSet | None:
        operations: list[WikiOperation] = []
        for page in await self.repository.list_pages():
            updated = deepcopy(page)
            changed = False
            has_stale_source = False
            for claim in updated.claims:
                if any(
                    reference.paper_id == paper_id
                    and reference.content_hash != current_hash
                    for reference in claim.sources
                ):
                    has_stale_source = True
                    if claim.status != "stale":
                        claim.status = "stale"
                        changed = True
            if has_stale_source and updated.status != "stale":
                updated.status = "stale"
                changed = True
            if changed:
                operations.append(
                    WikiOperation(
                        operation="update_page",
                        page_id=page.page_id,
                        page=updated,
                        expected_revision=page.revision,
                        reason=f"source {paper_id} changed",
                    )
                )
        if not operations:
            return None
        targets = "|".join(
            f"{operation.page_id}:{operation.expected_revision}"
            for operation in operations
        )
        digest = sha256(
            f"{paper_id}|{current_hash}|{targets}".encode("utf-8")
        ).hexdigest()
        return WikiChangeSet(
            change_id=f"stale-{digest[:24]}",
            operations=operations,
            source_hashes=[current_hash],
            compiler_version="wiki-maintenance-v1",
        )

    async def lint(self) -> WikiLintReport:
        pages = await self.repository.list_pages()
        page_ids = {page.page_id for page in pages}
        issues: list[WikiLintIssue] = []
        incoming: dict[str, int] = {page_id: 0 for page_id in page_ids}
        aliases: dict[str, str] = {}
        for page in pages:
            issues.extend(
                WikiLintIssue(code="invalid_page", message=message, page_id=page.page_id)
                for message in validate_page(page)
            )
            for link in page.links:
                if link.target_page_id not in page_ids:
                    issues.append(
                        WikiLintIssue(
                            code="dead_link",
                            message=f"missing target '{link.target_page_id}'",
                            page_id=page.page_id,
                        )
                    )
                else:
                    incoming[link.target_page_id] += 1
            for alias in [page.title, *page.aliases]:
                key = alias.strip().casefold()
                owner = aliases.get(key)
                if key and owner is not None and owner != page.page_id:
                    issues.append(
                        WikiLintIssue(
                            code="duplicate_alias",
                            message=f"alias '{alias}' also belongs to '{owner}'",
                            page_id=page.page_id,
                        )
                    )
                elif key:
                    aliases[key] = page.page_id
        for page in pages:
            if (
                page.page_type not in {"index", "source"}
                and not page.links
                and incoming[page.page_id] == 0
            ):
                issues.append(
                    WikiLintIssue(
                        code="orphan_page",
                        message="page has no incoming or outgoing links",
                        page_id=page.page_id,
                    )
                )
        return WikiLintReport(page_count=len(pages), issues=issues)
