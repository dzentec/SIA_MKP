"""Compatibility matrix verification (Invariant I14) and pre-flight checks."""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any
import yaml

from mkp_common.rules_schema import CompatibilityInfo, ManifestV3

logger = logging.getLogger(__name__)


def parse_semver(v_str: str) -> tuple[int, int, int]:
    """Parse version string into (major, minor, patch) integers."""
    v_clean = v_str.strip().lstrip("v")
    parts = v_clean.split(".")
    major = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
    minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    patch = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    return (major, minor, patch)


def is_version_compatible(server_version: str, min_ver: str, max_ver: str) -> bool:
    """Check if server_version is within [min_ver, max_ver] inclusive/wildcard."""
    s_major, s_minor, s_patch = parse_semver(server_version)
    min_major, min_minor, min_patch = parse_semver(min_ver)

    # Check min version
    if (s_major, s_minor, s_patch) < (min_major, min_minor, min_patch):
        return False

    # Check max version (handle wildcards like "2.x.x" or "2.x")
    max_clean = max_ver.strip().lstrip("v")
    if "x" in max_clean.lower() or "*" in max_clean:
        max_major_str = max_clean.split(".")[0]
        if max_major_str.isdigit():
            max_major = int(max_major_str)
            if s_major > max_major:
                return False
        return True
    else:
        max_major, max_minor, max_patch = parse_semver(max_ver)
        if (s_major, s_minor, s_patch) > (max_major, max_minor, max_patch):
            return False

    return True


def validate_compatibility(
    manifest: ManifestV3,
    server_version: str = "1.5.0",
) -> tuple[bool, str]:
    """Validate bookpack compatibility against running server version (Invariant I14)."""
    compat = manifest.compatibility
    if not compat:
        return True, "No compatibility block specified, default allowed"

    # 1. Check server version range
    if not is_version_compatible(server_version, compat.min_server_version, compat.max_server_version):
        return False, (
            f"Server version '{server_version}' incompatible with bookpack requirements: "
            f"min={compat.min_server_version}, max={compat.max_server_version} (Invariant I14)"
        )

    # 2. Check schema version
    if compat.bookpack_schema not in compat.supported_bookpack_schemas:
        return False, (
            f"Bookpack schema version '{compat.bookpack_schema}' is not in supported list: "
            f"{compat.supported_bookpack_schemas}"
        )

    return True, "Compatibility check passed"


def check_disk_space(
    storage_root: Path,
    incoming_package_path: Path,
    safety_multiplier: float = 2.0,
) -> tuple[bool, str]:
    """Preflight check: verify sufficient disk space (≥ 2× active + delta)."""
    try:
        total, used, free = shutil.disk_usage(str(storage_root))
        
        # Calculate active directory size
        active_dir = storage_root / "active"
        active_size = 0
        if active_dir.exists():
            for p in active_dir.rglob("*"):
                if p.is_file():
                    active_size += p.stat().st_size

        pkg_size = incoming_package_path.stat().st_size if incoming_package_path.is_file() else 0
        required_space = int(active_size * safety_multiplier + pkg_size)

        if free < required_space:
            return False, (
                f"Insufficient disk space: required {required_space / (1024*1024):.1f} MB, "
                f"available {free / (1024*1024):.1f} MB"
            )

        return True, "Disk space check passed"
    except Exception as e:
        logger.warning("Could not check disk space: %s", e)
        return True, f"Disk space check skipped: {e}"
