"""Docling-first PDF parser with a PyMuPDF text fallback."""

from hashlib import sha1
from pathlib import Path
import re
from typing import Any, Iterable

from science_agent.rag.routing import classify_section
from science_agent.rag.types import ElementType, PaperDocument, SectionKind, SourceElement


class PyMuPDFPageResolver:
    """Small auxiliary adapter for page-level text and dimensions."""

    def extract_blocks(self, path: Path) -> Iterable[tuple[int, tuple[float, float, float, float], str]]:
        try:
            import fitz
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency boundary
            raise ModuleNotFoundError(
                "PDF fallback requires PyMuPDF. Install with `pip install science-agent[rag]`."
            ) from exc
        with fitz.open(path) as document:
            for page_number, page in enumerate(document, start=1):
                for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
                    cleaned = text.strip()
                    if cleaned:
                        yield page_number, (x0, y0, x1, y1), cleaned


class DoclingPDFParser:
    """Extract source elements while retaining the parser's native payload."""

    def __init__(
        self,
        *,
        page_resolver: PyMuPDFPageResolver | None = None,
        artifact_dir: str | Path = "./data/paper_artifacts",
    ) -> None:
        self.page_resolver = page_resolver or PyMuPDFPageResolver()
        self.artifact_dir = Path(artifact_dir)

    def parse(self, path: str | Path, *, paper_id: str | None = None) -> tuple[PaperDocument, list[SourceElement]]:
        file_path = Path(path).resolve()
        if not file_path.is_file():
            raise FileNotFoundError(file_path)
        resolved_paper_id = paper_id or self._paper_id(file_path)
        try:
            elements = self._parse_with_docling(file_path, resolved_paper_id)
        except ModuleNotFoundError:
            elements = self._parse_with_pymupdf(file_path, resolved_paper_id)
        title = next((item.text for item in elements if item.element_type == "title"), None)
        return (
            PaperDocument(
                paper_id=resolved_paper_id,
                source_path=str(file_path),
                title=title,
                metadata={"parser": "docling" if elements and elements[0].raw_payload.get("parser") == "docling" else "pymupdf"},
            ),
            elements,
        )

    def _parse_with_docling(self, path: Path, paper_id: str) -> list[SourceElement]:
        try:
            from docling.document_converter import DocumentConverter
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency boundary
            raise ModuleNotFoundError("Docling is not installed") from exc
        result = DocumentConverter().convert(str(path))
        document = result.document
        elements: list[SourceElement] = []
        active_section: SectionKind = "other"
        for ordinal, entry in enumerate(document.iterate_items()):
            item = entry[0] if isinstance(entry, tuple) else entry
            element_type = self._element_type(item)
            text = str(getattr(item, "text", "") or "").strip()
            table_markdown = self._table_markdown(item) if element_type == "table" else None
            if element_type == "section_heading":
                active_section = classify_section(text)
            elif element_type == "title":
                active_section = "background"
            if not text and not table_markdown and element_type not in {"figure", "formula"}:
                continue
            page_no, bbox, coord_origin = self._provenance(item)
            raw_payload: dict[str, Any] = {
                "parser": "docling",
                "docling_type": type(item).__name__,
            }
            if coord_origin:
                raw_payload["coord_origin"] = coord_origin
            caption = self._caption(item)
            if caption:
                raw_payload["caption"] = caption
            image_path = None
            if element_type == "figure":
                image_path, image_width, image_height = self._write_figure_image(
                    item, document, paper_id, ordinal
                )
                if image_width is not None:
                    raw_payload["image_width"] = image_width
                if image_height is not None:
                    raw_payload["image_height"] = image_height
            elements.append(
                SourceElement(
                    element_id=f"{paper_id}:docling:{ordinal}",
                    paper_id=paper_id,
                    page_no=page_no,
                    bbox=bbox,
                    element_type=element_type,
                    section_kind=active_section,
                    text=text or caption,
                    table_markdown=table_markdown,
                    image_path=image_path,
                    raw_payload=raw_payload,
                )
            )
        if not elements:
            raise ValueError(f"Docling did not extract usable content from {path}")
        return elements

    def _parse_with_pymupdf(self, path: Path, paper_id: str) -> list[SourceElement]:
        elements: list[SourceElement] = []
        active_section: SectionKind = "other"
        for ordinal, (page_no, bbox, text) in enumerate(self.page_resolver.extract_blocks(path)):
            element_type: ElementType = "title" if ordinal == 0 else "paragraph"
            guessed_section = classify_section(text) if len(text) < 140 else "other"
            if guessed_section != "other":
                active_section = guessed_section
                element_type = "section_heading"
            elements.append(
                SourceElement(
                    element_id=f"{paper_id}:pymupdf:{ordinal}",
                    paper_id=paper_id,
                    page_no=page_no,
                    bbox=bbox,
                    element_type=element_type,
                    section_kind=active_section,
                    text=text,
                    raw_payload={
                        "parser": "pymupdf",
                        "coord_origin": "top_left",
                    },
                )
            )
        return elements

    @staticmethod
    def _paper_id(path: Path) -> str:
        digest = sha1(str(path).encode("utf-8")).hexdigest()[:16]
        return f"paper-{digest}"

    @staticmethod
    def _element_type(item: object) -> ElementType:
        label = str(getattr(item, "label", "") or type(item).__name__).lower()
        if "title" in label:
            return "title"
        if "section" in label or "heading" in label:
            return "section_heading"
        if "table" in label:
            return "table"
        if "figure" in label or "picture" in label or "image" in label:
            return "figure"
        if "caption" in label:
            return "caption"
        if "formula" in label or "equation" in label:
            return "formula"
        if "list" in label:
            return "list"
        if "code" in label:
            return "code"
        if "reference" in label:
            return "reference"
        return "paragraph"

    @staticmethod
    def _provenance(
        item: object,
    ) -> tuple[
        int | None,
        tuple[float, float, float, float] | None,
        str | None,
    ]:
        provenance = getattr(item, "prov", None) or []
        first = provenance[0] if provenance else None
        if first is None:
            return None, None, None
        bbox = getattr(first, "bbox", None)
        coordinates = None
        coord_origin = None
        if bbox is not None:
            coordinates = tuple(float(getattr(bbox, key)) for key in ("l", "t", "r", "b"))
            origin = getattr(bbox, "coord_origin", None)
            if origin is not None:
                coord_origin = str(getattr(origin, "value", origin)).lower()
        return getattr(first, "page_no", None), coordinates, coord_origin

    @staticmethod
    def _caption(item: object) -> str:
        captions = getattr(item, "captions", None) or []
        values = [str(getattr(caption, "text", "") or "").strip() for caption in captions]
        return " ".join(value for value in values if value)

    @staticmethod
    def _table_markdown(item: object) -> str | None:
        exporter = getattr(item, "export_to_markdown", None)
        if callable(exporter):
            value = exporter()
            return str(value).strip() or None
        data = getattr(item, "data", None)
        exporter = getattr(data, "export_to_markdown", None)
        if callable(exporter):
            value = exporter()
            return str(value).strip() or None
        return None

    def resolve_image(self, image_path: str) -> Path:
        """Reconstruct an absolute path for a stored relative figure reference."""
        return (self.artifact_dir / image_path).resolve()

    def _write_figure_image(
        self, item: object, document: object, paper_id: str, ordinal: int
    ) -> tuple[str | None, int | None, int | None]:
        """Persist Docling's rendered figure only when the item exposes one."""
        get_image = getattr(item, "get_image", None)
        if not callable(get_image):
            return None, None, None
        try:
            image = get_image(document)
        except (AttributeError, TypeError, ValueError):
            return None, None, None
        if image is None:
            return None, None, None
        safe_paper_id = re.sub(r"[^A-Za-z0-9._-]", "_", paper_id).strip(".")
        safe_paper_id = safe_paper_id or self._paper_id(Path(paper_id))
        target_dir = self.artifact_dir / safe_paper_id
        target_dir.mkdir(parents=True, exist_ok=True)
        relative = Path(safe_paper_id) / f"figure-{ordinal}.png"
        target = self.artifact_dir / relative
        try:
            image.save(target)
        except (AttributeError, OSError, ValueError):
            return None, None, None
        return (
            str(relative).replace("\\", "/"),
            getattr(image, "width", None),
            getattr(image, "height", None),
        )
