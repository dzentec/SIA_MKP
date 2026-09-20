"""Unit tests for mkp_common package."""

import json
from pathlib import Path
import pytest

from mkp_common.models import (
    DiagramType,
    VlmData,
    VisualAsset,
    ChunkRecord,
    PageRecord,
    QaReviewItem,
    BookMetadata,
    BookpackManifest,
    TermsBilingual,
    VerificationResult,
)
from mkp_common.location import parse_location_ref, format_pdf_ref, format_epub_ref, format_docx_ref
from mkp_common.cache import PersistentCache, make_cache_key, compute_sha256_bytes


def test_location_ref():
    ref_pdf = parse_location_ref("pdf:p42")
    assert ref_pdf.doc_format == "pdf"
    assert ref_pdf.page_number == 42
    assert str(ref_pdf) == "pdf:p42"

    ref_epub = parse_location_ref("epub:s12#fig_01")
    assert ref_epub.doc_format == "epub"
    assert ref_epub.spine_index == 12
    assert ref_epub.anchor == "fig_01"
    assert str(ref_epub) == "epub:s12#fig_01"

    assert format_pdf_ref(10) == "pdf:p10"
    assert format_epub_ref(5, "sec1") == "epub:s5#sec1"
    assert format_docx_ref(3) == "docx:p3"


def test_pydantic_models(tmp_path: Path):
    vlm = VlmData(
        model="qwen2.5vl:7b",
        prompt_ver="2.0",
        diagram_type=DiagramType.KNOT,
        description="Figure showing bowline knot tying sequence",
        structured={"knot": {"knot_name": "bowline", "purpose": "secure loop"}},
        terms=TermsBilingual(ru=["булинь", "беседочный узел"], en=["bowline knot"]),
        verification=VerificationResult(schema_status="pass", text_check="pass", visual_check="pass"),
    )

    asset = VisualAsset(
        image_path="assets/book_p01_fig01.png",
        image_sha256="abc123sha",
        vlm_data=vlm,
    )

    chunk = ChunkRecord(
        chunk_id="book_p01_c01",
        book_id="book",
        lang="en",
        page_number=1,
        location_ref="pdf:p1",
        section_path="Chapter 1 > Knots",
        text_content="The bowline is an ancient and essential loop knot.",
        visual_assets=[asset],
        n_tokens=45,
    )

    dumped = chunk.model_dump(by_alias=True)
    assert dumped["chunk_id"] == "book_p01_c01"
    assert dumped["visual_assets"][0]["vlm_data"]["diagram_type"] == "knot"
    assert dumped["visual_assets"][0]["vlm_data"]["terms"]["ru"] == ["булинь", "беседочный узел"]


def test_persistent_cache(tmp_path: Path):
    cache_file = tmp_path / "cache.json"
    cache = PersistentCache(cache_file)

    key = make_cache_key("img_sha", "qwen2.5vl:7b", "2.0")
    cache.set(key, {"diagram_type": "maneuver", "description": "Tacking maneuver"})
    cache.flush()

    assert cache_file.exists()

    # Re-open
    cache2 = PersistentCache(cache_file)
    assert cache2.contains(key)
    val = cache2.get(key)
    assert val["diagram_type"] == "maneuver"
