"""Write-Ahead Log (WAL) for transactional apply, recovery and rollback (Invariants I0, I7, I9, I10, REQ-S07)."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
from typing import Any

from mkp_server.storage import fsync_dir

logger = logging.getLogger(__name__)


class WALManager:
    """Manages transactional logging in apply.wal with immediate fsync durability."""

    def __init__(self, wal_path: Path | str):
        self.wal_path = Path(wal_path)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def log_event(self, kind: str, name_or_desc: str, **kwargs: Any) -> str:
        """Append an event entry to the WAL file with immediate fsync (kind: START, STEP, DONE, ERROR)."""
        extra_str = " ".join(f"{k}={v}" for k, v in kwargs.items())
        line = f"[{self._now_iso()}] {kind} {name_or_desc}"
        if extra_str:
            line += f" {extra_str}"
        line += "\n"

        self.wal_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.wal_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

        fsync_dir(self.wal_path.parent)
        return line.strip()

    def start_apply(self, description: str) -> str:
        return self.log_event("START", f"apply {description}")

    def step(self, step_name: str, **kwargs: Any) -> str:
        return self.log_event("STEP", step_name, **kwargs)

    def done(self) -> str:
        return self.log_event("DONE", "transaction_complete")

    def error(self, err_msg: str) -> str:
        return self.log_event("ERROR", err_msg)

    def start_rollback(self, rollback_type: str) -> str:
        return self.log_event("START", f"rollback {rollback_type}")

    def read_entries(self) -> list[str]:
        """Read all lines from WAL file."""
        if not self.wal_path.exists():
            return []
        with open(self.wal_path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

    def analyze_recovery_state(self) -> dict[str, Any]:
        """Analyze WAL history to detect interrupted transactions and recovery readiness (I0, I7, I9)."""
        entries = self.read_entries()
        if not entries:
            return {
                "status": "clean",
                "in_progress": False,
                "has_backup_verified": False,
                "last_step": None,
                "needs_recovery": False,
            }

        # Find last START transaction
        last_start_idx = -1
        for i, e in enumerate(entries):
            if "START" in e:
                last_start_idx = i

        if last_start_idx == -1:
            return {
                "status": "clean",
                "in_progress": False,
                "has_backup_verified": False,
                "last_step": None,
                "needs_recovery": False,
            }

        tx_entries = entries[last_start_idx:]
        is_done = any("DONE" in e for e in tx_entries)
        has_backup_verified = any("STEP backup_verified" in e for e in tx_entries)
        has_backup_created = any("STEP backup_created" in e for e in tx_entries)
        
        last_step = tx_entries[-1]

        if is_done:
            return {
                "status": "completed",
                "in_progress": False,
                "has_backup_verified": has_backup_verified,
                "last_step": last_step,
                "needs_recovery": False,
            }

        # If transaction started but never finished with DONE -> crash / power-loss
        return {
            "status": "interrupted",
            "in_progress": True,
            "has_backup_created": has_backup_created,
            "has_backup_verified": has_backup_verified,  # I9: recovery uses backup_verified as marker
            "last_step": last_step,
            "needs_recovery": True,
        }
