"""Unit tests for BookpackExporter and archive integrity verification."""

import json
import zipfile
from pathlib import Path
from mkp_builder.exporter import BookpackExporter, verify_bookpack_archive


def test_export_and_verify(tmp_path: Path):
    book_dir = tmp_path / "sample_book"
    book_dir.mkdir()
    assets_dir = book_dir / "assets"
    assets_dir.mkdir()

    # Create dummy files
    (book_dir / "pages.jsonl").write_text('{"page": 1}\n', encoding="utf-8")
    (book_dir / "chunks.jsonl").write_text('{"chunk_id": "c1"}\n', encoding="utf-8")
    (book_dir / "triplets.jsonl").write_text('{"subject": "s"}\n', encoding="utf-8")
    (book_dir / "qa_review_queue.jsonl").write_text("", encoding="utf-8")
    (book_dir / "book_metadata.json").write_text(
        json.dumps({"title": "Sample Book", "pagination": "physical"}), encoding="utf-8"
    )
    (assets_dir / "sample_p001_fig01.png").write_bytes(b"\x89PNG\r\n\x1a\nDummyPNGBytes")

    out_dir = tmp_path / "out"
    exporter = BookpackExporter()

    zip_path = exporter.export_archive(
        book_dir=book_dir,
        out_dir=out_dir,
        book_id="sample_book",
        title="Sample Book",
    )

    assert zip_path.exists()
    assert zip_path.name == "sample_book.bookpack.zip"

    # Verify zip content
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        assert "bookpack.json" in names
        assert "pages.jsonl" in names
        assert "chunks.jsonl" in names
        assert "triplets.jsonl" in names
        assert "qa_review_queue.jsonl" in names
        assert "assets/sample_p001_fig01.png" in names

        # Parse manifest
        manifest = json.loads(zf.read("bookpack.json").decode("utf-8"))
        assert manifest["artifact"] == "bookpack"
        assert manifest["schema_version"] == "1.5"
        assert manifest["counts"]["pages"] == 1
        assert manifest["counts"]["chunks"] == 1
        assert manifest["counts"]["figures"] == 1
        assert "pages.jsonl" in manifest["files_sha256"]
        assert "assets/sample_p001_fig01.png" in manifest["files_sha256"]

    # Test verify_bookpack_archive
    is_valid, issues = verify_bookpack_archive(zip_path)
    assert is_valid is True
    assert len(issues) == 0


def test_verify_corrupted_archive(tmp_path: Path):
    corrupt_zip = tmp_path / "bad.zip"
    with zipfile.ZipFile(corrupt_zip, "w") as zf:
        zf.writestr("some_file.txt", "hello")

    is_valid, issues = verify_bookpack_archive(corrupt_zip)
    assert is_valid is False
    assert any("missing bookpack.json" in issue.lower() for issue in issues)
