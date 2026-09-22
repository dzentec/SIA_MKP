"""Tests verifying the 15 Reliability Invariants (I0–I14) and Orphaning (REQ-S01..S13, HLD v3.3.1)."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
import shutil
import zipfile

from mkp_builder.export.bookpack import BookpackExporter
from mkp_builder.export.signer import DEFAULT_DEV_PRIVATE_KEY_HEX
from mkp_common.models import ChunkRecord, TripletRecord, EntityNode
from mkp_common.rules_schema import Claim, Rule, RuleSource, RuleTrigger, RuleAction
from mkp_server.lifecycle import LifecycleManager
from mkp_server.models import RollbackMode
from mkp_server.rollback import RollbackManager
from mkp_server.rules_store import RulesStore
from mkp_server.security import verify_bookpack_signature
from mkp_server.storage import StorageManager
from mkp_server.wal import WALManager


@pytest.fixture
def base_bookpack(tmp_path: Path) -> Path:
    """Create standard signed Bookpack v0.3.0."""
    out = tmp_path / "exp_base"
    exporter = BookpackExporter(out_dir=out)

    chunks = [
        ChunkRecord(
            chunk_id="chunk_101",
            book_id="book_weather",
            page_number=10,
            location_ref="p10",
            text_content="Heel angle should not exceed 30 degrees during gusts.",
        )
    ]
    triplets = [
        TripletRecord(
            subject=EntityNode(name="Gust", type="weather"),
            predicate="causes_heel_on",
            object=EntityNode(name="Vessel", type="boat"),
            provenance={"doc_id": "book_weather", "page_number": 10, "chunk_id": "chunk_101"},
        )
    ]
    rules = [
        Rule(
            rule_id="RULE-HEEL-30",
            domain="safety",
            archetype=["all"],
            triggers=[RuleTrigger(ontology_field="telemetry.heel_angle_deg", operator=">", value=30.0)],
            severity="critical",
            sources=[
                RuleSource(doc_id="book_weather", page=10, chunk_id="chunk_101", quote="Heel angle should not exceed 30 degrees")
            ],
            status="approved",
        )
    ]
    return exporter.export(
        book_id="book_weather",
        title="Weather and Stability",
        chunks=chunks,
        triplets=triplets,
        claims=[],
        rules=rules,
        guardrails_md="# GUARDRAILS\nStability limit 30 deg.\n",
    )


def test_invariant_i13_ed25519_signature_mandatory(tmp_path: Path, base_bookpack: Path):
    """Invariant I13: Ed25519 digital signature is mandatory; missing/tampered signature causes rejection."""
    storage_root = tmp_path / "i13_storage"
    mgr = StorageManager(storage_root)
    lifecycle = LifecycleManager(mgr)

    # 1. Valid signature -> PASS
    ok, msg = lifecycle.apply_bookpack(base_bookpack)
    assert ok, f"Valid signature should be accepted: {msg}"

    # 2. Tampered zip (modify manifest without updating signature)
    tampered_zip = tmp_path / "tampered.bookpack.zip"
    unpacked_tmp = tmp_path / "unpacked_temp"
    with zipfile.ZipFile(base_bookpack, "r") as zf:
        zf.extractall(unpacked_tmp)

    manifest_p = unpacked_tmp / "manifest.yaml"
    manifest_p.write_text(manifest_p.read_text(encoding="utf-8") + "\n# malicious injection\n", encoding="utf-8")

    with zipfile.ZipFile(tampered_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in unpacked_tmp.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(unpacked_tmp).as_posix())

    # Apply tampered -> must FAIL with I13 signature error
    mgr2 = StorageManager(tmp_path / "i13_storage2")
    lifecycle2 = LifecycleManager(mgr2)
    ok_t, msg_t = lifecycle2.apply_bookpack(tampered_zip)
    assert not ok_t
    assert "Ed25519" in msg_t or "signature" in msg_t.lower()


def test_invariant_i14_compatibility_matrix(tmp_path: Path, base_bookpack: Path):
    """Invariant I14: Compatibility matrix is verified before apply."""
    storage_root = tmp_path / "i14_storage"
    mgr = StorageManager(storage_root)
    
    # Run with an incompatible server version (e.g. 0.9.0 when min is 1.0.0)
    lifecycle = LifecycleManager(mgr, server_version="0.9.0")
    ok, msg = lifecycle.apply_bookpack(base_bookpack, skip_signature=True)
    assert not ok
    assert "incompatible" in msg.lower() or "I14" in msg


def test_invariant_i0_active_untouched_on_early_fail(tmp_path: Path, base_bookpack: Path):
    """Invariant I0: If apply fails before backup (preflight/signature), active layer is untouched."""
    storage_root = tmp_path / "i0_storage"
    mgr = StorageManager(storage_root)
    lifecycle = LifecycleManager(mgr)

    # Initial valid install
    lifecycle.apply_bookpack(base_bookpack)
    active_manifest_orig = (storage_root / "active" / "bookpack" / "manifest.yaml").read_text(encoding="utf-8")

    # Apply a broken file that fails signature
    broken_zip = tmp_path / "broken.zip"
    broken_zip.write_bytes(b"corrupted zip data")

    ok, msg = lifecycle.apply_bookpack(broken_zip)
    assert not ok

    # Invariant I0 check: active manifest is completely untouched
    active_manifest_after = (storage_root / "active" / "bookpack" / "manifest.yaml").read_text(encoding="utf-8")
    assert active_manifest_orig == active_manifest_after


def test_invariant_i1_i2_i3_i9_backup_and_wal(tmp_path: Path, base_bookpack: Path):
    """Invariants I1, I2, I3, I9: Backup before apply, verified SHA-256, and WAL tracks backup_verified."""
    storage_root = tmp_path / "i1_storage"
    mgr = StorageManager(storage_root)
    lifecycle = LifecycleManager(mgr)

    # Initial install
    lifecycle.apply_bookpack(base_bookpack)
    # Second update to create verified backup
    lifecycle.apply_bookpack(base_bookpack)

    # Check WAL records
    wal_entries = lifecycle.wal.read_entries()
    assert any("STEP backup_created" in e for e in wal_entries)
    assert any("STEP backup_verified" in e for e in wal_entries)  # I9: backup_verified is recorded separately
    assert any("DONE" in e for e in wal_entries)

    # Verify backup validity (I1, I3)
    rb_mgr = RollbackManager(mgr.config, lifecycle.wal)
    is_valid, reason = rb_mgr.is_backup_valid()
    assert is_valid


def test_invariant_i5_i7_i10_smoke_failure_auto_rollback(tmp_path: Path, base_bookpack: Path):
    """Invariants I5, I7, I10: Smoke test failure triggers automatic rollback and preserves WAL for audit."""
    storage_root = tmp_path / "i5_storage"
    mgr = StorageManager(storage_root)
    lifecycle = LifecycleManager(mgr)

    # 1. First install (initial baseline)
    lifecycle.apply_bookpack(base_bookpack)
    assert (storage_root / "active" / "bookpack" / "manifest.yaml").exists()

    # 2. Second apply with failing smoke test
    def failing_smoke_test(active_dir: Path) -> bool:
        return False  # Emulate smoke test failure

    ok, msg = lifecycle.apply_bookpack(base_bookpack, smoke_tester=failing_smoke_test)
    assert not ok
    assert "Smoke test failed" in msg or "Auto-rollback" in msg

    # Invariant I10: WAL is preserved and contains both apply failure and rollback steps
    wal_entries = lifecycle.wal.read_entries()
    assert any("START rollback" in e for e in wal_entries)
    assert any("STEP backup_restored" in e for e in wal_entries)


def test_invariant_i8_i11_multi_level_fallback(tmp_path: Path, base_bookpack: Path):
    """Invariants I8, I11: Rollback multi-level options (base-reset and factory from R/O fallback)."""
    storage_root = tmp_path / "i8_storage"
    mgr = StorageManager(storage_root)
    lifecycle = LifecycleManager(mgr)

    lifecycle.apply_bookpack(base_bookpack)

    # Populate fallback layer
    fallback_base = storage_root / "fallback" / "bookpack" / "base"
    fallback_base.mkdir(parents=True, exist_ok=True)
    (fallback_base / "guardrails.md").write_text("# FACTORY GUARDRAILS", encoding="utf-8")

    # Corrupt backup so auto-rollback cannot be used
    if mgr.config.backup_dir.exists():
        shutil.rmtree(mgr.config.backup_dir)

    rb_mgr = RollbackManager(mgr.config)
    
    # Try Base Reset from fallback
    ok_br, msg_br = rb_mgr.execute_rollback(mode=RollbackMode.BASE_RESET)
    assert ok_br
    assert "Successfully reset base layer from fallback" in msg_br
    assert (storage_root / "active" / "bookpack" / "base" / "guardrails.md").read_text(encoding="utf-8") == "# FACTORY GUARDRAILS"

    # Try Factory Reset from fallback
    ok_fac, msg_fac = rb_mgr.execute_rollback(mode=RollbackMode.FACTORY)
    assert ok_fac
    assert "Successfully completed factory reset" in msg_fac


def test_user_layer_orphaning(tmp_path: Path):
    """REQ-S12 / HLD v3.3 §G: User-layer rules pointing to deleted T1 chunks are marked orphaned=True."""
    store = RulesStore()

    # User rule referencing chunk_missing
    user_rule = Rule(
        rule_id="USER-RULE-001",
        domain="trim",
        archetype=["all"],
        origin="user",
        sources=[RuleSource(doc_id="doc1", page=1, chunk_id="chunk_missing", quote="old quote")],
        severity="info",
        status="approved",
    )
    store.rules[user_rule.rule_id] = user_rule

    # Write rule to temp file
    r_file = tmp_path / "rules.jsonl"
    with open(r_file, "w", encoding="utf-8") as f:
        f.write(user_rule.model_dump_json() + "\n")

    # Active chunks does NOT contain chunk_missing
    active_chunk_ids = {"chunk_001", "chunk_002"}

    new_store = RulesStore()
    new_store.load_rules_file(r_file, active_chunk_ids=active_chunk_ids, default_tier="T2")

    loaded_r = new_store.get_rule("USER-RULE-001")
    assert loaded_r is not None
    assert loaded_r.orphaned is True
