"""Logging setup for MKP builder and server."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_builder_logger(logs_dir: Path | str, name: str = "mkp_builder", keep_last: int = 10) -> logging.Logger:
    """Setup structured file logger for builder with timestamped log files."""
    logs_path = Path(logs_dir)
    logs_path.mkdir(parents=True, exist_ok=True)

    # Prune old logs if > keep_last
    log_files = sorted(logs_path.glob("builder_*.log"), key=os.path.getmtime)
    while len(log_files) >= keep_last:
        oldest = log_files.pop(0)
        try:
            oldest.unlink(missing_ok=True)
        except Exception:
            pass

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_path / f"builder_{ts}.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    # File handler (DEBUG)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh.setFormatter(fh_formatter)
    logger.addHandler(fh)

    return logger


def setup_server_logger(base_dir: Path | str, name: str = "mkp_server") -> logging.Logger:
    """Setup rotating file logger for server."""
    logs_path = Path(base_dir) / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    log_file = logs_path / "mcp_server.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    # Rotating file handler (10MB * 5)
    rfh = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    rfh.setLevel(logging.INFO)
    rfh_formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    rfh.setFormatter(rfh_formatter)
    logger.addHandler(rfh)

    return logger
