"""Render a page region from a PDF using normalized coordinates."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True, frozen=True)
class RenderedRegion:
    path: Path
    width: int
    height: int


def normalize_pdf_bbox(
    bbox: tuple[float, float, float, float],
    *,
    page_width: float,
    page_height: float,
    coord_origin: str | None,
    padding: float = 0,
) -> tuple[float, float, float, float]:
    """Convert bottom-left or top-left coordinates into PyMuPDF coordinates."""
    left, top, right, bottom = bbox
    if "bottom" in (coord_origin or "").lower():
        top, bottom = page_height - top, page_height - bottom
    x0, x1 = sorted((left, right))
    y0, y1 = sorted((top, bottom))
    x0 = max(0.0, x0 - padding)
    y0 = max(0.0, y0 - padding)
    x1 = min(page_width, x1 + padding)
    y1 = min(page_height, y1 + padding)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("The normalized PDF region has no visible area.")
    return x0, y0, x1, y1


class PDFRegionRenderer:
    def __init__(self, *, zoom: float = 2.5, padding: float = 12.0) -> None:
        if zoom <= 0:
            raise ValueError("zoom must be positive")
        self.zoom = zoom
        self.padding = padding

    def render(
        self,
        pdf_path: str | Path,
        *,
        page_no: int,
        bbox: tuple[float, float, float, float],
        output_path: str | Path,
        coord_origin: str | None = None,
    ) -> RenderedRegion:
        try:
            import fitz
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency boundary
            raise ModuleNotFoundError(
                "PDF region rendering requires PyMuPDF. "
                "Install with `pip install science-agent[rag]`."
            ) from exc

        source = Path(pdf_path)
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with fitz.open(source) as document:
            if page_no < 1 or page_no > document.page_count:
                raise ValueError(
                    f"Page {page_no} is outside the PDF page range 1-{document.page_count}."
                )
            page = document[page_no - 1]
            x0, y0, x1, y1 = normalize_pdf_bbox(
                bbox,
                page_width=page.rect.width,
                page_height=page.rect.height,
                coord_origin=coord_origin,
                padding=self.padding,
            )
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(self.zoom, self.zoom),
                clip=fitz.Rect(x0, y0, x1, y1),
                alpha=False,
            )
            pixmap.save(target)
            return RenderedRegion(
                path=target.resolve(), width=pixmap.width, height=pixmap.height
            )
