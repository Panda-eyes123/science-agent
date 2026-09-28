"""Build immutable RawSourceSnapshot records from the existing RAG parser output."""

import hashlib
import json
from dataclasses import asdict
from uuid import uuid4

from science_agent.rag.types import PaperDocument, SourceElement

from .types import RawSourceSnapshot


def create_source_snapshot(
    paper: PaperDocument,
    elements: list[SourceElement],
    *,
    version: int,
    snapshot_id: str | None = None,
) -> RawSourceSnapshot:
    payload = [asdict(element) for element in elements]
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    content_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return RawSourceSnapshot(
        snapshot_id=snapshot_id or f"snap_{uuid4().hex}",
        paper_id=paper.paper_id,
        source_path=paper.source_path,
        content_hash=content_hash,
        version=version,
        elements=tuple(elements),
    )
