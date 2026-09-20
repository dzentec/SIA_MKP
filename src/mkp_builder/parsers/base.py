"""Base definitions and data structures for document parsers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from mkp_common.location import LocationRef


@dataclass
class ParsedFigure:
    figure_id: str
    page_number: int
    image_bytes: bytes
    format: str = "png"
    bbox: list[float] | None = None
    caption: str | None = None
    location_ref: str = ""


@dataclass
class ParsedTable:
    table_id: str
    page_number: int
    markdown: str
    caption: str | None = None
    location_ref: str = ""


@dataclass
class ParsedPage:
    page_number: int
    location_ref: str
    text_content: str = ""
    markdown_content: str = ""
    ocr_text: str | None = None
    ocr_confidence_low: bool = False
    figures: list[ParsedFigure] = field(default_factory=list)
    tables: list[ParsedTable] = field(default_factory=list)
    spine_href: str | None = None
    title: str | None = None


@dataclass
class ParsedDocument:
    book_id: str
    title: str
    format: Literal["pdf", "epub", "docx"]
    pagination: Literal["physical", "virtual_spine"]
    pages: list[ParsedPage] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
