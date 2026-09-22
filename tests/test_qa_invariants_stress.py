"""Invariants Stress Testing and Failure Injection Suite (REQ-QA-02, Invariants I0–I14)."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
import shutil
import zipfile

from mkp_builder.export.bookpack import BookpackExporter
from mkp_common.models import ChunkRecord
from mkp_common.rules_schema import Rule, RuleSource, RuleTrigger, RuleAction
from mkp_server.lifecycle import LifecycleManager
from mkp_server.models import RollbackMode
from mkp_server.rollback import RollbackManager
from mkp_server.security import is_safe_path, sanitize_filename
from mkp_server.server import MKPServerEngine
from mkp_server.storage import StorageManager
from mkp_server.wal import WALManager


@pytest.fixture
def test_bookpack(tmp_path: Path) -> Path:
    """Create signed test bookpack."""
    out = tmp_path / "bp_stress_out"
    exporter = BookpackExporter(out_dir=out)
    chunks = [
        ChunkRecord(
            chunk_id="chk_s1",
            book_id="stress_manual",
            page_number=1,
            location_ref="p1",
            text_content="Stress test chunk 1",
        )
    ]
    return exporter.export(
        book_id="stress_manual",
        title="Stress Manual",
        chunks=chunks,
        triplets=[],
        claims=[],
        rules=[],
        guardrails_md="# GUARDRAILS",
    )


def test_power_loss_crash_matrix(tmp_path: Path):
    """Test WAL recovery state detection across simulated power-loss interruption points (I0, I7, I9)."""
    wal_file = tmp_path / "apply.wal"
    wal = WALManager(wal_file)

    # 1. Clean / empty state
    state0 = wal.analyze_recovery_state()
    assert state0["status"] == "clean"
    assert not state0["needs_recovery"]

    # 2. Interrupted before backup creation (I0: active untouched, backup not verified)
    wal.start_apply("delta v1->v2")
    wal.step("preflight_ok")
    wal.step("signature_ok")
    
    state1 = wal.analyze_recovery_state()
    assert state1["status"] == "interrupted"
    assert state1["needs_recovery"]
    assert not state1["has_backup_created"]
    assert not state1["has_backup_verified"]

    # 3. Interrupted after backup created but before verified (I9)
    wal.step("backup_created", sha="h123")
    state2 = wal.analyze_recovery_state()
    assert state2["has_backup_created"]
    assert not state2["has_backup_verified"]  # I9 prevents assuming validity

    # 4. Interrupted after backup verified (I9 marker present)
    wal.step("backup_verified", sha="h123")
    state3 = wal.analyze_recovery_state()
    assert state3["has_backup_verified"]

    # 5. Completed transaction
    wal.done()
    state4 = wal.analyze_recovery_state()
    assert state4["status"] == "completed"
    assert not state4["needs_recovery"]


def test_corrupted_backup_recovery_three_options(tmp_path: Path, test_bookpack: Path):
    """Test 3 recovery options when backup is corrupted/absent (Invariants I5, I8, I11)."""
    storage_root = tmp_path / "corrupt_backup_storage"
    mgr = StorageManager(storage_root)
    lifecycle = LifecycleManager(mgr)

    # 1. Initial valid install (creates active)
    lifecycle.apply_bookpack(test_bookpack)
    # 2. Second apply (backs up active into backup/)
    lifecycle.apply_bookpack(test_bookpack)

    # Initialize fallback layer
    fallback_base = storage_root / "fallback" / "bookpack" / "base"
    fallback_base.mkdir(parents=True, exist_ok=True)
    (fallback_base / "guardrails.md").write_text("# R/O FALLBACK GUARDRAILS", encoding="utf-8")

    # Corrupt backup directory checksums
    backup_chk = storage_root / "backup" / "bookpack" / "checksums.sha256"
    assert backup_chk.exists()
    backup_chk.write_text("invalid_hash  chunks.jsonl\n", encoding="utf-8")

    rb_mgr = RollbackManager(mgr.config)

    # Option 1: Auto-rollback rejects corrupted backup safely (I1, I5)
    ok_auto, msg_auto = rb_mgr.execute_rollback(mode=RollbackMode.AUTO)
    assert not ok_auto
    assert "Cannot perform auto-rollback" in msg_auto

    # Option 2: Base Reset restores from fallback layer (I8, §B.6)
    ok_br, msg_br = rb_mgr.execute_rollback(mode=RollbackMode.BASE_RESET)
    assert ok_br
    assert (storage_root / "active" / "bookpack" / "base" / "guardrails.md").read_text(encoding="utf-8") == "# R/O FALLBACK GUARDRAILS"

    # Option 3: Full Factory Reset from R/O fallback (I8, I11)
    ok_fac, msg_fac = rb_mgr.execute_rollback(mode=RollbackMode.FACTORY)
    assert ok_fac
    assert "Successfully completed factory reset" in msg_fac


def test_sequential_delta_update_storm(tmp_path: Path, test_bookpack: Path):
    """Test applying multiple sequential updates maintaining generation and registry integrity."""
    storage_root = tmp_path / "storm_storage"
    mgr = StorageManager(storage_root)
    lifecycle = LifecycleManager(mgr)

    # Apply 1: Full
    ok1, _ = lifecycle.apply_bookpack(test_bookpack, update_type="full")
    assert ok1
    assert mgr.load_registry().active_generation == 1

    # Apply 2: T1 delta
    ok2, _ = lifecycle.apply_bookpack(test_bookpack, update_type="t1_delta")
    assert ok2

    # Verify backup exists and is valid after sequential applies
    rb_mgr = RollbackManager(mgr.config)
    is_v, _ = rb_mgr.is_backup_valid()
    assert is_v


def test_path_traversal_fuzzing(tmp_path: Path, test_bookpack: Path):
    """Fuzzing get_diagram_image and path validation against directory traversal attack vectors (REQ-S08)."""
    storage_root = tmp_path / "sec_storage"
    mgr = StorageManager(storage_root)
    lifecycle = LifecycleManager(mgr)
    lifecycle.apply_bookpack(test_bookpack)

    engine = MKPServerEngine(storage_root)

    attack_payloads = [
        "../../../../windows/win.ini",
        "..\\..\\..\\boot.ini",
        "/etc/passwd",
        "%2e%2e%2fsecret.png",
        "....//....//config.json",
        "assets/../../../base.json",
    ]

    for payload in attack_payloads:
        # 1. Test server tool
        res = engine.get_diagram_image(doc_id="stress_manual", page=1, image_name=payload)
        assert "error" in res
        assert "Path traversal detected" in res["error"] or "not found" in res["error"]

        # 2. Test sanitize function
        sanitized = sanitize_filename(payload)
        assert ".." not in sanitized
        assert "/" not in sanitized
        assert "\\" not in sanitized
