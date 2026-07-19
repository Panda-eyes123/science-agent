"""JSON-backed storage for reviewable Wiki changesets."""

import asyncio
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from science_agent.wiki.errors import WikiConflictError
from science_agent.wiki.types import (
    SourceRef,
    WikiChangeSet,
    WikiClaim,
    WikiLink,
    WikiOperation,
    WikiPage,
)


class JsonWikiDraftStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self._lock = Lock()

    async def save(self, changeset: WikiChangeSet) -> None:
        await asyncio.to_thread(self._save, changeset)

    async def get(self, change_id: str) -> WikiChangeSet | None:
        return await asyncio.to_thread(self._get, change_id)

    async def list(self) -> list[WikiChangeSet]:
        return await asyncio.to_thread(self._list)

    async def delete(self, change_id: str) -> None:
        await asyncio.to_thread(self._delete, change_id)

    def _save(self, changeset: WikiChangeSet) -> None:
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            path = self._path(change_id=changeset.change_id)
            payload = asdict(changeset)
            if path.is_file():
                existing = json.loads(path.read_text(encoding="utf-8"))
                if existing != payload:
                    raise WikiConflictError(
                        f"draft '{changeset.change_id}' already has different content"
                    )
                return
            temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(path)

    def _get(self, change_id: str) -> WikiChangeSet | None:
        path = self._path(change_id=change_id)
        if not path.is_file():
            return None
        return self._deserialize(json.loads(path.read_text(encoding="utf-8")))

    def _list(self) -> list[WikiChangeSet]:
        if not self.root.is_dir():
            return []
        drafts = [
            self._deserialize(json.loads(path.read_text(encoding="utf-8")))
            for path in self.root.glob("*.json")
        ]
        drafts.sort(key=lambda item: item.created_at)
        return drafts

    def _delete(self, change_id: str) -> None:
        with self._lock:
            path = self._path(change_id=change_id)
            if path.exists():
                path.unlink()

    def _path(self, *, change_id: str) -> Path:
        name = sha256(change_id.encode("utf-8")).hexdigest()[:24]
        return self.root / f"{name}.json"

    @staticmethod
    def _deserialize(payload: dict[str, Any]) -> WikiChangeSet:
        operations: list[WikiOperation] = []
        for raw_operation in payload.get("operations", []):
            raw_page = raw_operation.get("page")
            page = None
            if raw_page is not None:
                page = WikiPage(
                    **{
                        **raw_page,
                        "claims": [
                            WikiClaim(
                                **{
                                    **claim,
                                    "sources": [
                                        SourceRef(**source)
                                        for source in claim.get("sources", [])
                                    ],
                                }
                            )
                            for claim in raw_page.get("claims", [])
                        ],
                        "links": [
                            WikiLink(**link) for link in raw_page.get("links", [])
                        ],
                    }
                )
            operations.append(WikiOperation(**{**raw_operation, "page": page}))
        return WikiChangeSet(**{**payload, "operations": operations})
