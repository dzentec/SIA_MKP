"""DOCX Parser for Word manuals."""

from __future__ import annotations

import io
import logging
from pathlib import Path
from docx import Document
from PIL import Image

from mkp_common.location import format_docx_ref
from mkp_builder.parsers.base import (
    ParsedDocument,
    ParsedPage,
    ParsedFigure,
    ParsedTable,
)

logger = logging.getLogger(__name__)


class DOCXParser:
    """Parses DOCX files into pages, extracting text, tables, and embedded figures."""

    def parse(
        self,
        docx_path: Path | str,
        book_id: str,
        title: str | None = None,
    ) -> ParsedDocument:
        docx_path = Path(docx_path)
        logger.info("Starting DOCX parsing for %s (book_id=%s)", docx_path.name, book_id)

        doc = Document(docx_path)
        book_title = title or docx_path.stem

        # Extract images from docx package parts
        figures: list[ParsedFigure] = []
        fig_idx = 1
        for rel in doc.part.rels.values():
            if "image" in rel.target_ref:
                img_part = rel.target_part
                img_data = img_part.blob
                try:
                    im = Image.open(io.BytesIO(img_data))
                    buf = io.BytesIO()
                    im.convert("RGB").save(buf, format="PNG")
                    png_bytes = buf.getvalue()
                except Exception:
                    png_bytes = img_data

                fig_id = f"{book_id}_p001_fig{fig_idx:02d}"
                figures.append(
                    ParsedFigure(
                        figure_id=fig_id,
                        page_number=1,
                        image_bytes=png_bytes,
                        format="png",
                        location_ref=format_docx_ref(1),
                    )
                )
                fig_idx += 1

        # Extract tables
        tables: list[ParsedTable] = []
        for t_idx, tbl in enumerate(doc.tables, start=1):
            rows_md = []
            for row in tbl.rows:
                cells = [cell.text.strip() for cell in row.cells]
                rows_md.append(" | ".join(cells))
            if rows_md:
                tables.append(
                    ParsedTable(
                        table_id=f"tbl_p001_{t_idx:02d}",
                        page_number=1,
                        markdown="\n".join(rows_md),
                        location_ref=format_docx_ref(1),
                    )
                )

        # Extract text paragraphs
        paragraphs_text = [p.text for p in doc.paragraphs if p.text.strip()]
        full_text = "\n\n".join(paragraphs_text)

        parsed_page = ParsedPage(
            page_number=1,
            location_ref=format_docx_ref(1),
            text_content=full_text,
            markdown_content=full_text,
            figures=figures,
            tables=tables,
        )

        return ParsedDocument(
            book_id=book_id,
            title=book_title,
            format="docx",
            pagination="physical",
            pages=[parsed_page],
            metadata={"num_figures": len(figures), "num_tables": len(tables)},
        )
