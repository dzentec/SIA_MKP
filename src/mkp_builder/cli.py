"""CLI Entrypoint for mkp-builder (REQ-B10)."""

from __future__ import annotations

import sys
from pathlib import Path
import click
from mkp_builder.pipeline import BuilderPipeline
from mkp_builder.exporter import BookpackExporter, verify_bookpack_archive


@click.group()
@click.version_option(version="1.5.0")
def main():
    """Maritime Knowledge Pack (MKP) Builder CLI."""
    pass


@main.command(name="build")
@click.option("--book", "-b", required=True, type=click.Path(exists=True, path_type=Path), help="Path to input PDF/EPUB/DOCX manual.")
@click.option("--book-id", "-i", type=str, default=None, help="Unique identifier for the book. Defaults to file stem.")
@click.option("--title", "-t", type=str, default=None, help="Human-readable title of the book.")
@click.option("--profile", "-p", type=click.Choice(["digital", "scanned", "mixed"]), default="digital", show_default=True, help="Processing profile for text extraction and OCR.")
@click.option("--lang", "-l", type=click.Choice(["ru", "en", "mixed"]), default="en", show_default=True, help="Dominant language of the manual.")
@click.option("--out", "-o", type=click.Path(path_type=Path), default=Path("./work"), show_default=True, help="Output working directory.")
@click.option("--force", "-f", is_flag=True, default=False, help="Force rebuild, invalidating cache.")
@click.option("--headless", is_flag=True, default=False, help="Run without Rich interactive TUI.")
@click.option("--skip-vlm", is_flag=True, default=False, help="Skip VLM annotation and verification (fast mode).")
@click.option("--skip-triplets", is_flag=True, default=False, help="Skip Triplet extraction (fast mode).")
@click.option("--ocr-engine", type=click.Choice(["rapidocr", "tesseract"]), default="rapidocr", show_default=True, help="OCR engine to use.")
def build_command(
    book: Path,
    book_id: str | None,
    title: str | None,
    profile: str,
    lang: str,
    out: Path,
    force: bool,
    headless: bool,
    skip_vlm: bool,
    skip_triplets: bool,
    ocr_engine: str,
):
    """Build knowledge components from a manual: parse -> OCR -> VLM -> verify -> chunk -> triplets -> export."""
    pipeline = BuilderPipeline(
        work_dir=out,
        force=force,
        headless=headless,
    )

    try:
        archive_path = pipeline.build_book(
            book_path=book,
            book_id=book_id,
            title=title,
            profile=profile,  # type: ignore
            lang=lang,
            ocr_engine=ocr_engine,  # type: ignore
            skip_vlm=skip_vlm,
            skip_triplets=skip_triplets,
        )
        click.secho(f"Successfully generated bookpack archive: {archive_path}", fg="green")
    except Exception as e:
        click.secho(f"Build failed: {e}", fg="red", err=True)
        sys.exit(1)


@main.command(name="export")
@click.option("--book-id", "-i", required=True, type=str, help="Book ID of an already processed book in work_dir.")
@click.option("--work-dir", "-w", type=click.Path(exists=True, path_type=Path), default=Path("./work"), show_default=True, help="Working directory containing processed books.")
@click.option("--out", "-o", type=click.Path(path_type=Path), default=None, help="Output folder for the .bookpack.zip file (defaults to work_dir/out).")
def export_command(
    book_id: str,
    work_dir: Path,
    out: Path | None,
):
    """Re-package an already processed book directory into a .bookpack.zip archive."""
    book_dir = work_dir / "books" / book_id
    if not book_dir.exists():
        click.secho(f"Book directory not found: {book_dir}", fg="red", err=True)
        sys.exit(1)

    target_out = out or (work_dir / "out")
    exporter = BookpackExporter()

    try:
        zip_path = exporter.export_archive(
            book_dir=book_dir,
            out_dir=target_out,
            book_id=book_id,
        )
        valid, issues = verify_bookpack_archive(zip_path)
        if not valid:
            click.secho(f"Archive validation failed: {issues}", fg="red", err=True)
            sys.exit(1)
        click.secho(f"Successfully exported and validated: {zip_path}", fg="green")
    except Exception as e:
        click.secho(f"Export failed: {e}", fg="red", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
