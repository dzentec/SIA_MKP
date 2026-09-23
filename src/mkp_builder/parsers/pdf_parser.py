"""PDF Parser using Docling with picture cropping and table extraction."""

from __future__ import annotations

import io
import logging
from collections import defaultdict
from pathlib import Path

from typing import Any

try:
    from PIL import Image
except (ImportError, AttributeError):
    Image = None

try:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling_core.types.doc.labels import DocItemLabel
except ImportError:
    class DocumentConverter:  # type: ignore
        def __init__(self, **kwargs: Any):
            pass
        def convert(self, *args: Any, **kwargs: Any):
            raise NotImplementedError("docling is required for PDF parsing")

    class PdfFormatOption:  # type: ignore
        def __init__(self, **kwargs: Any):
            pass

    class InputFormat:  # type: ignore
        PDF = "pdf"

    class DocItemLabel:  # type: ignore
        PICTURE = "picture"
        TABLE = "table"
        SECTION_HEADER = "section_header"
        TEXT = "text"

try:
    import fitz  # type: ignore
except ImportError:
    fitz = None

from mkp_common.location import format_pdf_ref
from mkp_builder.ocr import build_pipeline_options, OcrProfile, OcrEngine
from mkp_builder.parsers.base import (
    ParsedDocument,
    ParsedPage,
    ParsedFigure,
    ParsedTable,
)

logger = logging.getLogger(__name__)


