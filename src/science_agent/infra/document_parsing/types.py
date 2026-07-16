"""Document parsing protocol."""

from pathlib import Path
from typing import Protocol

from science_agent.rag.types import PaperDocument, SourceElement


class DocumentParser(Protocol):
    def parse(self, path: str | Path, *, paper_id: str | None = None) -> tuple[PaperDocument, list[SourceElement]]: ...
