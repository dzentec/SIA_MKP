"""Tests for document parsers."""

from pathlib import Path
import pytest
from mkp_builder.parsers import get_parser, EPUBParser, PDFParser


def test_epub_parser_real():
    epub_file = Path(".init_doc/source_doc/Illustrated Seamanship (Ivar Dedekam) (z-library.sk, 1lib.sk, z-lib.sk).epub")
    if not epub_file.exists():
        pytest.skip("EPUB sample not found")

    parser = EPUBParser()
    doc = parser.parse(epub_file, book_id="dedekam_seamanship")

    assert doc.book_id == "dedekam_seamanship"
    assert doc.format == "epub"
    assert doc.pagination == "virtual_spine"
    assert len(doc.pages) > 10

    # Verify figures extracted
    total_figs = sum(len(p.figures) for p in doc.pages)
    assert total_figs > 0

    first_fig = next(f for p in doc.pages for f in p.figures)
    assert first_fig.figure_id.startswith("dedekam_seamanship_")
    assert first_fig.location_ref.startswith("epub:s")
    assert len(first_fig.image_bytes) > 0


def test_get_parser_factory():
    p_pdf = get_parser("test.pdf")
    assert isinstance(p_pdf, PDFParser)

    p_epub = get_parser("test.epub")
    assert isinstance(p_epub, EPUBParser)