class PDFParser:
    """Parses PDF documents into structured pages, figures, and tables."""

    def __init__(
        self,
        profile: OcrProfile = "digital",
        ocr_engine: OcrEngine = "rapidocr",
        tessdata_path: str | None = None,
        images_scale: float = 2.0,
    ):
        self.profile = profile
        self.ocr_engine = ocr_engine
        try:
            self.pipeline_options = build_pipeline_options(
                profile=profile,
                ocr_engine=ocr_engine,
                tessdata_path=tessdata_path,
                images_scale=images_scale,
                generate_picture_images=True,
            )
            self.converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=self.pipeline_options)  # type: ignore
                }
            )
        except Exception:
            self.converter = None

    def _parse_with_pymupdf(
        self,
        pdf_path: Path,
        book_id: str,
        book_title: str,
        page_range: tuple[int, int] | None = None,
    ) -> ParsedDocument:
        if fitz is None:
            raise NotImplementedError("Neither docling nor fitz (PyMuPDF) is available for PDF parsing")

        logger.info("Parsing PDF with PyMuPDF for %s (book_id=%s)", pdf_path.name, book_id)
        doc = fitz.open(str(pdf_path))
        start_p = 1 if not page_range else page_range[0]
        end_p = len(doc) if not page_range else min(page_range[1], len(doc))

        pages_list: list[ParsedPage] = []
        fig_counter = 1

        for p_no in range(start_p, end_p + 1):
            page = doc[p_no - 1]
            text = page.get_text("text").strip()
            page_figs: list[ParsedFigure] = []

            # Extract embedded images
            images = page.get_images(full=True)
            for img_info in images:
                xref = img_info[0]
                try:
                    base_img = doc.extract_image(xref)
                    img_bytes = base_img.get("image")
                    img_ext = base_img.get("ext", "png")
                    width = base_img.get("width", 0)
                    height = base_img.get("height", 0)
                    if img_bytes and len(img_bytes) >= 2048 and width >= 80 and height >= 80:
                        fig_id = f"{book_id}_p{p_no:03d}_fig{fig_counter:02d}"
                        parsed_fig = ParsedFigure(
                            figure_id=fig_id,
                            page_number=p_no,
                            image_bytes=img_bytes,
                            format=img_ext,
                            location_ref=format_pdf_ref(p_no),
                        )
                        page_figs.append(parsed_fig)
                        fig_counter += 1
                except Exception as e:
                    logger.debug("Failed extracting image xref %d on page %d: %s", xref, p_no, e)

            parsed_p = ParsedPage(
                page_number=p_no,
                location_ref=format_pdf_ref(p_no),
                text_content=text,
                markdown_content=text,
                figures=page_figs,
                tables=[],
            )
            pages_list.append(parsed_p)

        doc.close()
        return ParsedDocument(
            book_id=book_id,
            title=book_title,
            format="pdf",
            pagination="physical",
            pages=pages_list,
            metadata={"num_pages": len(pages_list), "num_figures": sum(len(p.figures) for p in pages_list)},
        )

    def parse(
        self,
        pdf_path: Path | str,
        book_id: str,
        title: str | None = None,
        page_range: tuple[int, int] | None = None,
    ) -> ParsedDocument:
        pdf_path = Path(pdf_path)
        book_title = title or pdf_path.stem

        if self.converter is None:
            return self._parse_with_pymupdf(pdf_path, book_id, book_title, page_range)

        try:
            logger.info("Starting Docling PDF conversion for %s (book_id=%s)", pdf_path.name, book_id)
            kwargs = {}
            if page_range:
                kwargs["page_range"] = page_range
            conv_result = self.converter.convert(pdf_path, **kwargs)
            doc = conv_result.document
        except Exception as e:
            logger.warning("Docling conversion failed (%s), falling back to PyMuPDF", e)
            return self._parse_with_pymupdf(pdf_path, book_id, book_title, page_range)

        pages_dict: dict[int, ParsedPage] = {}
        page_figures: dict[int, list[ParsedFigure]] = defaultdict(list)
        page_tables: dict[int, list[ParsedTable]] = defaultdict(list)
        page_texts: dict[int, list[str]] = defaultdict(list)

        # 1. Extract Figures (Pictures)
        for idx, picture in enumerate(doc.pictures, start=1):
            page_no = 1
            bbox_coords = None
            if picture.prov:
                prov = picture.prov[0]
                page_no = prov.page_no
                if hasattr(prov, "bbox") and prov.bbox:
                    b = prov.bbox
                    bbox_coords = [b.l, b.t, b.r, b.b]

            caption_text = None
            if hasattr(picture, "caption") and picture.caption:
                caption_text = str(picture.caption)

            try:
                pil_image = picture.get_image(doc)
                if pil_image:
                    buf = io.BytesIO()
                    pil_image.save(buf, format="PNG")
                    img_bytes = buf.getvalue()

                    fig_id = f"{book_id}_p{page_no:03d}_fig{idx:02d}"
                    parsed_fig = ParsedFigure(
                        figure_id=fig_id,
                        page_number=page_no,
                        image_bytes=img_bytes,
                        format="png",
                        bbox=bbox_coords,
                        caption=caption_text,
                        location_ref=format_pdf_ref(page_no),
                    )
                    page_figures[page_no].append(parsed_fig)
            except Exception as e:
                logger.warning("Failed to extract image for picture %d on page %d: %s", idx, page_no, e)

        # 2. Extract Tables
        for idx, table in enumerate(doc.tables, start=1):
            page_no = 1
            if table.prov:
                page_no = table.prov[0].page_no

            try:
                md_repr = table.export_to_markdown()
            except Exception:
                md_repr = str(table)

            caption_text = None
            if hasattr(table, "caption") and table.caption:
                caption_text = str(table.caption)

            tbl_id = f"tbl_p{page_no:03d}_{idx:02d}"
            parsed_tbl = ParsedTable(
                table_id=tbl_id,
                page_number=page_no,
                markdown=md_repr,
                caption=caption_text,
                location_ref=format_pdf_ref(page_no),
            )
            page_tables[page_no].append(parsed_tbl)

        # 3. Extract text elements per page
        for item, _level in doc.iterate_items():
            if hasattr(item, "prov") and item.prov:
                p_no = item.prov[0].page_no
                if hasattr(item, "text") and item.text:
                    page_texts[p_no].append(item.text)

        # Determine all pages present
        all_page_nos = sorted(set(list(page_texts.keys()) + list(page_figures.keys()) + list(page_tables.keys())))
        if not all_page_nos:
            all_page_nos = [1]

        pages_list: list[ParsedPage] = []
        for p_no in all_page_nos:
            p_text = "\n".join(page_texts[p_no])
            p_figs = page_figures[p_no]
            p_tbls = page_tables[p_no]
            
            parsed_p = ParsedPage(
                page_number=p_no,
                location_ref=format_pdf_ref(p_no),
                text_content=p_text,
                markdown_content=p_text,
                figures=p_figs,
                tables=p_tbls,
            )
            pages_list.append(parsed_p)

        return ParsedDocument(
            book_id=book_id,
            title=book_title,
            format="pdf",
            pagination="physical",
            pages=pages_list,
            metadata={"num_pages": len(pages_list), "num_figures": sum(len(p.figures) for p in pages_list)},
        )
