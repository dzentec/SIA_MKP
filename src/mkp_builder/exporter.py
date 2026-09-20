"""Archive Exporter and Manifest Generator for .bookpack.zip (REQ-B07, Schema v1.5)."""

from __future__ import annotations

import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mkp_common.cache import compute_sha256_file, compute_sha256_bytes
from mkp_common.models import (
    BookpackManifest,
    BuilderInfo,
    EmbedModelInfo,
    ManifestCounts,
)

logger = logging.getLogger(__name__)


class BookpackExporter:
    """Packages processed book components into a validated .bookpack.zip archive."""

    def __init__(
        self,
        embed_model_name: str = "intfloat/multilingual-e5-large",
        embed_dim: int = 1024,
    ):
        self.embed_model_name = embed_model_name
        self.embed_dim = embed_dim

    def export_archive(
        self,
        book_dir: Path | str,
        out_dir: Path | str,
        book_id: str,
        title: str | None = None,
        lang: list[str] | None = None,
        pipeline_profile: str = "digital",
        pagination: str = "physical",
    ) -> Path:
        """Export book directory into {out_dir}/{book_id}.bookpack.zip with manifest."""
        book_dir = Path(book_dir)
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        zip_path = out_dir / f"{book_id}.bookpack.zip"
        logger.info("Packing book %s into archive: %s", book_id, zip_path)

        # 1. Inspect existing files and count entities
        pages_file = book_dir / "pages.jsonl"
        chunks_file = book_dir / "chunks.jsonl"
        triplets_file = book_dir / "triplets.jsonl"
        qa_file = book_dir / "qa_review_queue.jsonl"
        meta_file = book_dir / "book_metadata.json"
        assets_dir = book_dir / "assets"

        # Ensure empty files exist if not yet written
        for f in [pages_file, chunks_file, triplets_file, qa_file]:
            if not f.exists():
                f.touch()

        # Read counts
        def count_lines(filepath: Path) -> int:
            if not filepath.exists():
                return 0
            with open(filepath, "r", encoding="utf-8") as fp:
                return sum(1 for line in fp if line.strip())

        n_pages = count_lines(pages_file)
        n_chunks = count_lines(chunks_file)
        n_triples = count_lines(triplets_file)
        n_needs_review = count_lines(qa_file)

        asset_files = sorted(assets_dir.glob("*.png")) if assets_dir.exists() else []
        n_figures = len(asset_files)

        # Read book_metadata title if available
        book_title = title or book_id
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as fp:
                    meta_data = json.load(fp)
                    book_title = meta_data.get("title", book_title)
                    pagination = meta_data.get("pagination", pagination)
                    pipeline_profile = meta_data.get("pipeline_profile", pipeline_profile)
                    if not lang and meta_data.get("lang"):
                        lang = meta_data.get("lang")
            except Exception:
                pass

        # 2. Compute SHA-256 for all archive payload files
        files_sha256: dict[str, str] = {}
        files_to_pack: list[tuple[Path, str]] = []

        # JSONL / metadata files
        payload_files = [
            (book_metadata := meta_file, "book_metadata.json"),
            (pages_file, "pages.jsonl"),
            (chunks_file, "chunks.jsonl"),
            (triplets_file, "triplets.jsonl"),
            (qa_file, "qa_review_queue.jsonl"),
        ]

        for p_path, rel_name in payload_files:
            if p_path.exists():
                sha = compute_sha256_file(p_path)
                files_sha256[rel_name] = sha
                files_to_pack.append((p_path, rel_name))

        # Assets
        for asset in asset_files:
            rel_name = f"assets/{asset.name}"
            sha = compute_sha256_file(asset)
            files_sha256[rel_name] = sha
            files_to_pack.append((asset, rel_name))

        # 3. Build bookpack.json manifest
        manifest = BookpackManifest(
            artifact="bookpack",
            schema_version="1.5",
            book_id=book_id,
            title=book_title,
            lang=lang or ["en"],
            pagination=pagination,  # type: ignore
            pipeline_profile=pipeline_profile,  # type: ignore
            builder=BuilderInfo(
                product="mkp-builder",
                version="1.5.0",
                vlm="qwen2.5vl:7b@prompt2.0",
                ocr="rapidocr[ru,en]",
            ),
            embed_model=EmbedModelInfo(
                name=self.embed_model_name,
                dim=self.embed_dim,
            ),
            counts=ManifestCounts(
                pages=n_pages,
                chunks=n_chunks,
                figures=n_figures,
                triples=n_triples,
                needs_review=n_needs_review,
            ),
            files_sha256=files_sha256,
        )

        manifest_json_bytes = manifest.model_dump_json(indent=2).encode("utf-8")

        # 4. Write zip archive
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Write bookpack.json as the first entry
            zf.writestr("bookpack.json", manifest_json_bytes)

            # Write all other payload files
            for file_path, arcname in files_to_pack:
                zf.write(file_path, arcname=arcname)

        logger.info(
            "Successfully created archive %s (%d files, %.2f MB)",
            zip_path.name,
            len(files_to_pack) + 1,
            zip_path.stat().st_size / (1024 * 1024),
        )
        return zip_path


def verify_bookpack_archive(archive_path: Path | str) -> tuple[bool, list[str]]:
    """Verify integrity of a .bookpack.zip file against its embedded bookpack.json manifest."""
    archive_path = Path(archive_path)
    issues = []

    if not archive_path.exists():
        return False, [f"Archive file not found: {archive_path}"]

    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            # 1. Check bookpack.json exists
            if "bookpack.json" not in zf.namelist():
                return False, ["Archive is missing bookpack.json manifest"]

            manifest_bytes = zf.read("bookpack.json")
            manifest_data = json.loads(manifest_bytes.decode("utf-8"))

            # 2. Check schema major version
            schema_ver = str(manifest_data.get("schema_version", ""))
            if not schema_ver.startswith("1."):
                issues.append(f"Incompatible schema version: {schema_ver} (expected 1.x)")

            # 3. Check every file in files_sha256
            files_sha256 = manifest_data.get("files_sha256", {})
            for rel_path, expected_sha in files_sha256.items():
                if rel_path not in zf.namelist():
                    issues.append(f"Missing file in archive: {rel_path}")
                    continue

                actual_bytes = zf.read(rel_path)
                actual_sha = compute_sha256_bytes(actual_bytes)
                if actual_sha != expected_sha:
                    issues.append(
                        f"Checksum mismatch for {rel_path}: expected {expected_sha}, got {actual_sha}"
                    )

    except Exception as e:
        return False, [f"Corrupted zip archive: {e}"]

    is_valid = len(issues) == 0
    return is_valid, issues
