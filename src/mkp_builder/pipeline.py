"""Core Builder Pipeline Orchestrator (REQ-B01..B10)."""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from mkp_common.cache import PersistentCache, compute_sha256_bytes
from mkp_common.logger import setup_builder_logger
from mkp_common.models import (
    ChunkRecord,
    PageRecord,
    QaReviewItem,
    VisualAsset,
    BookMetadata,
    TripletRecord,
)
from mkp_builder.parsers import get_parser
from mkp_builder.parsers.base import ParsedDocument
from mkp_builder.vlm.client import OllamaClient
from mkp_builder.vlm.annotator import VLMAnnotator
from mkp_builder.vlm.verifier import VLMVerifier
from mkp_builder.triplets import TripletExtractor
from mkp_builder.chunker import SectionAwareChunker
from mkp_builder.exporter import BookpackExporter, verify_bookpack_archive
from mkp_builder.tui import BuilderProgressTracker

logger = logging.getLogger("mkp_builder")


class BuilderPipeline:
    """End-to-end processing pipeline for a single manual."""

    def __init__(
        self,
        work_dir: Path | str = "./work",
        out_dir: Path | str | None = None,
        ollama_host: str = "http://127.0.0.1:11434",
        vlm_model: str = "qwen2.5vl:7b",
        text_model: str = "qwen2.5:7b",
        max_tokens: int = 512,
        overlap: int = 64,
        force: bool = False,
        headless: bool = False,
    ):
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.out_dir = Path(out_dir) if out_dir else self.work_dir / "out"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.force = force
        self.headless = headless

        # Logging setup
        self.logger = setup_builder_logger(self.work_dir / "logs")

        # Cache setup
        cache_file = self.work_dir / "cache" / "vlm_cache.json"
        self.cache = PersistentCache(cache_file)
        if force:
            self.logger.info("Force flag enabled: clearing cache.")
            self.cache.clear()

        # Ollama client and components
        self.ollama = OllamaClient(
            host=ollama_host,
            vlm_model=vlm_model,
            text_model=text_model,
        )
        self.annotator = VLMAnnotator(client=self.ollama, cache=self.cache, model=vlm_model)
        self.verifier = VLMVerifier(
            client=self.ollama,
            cache=self.cache,
            text_model=text_model,
            vlm_model=vlm_model,
        )
        self.triplet_extractor = TripletExtractor(
            client=self.ollama,
            cache=self.cache,
            model=text_model,
        )
        self.chunker = SectionAwareChunker(max_tokens=max_tokens, overlap=overlap)
        self.exporter = BookpackExporter()
        self.tui = BuilderProgressTracker(headless=headless)

    def build_book(
        self,
        book_path: Path | str,
        book_id: str | None = None,
        profile: Literal["digital", "scanned", "mixed"] = "digital",
        lang: str = "en",
        title: str | None = None,
        ocr_engine: Literal["rapidocr", "tesseract"] = "rapidocr",
        tessdata_path: str | None = None,
        skip_vlm: bool = False,
        skip_triplets: bool = False,
    ) -> Path:
        start_time = time.time()
        book_path = Path(book_path)
        actual_book_id = book_id or book_path.stem.replace(" ", "_").lower()

        # Directory structure for this book run
        book_out_dir = self.work_dir / "books" / actual_book_id
        assets_dir = book_out_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info("Starting build for book: %s (id: %s)", book_path.name, actual_book_id)

        self.tui.start()
        self.tui.add_stage("parse", "1. Parsing Layout & Figures", total=100)
        self.tui.add_stage("vlm", "2. VLM Annotation & Verification", total=100)
        self.tui.add_stage("chunk", "3. Section-Aware Chunking", total=100)
        self.tui.add_stage("triplets", "4. Triplet Extraction (GraphRAG)", total=100)
        self.tui.add_stage("export", "5. Packaging .bookpack.zip Archive", total=100)

        # 1. Parse Document
        parser = get_parser(
            file_path=book_path,
            profile=profile,
            ocr_engine=ocr_engine,
            tessdata_path=tessdata_path,
        )
        doc: ParsedDocument = parser.parse(
            file_path if (file_path := book_path) else book_path,
            book_id=actual_book_id,
            title=title,
        )
        self.tui.update_stage("parse", completed=100)
        self.tui.stats["pages"] = len(doc.pages)

        # Count total figures
        all_figures = [fig for page in doc.pages for fig in page.figures]
        self.tui.stats["figures"] = len(all_figures)
        self.tui.update_stage("vlm", completed=0, total=max(len(all_figures), 1))

        # 2. Process Figures (Save PNG + VLM Annotate + Verify)
        visual_assets_by_page: dict[int, list[VisualAsset]] = defaultdict(list)
        qa_review_items: list[QaReviewItem] = []

        if (not skip_vlm or not skip_triplets) and (all_figures or doc.pages):
            self.ollama.ensure_server()

        for idx, fig in enumerate(all_figures, start=1):
            fig_rel_path = f"assets/{fig.figure_id}.png"
            fig_abs_path = book_out_dir / fig_rel_path
            
            # Save PNG asset
            if not fig_abs_path.exists() or self.force:
                with open(fig_abs_path, "wb") as f:
                    f.write(fig.image_bytes)

            img_sha = compute_sha256_bytes(fig.image_bytes)

            vlm_data = None
            if not skip_vlm:
                # Annotation
                vlm_data, hit = self.annotator.annotate(fig.image_bytes, img_sha)
                if hit:
                    self.tui.stats["vlm_cache_hits"] += 1
                else:
                    self.tui.stats["vlm_api_calls"] += 1

                # Verification
                vlm_data, qa_item = self.verifier.verify(
                    vlm_data=vlm_data,
                    image_bytes=fig.image_bytes,
                    image_sha256=img_sha,
                    book_id=actual_book_id,
                    image_path=fig_rel_path,
                )

                if qa_item:
                    qa_review_items.append(qa_item)
                    self.tui.stats["needs_review"] += 1

            asset = VisualAsset(
                image_path=fig_rel_path,
                image_sha256=img_sha,
                vlm_data=vlm_data,
                bbox=fig.bbox,
            )
            visual_assets_by_page[fig.page_number].append(asset)
            self.tui.update_stage("vlm", completed=idx)

        # 3. Chunk Document
        chunks = self.chunker.chunk_document(doc, visual_assets_by_page=visual_assets_by_page)
        self.tui.stats["chunks"] = len(chunks)
        self.tui.update_stage("chunk", completed=100)

        # 4. Triplet Extraction
        triplets: list[TripletRecord] = []
        if not skip_triplets:
            self.tui.update_stage("triplets", completed=0, total=len(chunks))
            for c_idx, c in enumerate(chunks, start=1):
                c_triplets = self.triplet_extractor.extract_from_text(
                    text=c.text_content,
                    chunk_id=c.chunk_id,
                    book_id=actual_book_id,
                    page_number=c.page_number,
                    location_ref=c.location_ref,
                )
                triplets.extend(c_triplets)
                self.tui.update_stage("triplets", completed=c_idx)
        else:
            self.tui.update_stage("triplets", completed=100)

        self.tui.stats["triplets"] = len(triplets)

        # 5. Write local jsonl / metadata files
        self.tui.update_stage("export", completed=20)
        
        # Write chunks.jsonl
        chunks_file = book_out_dir / "chunks.jsonl"
        with open(chunks_file, "w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c.model_dump(by_alias=True), ensure_ascii=False) + "\n")

        # Map chunks per page
        chunks_by_page: dict[int, list[str]] = defaultdict(list)
        for c in chunks:
            chunks_by_page[c.page_number].append(c.chunk_id)

        # Write pages.jsonl
        pages_file = book_out_dir / "pages.jsonl"
        with open(pages_file, "w", encoding="utf-8") as f:
            for p in doc.pages:
                page_rec = PageRecord(
                    book_id=actual_book_id,
                    lang=lang,
                    page_number=p.page_number,
                    pagination=doc.pagination,
                    location_ref=p.location_ref,
                    spine_href=p.spine_href,
                    title=p.title,
                    full_page_markdown=p.markdown_content,
                    ocr_text=p.ocr_text,
                    assets_list=[fig.figure_id + ".png" for fig in p.figures],
                    tables_list=[tbl.table_id for tbl in p.tables],
                    chunk_ids=chunks_by_page[p.page_number],
                )
                f.write(json.dumps(page_rec.model_dump(by_alias=True), ensure_ascii=False) + "\n")

        # Write triplets.jsonl
        triplets_file = book_out_dir / "triplets.jsonl"
        with open(triplets_file, "w", encoding="utf-8") as f:
            for t in triplets:
                f.write(json.dumps(t.model_dump(), ensure_ascii=False) + "\n")

        # Write qa_review_queue.jsonl
        qa_file = book_out_dir / "qa_review_queue.jsonl"
        with open(qa_file, "w", encoding="utf-8") as f:
            for qa in qa_review_items:
                f.write(json.dumps(qa.model_dump(), ensure_ascii=False) + "\n")

        # Write book_metadata.json
        meta = BookMetadata(
            book_id=actual_book_id,
            title=doc.title,
            lang=[lang],
            pagination=doc.pagination,
            pipeline_profile=profile,
            ocr_engine=ocr_engine,
            spine_map=[
                {"spine_index": p.page_number, "href": p.spine_href, "title": p.title}
                for p in doc.pages
                if p.spine_href
            ],
        )
        meta_file = book_out_dir / "book_metadata.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(meta.model_dump(), ensure_ascii=False, indent=2))

        # 6. Export .bookpack.zip archive
        self.tui.update_stage("export", completed=60)
        zip_path = self.exporter.export_archive(
            book_dir=book_out_dir,
            out_dir=self.out_dir,
            book_id=actual_book_id,
            title=doc.title,
            lang=[lang],
            pipeline_profile=profile,
            pagination=doc.pagination,
        )
        self.tui.stats["archive_path"] = str(zip_path)

        # Validate archive integrity
        valid, issues = verify_bookpack_archive(zip_path)
        if not valid:
            self.logger.error("Bookpack archive validation failed: %s", issues)
            raise RuntimeError(f"Exported bookpack archive integrity check failed: {issues}")
        else:
            self.logger.info("Bookpack archive integrity verified successfully (SHA-256 match).")

        # 7. Write ingest_report.md
        duration = time.time() - start_time
        report_file = book_out_dir / "ingest_report.md"
        self._write_ingest_report(
            report_file=report_file,
            book_id=actual_book_id,
            title=doc.title,
            pages=len(doc.pages),
            figures=len(all_figures),
            chunks=len(chunks),
            triplets=len(triplets),
            needs_review=len(qa_review_items),
            archive_path=str(zip_path),
            duration=duration,
        )

        self.tui.update_stage("export", completed=100)
        self.tui.stop()
        self.tui.print_summary(actual_book_id, duration)

        self.logger.info(
            "Build complete for %s in %.2fs. Archive: %s",
            actual_book_id,
            duration,
            zip_path,
        )

        return zip_path

    def _write_ingest_report(
        self,
        report_file: Path,
        book_id: str,
        title: str,
        pages: int,
        figures: int,
        chunks: int,
        triplets: int,
        needs_review: int,
        archive_path: str,
        duration: float,
    ) -> None:
        nr_rate = (needs_review / max(figures, 1)) * 100.0
        gate_status = "PASS ✅" if nr_rate <= 5.0 else "WARNING ⚠️ (needs review > 5%)"

        content = f"""# Ingestion Report — {book_id}

- **Title:** {title}
- **Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
- **Duration:** {duration:.2f} seconds
- **Acceptance Gate (needs_review ≤ 5%):** {gate_status}
- **Exported Archive:** `{archive_path}`

## Summary Metrics

| Metric | Count |
|---|---|
| Pages / Spine Items | {pages} |
| Extracted Figures | {figures} |
| Generated Chunks | {chunks} |
| Extracted Triplets | {triplets} |
| VLM Needs Review (QA Queue) | {needs_review} ({nr_rate:.1f}%) |
| VLM Cache Hits | {self.tui.stats['vlm_cache_hits']} |
| VLM API Calls | {self.tui.stats['vlm_api_calls']} |

## Artifact Files Inside Archive

- `bookpack.json` (schema_version: "1.5", files_sha256 manifest)
- `book_metadata.json`
- `pages.jsonl`
- `chunks.jsonl`
- `triplets.jsonl`
- `qa_review_queue.jsonl`
- `assets/` ({figures} PNG figures)
"""
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(content)
