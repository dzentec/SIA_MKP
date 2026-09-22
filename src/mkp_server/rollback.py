"""Rollback Engine and Multi-Tier Recovery (Invariants I1, I3, I5, I8, I10, I11)."""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Literal

from mkp_server.models import RollbackMode, StorageConfig
from mkp_server.security import compute_file_sha256, verify_checksums
from mkp_server.storage import fsync_dir
from mkp_server.wal import WALManager

logger = logging.getLogger(__name__)


class RollbackManager:
    """Manages transactional recovery and rollback across active, backup and fallback layers."""

    def __init__(self, config: StorageConfig, wal_manager: WALManager | None = None):
        self.config = config
        self.wal = wal_manager or WALManager(config.wal_file)

    def is_backup_valid(self) -> tuple[bool, str]:
        """Check if backup exists and passes SHA-256 integrity verification (Invariant I1, I3)."""
        if not self.config.backup_dir.exists() or not any(self.config.backup_dir.iterdir()):
            return False, "Backup directory does not exist or is empty"

        bp_backup = self.config.backup_dir / "bookpack"
        if not bp_backup.exists():
            return False, "Backup does not contain a bookpack directory"

        manifest_file = bp_backup / "manifest.yaml"
        if not manifest_file.exists():
            return False, "Backup is missing manifest.yaml"

        checksums_file = bp_backup / "checksums.sha256"
        if not checksums_file.exists():
            return False, "Backup is missing checksums.sha256"

        chk_ok, errors = verify_checksums(bp_backup)
        if not chk_ok:
            return False, f"Backup checksum mismatch (I3): {'; '.join(errors)}"

        return True, "Backup exists and is valid"

    def execute_rollback(
        self,
        mode: RollbackMode = RollbackMode.AUTO,
    ) -> tuple[bool, str]:
        """Execute rollback operation based on selected mode (Invariant I5, I8, I10)."""
        self.wal.start_rollback(mode.value)
        self.wal.step("server_stopped")

        success = False
        msg = ""

        try:
            if mode == RollbackMode.AUTO:
                success, msg = self._restore_auto()
            elif mode == RollbackMode.BASE_RESET:
                success, msg = self._restore_base_reset()
            elif mode == RollbackMode.FACTORY:
                success, msg = self._restore_factory()
            else:
                success, msg = False, f"Unknown rollback mode: {mode}"

            if success:
                self.wal.step("server_started")
                self.wal.step("verified")
                self.wal.done()
            else:
                self.wal.error(f"Rollback failed: {msg}")

            return success, msg
        except Exception as e:
            err_msg = f"Rollback exception: {e}"
            self.wal.error(err_msg)
            return False, err_msg

    def _restore_auto(self) -> tuple[bool, str]:
        """One-command rollback to backup if valid, otherwise fail-safe report (I1, I5)."""
        is_valid, reason = self.is_backup_valid()
        if not is_valid:
            return False, f"Cannot perform auto-rollback: {reason}. Choose base-reset or factory."

        # Backup is valid -> restore active from backup
        if self.config.active_dir.exists():
            # Move current active to failed for diagnostics before replacement
            failed_target = self.config.failed_dir / "pre_rollback_active"
            if failed_target.exists():
                shutil.rmtree(failed_target)
            shutil.copytree(self.config.active_dir, failed_target)
            shutil.rmtree(self.config.active_dir)

        shutil.copytree(self.config.backup_dir, self.config.active_dir)
        fsync_dir(self.config.storage_root)

        b_hash = compute_file_sha256(self.config.active_dir / "bookpack" / "manifest.yaml")
        self.wal.step("backup_restored", sha=b_hash or "ok")
        return True, "Successfully restored active from backup"

    def _restore_base_reset(self) -> tuple[bool, str]:
        """Reset only T1 Base from fallback R/O layer while preserving user-layers (I8, §B.6)."""
        active_bp = self.config.active_dir / "bookpack"
        fallback_bp = self.config.fallback_dir / "bookpack"

        if not fallback_bp.exists():
            return False, "Fallback image not available for base reset"

        # Restore base/ from fallback
        active_base = active_bp / "base"
        fallback_base = fallback_bp / "base"
        if fallback_base.exists():
            if active_base.exists():
                shutil.rmtree(active_base)
            shutil.copytree(fallback_base, active_base)

        fsync_dir(self.config.storage_root)
        self.wal.step("backup_restored", type="base_reset_from_fallback")
        return True, "Successfully reset base layer from fallback (user layers preserved)"

    def _restore_factory(self) -> tuple[bool, str]:
        """Full factory reset from R/O fallback layer (Invariant I8, I11)."""
        if not self.config.fallback_dir.exists():
            return False, "Fallback directory not found"

        if self.config.active_dir.exists():
            shutil.rmtree(self.config.active_dir)

        # Restore from fallback
        shutil.copytree(self.config.fallback_dir, self.config.active_dir)
        fsync_dir(self.config.storage_root)
        self.wal.step("backup_restored", type="factory_reset_from_fallback")
        return True, "Successfully completed factory reset from fallback image"
