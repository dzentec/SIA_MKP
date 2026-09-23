"""Session logger for RunPod Orchestrator and TUI.

Creates timestamped session logs in tools/runpod/logs/session_YYYYMMDD_HHMMSS.log
and mirrors output to tools/runpod/logs/latest.log with real-time flushing
and live console output before/after TUI initialization.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console


class OrchestratorLogger:
    """Manages session-level file, console, and memory logging for the RunPod orchestrator."""

    def __init__(self, logs_dir: Path | str | None = None, console_output: bool = True) -> None:
        if logs_dir is None:
            self.logs_dir = Path(__file__).parent / "logs"
        else:
            self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.console_output = console_output
        self.console = Console(legacy_windows=False, force_terminal=True)

        self.session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.session_log_path = self.logs_dir / f"session_{self.session_id}.log"
        self.latest_log_path = self.logs_dir / "latest.log"

        self.logger = logging.getLogger(f"runpod_orch_{self.session_id}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

        # Formatter
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # File Handler (Flush on every write)
        self._file_handler = logging.FileHandler(self.session_log_path, encoding="utf-8")
        self._file_handler.setFormatter(formatter)
        self.logger.addHandler(self._file_handler)

        # In-memory buffer of recent logs for TUI display
        self.recent_entries: list[tuple[str, str, str]] = []  # (timestamp, level, message)
        self._max_recent = 100

        self.info(f"=== Session Started: {self.session_id} ===")
        self._update_latest_link()

    def mute_console(self) -> None:
        """Mutes direct terminal printing when Rich Live TUI takes over the screen."""
        self.console_output = False

    def unmute_console(self) -> None:
        """Unmutes direct terminal printing when TUI completes."""
        self.console_output = True

    def _update_latest_link(self) -> None:
        """Copies session log to latest.log for easy inspection."""
        try:
            shutil.copy2(self.session_log_path, self.latest_log_path)
        except Exception:
            pass

    def _record(self, level: str, msg: str) -> None:
        now_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self.recent_entries.append((now_str, level, msg))
        if len(self.recent_entries) > self._max_recent:
            self.recent_entries.pop(0)

        # Print to terminal if console output is enabled
        if self.console_output:
            lvl_style = "bold red" if level == "ERROR" else "bold yellow" if level == "WARN" else "bold cyan"
            self.console.print(f"[dim]{now_str}[/dim] [{lvl_style}][{level}][/{lvl_style}] {msg}")

        self._update_latest_link()

    def info(self, msg: str) -> None:
        self.logger.info(msg)
        self._file_handler.flush()
        self._record("INFO", msg)

    def warning(self, msg: str) -> None:
        self.logger.warning(msg)
        self._file_handler.flush()
        self._record("WARN", msg)

    def error(self, msg: str) -> None:
        self.logger.error(msg)
        self._file_handler.flush()
        self._record("ERROR", msg)

    def get_recent(self, n: int = 10) -> list[tuple[str, str, str]]:
        return self.recent_entries[-n:]

    def close(self) -> None:
        self.info(f"=== Session Finished: {self.session_id} ===")
        self._update_latest_link()
        self._file_handler.close()
