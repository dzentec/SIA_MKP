"""Fixture generator for the 30-question Golden Dataset & 15 Golden Rules corpus (REQ-QA-01)."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

from mkp_builder.export.bookpack import BookpackExporter
from mkp_common.models import (
    ChunkRecord,
    TripletRecord,
    EntityNode,
    VisualAsset,
    VlmData,
    DiagramType,
)
from mkp_common.rules_schema import (
    Claim,
    Rule,
    RuleSource,
    RuleTrigger,
    RuleAction,
)
from mkp_server.lifecycle import LifecycleManager
from mkp_server.storage import StorageManager


def load_golden_dataset(qa_dir: Path | str | None = None) -> list[dict]:
    """Load the ground truth dataset (golden_full_dataset.json or fallback)."""
    base = Path(qa_dir) if qa_dir else Path(__file__).parent
    ds_full = base / "golden_full_dataset.json"
    if ds_full.exists():
        with open(ds_full, "r", encoding="utf-8") as f:
            return json.load(f)
    ds_file = base / "golden_dataset.json"
    with open(ds_file, "r", encoding="utf-8") as f:
        return json.load(f)


def load_golden_rules(qa_dir: Path | str | None = None) -> list[Rule]:
    """Load the verified Golden Rules."""
    base = Path(qa_dir) if qa_dir else Path(__file__).parent
    r_file = base / "golden_rules.json"
    with open(r_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Rule.model_validate(item) for item in data]


def build_golden_bookpack(
    book_id: str,
    out_dir: Path,
    dataset: list[dict],
    rules: list[Rule],
) -> Path:
    """Build a complete, signed .bookpack.zip v0.3.0 for a given book from ground truth dataset."""
    book_questions = [
        q for q in dataset
        if q.get("expected_book") == book_id
        or (book_id in q.get("expected_books", []))
    ]
    exporter = BookpackExporter(out_dir=out_dir)

    # 1. Chunks & Visual Assets
    chunks: list[ChunkRecord] = []
    assets_tmp = out_dir / f"{book_id}_assets_tmp"
    assets_tmp.mkdir(parents=True, exist_ok=True)

    dummy_png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"

    for q in book_questions:
        if book_id in q.get("expected_books", []):
            b_idx = q["expected_books"].index(book_id)
            page = q.get("expected_pages", [q.get("expected_page", 1)])[b_idx]
            loc_ref = f"pdf:p{page}" if book_id == "dedekam_sail_trim" else f"epub:s{page}"
        else:
            page = q.get("expected_page", 1)
            loc_ref = q.get("expected_location_ref", f"pdf:p{page}")

        chunk_id = f"{book_id}_p{page:03d}_c01"
        lang = q.get("lang", "en")

        # Visual asset if diagram is present
        visual_assets = []
        if q.get("diagram_type"):
            diag_str = q["diagram_type"]
            img_name = f"fig_{book_id}_p{page}.png"
            img_file = assets_tmp / img_name
            if not img_file.exists():
                img_file.write_bytes(dummy_png_bytes)

            try:
                dtype = DiagramType(diag_str)
            except Exception:
                dtype = DiagramType.OTHER

            visual_assets.append(
                VisualAsset(
                    image_path=f"assets/{img_name}",
                    image_sha256="deadbeef12345678",
                    vlm_data=VlmData(
                        diagram_type=dtype,
                        description=f"Detailed illustrated diagram explaining {q['query']} with terms {', '.join(q['must_contain_terms'])}.",
                    ),
                )
            )

        # Ground truth chunk text containing must_contain_terms
        terms_snippet = " ".join(q.get("must_contain_terms", []))
        chunk_text = (
            f"Official Seamanship Manual — {book_id.replace('_', ' ').title()}, Page {page}.\n"
            f"Topic: {q['query']}.\n"
            f"Detailed instruction: {terms_snippet}. Ensure proper trimming, navigation, and safety procedures."
        )

        chunks.append(
            ChunkRecord(
                chunk_id=chunk_id,
                book_id=book_id,
                page_number=page,
                location_ref=loc_ref,
                section_path=f"Section > Page {page}",
                text_content=chunk_text,
                lang=lang,
                visual_assets=visual_assets,
            )
        )

    # 2. Triplets (extract from questions with expected_triples)
    triplets: list[TripletRecord] = []
    for q in book_questions:
        if q.get("expected_triples"):
            page = q["expected_page"]
            loc_ref = q["expected_location_ref"]
            chunk_id = f"{book_id}_p{page:03d}_c01"

            for tr in q["expected_triples"]:
                subj, pred, obj = tr
                triplets.append(
                    TripletRecord(
                        subject=EntityNode(name=subj, type="concept", lang=q.get("lang", "en")),
                        predicate=pred,
                        object=EntityNode(name=obj, type="concept", lang=q.get("lang", "en")),
                        provenance={
                            "doc_id": book_id,
                            "page_number": page,
                            "chunk_id": chunk_id,
                            "location_ref": loc_ref,
                        },
                    )
                )

    # 3. Rules for this book
    book_rules = [r for r in rules if r.sources and r.sources[0].doc_id == book_id]
    if not book_rules and rules:
        book_rules = rules[:8]  # Assign subset if doc_id generic

    guardrails_md = (
        f"# GUARDRAILS — {book_id.upper()}\n"
        f"- Always wear lifejackets and clip safety harnesses in heavy weather.\n"
        f"- Never delay reefing: reef early to maintain control and safety.\n"
    )

    zip_path = exporter.export(
        book_id=book_id,
        title=book_id.replace("_", " ").title(),
        chunks=chunks,
        triplets=triplets,
        claims=[],
        rules=book_rules,
        guardrails_md=guardrails_md,
        assets_dir=assets_tmp,
        tier="T1",
    )

    return zip_path


def setup_golden_storage(storage_root: Path, qa_dir: Path | str | None = None) -> StorageManager:
    """Setup a populated mkp-server storage with both golden books imported and verified."""
    mgr = StorageManager(storage_root)
    lifecycle = LifecycleManager(mgr)

    qa_p = Path(qa_dir) if qa_dir else Path(__file__).parent
    dataset = load_golden_dataset(qa_p)
    rules = load_golden_rules(qa_p)

    build_tmp = storage_root / "build_temp"
    build_tmp.mkdir(parents=True, exist_ok=True)

    # 1. Build and import dedekam_sail_trim
    bp_trim = build_golden_bookpack("dedekam_sail_trim", build_tmp, dataset, rules)
    ok1, msg1 = lifecycle.apply_bookpack(bp_trim)
    if not ok1:
        raise RuntimeError(f"Failed to apply dedekam_sail_trim: {msg1}")

    # 2. Build and import dedekam_seamanship
    bp_seamanship = build_golden_bookpack("dedekam_seamanship", build_tmp, dataset, rules)
    ok2, msg2 = lifecycle.apply_bookpack(bp_seamanship)
    if not ok2:
        raise RuntimeError(f"Failed to apply dedekam_seamanship: {msg2}")

    return mgr
