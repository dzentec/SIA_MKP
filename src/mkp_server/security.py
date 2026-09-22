"""Security, Ed25519 verification and Path Traversal protection (Invariant I3, I13, REQ-S08)."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any
import zipfile

from mkp_builder.export.signer import (
    DEFAULT_DEV_PUBLIC_KEY_HEX,
    verify_data_hex,
)
from mkp_common.cache import compute_sha256_bytes

logger = logging.getLogger(__name__)


def compute_file_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file on disk."""
    if not file_path.is_file():
        return ""
    with open(file_path, "rb") as f:
        return compute_sha256_bytes(f.read())


def verify_bookpack_signature(
    extracted_dir: Path,
    public_key_hex: str = DEFAULT_DEV_PUBLIC_KEY_HEX,
) -> tuple[bool, str]:
    """Verify Ed25519 digital signature of an extracted bookpack (Invariant I13).
    
    The signed payload is: manifest.yaml bytes + b'\\n---CHECKSUMS---\\n' + checksums.sha256 bytes.
    """
    manifest_file = extracted_dir / "manifest.yaml"
    checksums_file = extracted_dir / "checksums.sha256"
    sig_file = extracted_dir / "signature.ed25519"

    if not sig_file.exists():
        return False, "Missing signature.ed25519 (Invariant I13: signature is mandatory)"

    if not manifest_file.exists():
        return False, "Missing manifest.yaml"

    if not checksums_file.exists():
        return False, "Missing checksums.sha256"

    try:
        sig_hex = sig_file.read_text(encoding="utf-8").strip()
        manifest_bytes = manifest_file.read_bytes()
        checksums_bytes = checksums_file.read_bytes()
        payload = manifest_bytes + b"\n---CHECKSUMS---\n" + checksums_bytes

        is_valid = verify_data_hex(payload, sig_hex, public_key_hex)
        if not is_valid:
            return False, "Invalid Ed25519 signature (tampered archive or wrong public key)"
        return True, "Signature valid"
    except Exception as e:
        return False, f"Signature verification error: {e}"


def verify_checksums(extracted_dir: Path) -> tuple[bool, list[str]]:
    """Verify all file SHA-256 hashes against checksums.sha256 and per-artifact files (Invariant I3)."""
    checksums_file = extracted_dir / "checksums.sha256"
    if not checksums_file.exists():
        return False, ["Missing checksums.sha256 file"]

    errors: list[str] = []
    
    # 1. Verify general checksums.sha256
    with open(checksums_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                errors.append(f"Invalid format in checksums.sha256 line {line_num}: {line}")
                continue
            expected_hash, rel_path_str = parts[0], parts[1].strip()
            file_p = extracted_dir / rel_path_str
            if not file_p.is_file():
                errors.append(f"Referenced file missing: {rel_path_str}")
                continue
            actual_hash = compute_file_sha256(file_p)
            if actual_hash.lower() != expected_hash.lower():
                errors.append(
                    f"Hash mismatch for {rel_path_str}: expected {expected_hash}, got {actual_hash}"
                )

    # 2. Verify per-artifact sha256 files in layers
    for layer in ("base", "yacht", "voyage", "personal"):
        layer_dir = extracted_dir / layer
        if layer_dir.is_dir():
            for sha_file in layer_dir.glob("*.sha256"):
                content = sha_file.read_text(encoding="utf-8").strip()
                if content:
                    parts = content.split(maxsplit=1)
                    if len(parts) == 2:
                        exp_h, target_name = parts[0], parts[1].strip()
                        target_f = layer_dir / target_name
                        if target_f.is_file():
                            act_h = compute_file_sha256(target_f)
                            if act_h.lower() != exp_h.lower():
                                errors.append(
                                    f"Per-artifact hash mismatch in {layer}/{sha_file.name}: "
                                    f"expected {exp_h}, got {act_h}"
                                )

    if errors:
        return False, errors
    return True, []


def is_safe_path(base_dir: Path | str, target_path: Path | str) -> bool:
    """Ensure target_path is strictly inside base_dir (Path Traversal protection, REQ-S08)."""
    base_resolved = Path(base_dir).resolve()
    target_resolved = Path(target_path).resolve()
    try:
        target_resolved.relative_to(base_resolved)
        return True
    except ValueError:
        return False


def sanitize_filename(filename: str) -> str:
    """Remove dangerous directory navigation characters from filename."""
    # Strip any directory separators and relative navigation
    clean = filename.replace("\\", "/").split("/")[-1]
    clean = clean.replace("..", "").replace(":", "").strip()
    return clean
