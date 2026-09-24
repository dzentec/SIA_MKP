"""Rich TUI and progress tracking for mkp-builder (REQ-B08)."""

from __future__ import annotations

import json
import os
import tempfile
import time
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
    """Manages Rich multi-stage progress bars, telemetry publishing, and execution statistics."""

    def __init__(
        self,
        console: Console | None = None,
        headless: bool = False,
        telemetry_file: Path | str | None = None,
    ):
        self.console = console or Console()
        self.headless = headless
        
        # Telemetry path: explicit argument -> MKP_TELEMETRY_PATH -> default /tmp or temp dir
        default_telem = os.getenv("MKP_TELEMETRY_PATH")
        if not default_telem:
            if os.name == "nt":
                default_telem = str(Path(tempfile.gettempdir()) / "mkp_progress.json")
            else:
                default_telem = "/tmp/mkp_progress.json"
        self.telemetry_path = Path(telemetry_file) if telemetry_file else Path(default_telem)

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
        self.stage_data: dict[str, dict[str, Any]] = {}
        self.current_book: str = ""
        self.status: str = "idle"
        self.start_time: float = 0.0
        self.stats = {
            "pages": 0,
            "figures": 0,
            "vlm_cache_hits": 0,
            "vlm_api_calls": 0,
            "needs_review": 0,
            "chunks": 0,
            "triplets": 0,
            "gpu_tps": 0.0,
            "archive_path": "",
        }

    def start(self, book_id: str = "") -> None:
        self.current_book = book_id
        self.status = "running"
        self.start_time = time.time()
        if not self.headless:
            self.progress.start()
        self.publish_state()

    def stop(self, status: str = "completed") -> None:
        self.status = status
        if not self.headless:
            self.progress.stop()
        self.publish_state()

    def add_stage(self, stage_id: str, description: str, total: int = 100) -> None:
        self.stage_data[stage_id] = {
            "id": stage_id,
            "description": description,
            "completed": 0,
            "total": total,
            "status": "pending",
        }
        if not self.headless:
            t_id = self.progress.add_task(description, total=total)
            self.tasks[stage_id] = t_id
        self.publish_state()

    def advance_stage(self, stage_id: str, advance: int = 1) -> None:
        if stage_id in self.stage_data:
            self.stage_data[stage_id]["completed"] += advance
            self.stage_data[stage_id]["status"] = "in_progress"
        if not self.headless and stage_id in self.tasks:
            self.progress.advance(self.tasks[stage_id], advance)
        self.publish_state()

    def update_stage(self, stage_id: str, completed: int, total: int | None = None) -> None:
        if stage_id in self.stage_data:
            self.stage_data[stage_id]["completed"] = completed
            if total is not None:
                self.stage_data[stage_id]["total"] = total
            tot = self.stage_data[stage_id]["total"]
            if completed >= tot and tot > 0:
                self.stage_data[stage_id]["status"] = "completed"
            elif completed > 0:
                self.stage_data[stage_id]["status"] = "in_progress"

        if not self.headless and stage_id in self.tasks:
            kwargs: dict[str, Any] = {"completed": completed}
            if total is not None:
                kwargs["total"] = total
            self.progress.update(self.tasks[stage_id], **kwargs)
        self.publish_state()

    def publish_state(self, state_file: Path | str | None = None) -> None:
        """Atomically dump current telemetry snapshot to JSON file with zero overhead."""
        target_path = Path(state_file) if state_file else self.telemetry_path
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            elapsed = time.time() - self.start_time if self.start_time > 0 else 0.0
            
            payload = {
                "timestamp": time.time(),
                "status": self.status,
                "current_book": self.current_book,
                "elapsed_sec": round(elapsed, 2),
                "stats": self.stats,
                "stages": self.stage_data,
            }
            tmp_file = target_path.with_suffix(".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            if tmp_file.exists():
                tmp_file.replace(target_path)
        except Exception:
            pass  # Zero overhead, non-blocking fallback

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
