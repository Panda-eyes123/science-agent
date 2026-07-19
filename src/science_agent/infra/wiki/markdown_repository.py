"""Markdown-backed canonical Wiki repository with revision checks."""

import asyncio
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from science_agent.wiki.errors import WikiConflictError, WikiNotFoundError
from science_agent.wiki.types import (
    SourceRef,
    WikiApplyResult,
    WikiChangeSet,
    WikiClaim,
    WikiLink,
    WikiPage,
    utc_now_iso,
)
from science_agent.wiki.validation import ensure_valid_changeset, validate_page_id


class MarkdownWikiRepository:
    """Store each Wiki aggregate as one human-readable Markdown file.

    Metadata is JSON inside standard ``---`` front matter. JSON is valid YAML,
    so files remain compatible with common Markdown knowledge tools without
    adding a YAML dependency to the SDK.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.changes_dir = self.root / ".changes"
        self._lock = Lock()

    async def get_page(self, page_id: str) -> WikiPage | None:
        return await asyncio.to_thread(self._get_page, page_id)

    async def list_pages(self) -> list[WikiPage]:
        return await asyncio.to_thread(self._list_pages)

    async def apply(self, changeset: WikiChangeSet) -> WikiApplyResult:
        return await asyncio.to_thread(self._apply, changeset)

    def _get_page(self, page_id: str) -> WikiPage | None:
        path = self._page_path(page_id)
        if not path.is_file():
            return None
        return self._deserialize(path.read_text(encoding="utf-8"))

    def _list_pages(self) -> list[WikiPage]:
        if not self.root.is_dir():
            return []
        pages = [
            self._deserialize(path.read_text(encoding="utf-8"))
            for path in self.root.rglob("*.md")
            if self.changes_dir not in path.parents
        ]
        pages.sort(key=lambda page: page.page_id)
        return pages

    def _apply(self, changeset: WikiChangeSet) -> WikiApplyResult:
        with self._lock:
            return self._apply_locked(changeset)

    def _apply_locked(self, changeset: WikiChangeSet) -> WikiApplyResult:
        ensure_valid_changeset(changeset)
        if self._audit_exists(changeset):
            page_ids = sorted({operation.page_id for operation in changeset.operations})
            pages = [self._get_page(page_id) for page_id in page_ids]
            return WikiApplyResult(
                change_id=changeset.change_id,
                changed_pages=[page for page in pages if page is not None],
            )
        relevant_ids = {
            operation.page_id for operation in changeset.operations
        } | {
            operation.target_page_id
            for operation in changeset.operations
            if operation.target_page_id is not None
        } | {
            link.target_page_id
            for operation in changeset.operations
            if operation.page is not None
            for link in operation.page.links
        }
        original = {page_id: self._get_page(page_id) for page_id in relevant_ids}
        working = deepcopy(original)
        changed_ids: set[str] = set()
        checked_revisions: dict[str, int] = {}

        for operation in changeset.operations:
            current = working.get(operation.page_id)
            if operation.operation == "create_page":
                if current is not None:
                    raise WikiConflictError(
                        f"page '{operation.page_id}' already exists"
                    )
                assert operation.page is not None
                working[operation.page_id] = replace(
                    deepcopy(operation.page),
                    revision=1,
                    created_at=utc_now_iso(),
                    updated_at=utc_now_iso(),
                )
                changed_ids.add(operation.page_id)
                continue

            current = self._require_page(operation.page_id, current)
            self._check_revision(
                operation.page_id,
                operation.expected_revision,
                original,
                checked_revisions,
            )
            if operation.operation == "update_page":
                assert operation.page is not None
                working[operation.page_id] = replace(
                    deepcopy(operation.page),
                    revision=current.revision,
                    created_at=current.created_at,
                    updated_at=current.updated_at,
                )
            elif operation.operation == "link_pages":
                target_id = operation.target_page_id
                assert target_id is not None
                self._require_page(target_id, working.get(target_id))
                link = WikiLink(target_page_id=target_id, relation=operation.relation)
                if link not in current.links:
                    current.links.append(link)
            elif operation.operation == "mark_conflict":
                current.status = "conflicting"
            elif operation.operation == "mark_stale":
                current.status = "stale"
            changed_ids.add(operation.page_id)

        timestamp = utc_now_iso()
        for page_id in changed_ids:
            page = working[page_id]
            assert page is not None
            for link in page.links:
                self._require_page(link.target_page_id, working.get(link.target_page_id))
            original_page = original.get(page_id)
            if original_page is not None:
                page.revision = original_page.revision + 1
                page.created_at = original_page.created_at
            page.updated_at = timestamp

        changed_pages = [working[page_id] for page_id in sorted(changed_ids)]
        for page in changed_pages:
            assert page is not None
            self._write_page(page)
        self._write_audit(changeset)
        return WikiApplyResult(
            change_id=changeset.change_id,
            changed_pages=[page for page in changed_pages if page is not None],
        )

    @staticmethod
    def _require_page(page_id: str, page: WikiPage | None) -> WikiPage:
        if page is None:
            raise WikiNotFoundError(f"page '{page_id}' does not exist")
        return page

    @staticmethod
    def _check_revision(
        page_id: str,
        expected: int | None,
        original: dict[str, WikiPage | None],
        checked: dict[str, int],
    ) -> None:
        base = original.get(page_id)
        if base is None:
            if expected != 0:
                raise WikiConflictError(
                    f"new page '{page_id}' expects revision 0, got {expected}"
                )
            checked[page_id] = 0
            return
        if page_id in checked:
            if checked[page_id] != expected:
                raise WikiConflictError(
                    f"changeset uses inconsistent revisions for page '{page_id}'"
                )
            return
        if expected != base.revision:
            raise WikiConflictError(
                f"page '{page_id}' revision is {base.revision}, expected {expected}"
            )
        checked[page_id] = base.revision

    def _page_path(self, page_id: str) -> Path:
        issues = validate_page_id(page_id)
        if issues:
            raise ValueError(issues[0])
        path = (self.root / f"{page_id}.md").resolve()
        if self.root != path and self.root not in path.parents:
            raise ValueError(f"page_id escapes Wiki root: {page_id}")
        return path

    def _write_page(self, page: WikiPage) -> None:
        path = self._page_path(page.page_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        temporary.write_text(self._serialize(page), encoding="utf-8")
        temporary.replace(path)

    def _write_audit(self, changeset: WikiChangeSet) -> None:
        self.changes_dir.mkdir(parents=True, exist_ok=True)
        path = self._audit_path(changeset.change_id)
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if self._comparable_changeset(existing) != self._comparable_changeset(
                asdict(changeset)
            ):
                raise WikiConflictError(
                    f"change_id '{changeset.change_id}' was reused with new content"
                )
            return
        path.write_text(
            json.dumps(asdict(changeset), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _audit_exists(self, changeset: WikiChangeSet) -> bool:
        path = self._audit_path(changeset.change_id)
        if not path.is_file():
            return False
        existing = json.loads(path.read_text(encoding="utf-8"))
        if self._comparable_changeset(existing) != self._comparable_changeset(
            asdict(changeset)
        ):
            raise WikiConflictError(
                f"change_id '{changeset.change_id}' was reused with new content"
            )
        return True

    def _audit_path(self, change_id: str) -> Path:
        audit_id = sha256(change_id.encode("utf-8")).hexdigest()[:20]
        return self.changes_dir / f"{audit_id}.json"

    @staticmethod
    def _comparable_changeset(payload: dict[str, Any]) -> dict[str, Any]:
        comparable = dict(payload)
        comparable.pop("created_at", None)
        return comparable

    @staticmethod
    def _serialize(page: WikiPage) -> str:
        page.content_hash = MarkdownWikiRepository._content_hash(page)
        metadata = asdict(page)
        body = metadata.pop("body")
        front_matter = json.dumps(metadata, ensure_ascii=False, indent=2)
        return f"---\n{front_matter}\n---\n\n{body.rstrip()}\n"

    @staticmethod
    def _deserialize(content: str) -> WikiPage:
        if not content.startswith("---\n"):
            raise ValueError("Wiki page is missing JSON front matter")
        front_matter, separator, body = content[4:].partition("\n---\n")
        if not separator:
            raise ValueError("Wiki page front matter is not terminated")
        payload: dict[str, Any] = json.loads(front_matter)
        payload["body"] = body.strip()
        payload["claims"] = [
            WikiClaim(
                **{
                    **claim,
                    "sources": [SourceRef(**source) for source in claim["sources"]],
                }
            )
            for claim in payload.get("claims", [])
        ]
        payload["links"] = [WikiLink(**link) for link in payload.get("links", [])]
        page = WikiPage(**payload)
        stored_hash = page.content_hash
        actual_hash = MarkdownWikiRepository._content_hash(page)
        if stored_hash is not None and stored_hash != actual_hash:
            page.revision += 1
            page.updated_at = utc_now_iso()
        page.content_hash = actual_hash
        return page

    @staticmethod
    def _content_hash(page: WikiPage) -> str:
        payload = asdict(page)
        for field_name in ("content_hash", "revision", "created_at", "updated_at"):
            payload.pop(field_name, None)
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(encoded).hexdigest()
