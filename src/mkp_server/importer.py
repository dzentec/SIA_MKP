"""Update Ingestion, Archive Unpacking and Delta Merging (REQ-S02, REQ-S03, REQ-S04, REQ-S12)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
from typing import Any, Literal
import zipfile
import yaml

from mkp_common.models import ChunkRecord, TripletRecord
from mkp_common.rules_schema import Claim, Rule, ManifestV3, CompatibilityInfo
from mkp_server.models import StorageConfig, BookRecord
from mkp_server.security import verify_bookpack_signature, verify_checksums
from mkp_server.verifier import validate_compatibility

logger = logging.getLogger(__name__)


class BookpackImporter:
    """Handles unpacking, validation and merging of .bookpack.zip packages and deltas."""

    def __init__(self, config: StorageConfig, server_version: str = "1.5.0"):
        self.config = config
        self.server_version = server_version

    def unpack_and_validate(
        self,
        package_path: Path | str,
        target_dir: Path | str,
        public_key_hex: str | None = None,
        skip_signature_check: bool = False,
    ) -> tuple[bool, str, ManifestV3 | None]:
        """Extract .bookpack.zip into target_dir and execute full validation pipeline."""
        pkg_p = Path(package_path)
        tgt_p = Path(target_dir)

        if not pkg_p.is_file():
            return False, f"Package file not found: {pkg_p}", None

        if tgt_p.exists():
            shutil.rmtree(tgt_p)
        tgt_p.mkdir(parents=True, exist_ok=True)

        # 1. Unzip archive
        try:
            with zipfile.ZipFile(pkg_p, "r") as zf:
                zf.extractall(tgt_p)
        except Exception as e:
            return False, f"Failed to extract zip archive: {e}", None

        # 2. Check and verify signature (Invariant I13)
        if not skip_signature_check:
            sig_ok, sig_msg = verify_bookpack_signature(
                tgt_p,
                public_key_hex=public_key_hex or "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
            )
            if not sig_ok:
                return False, f"Ed25519 signature rejection (I13): {sig_msg}", None

        # 3. Load manifest.yaml
        manifest_file = tgt_p / "manifest.yaml"
        if not manifest_file.exists():
            return False, "Missing manifest.yaml in bookpack archive", None

        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest_data = yaml.safe_load(f)
            manifest = ManifestV3.model_validate(manifest_data)
        except Exception as e:
            return False, f"Failed to parse manifest.yaml: {e}", None

        # 4. Check compatibility matrix (Invariant I14)
        comp_ok, comp_msg = validate_compatibility(manifest, self.server_version)
        if not comp_ok:
            return False, f"Compatibility matrix rejection (I14): {comp_msg}", manifest

        # 5. Check SHA-256 checksums (Invariant I3)
        chk_ok, chk_errors = verify_checksums(tgt_p)
        if not chk_ok:
            return False, f"SHA-256 checksum verification failed (I3): {'; '.join(chk_errors)}", manifest

        return True, "Package unpacked and verified successfully", manifest

    def merge_into_staging(
        self,
        extracted_dir: Path,
        staging_dir: Path,
        update_type: Literal["full", "t1_delta", "user_delta"] = "full",
    ) -> None:
        """Merge unpacked bookpack into staging area with tier isolation."""
        staging_bp = staging_dir / "bookpack"
        staging_bp.mkdir(parents=True, exist_ok=True)

        # 1. Update manifest, checksums, signature
        for meta_name in ("manifest.yaml", "checksums.sha256", "signature.ed25519"):
            src_m = extracted_dir / meta_name
            if src_m.exists():
                shutil.copy2(src_m, staging_bp / meta_name)

        # 2. Layer handling
        tiers_to_copy: list[str] = []
        if update_type == "full":
            tiers_to_copy = ["base", "yacht", "voyage", "personal"]
        elif update_type == "t1_delta":
            tiers_to_copy = ["base"]
        elif update_type == "user_delta":
            tiers_to_copy = ["yacht", "voyage", "personal"]

        for tier in ("base", "yacht", "voyage", "personal"):
            src_tier_dir = extracted_dir / tier
            dst_tier_dir = staging_bp / tier
            dst_tier_dir.mkdir(parents=True, exist_ok=True)

            if tier in tiers_to_copy and src_tier_dir.is_dir():
                # Chunks merge (key: chunk_id)
                src_chunks = src_tier_dir / "chunks.jsonl"
                dst_chunks = dst_tier_dir / "chunks.jsonl"
                if src_chunks.exists():
                    merged_chunks: dict[str, str] = {}
                    if dst_chunks.exists():
                        for line in dst_chunks.read_text(encoding="utf-8").splitlines():
                            line_str = line.strip()
                            if line_str:
                                try:
                                    cid = json.loads(line_str).get("chunk_id")
                                    if cid:
                                        merged_chunks[cid] = line_str
                                except Exception:
                                    pass
                    for line in src_chunks.read_text(encoding="utf-8").splitlines():
                        line_str = line.strip()
                        if line_str:
                            try:
                                cid = json.loads(line_str).get("chunk_id")
                                if cid:
                                    merged_chunks[cid] = line_str
                            except Exception:
                                pass
                    dst_chunks.write_text("\n".join(merged_chunks.values()) + ("\n" if merged_chunks else ""), encoding="utf-8")

                # Rules merge (key: rule_id)
                src_rules = src_tier_dir / "rules.jsonl"
                dst_rules = dst_tier_dir / "rules.jsonl"
                if src_rules.exists():
                    merged_rules: dict[str, str] = {}
                    if dst_rules.exists():
                        for line in dst_rules.read_text(encoding="utf-8").splitlines():
                            line_str = line.strip()
                            if line_str:
                                try:
                                    rid = json.loads(line_str).get("rule_id")
                                    if rid:
                                        merged_rules[rid] = line_str
                                except Exception:
                                    pass
                    for line in src_rules.read_text(encoding="utf-8").splitlines():
                        line_str = line.strip()
                        if line_str:
                            try:
                                rid = json.loads(line_str).get("rule_id")
                                if rid:
                                    merged_rules[rid] = line_str
                            except Exception:
                                pass
                    dst_rules.write_text("\n".join(merged_rules.values()) + ("\n" if merged_rules else ""), encoding="utf-8")

                # Triplets merge
                src_triplets = src_tier_dir / "triplets.jsonl"
                dst_triplets = dst_tier_dir / "triplets.jsonl"
                if src_triplets.exists():
                    merged_triplets: set[str] = set()
                    if dst_triplets.exists():
                        for line in dst_triplets.read_text(encoding="utf-8").splitlines():
                            if line.strip():
                                merged_triplets.add(line.strip())
                    for line in src_triplets.read_text(encoding="utf-8").splitlines():
                        if line.strip():
                            merged_triplets.add(line.strip())
                    dst_triplets.write_text("\n".join(sorted(merged_triplets)) + ("\n" if merged_triplets else ""), encoding="utf-8")

                # Guardrails
                src_g = src_tier_dir / "guardrails.md"
                dst_g = dst_tier_dir / "guardrails.md"
                if src_g.exists():
                    new_g = src_g.read_text(encoding="utf-8")
                    if dst_g.exists():
                        old_g = dst_g.read_text(encoding="utf-8")
                        combined_g = old_g.strip() + "\n\n" + new_g.strip() + "\n"
                        if len(combined_g) <= 8000 and new_g not in old_g:
                            dst_g.write_text(combined_g, encoding="utf-8")
                        else:
                            dst_g.write_text(new_g, encoding="utf-8")
                    else:
                        dst_g.write_text(new_g, encoding="utf-8")

                # Other files (sha256, claims, etc.)
                for item in src_tier_dir.iterdir():
                    if item.name not in ("chunks.jsonl", "rules.jsonl", "triplets.jsonl", "guardrails.md"):
                        if item.is_file():
                            shutil.copy2(item, dst_tier_dir / item.name)

        # 3. Copy visual assets
        src_assets = extracted_dir / "assets"
        dst_assets = staging_bp / "assets"
        dst_assets.mkdir(parents=True, exist_ok=True)
        if src_assets.is_dir():
            for img in src_assets.glob("*.png"):
                shutil.copy2(img, dst_assets / img.name)

        # 4. Regenerate checksums.sha256 for merged staging
        from mkp_server.security import compute_file_sha256
        checksum_lines = []
        for file_p in sorted(staging_bp.rglob("*")):
            if file_p.is_file() and file_p.name not in ("checksums.sha256", "signature.ed25519"):
                rel = file_p.relative_to(staging_bp).as_posix()
                f_hash = compute_file_sha256(file_p)
                checksum_lines.append(f"{f_hash}  {rel}")
        (staging_bp / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
