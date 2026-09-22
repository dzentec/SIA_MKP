"""Storage layout, registry management, directory syncing and server logging (REQ-S01, REQ-S10, REQ-S11)."""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import shutil
from typing import Any

from mkp_server.models import BaseRegistry, BookRecord, StorageConfig, StorageStats


def fsync_dir(dir_path: Path | str) -> None:
    """Fsync a directory path to disk ensuring durability on POSIX and Windows."""
    dir_p = Path(dir_path)
    if not dir_p.exists():
        return
    try:
        # On POSIX, opening directory with O_RDONLY and fsync works
        if hasattr(os, "O_DIRECTORY"):
            fd = os.open(str(dir_p), os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    except Exception:
        # Non-critical fallback if OS/filesystem does not support directory fsync
        pass


def setup_server_logging(logs_dir: Path | str, log_level: int = logging.INFO) -> logging.Logger:
    """Configure rotating file logger for mkp-server (REQ-S11: 10MB x 5 backups)."""
    logs_p = Path(logs_dir)
    logs_p.mkdir(parents=True, exist_ok=True)
    log_file = logs_p / "mcp_server.log"

    logger = logging.getLogger("mkp_server")
    logger.setLevel(log_level)

    # Ensure handler for this specific target log_file exists
    target_abs = str(log_file.resolve())
    has_target_handler = any(
        isinstance(h, RotatingFileHandler) and str(Path(getattr(h, "baseFilename", "")).resolve()) == target_abs
        for h in logger.handlers
    )
    if not has_target_handler:
        handler = RotatingFileHandler(
            str(log_file),
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


class StorageManager:
    """Manages the 4-tier storage hierarchy and base registry for a topic."""

    def __init__(self, storage_root: Path | str, topic: str = "marine"):
        self.config = StorageConfig(storage_root=Path(storage_root), topic=topic)
        self.logger = setup_server_logging(self.config.logs_dir)
        self.init_storage_structure()

    def init_storage_structure(self) -> None:
        """Create all required directory tiers if they don't exist."""
        # Active subdirectories
        for d in [
            self.config.active_dir / "server",
            self.config.active_dir / "bookpack" / "base",
            self.config.active_dir / "bookpack" / "yacht",
            self.config.active_dir / "bookpack" / "voyage",
            self.config.active_dir / "bookpack" / "personal",
            self.config.active_dir / "bookpack" / "assets",
            self.config.active_dir / "derived" / "lancedb",
            self.config.backup_dir,
            self.config.staging_dir,
            self.config.fallback_dir,
            self.config.failed_dir,
            self.config.logs_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

        # Initialize base.json if not present
        if not self.config.base_registry_file.exists():
            registry = BaseRegistry(topic=self.config.topic)
            self.save_registry(registry)

        # Also ensure fallback has an initial baseline if fallback is empty
        fallback_flag = self.config.fallback_dir / ".fallback_initialized"
        if not fallback_flag.exists():
            # Create a baseline fallback structure
            (self.config.fallback_dir / "bookpack" / "base").mkdir(parents=True, exist_ok=True)
            fallback_flag.touch()

    def load_registry(self) -> BaseRegistry:
        """Load base.json registry from storage root."""
        if not self.config.base_registry_file.exists():
            return BaseRegistry(topic=self.config.topic)
        try:
            with open(self.config.base_registry_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return BaseRegistry.model_validate(data)
        except Exception as e:
            self.logger.warning("Could not parse base.json, creating default: %s", e)
            return BaseRegistry(topic=self.config.topic)

    def save_registry(self, registry: BaseRegistry) -> None:
        """Atomically save base.json registry with fsync."""
        temp_file = self.config.storage_root / "base.json.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(registry.model_dump(), f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        # Atomic replace
        if os.name == "nt" and self.config.base_registry_file.exists():
            os.replace(str(temp_file), str(self.config.base_registry_file))
        else:
            temp_file.replace(self.config.base_registry_file)

        fsync_dir(self.config.storage_root)

    def add_book_to_registry(self, book_record: BookRecord) -> None:
        """Register or update an imported book record."""
        registry = self.load_registry()
        registry.books[book_record.book_id] = book_record
        registry.last_updated_at = book_record.imported_at
        self.save_registry(registry)

    def remove_book_from_registry(self, book_id: str) -> bool:
        """Remove a book from the registry."""
        registry = self.load_registry()
        if book_id in registry.books:
            del registry.books[book_id]
            self.save_registry(registry)
            return True
        return False

    def get_stats(self) -> StorageStats:
        """Compute comprehensive statistics of the active storage."""
        registry = self.load_registry()
        
        # Calculate disk usage
        total_bytes = 0
        for p in self.config.storage_root.rglob("*"):
            if p.is_file():
                try:
                    total_bytes += p.stat().st_size
                except Exception:
                    pass

        # Count chunks, rules and triplets in active layer
        total_chunks = 0
        total_rules = 0
        total_triplets = 0

        for tier in ("base", "yacht", "voyage", "personal"):
            t_dir = self.config.active_dir / "bookpack" / tier
            if (t_dir / "chunks.jsonl").exists():
                with open(t_dir / "chunks.jsonl", "r", encoding="utf-8") as f:
                    total_chunks += sum(1 for line in f if line.strip())
            if (t_dir / "rules.jsonl").exists():
                with open(t_dir / "rules.jsonl", "r", encoding="utf-8") as f:
                    total_rules += sum(1 for line in f if line.strip())
            if (t_dir / "triplets.jsonl").exists():
                with open(t_dir / "triplets.jsonl", "r", encoding="utf-8") as f:
                    total_triplets += sum(1 for line in f if line.strip())

        wal_status = "idle"
        if self.config.wal_file.exists():
            with open(self.config.wal_file, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
                if lines:
                    last_line = lines[-1]
                    wal_status = "completed" if "DONE" in last_line else f"in_progress: {last_line}"

        return StorageStats(
            topic=self.config.topic,
            storage_path=str(self.config.storage_root),
            total_books=len(registry.books),
            total_chunks=total_chunks,
            total_rules=total_rules,
            total_triplets=total_triplets,
            active_generation=registry.active_generation,
            disk_usage_bytes=total_bytes,
            has_backup=self.config.backup_dir.exists() and any(self.config.backup_dir.iterdir()),
            has_fallback=self.config.fallback_dir.exists(),
            wal_status=wal_status,
        )
