"""Stand-alone runner to build maritime books on RunPod with Qwen2.5-VL 32B."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import time

repo_root = Path(__file__).resolve().parent.parent.parent
if str(repo_root / "src") not in sys.path:
    sys.path.insert(0, str(repo_root / "src"))
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

if "MKP_TELEMETRY_PATH" not in os.environ:
    os.environ["MKP_TELEMETRY_PATH"] = "/tmp/mkp_progress.json"

from mkp_builder.pipeline import BuilderPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="RunPod 32B VLM Builder Runner")
    parser.add_argument(
        "--book",
        choices=["sail_and_rig_tuning", "illustrated_seamanship", "all"],
        default="sail_and_rig_tuning",
        help="Target book to build (default: sail_and_rig_tuning)",
    )
    args = parser.parse_args()

    source_dir = repo_root / ".init_doc" / "source_doc"
    work_dir = repo_root / "cloud_build"
    work_dir.mkdir(parents=True, exist_ok=True)

    epub_files = [f for f in source_dir.glob("*.epub") if "seamanship" in f.name.lower()] or list(source_dir.glob("*.epub"))
    pdf_files = [f for f in source_dir.glob("*.pdf") if "sail" in f.name.lower() or "tuning" in f.name.lower()] or list(source_dir.glob("*.pdf"))

    pipeline = BuilderPipeline(
        work_dir=work_dir,
        ollama_host="http://127.0.0.1:11434",
        vlm_model="qwen2.5vl:32b",
        text_model="qwen2.5vl:32b",
        force=True,
        headless=True,
    )

    if args.book in ["illustrated_seamanship", "all"]:
        if not epub_files:
            print(f"ERROR: Illustrated Seamanship EPUB not found in {source_dir}", file=sys.stderr)
            if args.book != "all":
                sys.exit(1)
        else:
            epub_path = epub_files[0]
            print("\n=======================================================", flush=True)
            print(f">>> Building Illustrated Seamanship ({epub_path.name}) with 32B VLM...", flush=True)
            print("=======================================================", flush=True)
            t0 = time.time()
            bp1 = pipeline.build_book(
                book_path=epub_path,
                book_id="illustrated_seamanship",
                tier="T1",
                title="Illustrated Seamanship",
                lang="en",
                skip_vlm=False,
                skip_triplets=False,
                skip_rules=False,
                seed_golden_rules=True,
            )
            print(f">>> Illustrated Seamanship COMPLETED in {time.time()-t0:.2f}s: {bp1}", flush=True)

    if args.book in ["sail_and_rig_tuning", "all"]:
        if not pdf_files:
            print(f"ERROR: Sail and Rig Tuning PDF not found in {source_dir}", file=sys.stderr)
            sys.exit(1)
        pdf_path = pdf_files[0]
        print("\n=======================================================", flush=True)
        print(f">>> Building Sail and Rig Tuning ({pdf_path.name}) with 32B VLM...", flush=True)
        print("=======================================================", flush=True)
        t1 = time.time()
        bp2 = pipeline.build_book(
            book_path=pdf_path,
            book_id="sail_and_rig_tuning",
            tier="T1",
            title="Sail and Rig Tuning",
            lang="en",
            skip_vlm=False,
            skip_triplets=False,
            skip_rules=False,
            seed_golden_rules=True,
        )
        print(f">>> Sail and Rig Tuning COMPLETED in {time.time()-t1:.2f}s: {bp2}", flush=True)

    print("\nBUILD FINISHED SUCCESSFULLY WITH QWEN2.5-VL 32B!", flush=True)


if __name__ == "__main__":
    main()
