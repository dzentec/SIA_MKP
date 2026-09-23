"""Stand-alone runner to build both maritime books on RunPod with Qwen2.5-VL 32B."""

from __future__ import annotations

from pathlib import Path
import sys
import time

from mkp_builder.pipeline import BuilderPipeline

def main() -> None:
    repo_root = Path(__file__).parent.resolve()
    source_dir = repo_root / ".init_doc" / "source_doc"
    
    # Locate epub and pdf
    epub_files = list(source_dir.glob("*.epub"))
    pdf_files = list(source_dir.glob("*.pdf"))
    
    if not epub_files:
        print(f"ERROR: No EPUB found in {source_dir}", file=sys.stderr)
        sys.exit(1)
    if not pdf_files:
        print(f"ERROR: No PDF found in {source_dir}", file=sys.stderr)
        sys.exit(1)
        
    epub_path = epub_files[0]
    pdf_path = pdf_files[0]
    
    print(f"Found EPUB: {epub_path.name} ({epub_path.stat().st_size} bytes)", flush=True)
    print(f"Found PDF:  {pdf_path.name} ({pdf_path.stat().st_size} bytes)", flush=True)

    work_dir = repo_root / "cloud_build"
    work_dir.mkdir(parents=True, exist_ok=True)

    pipeline = BuilderPipeline(
        work_dir=work_dir,
        ollama_host="http://127.0.0.1:11434",
        vlm_model="qwen2.5vl:32b",
        text_model="qwen2.5vl:32b",
        force=True,
        headless=True,
    )

    print("\n=======================================================", flush=True)
    print(">>> [1/2] Building Illustrated Seamanship with 32B VLM...", flush=True)
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
    print(f">>> [1/2] COMPLETED in {time.time()-t0:.2f}s: {bp1}", flush=True)

    print("\n=======================================================", flush=True)
    print(">>> [2/2] Building Sail and Rig Tuning with 32B VLM...", flush=True)
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
    print(f">>> [2/2] COMPLETED in {time.time()-t1:.2f}s: {bp2}", flush=True)
    print("\nALL 2 BOOKS BUILT SUCCESSFULLY WITH QWEN2.5-VL 32B!", flush=True)


if __name__ == "__main__":
    main()
