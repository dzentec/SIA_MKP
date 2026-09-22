"""CLI Entrypoint for mkp-builder (REQ-B08, REQ-B10, REQ-R06, HLD v3.3.1)."""

from __future__ import annotations

import sys
from pathlib import Path
import click
from rich.prompt import Prompt
from rich.console import Console

from mkp_builder.pipeline import BuilderPipeline
from mkp_builder.review import review_rules_cli


@click.group()
@click.version_option(version="0.3.0")
def main():
    """Maritime Knowledge Pack (MKP) Builder CLI."""
    pass


@main.command(name="build")
@click.option("--book", "-b", required=True, type=click.Path(exists=True, path_type=Path), help="Path to input PDF/EPUB/DOCX manual.")
@click.option("--book-id", "-i", type=str, default=None, help="Unique identifier for the book. Defaults to file stem.")
@click.option("--tier", "-t", type=click.Choice(["T1", "T2", "T2.5", "T3"]), default=None, help="Document content tier: T1 (Base), T2 (Yacht), T2.5 (Voyage), T3 (Personal).")
@click.option("--region", "-r", type=str, default=None, help="Geographical region for T2.5 Voyage documents (e.g., 'Mediterranean', 'Baltic').")
@click.option("--title", type=str, default=None, help="Human-readable title of the book.")
@click.option("--profile", "-p", type=click.Choice(["digital", "scanned", "mixed"]), default="digital", show_default=True, help="Processing profile for text extraction and OCR.")
@click.option("--lang", "-l", type=click.Choice(["ru", "en", "mixed"]), default="en", show_default=True, help="Dominant language of the manual.")
@click.option("--out", "-o", type=click.Path(path_type=Path), default=Path("./work"), show_default=True, help="Output working directory.")
@click.option("--force", "-f", is_flag=True, default=False, help="Force rebuild, invalidating cache.")
@click.option("--headless", is_flag=True, default=False, help="Run without Rich interactive TUI.")
@click.option("--skip-vlm", is_flag=True, default=False, help="Skip VLM annotation and verification (fast mode).")
@click.option("--skip-triplets", is_flag=True, default=False, help="Skip Triplet extraction (fast mode).")
@click.option("--skip-rules", is_flag=True, default=False, help="Skip Claims/Rules pipeline (fast mode).")
@click.option("--ocr-engine", type=click.Choice(["rapidocr", "tesseract"]), default="rapidocr", show_default=True, help="OCR engine to use.")
def build_command(
    book: Path,
    book_id: str | None,
    tier: str | None,
    region: str | None,
    title: str | None,
    profile: str,
    lang: str,
    out: Path,
    force: bool,
    headless: bool,
    skip_vlm: bool,
    skip_triplets: bool,
    skip_rules: bool,
    ocr_engine: str,
):
    """Build knowledge components: parse -> OCR -> VLM -> chunk -> triplets -> claims -> rules -> signed Bookpack v0.3.0."""
    console = Console()

    # Interactive TUI selection if tier not provided (REQ-B08)
    chosen_tier = tier
    chosen_region = region

    if not chosen_tier and not headless:
        console.print("[bold cyan]=== SIA Document Tier Selection ===[/bold cyan]")
        console.print("  [1] [green]T1: Base[/green]     — Maritime books, COLREGs, physics, seamanship")
        console.print("  [2] [yellow]T2: Yacht[/yellow]    — Vessel manual, engine, electrical, rigging")
        console.print("  [3] [blue]T2.5: Voyage[/blue]  — Pilot books, cruising guides, regional rules")
        console.print("  [4] [magenta]T3: Personal[/magenta]  — Personal notes, onboard medicine, galley (search only)")
        
        tier_choice = Prompt.ask(
            "Select document tier",
            choices=["1", "2", "3", "4", "T1", "T2", "T2.5", "T3"],
            default="1",
        )
        mapping = {"1": "T1", "2": "T2", "3": "T2.5", "4": "T3"}
        chosen_tier = mapping.get(tier_choice, tier_choice)

        if chosen_tier == "T2.5" and not chosen_region:
            chosen_region = Prompt.ask("Enter voyage region name (e.g. 'Mediterranean', 'Atlantic')", default="Global")
    elif not chosen_tier:
        chosen_tier = "T1"

    pipeline = BuilderPipeline(
        work_dir=out,
        force=force,
        headless=headless,
    )

    try:
        archive_path = pipeline.build_book(
            book_path=book,
            book_id=book_id,
            tier=chosen_tier,  # type: ignore
            region=chosen_region,
            title=title,
            profile=profile,  # type: ignore
            lang=lang,
            ocr_engine=ocr_engine,  # type: ignore
            skip_vlm=skip_vlm,
            skip_triplets=skip_triplets,
            skip_rules=skip_rules,
        )
        click.secho(f"Successfully generated signed bookpack archive: {archive_path}", fg="green")
    except Exception as e:
        click.secho(f"Build failed: {e}", fg="red", err=True)
        sys.exit(1)


@main.command(name="review-rules")
@click.option("--rules", "-r", required=True, type=click.Path(exists=True, path_type=Path), help="Path to rules.jsonl file to review.")
def review_command(rules: Path):
    """View and review extracted rules with full provenance and status."""
    review_rules_cli(rules)


if __name__ == "__main__":
    main()
