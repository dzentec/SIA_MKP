"""EPUB Parser using ebooklib and zipfile fallback with spine mapping."""

from __future__ import annotations

import io
import logging
import re
import zipfile
from pathlib import Path
from bs4 import BeautifulSoup
import ebooklib
from ebooklib import epub
from PIL import Image

from mkp_common.location import format_epub_ref
from mkp_builder.parsers.base import (
    ParsedDocument,
    ParsedPage,
    ParsedFigure,
    ParsedTable,
)

logger = logging.getLogger(__name__)


class EPUBParser:
    """Parses EPUB documents into virtual spine pages with bound figures and tables."""

    def parse(
        self,
        epub_path: Path | str,
        book_id: str,
        title: str | None = None,
    ) -> ParsedDocument:
        epub_path = Path(epub_path)
        logger.info("Starting EPUB parsing for %s (book_id=%s)", epub_path.name, book_id)

        book = epub.read_epub(str(epub_path))
        book_title = title or book.get_metadata("DC", "title")
        if isinstance(book_title, list) and book_title:
            book_title = book_title[0][0] if isinstance(book_title[0], tuple) else str(book_title[0])
        else:
            book_title = str(book_title or epub_path.stem)

        # 1. Extract all image items from zip container
        image_bytes_map: dict[str, bytes] = {}
        with zipfile.ZipFile(epub_path, "r") as zf:
            for name in zf.namelist():
                lower_name = name.lower()
                if lower_name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
                    image_bytes_map[Path(name).name] = zf.read(name)
                    image_bytes_map[name] = image_bytes_map[Path(name).name]

        # 2. Iterate spine items (virtual pages)
        pages_list: list[ParsedPage] = []
        spine_items = book.spine

        figure_idx = 1
        table_idx = 1

        for spine_idx, spine_entry in enumerate(spine_items, start=1):
            item_id = spine_entry[0] if isinstance(spine_entry, tuple) else spine_entry
            item = book.get_item_with_id(item_id)
            if not item:
                continue

            raw_content = item.get_content().decode("utf-8", errors="replace")
            soup = BeautifulSoup(raw_content, "html.parser")

            # Page Title
            h1 = soup.find(["h1", "h2", "title"])
            page_title = h1.get_text(strip=True) if h1 else None

            # Location ref
            loc_ref = format_epub_ref(spine_idx)

            # Extract Figures
            page_figures: list[ParsedFigure] = []
            for img_tag in soup.find_all("img"):
                src = img_tag.get("src", "")
                img_filename = Path(src).name
                img_data = image_bytes_map.get(img_filename) or image_bytes_map.get(src)
                
                if img_data:
                    # Convert to PNG if needed
                    try:
                        im = Image.open(io.BytesIO(img_data))
                        buf = io.BytesIO()
                        im.convert("RGB").save(buf, format="PNG")
                        png_bytes = buf.getvalue()
                    except Exception:
                        png_bytes = img_data

                    alt = img_tag.get("alt")
                    anchor = img_tag.get("id")
                    fig_ref = format_epub_ref(spine_idx, anchor)

                    fig_id = f"{book_id}_s{spine_idx:03d}_fig{figure_idx:02d}"
                    parsed_fig = ParsedFigure(
                        figure_id=fig_id,
                        page_number=spine_idx,
                        image_bytes=png_bytes,
                        format="png",
                        caption=alt,
                        location_ref=fig_ref,
                    )
                    page_figures.append(parsed_fig)
                    figure_idx += 1

            # Extract Tables
            page_tables: list[ParsedTable] = []
            for tbl_tag in soup.find_all("table"):
                rows = []
                for tr in tbl_tag.find_all("tr"):
                    cols = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                    if cols:
                        rows.append(" | ".join(cols))
                
                if rows:
                    md_table = "\n".join(rows)
                    tbl_id = f"tbl_s{spine_idx:03d}_{table_idx:02d}"
                    parsed_tbl = ParsedTable(
                        table_id=tbl_id,
                        page_number=spine_idx,
                        markdown=md_table,
                        location_ref=loc_ref,
                    )
                    page_tables.append(parsed_tbl)
                    table_idx += 1

            # Clean text content
            text_content = soup.get_text(separator="\n", strip=True)

            parsed_page = ParsedPage(
                page_number=spine_idx,
                location_ref=loc_ref,
                text_content=text_content,
                markdown_content=text_content,
                figures=page_figures,
                tables=page_tables,
                spine_href=item.get_name(),
                title=page_title,
            )
            pages_list.append(parsed_page)

        return ParsedDocument(
            book_id=book_id,
            title=book_title,
            format="epub",
            pagination="virtual_spine",
            pages=pages_list,
            metadata={
                "num_spine_items": len(pages_list),
                "num_figures": sum(len(p.figures) for p in pages_list),
            },
        )
