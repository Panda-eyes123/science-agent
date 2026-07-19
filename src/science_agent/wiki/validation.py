"""Deterministic validation for LLM- or human-authored Wiki changes."""

import re

from science_agent.wiki.errors import WikiValidationError
from science_agent.wiki.types import WikiChangeSet, WikiPage

_PAGE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9/_-]*$")
_MAX_PAGE_CHARS = 50_000
_MAX_INDEX_CHARS = 60_000


def validate_page_id(page_id: str) -> list[str]:
    if len(page_id) > 240:
        return [f"page_id exceeds 240 characters: '{page_id}'"]
    if not _PAGE_ID_PATTERN.fullmatch(page_id):
        return [
            f"invalid page_id '{page_id}'; use lowercase letters, digits, '/', '_' or '-'"
        ]
    if "//" in page_id or page_id.endswith("/"):
        return [f"invalid page_id path '{page_id}'"]
    return []


def validate_page(page: WikiPage) -> list[str]:
    issues = validate_page_id(page.page_id)
    if not page.title.strip():
        issues.append(f"page '{page.page_id}' has no title")
    elif len(page.title) > 1_000:
        issues.append(f"page '{page.page_id}' title exceeds 1000 characters")
    if not page.body.strip():
        issues.append(f"page '{page.page_id}' has no body")
    if len(page.body) > _MAX_PAGE_CHARS:
        issues.append(f"page '{page.page_id}' exceeds {_MAX_PAGE_CHARS} characters")
    index_chars = sum(
        len(value)
        for value in [page.title, *page.aliases, page.body]
    ) + sum(len(claim.text) for claim in page.claims)
    if index_chars > _MAX_INDEX_CHARS:
        issues.append(
            f"page '{page.page_id}' index text exceeds {_MAX_INDEX_CHARS} characters"
        )
    if page.revision < 0:
        issues.append(f"page '{page.page_id}' has a negative revision")

    claim_ids: set[str] = set()
    for claim in page.claims:
        if not claim.claim_id.strip():
            issues.append(f"page '{page.page_id}' contains a claim without an id")
        elif claim.claim_id in claim_ids:
            issues.append(f"page '{page.page_id}' repeats claim '{claim.claim_id}'")
        claim_ids.add(claim.claim_id)
        if not claim.text.strip():
            issues.append(f"claim '{claim.claim_id}' has no text")
        if not claim.sources:
            issues.append(f"claim '{claim.claim_id}' has no raw source reference")
        for source in claim.sources:
            if not source.paper_id or not source.element_id:
                issues.append(
                    f"claim '{claim.claim_id}' has an incomplete source reference"
                )
        if claim.confidence is not None and not 0 <= claim.confidence <= 1:
            issues.append(f"claim '{claim.claim_id}' confidence must be between 0 and 1")

    seen_links: set[tuple[str, str]] = set()
    for link in page.links:
        issues.extend(validate_page_id(link.target_page_id))
        if link.target_page_id == page.page_id:
            issues.append(f"page '{page.page_id}' links to itself")
        if not link.relation.strip():
            issues.append(f"page '{page.page_id}' contains a link without a relation")
        link_key = (link.target_page_id, link.relation)
        if link_key in seen_links:
            issues.append(
                f"page '{page.page_id}' repeats link to '{link.target_page_id}'"
            )
        seen_links.add(link_key)
    return issues


def validate_changeset(changeset: WikiChangeSet) -> list[str]:
    issues: list[str] = []
    if not changeset.change_id.strip():
        issues.append("changeset has no change_id")
    if not changeset.operations:
        issues.append("changeset contains no operations")
    for operation in changeset.operations:
        issues.extend(validate_page_id(operation.page_id))
        if operation.operation in {"create_page", "update_page"}:
            if operation.page is None:
                issues.append(f"{operation.operation} requires a page payload")
            else:
                if operation.page.page_id != operation.page_id:
                    issues.append(
                        f"operation page_id '{operation.page_id}' does not match payload"
                    )
                issues.extend(validate_page(operation.page))
        if operation.operation != "create_page" and operation.expected_revision is None:
            issues.append(f"{operation.operation} requires expected_revision")
        if operation.operation == "link_pages":
            if operation.target_page_id is None:
                issues.append("link_pages requires target_page_id")
            else:
                issues.extend(validate_page_id(operation.target_page_id))
            if not operation.relation.strip():
                issues.append("link_pages requires a relation")
        elif operation.target_page_id is not None:
            issues.append(f"{operation.operation} cannot set target_page_id")
    return issues


def ensure_valid_page(page: WikiPage) -> None:
    issues = validate_page(page)
    if issues:
        raise WikiValidationError(issues)


def ensure_valid_changeset(changeset: WikiChangeSet) -> None:
    issues = validate_changeset(changeset)
    if issues:
        raise WikiValidationError(issues)
