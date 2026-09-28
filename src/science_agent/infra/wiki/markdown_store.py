"""Filesystem adapter where Markdown is the authoritative Wiki content."""

import json
import re
from pathlib import Path

from science_agent.wiki.types import WikiPage

_HEADER = "<!-- science-agent-wiki "
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class MarkdownWikiStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, page_id: str) -> Path:
        if not _SAFE_ID.fullmatch(page_id):
            raise ValueError("Wiki page id contains unsupported characters.")
        return self.root / f"{page_id}.md"

    async def get(self, page_id: str) -> WikiPage | None:
        path = self._path(page_id)
        if not path.exists():
            return None
        return self._decode(path.read_text(encoding="utf-8"), page_id)

    async def list(self) -> list[WikiPage]:
        pages: list[WikiPage] = []
        for path in sorted(self.root.glob("*.md")):
            pages.append(self._decode(path.read_text(encoding="utf-8"), path.stem))
        return pages

    async def put(self, page: WikiPage, *, expected_version: int) -> WikiPage:
        current = await self.get(page.page_id)
        current_version = current.version if current is not None else 0
        if current_version != expected_version:
            raise RuntimeError(
                f"Wiki page {page.page_id} version conflict: expected {expected_version}, "
                f"found {current_version}."
            )
        path = self._path(page.page_id)
        temporary = path.with_suffix(".md.tmp")
        temporary.write_text(self._encode(page), encoding="utf-8")
        temporary.replace(path)
        return page

    def _encode(self, page: WikiPage) -> str:
        metadata = {
            "page_id": page.page_id,
            "title": page.title,
            "version": page.version,
            "source_snapshot_ids": page.source_snapshot_ids,
            "status": page.status,
            "stale_sources": page.stale_sources,
            "updated_at": page.updated_at,
        }
        # 元数据和正文同文件保存；Milvus 只索引正文，删除索引不会丢 Wiki 内容。
        return f"{_HEADER}{json.dumps(metadata, ensure_ascii=False)} -->\n{page.markdown.rstrip()}\n"

    def _decode(self, content: str, fallback_id: str) -> WikiPage:
        first, separator, markdown = content.partition("\n")
        if not first.startswith(_HEADER) or not first.endswith(" -->"):
            raise ValueError(f"Wiki page {fallback_id} is missing its metadata header.")
        metadata = json.loads(first[len(_HEADER) : -len(" -->")])
        return WikiPage(
            page_id=metadata.get("page_id", fallback_id),
            title=metadata["title"],
            markdown=markdown if separator else "",
            version=metadata["version"],
            source_snapshot_ids=list(metadata.get("source_snapshot_ids", [])),
            status=metadata.get("status", "fresh"),
            stale_sources=list(metadata.get("stale_sources", [])),
            updated_at=metadata["updated_at"],
        )
