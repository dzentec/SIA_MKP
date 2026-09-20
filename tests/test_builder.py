"""Integration and unit tests for mkp-builder pipeline."""

import json
from pathlib import Path
import pytest

from mkp_common.models import (
    DiagramType,
    VlmData,
    TermsBilingual,
    VerificationResult,
)
from mkp_builder.parsers.base import (
    ParsedDocument,
    ParsedPage,
    ParsedFigure,
    ParsedTable,
)
from mkp_builder.chunker import SectionAwareChunker, count_tokens
from mkp_builder.vlm.verifier import VLMVerifier
from mkp_builder.vlm.client import OllamaClient
from mkp_builder.pipeline import BuilderPipeline


def test_chunker_basic():
    doc = ParsedDocument(
        book_id="test_book",
        title="Test Book",
        format="pdf",
        pagination="physical",
        pages=[
            ParsedPage(
                page_number=1,
                location_ref="pdf:p1",
                text_content="Section 1\n\nThis is paragraph one about mainsail trim.\n\nThis is paragraph two.",
                tables=[
                    ParsedTable(
                        table_id="tbl_p001_01",
                        page_number=1,
                        markdown="| Heading | Value |\n|---|---|\n| Wind | 20kt |",
                        caption="Wind table",
                    )
                ],
            ),
            ParsedPage(
                page_number=2,
                location_ref="pdf:p2",
                text_content="Section 2\n\nThis is page 2 content explaining knots.",
            ),
        ],
    )

    chunker = SectionAwareChunker(max_tokens=100, overlap=20)
    chunks = chunker.chunk_document(doc)

    assert len(chunks) >= 3
    # Check table chunk
    tbl_chunk = next(c for c in chunks if c.tables)
    assert tbl_chunk.location_ref == "pdf:p1"
    assert tbl_chunk.tables[0].table_id == "tbl_p001_01"


def test_verifier_schema_validation():
    client = OllamaClient()
    verifier = VLMVerifier(client=client)

    # Valid knot
    vlm_valid = VlmData(
        model="qwen2.5vl:7b",
        prompt_ver="2.0",
        diagram_type=DiagramType.KNOT,
        description="Figure showing knot",
        structured={"knot": {"knot_name": "bowline", "purpose": "loop"}},
        terms=TermsBilingual(ru=["булинь"], en=["bowline"]),
    )
    ok, issues = verifier.verify_schema(vlm_valid)
    assert ok is True
    assert len(issues) == 0

    # Invalid structured key (mismatch with diagram_type)
    vlm_invalid = VlmData(
        model="qwen2.5vl:7b",
        prompt_ver="2.0",
        diagram_type=DiagramType.KNOT,
        description="Figure showing knot",
        structured={"maneuver": {"maneuver_type": "tack"}},
        terms=TermsBilingual(),
    )
    ok_inv, issues_inv = verifier.verify_schema(vlm_invalid)
    assert ok_inv is False
    assert len(issues_inv) > 0


def test_builder_pipeline_fast(tmp_path: Path):
    epub_file = Path(".init_doc/source_doc/Illustrated Seamanship (Ivar Dedekam) (z-library.sk, 1lib.sk, z-lib.sk).epub")
    if not epub_file.exists():
        pytest.skip("EPUB sample not found")

    pipeline = BuilderPipeline(
        work_dir=tmp_path / "work",
        headless=True,
    )

    # Fast test with skip_vlm=True & skip_triplets=True to test parsing + chunking + export end-to-end
    zip_path = pipeline.build_book(
        book_path=epub_file,
        book_id="test_dedekam",
        profile="digital",
        lang="en",
        skip_vlm=True,
        skip_triplets=True,
    )

    assert zip_path.exists()
    assert zip_path.name == "test_dedekam.bookpack.zip"

    book_dir = tmp_path / "work" / "books" / "test_dedekam"
    assert book_dir.exists()
    assert (book_dir / "chunks.jsonl").exists()
    assert (book_dir / "pages.jsonl").exists()
    assert (book_dir / "book_metadata.json").exists()
    assert (book_dir / "ingest_report.md").exists()
    assert (book_dir / "assets").is_dir()

    # Read chunks
    with open(book_dir / "chunks.jsonl", "r", encoding="utf-8") as f:
        chunk_lines = [json.loads(line) for line in f]
    assert len(chunk_lines) > 0
    assert chunk_lines[0]["book_id"] == "test_dedekam"
    assert chunk_lines[0]["location_ref"].startswith("epub:s")
