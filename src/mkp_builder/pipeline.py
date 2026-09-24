"""Core Builder Pipeline Orchestrator (REQ-B01..B10, REQ-R01..R06, HLD v3.3.1)."""

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
from mkp_common.rules_schema import (
    Claim,
    Cluster,
    Rule,
)
from mkp_builder.parsers import get_parser
from mkp_builder.parsers.base import ParsedDocument
from mkp_builder.vlm.client import OllamaClient
from mkp_builder.vlm.annotator import VLMAnnotator
from mkp_builder.vlm.verifier import VLMVerifier
from mkp_builder.triplets import TripletExtractor
from mkp_builder.chunker import SectionAwareChunker
from mkp_builder.extract.claims import ClaimsExtractor
from mkp_builder.synthesize.cluster import ClaimsClusterer
from mkp_builder.synthesize.synthesize import RuleSynthesizer
from mkp_builder.compile.guardrails import GuardrailsCompiler
from mkp_builder.export.bookpack import BookpackExporter
from mkp_builder.review import generate_golden_t1_rules
from mkp_builder.tui import BuilderProgressTracker

logger = logging.getLogger("mkp_builder")


class BuilderPipeline:
    """End-to-end processing pipeline for maritime documents & rules."""

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
        self.claims_extractor = ClaimsExtractor(
            client=self.ollama,
            cache=self.cache,
            model=text_model,
        )
        self.synthesizer = RuleSynthesizer(
            client=self.ollama,
            cache=self.cache,
            model=text_model,
        )
        self.guardrails_compiler = GuardrailsCompiler()
        self.exporter = BookpackExporter(out_dir=self.out_dir)
        self.tui = BuilderProgressTracker(headless=headless)

    def build_book(
        self,
        book_path: Path | str,
        book_id: str | None = None,
        tier: Literal["T1", "T2", "T2.5", "T3"] = "T1",
        region: str | None = None,
        profile: Literal["digital", "scanned", "mixed"] = "digital",
        lang: str = "en",
        title: str | None = None,
        ocr_engine: Literal["rapidocr", "tesseract"] = "rapidocr",
        tessdata_path: str | None = None,
        skip_vlm: bool = False,
        skip_triplets: bool = False,
        skip_rules: bool = False,
        seed_golden_rules: bool = True,
    ) -> Path:
        start_time = time.time()
        book_path = Path(book_path)
        actual_book_id = book_id or book_path.stem.replace(" ", "_").lower()

        # Directory structure for this book run
        book_out_dir = self.work_dir / "books" / actual_book_id
        assets_dir = book_out_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info(
            "Starting build for book: %s (id: %s, tier: %s, region: %s)",
            book_path.name,
            actual_book_id,
            tier,
            region,
        )

        self.tui.start(actual_book_id)
        self.tui.add_stage("parse", "1. Parsing Layout & Figures", total=100)
        self.tui.add_stage("vlm", "2. VLM Annotation & Verification", total=100)
        self.tui.add_stage("chunk", "3. Section-Aware Chunking", total=100)
        self.tui.add_stage("triplets", "4. Triplet Extraction (GraphRAG)", total=100)
        self.tui.add_stage("rules", "5. Claims & Rules Pipeline", total=100)
        self.tui.add_stage("export", "6. Signed Bookpack v0.3.0 Export", total=100)

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

        if (not skip_vlm or not skip_triplets or not skip_rules) and (all_figures or doc.pages):
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
                vlm_data, is_cache = self.annotator.annotate(
                    image_bytes=fig.image_bytes,
                    image_sha256=img_sha,
                )
                if is_cache:
                    self.tui.stats["vlm_cache_hits"] += 1
                else:
                    self.tui.stats["vlm_api_calls"] += 1

                # 3-step Verification
                vlm_data, qa_item = self.verifier.verify(
                    vlm_data=vlm_data,
                    image_bytes=fig.image_bytes,
                    image_sha256=img_sha,
                    book_id=actual_book_id,
                    image_path=fig_rel_path,
                )

                if qa_item is not None:
                    qa_review_items.append(qa_item)

            asset = VisualAsset(
                image_path=fig_rel_path,
                image_sha256=img_sha,
                vlm_data=vlm_data,
                bbox=fig.bbox,
            )
            visual_assets_by_page[fig.page_number].append(asset)
            if hasattr(self.ollama, "last_tps") and self.ollama.last_tps > 0:
                self.tui.stats["gpu_tps"] = self.ollama.last_tps
            self.tui.update_stage("vlm", completed=idx)

        self.tui.stats["needs_review"] = len(qa_review_items)

        # 3. Chunking
        self.tui.update_stage("chunk", completed=0, total=100)
        chunks: list[ChunkRecord] = self.chunker.chunk_document(
            doc=doc,
            visual_assets_by_page=visual_assets_by_page,
        )
        self.tui.update_stage("chunk", completed=100)
        self.tui.stats["chunks"] = len(chunks)

        # 4. Triplet Extraction
        self.tui.update_stage("triplets", completed=0, total=max(len(chunks), 1))
        triplets: list[TripletRecord] = []
        if not skip_triplets:
            for c_idx, c in enumerate(chunks, start=1):
                c_triplets = self.triplet_extractor.extract_from_text(
                    text=c.text_content,
                    chunk_id=c.chunk_id,
                    book_id=actual_book_id,
                    page_number=c.page_number,
                    location_ref=c.location_ref,
                )
                triplets.extend(c_triplets)
                if hasattr(self.ollama, "last_tps") and self.ollama.last_tps > 0:
                    self.tui.stats["gpu_tps"] = self.ollama.last_tps
                self.tui.update_stage("triplets", completed=c_idx)
        else:
            self.tui.update_stage("triplets", completed=100)

        self.tui.stats["triplets"] = len(triplets)

        # 5. Claims, Clustering & Rule Synthesis
        self.tui.update_stage("rules", completed=0, total=100)
        claims: list[Claim] = []
        clusters: list[Cluster] = []
        rules: list[Rule] = []
        guardrails_md = ""

        if not skip_rules:
            # 5.1 Claims extraction
            self.logger.info("Extracting claims across %d chunks...", len(chunks))
            self.tui.update_stage("rules", completed=10, total=100)
            claims = self.claims_extractor.extract_from_chunks(chunks=chunks, tier=tier)
            self.tui.stats["claims"] = len(claims)
            
            # 5.2 Clustering
            self.logger.info("Clustering %d claims...", len(claims))
            self.tui.update_stage("rules", completed=30, total=100)
            clusterer = ClaimsClusterer(book_id=actual_book_id)
            clusters = clusterer.cluster_claims(claims=claims, tier=tier if tier != "T3" else "T1")
            self.tui.stats["clusters"] = len(clusters)
            self.logger.info("Created %d semantic clusters for synthesis", len(clusters))

            # 5.3 Granular rule synthesis (30% -> 90%)
            def _on_rule_progress(idx: int, total: int, rule: Rule | None) -> None:
                pct = 30 + int(60.0 * (idx / max(total, 1)))
                if hasattr(self.ollama, "last_tps") and self.ollama.last_tps > 0:
                    self.tui.stats["gpu_tps"] = self.ollama.last_tps
                self.tui.update_stage("rules", completed=pct, total=100)

            rules = self.synthesizer.synthesize_rules(
                clusters=clusters,
                claims=claims,
                tier=tier if tier != "T3" else "T1",
                region=region,
                on_progress=_on_rule_progress,
            )
            self.tui.stats["rules"] = len(rules)

            # 5.4 Golden rules inclusion for T1 Base & Guardrails compilation (90% -> 100%)
            self.tui.update_stage("rules", completed=90, total=100)
            if tier == "T1" and seed_golden_rules:
                golden_rules = generate_golden_t1_rules(book_id=actual_book_id)
                # deduplicate by rule_id
                existing_ids = {r.rule_id for r in rules}
                for gr in golden_rules:
                    if gr.rule_id not in existing_ids:
                        rules.append(gr)
                self.tui.stats["rules"] = len(rules)

            # Compile Guardrails
            guardrails_md = self.guardrails_compiler.compile(rules=rules, include_draft=True)
            self.tui.update_stage("rules", completed=100, total=100)
        else:
            if tier == "T1" and seed_golden_rules:
                rules = generate_golden_t1_rules(book_id=actual_book_id)
                guardrails_md = self.guardrails_compiler.compile(rules=rules, include_draft=True)
                self.tui.stats["rules"] = len(rules)
            self.tui.update_stage("rules", completed=100, total=100)

        # 6. Write local jsonl files
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

        # Write claims.jsonl
        claims_file = book_out_dir / "claims.jsonl"
        with open(claims_file, "w", encoding="utf-8") as f:
            for cl in claims:
                f.write(json.dumps(cl.model_dump(), ensure_ascii=False) + "\n")

        # Write rules.jsonl
        rules_file = book_out_dir / "rules.jsonl"
        with open(rules_file, "w", encoding="utf-8") as f:
            for r in rules:
                f.write(json.dumps(r.model_dump(), ensure_ascii=False) + "\n")

        # Write guardrails.md
        guardrails_file = book_out_dir / "guardrails.md"
        with open(guardrails_file, "w", encoding="utf-8") as f:
            f.write(guardrails_md)

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

        # 7. Export signed Bookpack v0.3.0 archive
        self.tui.update_stage("export", completed=60)
        zip_path = self.exporter.export(
            book_id=actual_book_id,
            title=doc.title,
            chunks=chunks,
            triplets=triplets,
            claims=claims,
            rules=rules,
            guardrails_md=guardrails_md,
            assets_dir=assets_dir,
            tier=tier,
            region=region,
        )
        self.tui.stats["archive_path"] = str(zip_path)

        # 8. Write ingest_report.md
        duration = time.time() - start_time
        report_file = book_out_dir / "ingest_report.md"
        self._write_ingest_report(
            report_file=report_file,
            book_id=actual_book_id,
            title=doc.title,
            tier=tier,
            pages=len(doc.pages),
            figures=len(all_figures),
            chunks=len(chunks),
            triplets=len(triplets),
            claims=len(claims),
            rules=len(rules),
            needs_review=len(qa_review_items),
            archive_path=str(zip_path),
            duration=duration,
        )

        self.tui.update_stage("export", completed=100)
        self.tui.stop()
        self.tui.print_summary(actual_book_id, duration)

        self.logger.info(
            "Build complete for %s (tier=%s) in %.2fs. Archive: %s",
            actual_book_id,
            tier,
            duration,
            zip_path,
        )

        return zip_path

    def _write_ingest_report(
        self,
        report_file: Path,
        book_id: str,
        title: str,
        tier: str,
        pages: int,
        figures: int,
        chunks: int,
        triplets: int,
        claims: int,
        rules: int,
        needs_review: int,
        archive_path: str,
        duration: float,
    ) -> None:
        nr_rate = (needs_review / max(figures, 1)) * 100.0
        gate_status = "PASS ✅" if nr_rate <= 5.0 else "WARNING ⚠️ (needs review > 5%)"

        content = f"""# Ingestion Report — {book_id} (Tier: {tier})

- **Title:** {title}
- **Tier:** {tier}
- **Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
- **Duration:** {duration:.2f} seconds
- **Acceptance Gate (needs_review ≤ 5%):** {gate_status}
- **Exported Archive:** `{archive_path}` (Signed Bookpack v0.3.0)

## Summary Metrics

| Metric | Count |
|---|---|
| Pages / Spine Items | {pages} |
| Extracted Figures | {figures} |
| Generated Chunks | {chunks} |
| Extracted Triplets | {triplets} |
| Extracted Claims | {claims} |
| Synthesized Rules | {rules} |
| VLM Needs Review (QA Queue) | {needs_review} ({nr_rate:.1f}%) |
| VLM Cache Hits | {self.tui.stats['vlm_cache_hits']} |
| VLM API Calls | {self.tui.stats['vlm_api_calls']} |

## Artifact Files Inside Archive
- `manifest.yaml` (bookpack_version: "0.3.0", generation, compatibility, base/user hashes)
- `checksums.sha256` + per-artifact sha256 (`base/chunks.sha256`, `base/rules.sha256`)
- `signature.ed25519` (digital signature)
- `base/` (chunks, triplets, claims, rules, guardrails.md)
- `yacht/`, `voyage/`, `personal/` (stubs)
- `assets/` ({figures} PNG figures)
"""
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(content)
