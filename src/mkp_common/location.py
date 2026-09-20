"""Location reference utilities for PDF, EPUB, and DOCX documents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

DocFormat = Literal["pdf", "epub", "docx", "unknown"]


@dataclass(frozen=True)
class LocationRef:
    doc_format: DocFormat
    page_number: int | None = None
    spine_index: int | None = None
    anchor: str | None = None
    raw: str = ""

    def __str__(self) -> str:
        return self.raw or self.format()

    def format(self) -> str:
        if self.doc_format == "pdf":
            return f"pdf:p{self.page_number or 1}"
        elif self.doc_format == "docx":
            return f"docx:p{self.page_number or 1}"
        elif self.doc_format == "epub":
            spine = self.spine_index if self.spine_index is not None else 1
            if self.anchor:
                return f"epub:s{spine}#{self.anchor}"
            return f"epub:s{spine}"
        return self.raw or "unknown:0"


_PDF_REGEX = re.compile(r"^pdf:p(?P<page>\d+)$", re.IGNORECASE)
_DOCX_REGEX = re.compile(r"^docx:p(?P<page>\d+)$", re.IGNORECASE)
_EPUB_REGEX = re.compile(r"^epub:s(?P<spine>\d+)(?:#(?P<anchor>[\w\-.:]+))?$", re.IGNORECASE)


def parse_location_ref(ref_str: str) -> LocationRef:
    """Parse a location reference string into a LocationRef object."""
    ref_str = (ref_str or "").strip()
    if not ref_str:
        return LocationRef(doc_format="unknown", raw="")

    m = _PDF_REGEX.match(ref_str)
    if m:
        return LocationRef(
            doc_format="pdf",
            page_number=int(m.group("page")),
            raw=ref_str,
        )

    m = _DOCX_REGEX.match(ref_str)
    if m:
        return LocationRef(
            doc_format="docx",
            page_number=int(m.group("page")),
            raw=ref_str,
        )

    m = _EPUB_REGEX.match(ref_str)
    if m:
        spine = int(m.group("spine"))
        anchor = m.group("anchor")
        return LocationRef(
            doc_format="epub",
            spine_index=spine,
            page_number=spine,  # virtual page number corresponds to spine index
            anchor=anchor,
            raw=ref_str,
        )

    return LocationRef(doc_format="unknown", raw=ref_str)


def format_pdf_ref(page_number: int) -> str:
    return f"pdf:p{page_number}"


def format_docx_ref(page_number: int) -> str:
    return f"docx:p{page_number}"


def format_epub_ref(spine_index: int, anchor: str | None = None) -> str:
    if anchor:
        return f"epub:s{spine_index}#{anchor}"
    return f"epub:s{spine_index}"
