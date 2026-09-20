"""
P0-01 — Docling: Extract figures from PDF (figure crop)
REQ: REQ-P0-01
Extracts all PictureItem from PDF using generate_picture_images=True, scale=2.0
Saves to poc/assets/crops/{book_id}_p{page}_fig{idx}.png
"""

import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()

PDF_PATH = Path(__file__).parent.parent / ".init_doc" / "source_doc" / \
    "Sail and Rig Tuning (Ivar Dedekam) (z-library.sk, 1lib.sk, z-lib.sk).pdf"

CROPS_DIR = Path(__file__).parent / "assets" / "crops"
BOOK_ID = "dedekam_rig"

# Limit to first N pages for PoC speed (full PDF is large)
MAX_PAGES = 30


def main():
    console.print("\n[bold cyan]═══ T0-01: Docling Figure Crop (PDF → PNG) ═══[/bold cyan]\n")

    if not PDF_PATH.exists():
        console.print(f"[red]✗ PDF not found: {PDF_PATH}[/red]")
        return {"pass": False}

    console.print(f"PDF: {PDF_PATH.name} ({PDF_PATH.stat().st_size / 1024 / 1024:.1f} MB)")
    console.print(f"Processing first {MAX_PAGES} pages for PoC...")

    CROPS_DIR.mkdir(parents=True, exist_ok=True)

    # ─── Import Docling ───
    console.print("[yellow]Loading Docling...[/yellow]")
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling_core.types.doc import PictureItem
    except ImportError as e:
        console.print(f"[red]✗ Docling import failed: {e}[/red]")
        return {"pass": False, "error": str(e)}

    # ─── Configure pipeline ───
    options = PdfPipelineOptions(
        generate_picture_images=True,
        images_scale=2.0,
    )
    converter = DocumentConverter(
        format_options={"pdf": PdfFormatOption(pipeline_options=options)}
    )

    console.print("[yellow]Parsing PDF with Docling (this may take a minute)...[/yellow]")
    try:
        # Use page_range=(start, end) — 1-indexed inclusive
        result = converter.convert(
            str(PDF_PATH),
            page_range=(1, MAX_PAGES),
            raises_on_error=True,
        )
        doc = result.document
        console.print(f"[green]✓ Parsed: {len(doc.pages)} pages[/green]")
    except Exception as e:
        console.print(f"[red]✗ Docling conversion failed: {e}[/red]")
        return {"pass": False, "error": str(e)}

    # ─── Extract PictureItems ───
    console.print("[yellow]Extracting PictureItems...[/yellow]")
    pics = []
    page_fig_counts: dict[int, int] = {}

    for elem, _level in doc.iterate_items():
        if not isinstance(elem, PictureItem):
            continue

        # Get page number
        page_no = None
        if hasattr(elem, "prov") and elem.prov:
            prov = elem.prov[0] if isinstance(elem.prov, list) else elem.prov
            page_no = getattr(prov, "page_no", None)

        if page_no is None:
            page_no = 0

        # Figure index on this page
        fig_idx = page_fig_counts.get(page_no, 0)
        page_fig_counts[page_no] = fig_idx + 1

        # File name: {book_id}_p{page}_fig{idx}.png
        filename = f"{BOOK_ID}_p{page_no}_fig{fig_idx}.png"
        output_path = CROPS_DIR / filename

        # Save image
        saved = False
        file_size = 0
        width = height = 0
        img_type = "unknown"

        if hasattr(elem, "image") and elem.image is not None:
            try:
                img = elem.image.pil_image
                if img is not None:
                    width, height = img.size
                    img_type = "raster" if img.mode != "RGBA" else "raster+alpha"
                    img.save(str(output_path), "PNG")
                    file_size = output_path.stat().st_size
                    saved = True
            except Exception as e:
                img_type = f"error: {e}"

        pics.append({
            "filename": filename,
            "page": page_no,
            "fig_idx": fig_idx,
            "width": width,
            "height": height,
            "file_size_kb": round(file_size / 1024, 1),
            "type": img_type,
            "saved": saved,
        })

    console.print(f"\n[bold]Extracted {len(pics)} figures from {MAX_PAGES} pages[/bold]")

    # ─── Results table ───
    table = Table(title=f"Figure Extraction Results (first {min(20, len(pics))} of {len(pics)})")
    table.add_column("File", style="cyan")
    table.add_column("Page", justify="center")
    table.add_column("Size (KB)", justify="right")
    table.add_column("WxH", justify="center")
    table.add_column("Type")
    table.add_column("Saved", justify="center")

    for p in pics[:20]:
        saved_str = "[green]✓[/green]" if p["saved"] else "[red]✗[/red]"
        dim = f"{p['width']}x{p['height']}" if p["saved"] else "—"
        table.add_row(
            p["filename"],
            str(p["page"]),
            str(p["file_size_kb"]),
            dim,
            p["type"][:20],
            saved_str,
        )
    console.print(table)

    # ─── Acceptance criteria ───
    saved_pics = [p for p in pics if p["saved"]]
    non_empty = [p for p in saved_pics if p["file_size_kb"] > 0]
    min_512 = [p for p in saved_pics if p["width"] >= 512 and p["height"] >= 512]

    # Check naming uniqueness
    filenames = [p["filename"] for p in pics]
    unique_names = len(set(filenames)) == len(filenames)

    console.print("\n[bold]Acceptance Criteria:[/bold]")
    ac1 = len(saved_pics) > 0
    ac2 = len(non_empty) == len(saved_pics)  # no empty files
    ac3 = len(min_512) > 0 if saved_pics else False  # at least some >= 512x512
    ac4 = unique_names

    console.print(f"  [{'green' if ac1 else 'red'}]{'✓' if ac1 else '✗'}[/] Figures extracted as PNG: {len(saved_pics)}/{len(pics)}")
    console.print(f"  [{'green' if ac2 else 'red'}]{'✓' if ac2 else '✗'}[/] No empty files: {len(non_empty)}/{len(saved_pics)} non-empty")
    console.print(f"  [{'green' if ac3 else 'yellow'}]{'✓' if ac3 else '⚠'}[/] Min 512x512: {len(min_512)}/{len(saved_pics)} figures")
    console.print(f"  [{'green' if ac4 else 'red'}]{'✓' if ac4 else '✗'}[/] Unique naming: {'yes' if unique_names else 'COLLISION!'}")

    if saved_pics:
        console.print(f"\n  [dim]Crops saved to: {CROPS_DIR}[/dim]")
        console.print(f"  [dim]Example: {saved_pics[0]['filename']}[/dim]")

    passed = ac1 and ac2 and ac4

    return {
        "total_found": len(pics),
        "saved": len(saved_pics),
        "non_empty": len(non_empty),
        "min_512x512": len(min_512),
        "unique_naming": unique_names,
        "crops_dir": str(CROPS_DIR),
        "pass": passed,
    }


if __name__ == "__main__":
    result = main()
    sys.exit(0 if result.get("pass") else 1)
