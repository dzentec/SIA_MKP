"""Bookpack v0.3.0 Exporter with 4-tier content, per-artifact checksums and Ed25519 signing (REQ-B07, I13, I14)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
from typing import Any, Literal
import zipfile
import yaml

from mkp_common.cache import compute_sha256_bytes
from mkp_common.models import ChunkRecord, TripletRecord
from mkp_common.rules_schema import (
    Claim,
    Rule,
    ManifestV3,
    ManifestBase,
    ManifestUser,
    CompatibilityInfo,
)
from mkp_builder.export.signer import sign_data_hex

logger = logging.getLogger(__name__)


def compute_file_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file on disk."""
    if not file_path.exists():
        return ""
    with open(file_path, "rb") as f:
        return compute_sha256_bytes(f.read())


class BookpackExporter:
    """Exports processed documents, rules and assets into signed .bookpack.zip v0.3.0."""

    def __init__(self, out_dir: Path | str):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def export(
        self,
        book_id: str,
        title: str,
        chunks: list[ChunkRecord],
        triplets: list[TripletRecord],
        claims: list[Claim],
        rules: list[Rule],
        guardrails_md: str,
        assets_dir: Path | str | None = None,
        tier: Literal["T1", "T2", "T2.5", "T3"] = "T1",
        region: str | None = None,
        signing_private_key_hex: str | None = None,
    ) -> Path:
        """Export artifacts to 4-tier staging structure and create signed .bookpack.zip."""
        staging_dir = self.out_dir / f"{book_id}_bookpack_staging"
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        staging_dir.mkdir(parents=True, exist_ok=True)

        # 1. Create directory hierarchy
        base_dir = staging_dir / "base"
        yacht_dir = staging_dir / "yacht"
        voyage_dir = staging_dir / "voyage"
        personal_dir = staging_dir / "personal"
        staged_assets_dir = staging_dir / "assets"

        for d in (base_dir, yacht_dir, voyage_dir, personal_dir, staged_assets_dir):
            d.mkdir(parents=True, exist_ok=True)

        # 2. Target layer directory based on tier
        target_dir = {
            "T1": base_dir,
            "T2": yacht_dir,
            "T2.5": voyage_dir,
            "T3": personal_dir,
        }.get(tier, base_dir)

        # 3. Write data files to target layer
        chunks_file = target_dir / "chunks.jsonl"
        with open(chunks_file, "w", encoding="utf-8") as f:
            for c in chunks:
                f.write(c.model_dump_json() + "\n")

        triplets_file = target_dir / "triplets.jsonl"
        with open(triplets_file, "w", encoding="utf-8") as f:
            for t in triplets:
                f.write(t.model_dump_json() + "\n")

        claims_file = target_dir / "claims.jsonl"
        with open(claims_file, "w", encoding="utf-8") as f:
            for cl in claims:
                f.write(cl.model_dump_json() + "\n")

        rules_file = target_dir / "rules.jsonl"
        with open(rules_file, "w", encoding="utf-8") as f:
            for r in rules:
                f.write(r.model_dump_json() + "\n")

        guardrails_file = target_dir / "guardrails.md"
        with open(guardrails_file, "w", encoding="utf-8") as f:
            f.write(guardrails_md)

        # 4. Fill empty stubs for other layers
        for d in (base_dir, yacht_dir, voyage_dir, personal_dir):
            if d != target_dir:
                for stub_name in ("chunks.jsonl", "triplets.jsonl", "claims.jsonl", "rules.jsonl"):
                    stub_f = d / stub_name
                    if not stub_f.exists():
                        stub_f.touch()
                stub_g = d / "guardrails.md"
                if not stub_g.exists():
                    stub_g.touch()

        # 5. Copy visual assets
        if assets_dir and Path(assets_dir).exists():
            for img_path in Path(assets_dir).glob("*.png"):
                shutil.copy2(img_path, staged_assets_dir / img_path.name)

        # 6. Compute per-artifact SHA-256
        per_artifact_hashes: dict[str, Any] = {}
        for layer_name, layer_path in [
            ("base", base_dir),
            ("yacht", yacht_dir),
            ("voyage", voyage_dir),
            ("personal", personal_dir),
        ]:
            c_sha = compute_file_sha256(layer_path / "chunks.jsonl")
            r_sha = compute_file_sha256(layer_path / "rules.jsonl")
            g_sha = compute_file_sha256(layer_path / "guardrails.md")

            # Write per-artifact sha files
            with open(layer_path / "chunks.sha256", "w", encoding="utf-8") as f:
                f.write(f"{c_sha}  chunks.jsonl\n")
            with open(layer_path / "rules.sha256", "w", encoding="utf-8") as f:
                f.write(f"{r_sha}  rules.jsonl\n")

            c_count = len(chunks) if layer_path == target_dir else 0
            r_count = len(rules) if layer_path == target_dir else 0

            per_artifact_hashes[layer_name] = {
                "chunks": {"count": c_count, "sha256": c_sha, "per_artifact": f"{layer_name}/chunks.sha256"},
                "rules": {"count": r_count, "sha256": r_sha, "per_artifact": f"{layer_name}/rules.sha256"},
                "guardrails": {"size_bytes": len(guardrails_md) if layer_path == target_dir else 0, "sha256": g_sha},
            }

        # 7. Generate checksums.sha256
        checksum_lines = []
        for file_p in sorted(staging_dir.rglob("*")):
            if file_p.is_file() and file_p.name not in ("manifest.yaml", "checksums.sha256", "signature.ed25519"):
                rel = file_p.relative_to(staging_dir).as_posix()
                f_hash = compute_file_sha256(file_p)
                checksum_lines.append(f"{f_hash}  {rel}")

        checksums_content = "\n".join(checksum_lines) + "\n"
        with open(staging_dir / "checksums.sha256", "w", encoding="utf-8", newline="\n") as f:
            f.write(checksums_content)

        # 8. Generate manifest.yaml (v0.3.0)
        base_t1_hash = compute_file_sha256(base_dir / "chunks.jsonl")
        manifest_obj = ManifestV3(
            bookpack_version="0.3.0",
            schema_version="1.0",
            ontology_version="0.1.0",
            generation=1,
            parent_hash=None,
            user_id="local",
            base=ManifestBase(
                t1_version="1.0.0",
                t1_hash=base_t1_hash,
            ),
            user=ManifestUser(
                t2_hash=compute_file_sha256(yacht_dir / "chunks.jsonl") if tier == "T2" else None,
                t25_hash=compute_file_sha256(voyage_dir / "chunks.jsonl") if tier == "T2.5" else None,
                t3_hash=compute_file_sha256(personal_dir / "chunks.jsonl") if tier == "T3" else None,
            ),
            compatibility=CompatibilityInfo(
                min_server_version="1.0.0",
                max_server_version="2.x.x",
                bookpack_schema="1.0",
                supported_bookpack_schemas=["0.1", "0.2", "0.3", "1.0"],
            ),
            content=per_artifact_hashes,
        )

        manifest_yaml_str = yaml.dump(
            manifest_obj.model_dump(),
            sort_keys=False,
            allow_unicode=True,
        )
        with open(staging_dir / "manifest.yaml", "w", encoding="utf-8", newline="\n") as f:
            f.write(manifest_yaml_str)

        # 9. Generate Ed25519 signature (I13)
        # Read exact on-disk bytes for manifest and checksums
        manifest_bytes = (staging_dir / "manifest.yaml").read_bytes()
        checksums_bytes = (staging_dir / "checksums.sha256").read_bytes()
        payload_to_sign = manifest_bytes + b"\n---CHECKSUMS---\n" + checksums_bytes

        if signing_private_key_hex:
            signature_hex = sign_data_hex(payload_to_sign, signing_private_key_hex)
        else:
            signature_hex = sign_data_hex(payload_to_sign)

        with open(staging_dir / "signature.ed25519", "w", encoding="utf-8", newline="\n") as f:
            f.write(signature_hex + "\n")

        # 10. Zip archive
        zip_path = self.out_dir / f"{book_id}.bookpack.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_p in sorted(staging_dir.rglob("*")):
                if file_p.is_file():
                    arcname = file_p.relative_to(staging_dir).as_posix()
                    zf.write(file_p, arcname=arcname)

        # Cleanup staging
        shutil.rmtree(staging_dir)

        logger.info("Exported signed Bookpack v0.3.0 to %s", zip_path)
        return zip_path
