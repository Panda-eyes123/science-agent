"""Resolve exported Docling figures or crop them from the source PDF."""

import asyncio
from hashlib import sha1
from pathlib import Path

from science_agent.infra.visual_assets.region_renderer import PDFRegionRenderer
from science_agent.rag.multimodal.types import VisualAsset
from science_agent.rag.types import PaperDocument, SourceElement


class PDFVisualAssetResolver:
    def __init__(
        self,
        *,
        artifact_root: str | Path = "./data/paper_artifacts",
        crop_root: str | Path = "./data/paper_crops",
        renderer: PDFRegionRenderer | None = None,
    ) -> None:
        self.artifact_root = Path(artifact_root)
        self.crop_root = Path(crop_root)
        self.renderer = renderer or PDFRegionRenderer()

    async def resolve(
        self,
        element: SourceElement,
        paper: PaperDocument,
        *,
        context: str = "",
    ) -> VisualAsset | None:
        return await asyncio.to_thread(self._resolve, element, paper, context)

    def _resolve(
        self, element: SourceElement, paper: PaperDocument, context: str
    ) -> VisualAsset | None:
        caption = element.raw_payload.get("caption") or element.text
        exported = self._exported_path(element.image_path)
        if exported is not None and exported.is_file():
            width, height = self._image_dimensions(exported)
            return VisualAsset(
                element_id=element.element_id,
                paper_id=element.paper_id,
                image_path=str(exported.resolve()),
                source="docling_export",
                page_no=element.page_no,
                bbox=element.bbox,
                element_type=element.element_type,
                caption=caption,
                context=context,
                width=width,
                height=height,
            )
        if element.page_no is None or element.bbox is None:
            return None
        digest = sha1(element.element_id.encode("utf-8")).hexdigest()[:16]
        paper_digest = sha1(element.paper_id.encode("utf-8")).hexdigest()[:16]
        output = self.crop_root / f"paper-{paper_digest}" / f"visual-{digest}.png"
        rendered = self.renderer.render(
            paper.source_path,
            page_no=element.page_no,
            bbox=element.bbox,
            output_path=output,
            coord_origin=element.raw_payload.get("coord_origin"),
        )
        return VisualAsset(
            element_id=element.element_id,
            paper_id=element.paper_id,
            image_path=str(rendered.path),
            source="pdf_crop",
            page_no=element.page_no,
            bbox=element.bbox,
            element_type=element.element_type,
            caption=caption,
            context=context,
            width=rendered.width,
            height=rendered.height,
        )

    def _exported_path(self, image_path: str | None) -> Path | None:
        if not image_path:
            return None
        path = Path(image_path)
        if path.is_absolute():
            return path
        root = self.artifact_root.resolve()
        candidate = (root / path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        return candidate

    @staticmethod
    def _image_dimensions(path: Path) -> tuple[int | None, int | None]:
        try:
            import fitz
        except ModuleNotFoundError:  # pragma: no cover - optional enrichment
            return None, None
        try:
            pixmap = fitz.Pixmap(str(path))
        except (RuntimeError, ValueError):
            return None, None
        return pixmap.width, pixmap.height
