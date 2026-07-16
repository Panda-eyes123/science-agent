"""Parent-child chunking that preserves source-element provenance."""

from dataclasses import dataclass
from hashlib import sha1

from science_agent.rag.types import ChildChunk, ChunkType, ParentChunk, SourceElement


@dataclass(slots=True)
class ChunkedPaper:
    parents: list[ParentChunk]
    children: list[ChildChunk]


class PaperChunker:
    """Build section-aware parent chunks and retrieval-sized child chunks."""

    def __init__(self, *, parent_max_chars: int = 3_200, child_max_chars: int = 900) -> None:
        if child_max_chars > parent_max_chars:
            raise ValueError("child_max_chars cannot exceed parent_max_chars")
        self.parent_max_chars = parent_max_chars
        self.child_max_chars = child_max_chars

    def chunk(self, elements: list[SourceElement]) -> ChunkedPaper:
        parents: list[ParentChunk] = []
        children: list[ChildChunk] = []
        pending: list[SourceElement] = []
        current_section: str | None = None

        def flush() -> None:
            if not pending:
                return
            parent, child_items = self._chunk_group(pending)
            parents.append(parent)
            children.extend(child_items)
            pending.clear()

        for element in elements:
            if element.element_type == "section_heading":
                if current_section is not None and element.section_kind != current_section:
                    flush()
                current_section = element.section_kind
            if not self._is_retrievable(element):
                continue
            if pending and (
                element.section_kind != pending[-1].section_kind
                or self._text_length(pending + [element]) > self.parent_max_chars
            ):
                flush()
            pending.append(element)
        flush()
        return ChunkedPaper(parents=parents, children=children)

    def _chunk_group(self, elements: list[SourceElement]) -> tuple[ParentChunk, list[ChildChunk]]:
        first = elements[0]
        paper_id = first.paper_id
        parent_id = self._stable_id("parent", paper_id, *[item.element_id for item in elements])
        parent_text = "\n\n".join(self._element_text(item) for item in elements).strip()
        pages = [item.page_no for item in elements if item.page_no is not None]
        chunk_type = self._group_type(elements)
        parent = ParentChunk(
            chunk_id=parent_id,
            paper_id=paper_id,
            section_kind=first.section_kind,
            text=parent_text,
            source_element_ids=[item.element_id for item in elements],
            chunk_type=chunk_type,
            page_start=min(pages) if pages else None,
            page_end=max(pages) if pages else None,
        )
        children: list[ChildChunk] = []
        for ordinal, child_elements in enumerate(self._split_children(elements)):
            children.append(
                ChildChunk(
                    chunk_id=self._stable_id("child", parent_id, str(ordinal)),
                    parent_chunk_id=parent_id,
                    paper_id=paper_id,
                    section_kind=first.section_kind,
                    text="\n\n".join(self._element_text(item) for item in child_elements).strip(),
                    source_element_ids=[item.element_id for item in child_elements],
                    chunk_type=self._group_type(child_elements),
                    ordinal=ordinal,
                )
            )
        return parent, children

    def _split_children(self, elements: list[SourceElement]) -> list[list[SourceElement]]:
        groups: list[list[SourceElement]] = []
        pending: list[SourceElement] = []
        for element in elements:
            if pending and self._text_length(pending + [element]) > self.child_max_chars:
                groups.append(pending)
                pending = []
            pending.append(element)
        if pending:
            groups.append(pending)
        return groups

    @staticmethod
    def _stable_id(prefix: str, *parts: str) -> str:
        digest = sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]
        return f"{prefix}-{digest}"

    @staticmethod
    def _is_retrievable(element: SourceElement) -> bool:
        return bool(PaperChunker._element_text(element)) and element.element_type not in {"reference", "section_heading"}

    @staticmethod
    def _element_text(element: SourceElement) -> str:
        if element.element_type == "table" and element.table_markdown:
            return element.table_markdown
        if element.element_type == "figure":
            return "\n".join(part for part in (element.text, element.raw_payload.get("caption", "")) if part)
        return element.text

    @staticmethod
    def _text_length(elements: list[SourceElement]) -> int:
        return sum(len(PaperChunker._element_text(item)) for item in elements)

    @staticmethod
    def _group_type(elements: list[SourceElement]) -> ChunkType:
        kinds = {element.element_type for element in elements}
        if kinds == {"table"}:
            return "table"
        if kinds == {"figure"}:
            return "figure"
        if kinds == {"formula"}:
            return "formula"
        return "mixed" if len(kinds) > 1 else "text"
