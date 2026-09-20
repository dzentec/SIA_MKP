"""Rich TUI and progress tracking for mkp-builder (REQ-B08)."""

from __future__ import annotations

from typing import Any
from pathlib import Path
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
    TimeElapsedColumn,
)
from rich.panel import Panel
from rich.table import Table


class BuilderProgressTracker:
    """Manages Rich multi-stage progress bars and execution statistics."""

    def __init__(self, console: Console | None = None, headless: bool = False):
        self.console = console or Console()
        self.headless = headless
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=30),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=self.console,
            disable=headless,
        )

        self.tasks: dict[str, Any] = {}
        self.stats = {
            "pages": 0,
            "figures": 0,
            "vlm_cache_hits": 0,
            "vlm_api_calls": 0,
            "needs_review": 0,
            "chunks": 0,
            "triplets": 0,
            "archive_path": "",
        }

    def start(self) -> None:
        if not self.headless:
            self.progress.start()

    def stop(self) -> None:
        if not self.headless:
            self.progress.stop()

    def add_stage(self, stage_id: str, description: str, total: int = 100) -> None:
        if not self.headless:
            t_id = self.progress.add_task(description, total=total)
            self.tasks[stage_id] = t_id

    def advance_stage(self, stage_id: str, advance: int = 1) -> None:
        if not self.headless and stage_id in self.tasks:
            self.progress.advance(self.tasks[stage_id], advance)

    def update_stage(self, stage_id: str, completed: int, total: int | None = None) -> None:
        if not self.headless and stage_id in self.tasks:
            kwargs: dict[str, Any] = {"completed": completed}
            if total is not None:
                kwargs["total"] = total
            self.progress.update(self.tasks[stage_id], **kwargs)

    def print_summary(self, book_id: str, duration_sec: float) -> None:
        table = Table(title=f"MKP Builder Summary — {book_id}", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total Pages", str(self.stats["pages"]))
        table.add_row("Total Figures", str(self.stats["figures"]))
        table.add_row("VLM API Calls", str(self.stats["vlm_api_calls"]))
        table.add_row("VLM Cache Hits", str(self.stats["vlm_cache_hits"]))
        
        nr_style = "red" if self.stats["needs_review"] > 0 else "green"
        table.add_row("Needs Review (QA)", f"[{nr_style}]{self.stats['needs_review']}[/{nr_style}]")
        table.add_row("Generated Chunks", str(self.stats["chunks"]))
        table.add_row("Extracted Triplets", str(self.stats["triplets"]))
        if self.stats["archive_path"]:
            table.add_row("Exported Archive", str(self.stats["archive_path"]))
        table.add_row("Elapsed Time", f"{duration_sec:.1f} s")

        self.console.print(Panel(table, expand=False))
