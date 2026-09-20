"""Section and Table-Aware Chunking Engine (REQ-B05)."""

from __future__ import annotations

import logging
import re
from typing import Any
from mkp_common.models import ChunkRecord, VisualAsset, TableItem
from mkp_builder.parsers.base import ParsedPage, ParsedDocument

logger = logging.getLogger(__name__)


def count_tokens(text: str) -> int:
    """Approximate token count for multilingual English/Russian text (~3.8 chars/token)."""
    if not text:
        return 0
    # Use word-based + subword estimation
    words = len(text.split())
    chars = len(text)
    return max(words, int(chars / 3.8))


class SectionAwareChunker:
    """Splits parsed pages into section-aware and table-aware chunks."""

    def __init__(
        self,
        max_tokens: int = 512,
        overlap: int = 64,
        default_lang: str = "en",
    ):
        self.max_tokens = max_tokens
        self.overlap = overlap
        self.default_lang = default_lang

    def _split_into_paragraphs(self, text: str) -> list[str]:
        """Split text by double newlines or section headings."""
        paragraphs = re.split(r"\n\s*\n", text.strip())
        return [p.strip() for p in paragraphs if p.strip()]

    def chunk_document(
        self,
        doc: ParsedDocument,
        visual_assets_by_page: dict[int, list[VisualAsset]] | None = None,
    ) -> list[ChunkRecord]:
        """Convert a ParsedDocument into a list of ChunkRecords."""
        chunks: list[ChunkRecord] = []
        visual_map = visual_assets_by_page or {}

        chunk_counter = 1

        for page in doc.pages:
            p_no = page.page_number
            p_loc = page.location_ref
            page_assets = visual_map.get(p_no, [])

            # 1. Process Tables as Standalone Chunks (REQ-B05)
            for tbl in page.tables:
                table_item = TableItem(
                    table_id=tbl.table_id,
                    markdown_repr=tbl.markdown,
                    caption=tbl.caption,
                )
                tbl_text = f"{tbl.caption or 'Table'}\n\n{tbl.markdown}"
                tbl_chunk = ChunkRecord(
                    chunk_id=f"{doc.book_id}_p{p_no:03d}_c{chunk_counter:02d}",
                    book_id=doc.book_id,
                    lang=self.default_lang,
                    page_number=p_no,
                    location_ref=p_loc,
                    section_path=page.title or f"Page {p_no}",
                    text_content=tbl_text,
                    tables=[table_item],
                    n_tokens=count_tokens(tbl_text),
                )
                chunks.append(tbl_chunk)
                chunk_counter += 1

            # 2. Process Text Content with Section / Paragraph Splitting
            paragraphs = self._split_into_paragraphs(page.markdown_content or page.text_content)
            
            if not paragraphs and not page.tables and page_assets:
                # Page has figures but no text: create a figure chunk
                fig_chunk = ChunkRecord(
                    chunk_id=f"{doc.book_id}_p{p_no:03d}_c{chunk_counter:02d}",
                    book_id=doc.book_id,
                    lang=self.default_lang,
                    page_number=p_no,
                    location_ref=p_loc,
                    section_path=page.title or f"Page {p_no}",
                    text_content="",
                    visual_assets=page_assets,
                    n_tokens=0,
                )
                chunks.append(fig_chunk)
                chunk_counter += 1
                continue

            current_text_parts: list[str] = []
            current_tokens = 0
            assets_assigned = False

            for para in paragraphs:
                para_tokens = count_tokens(para)

                if current_tokens + para_tokens > self.max_tokens and current_text_parts:
                    # Flush current chunk
                    chunk_text = "\n\n".join(current_text_parts)
                    chunk_rec = ChunkRecord(
                        chunk_id=f"{doc.book_id}_p{p_no:03d}_c{chunk_counter:02d}",
                        book_id=doc.book_id,
                        lang=self.default_lang,
                        page_number=p_no,
                        location_ref=p_loc,
                        section_path=page.title or f"Page {p_no}",
                        text_content=chunk_text,
                        visual_assets=page_assets if not assets_assigned else [],
                        n_tokens=count_tokens(chunk_text),
                    )
                    chunks.append(chunk_rec)
                    chunk_counter += 1
                    assets_assigned = True

                    # Overlap handling
                    overlap_parts = []
                    overlap_tokens = 0
                    for p in reversed(current_text_parts):
                        tok = count_tokens(p)
                        if overlap_tokens + tok <= self.overlap:
                            overlap_parts.insert(0, p)
                            overlap_tokens += tok
                        else:
                            break
                    current_text_parts = overlap_parts + [para]
                    current_tokens = count_tokens("\n\n".join(current_text_parts))
                else:
                    current_text_parts.append(para)
                    current_tokens += para_tokens

            # Flush remaining chunk on this page
            if current_text_parts:
                chunk_text = "\n\n".join(current_text_parts)
                chunk_rec = ChunkRecord(
                    chunk_id=f"{doc.book_id}_p{p_no:03d}_c{chunk_counter:02d}",
                    book_id=doc.book_id,
                    lang=self.default_lang,
                    page_number=p_no,
                    location_ref=p_loc,
                    section_path=page.title or f"Page {p_no}",
                    text_content=chunk_text,
                    visual_assets=page_assets if not assets_assigned else [],
                    n_tokens=count_tokens(chunk_text),
                )
                chunks.append(chunk_rec)
                chunk_counter += 1

        logger.info(
            "Chunking completed for %s: generated %d chunks from %d pages",
            doc.book_id,
            len(chunks),
            len(doc.pages),
        )
        return chunks
