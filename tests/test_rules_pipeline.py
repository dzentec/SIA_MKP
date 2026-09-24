"""Comprehensive test suite for Rules Pipeline & Bookpack v0.3.0 Export (Phase 2.1)."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import zipfile
import pytest
import yaml

from mkp_common.models import ChunkRecord, TripletRecord, EntityNode
from mkp_common.rules_schema import (
    Claim,
    Cluster,
    Rule,
    RuleSource,
    RuleTrigger,
    RuleAction,
    CompatibilityInfo,
    ManifestV3,
    BookpackInfo,
    load_ontology,
    load_relations,
    load_mappings,
)
from mkp_builder.extract.claims import ClaimsExtractor
from mkp_builder.synthesize.cluster import ClaimsClusterer
from mkp_builder.synthesize.synthesize import RuleSynthesizer, extract_numbers_from_text
from mkp_builder.compile.guardrails import GuardrailsCompiler
from mkp_builder.export.signer import sign_data_hex, verify_data_hex
from mkp_builder.export.bookpack import BookpackExporter
from mkp_builder.review import generate_golden_t1_rules


def test_ontology_and_relations_loading():
    """Verify ontology files load and contain valid entities and relations."""
    onto = load_ontology()
    assert "domains" in onto and len(onto["domains"]) >= 4
    assert "archetypes" in onto and len(onto["archetypes"]) >= 4
    assert "signals" in onto and len(onto["signals"]) >= 5
    assert "actions" in onto and len(onto["actions"]) >= 5

    rels = load_relations()
    assert "relations" in rels and len(rels["relations"]) >= 5

    mappings = load_mappings()
    assert "mappings" in mappings and len(mappings["mappings"]) >= 10


def test_pydantic_schemas_validation():
    """Verify strict validation of all rules and manifest schemas."""
    src = RuleSource(doc_id="doc1", page=5, chunk_id="doc1_p005_c01", quote="Ease main sheet when heeling over 20 degrees.")
    
    claim = Claim(
        claim_id="cl_01",
        text="Mainsheet should be eased at 20 deg heel",
        type="procedural",
        subject="actions.ease_main_sheet",
        predicate="REQUIRES_ACTION",
        object="telemetry.heel_angle_deg >= 20",
        source=src,
        confidence=0.95,
        mapped=True,
        tier="T1",
    )
    assert claim.type == "procedural"
    assert claim.tier == "T1"

    rule = Rule(
        rule_id="RULE_SAFETY_TEST_001",
        domain="safety",
        archetype=["all_monohulls"],
        triggers=[RuleTrigger(ontology_field="telemetry.heel_angle_deg", operator=">=", value=20.0, unit="deg")],
        actions=[RuleAction(action_id="actions.ease_main_sheet", description="Ease main sheet")],
        severity="warning",
        uncertainty="verified",
        tier="T1",
        sources=[src],
        status="approved",
        deprecated=False,
        orphaned=False,
    )
    assert rule.rule_id == "RULE_SAFETY_TEST_001"
    assert rule.deprecated is False
    assert rule.orphaned is False

    # Compatibility & ManifestV3
    compat = CompatibilityInfo(
        min_server_version="1.0.0",
        max_server_version="2.x.x",
        bookpack_schema="1.0",
        supported_bookpack_schemas=["0.1", "0.2", "0.3", "1.0"],
    )
    manifest = ManifestV3(
        bookpack_version="0.3.0",
        schema_version="1.0",
        generation=1,
        compatibility=compat,
    )
    assert manifest.bookpack_version == "0.3.0"
    assert manifest.generation == 1


def test_ed25519_signature_and_tamper_detection():
    """Verify Ed25519 digital signature signing and tamper detection (Invariant I13)."""
    payload = b"manifest_data_v030\nchecksums_sha256_entries"
    sig = sign_data_hex(payload)
    assert len(sig) == 128  # 64 bytes hex encoded

    # Valid verification
    assert verify_data_hex(payload, sig) is True

    # Tampered payload fails
    tampered = payload + b"TAMPERED"
    assert verify_data_hex(tampered, sig) is False

    # Corrupted signature fails
    bad_sig = sig[:-4] + "0000"
    assert verify_data_hex(payload, bad_sig) is False


def test_claims_extractor_tier_skipping_and_mapping():
    """Verify ClaimsExtractor skips T3 and maps ontology terms."""
    extractor = ClaimsExtractor(client=None, cache=None)  # type: ignore

    # Test term mapping
    mapped_id, is_mapped = extractor.map_term("tws")
    assert is_mapped is True
    assert mapped_id == "telemetry.true_wind_speed_kt"

    mapped_reef, is_reef = extractor.map_term("take a reef")
    assert is_reef is True
    assert mapped_reef == "actions.reef_main_1"

    # T3 skip test
    c_t3 = ChunkRecord(
        chunk_id="test_t3_p01_c01",
        book_id="cooking_guide",
        page_number=1,
        location_ref="epub:s1",
        text_content="Add two spoons of salt into the boiling water.",
    )
    claims_t3 = extractor.extract_from_chunk(c_t3, tier="T3")
    assert len(claims_t3) == 0


def test_claims_clustering_and_contradictions():
    """Verify ClaimsClusterer groups by topics and identifies contradictions."""
    clusterer = ClaimsClusterer(book_id="test_book")

    src1 = RuleSource(doc_id="book1", page=10, chunk_id="b1_c1", quote="Reef at 18 knots")
    src2 = RuleSource(doc_id="book2", page=20, chunk_id="b2_c2", quote="Do not reef before 25 knots")

    c1 = Claim(
        claim_id="c01",
        text="Reef main at 18 knots",
        type="procedural",
        subject="actions.reef_main_1",
        predicate="REQUIRES_ACTION",
        object="18 kt",
        source=src1,
        mapped=True,
    )
    c2 = Claim(
        claim_id="c02",
        text="Hold full sail up to 25 knots",
        type="procedural",
        subject="actions.reef_main_1",
        predicate="CONTRADICTS",
        object="25 kt",
        source=src2,
        mapped=True,
    )

    clusters = clusterer.cluster_claims([c1, c2], tier="T1")
    assert len(clusters) >= 1
    reef_cluster = clusters[0]
    assert len(reef_cluster.claims) == 2
    assert len(reef_cluster.contradictions) == 1


def test_rule_synthesizer_threshold_validation():
    """Verify threshold validator blocks invented numbers (Anti-hallucination)."""
    text = "At 22 knots of wind, take the second reef. If heel reaches 25 degrees, ease the sheet."
    allowed_nums = extract_numbers_from_text(text)
    assert 22.0 in allowed_nums
    assert 25.0 in allowed_nums

    synthesizer = RuleSynthesizer(client=None, cache=None)  # type: ignore

    # Valid triggers present in text
    valid_triggers = [
        RuleTrigger(ontology_field="telemetry.true_wind_speed_kt", operator=">=", value=22.0, unit="knots"),
        RuleTrigger(ontology_field="telemetry.heel_angle_deg", operator=">=", value=25.0, unit="deg"),
    ]
    assert synthesizer.validate_triggers_against_quotes(valid_triggers, allowed_nums) is True

    # Hallucinated trigger not in text
    hallucinated_triggers = [
        RuleTrigger(ontology_field="telemetry.true_wind_speed_kt", operator=">=", value=45.0, unit="knots")
    ]
    assert synthesizer.validate_triggers_against_quotes(hallucinated_triggers, allowed_nums) is False


def test_guardrails_compiler_structure_and_limits():
    """Verify GuardrailsCompiler produces compact valid Markdown under 8000 chars."""
    rules = generate_golden_t1_rules(book_id="dedekam_seamanship")
    assert len(rules) >= 15

    compiler = GuardrailsCompiler()
    guardrails_md = compiler.compile(rules, include_draft=True)

    assert "# SIA MARITIME STATIC SAFETY GUARDRAILS" in guardrails_md
    assert "🔴 CRITICAL" in guardrails_md
    assert "🟡 WARNING" in guardrails_md
    assert len(guardrails_md) <= 8000
    assert len(guardrails_md) > 500


def test_golden_rules_dataset_integrity():
    """Verify all 15+ golden rules meet full provenance and trigger criteria."""
    rules = generate_golden_t1_rules(book_id="dedekam_seamanship")
    assert len(rules) >= 15

    for r in rules:
        assert r.rule_id.startswith("RULE_")
        assert r.tier == "T1"
        assert r.status == "approved"
        assert len(r.sources) >= 1
        assert len(r.sources[0].quote) > 10
        assert len(r.triggers) >= 1
        assert len(r.actions) >= 1


def test_bookpack_v03_export_and_signature_verification():
    """Verify BookpackExporter creates valid signed Bookpack v0.3.0 with 4 layers and per-artifact sha."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        exporter = BookpackExporter(out_dir=tmp_path)

        rules = generate_golden_t1_rules(book_id="demo_book")
        chunks = [
            ChunkRecord(
                chunk_id="demo_book_p001_c01",
                book_id="demo_book",
                page_number=1,
                location_ref="pdf:p1",
                text_content="Heel angle should never exceed 20 degrees.",
            )
        ]
        triplets = [
            TripletRecord(
                subject=EntityNode(name="mainsail", type="Sail"),
                predicate="CONTROLLED_BY",
                object=EntityNode(name="mainsheet", type="Rigging"),
                provenance={"book_id": "demo_book", "page_number": 1, "chunk_id": "demo_book_p001_c01", "location_ref": "pdf:p1"},
            )
        ]
        claims = [
            Claim(
                claim_id="cl_demo_01",
                text="Heel limit is 20 deg",
                type="procedural",
                subject="telemetry.heel_angle_deg",
                predicate="TRIGGERS_AT",
                object="20 deg",
                source=RuleSource(doc_id="demo_book", page=1, chunk_id="demo_book_p001_c01", quote="Heel angle should never exceed 20 degrees."),
                mapped=True,
            )
        ]
        compiler = GuardrailsCompiler()
        guardrails_md = compiler.compile(rules, include_draft=True)

        zip_path = exporter.export(
            book_id="demo_book",
            title="Demo Seamanship Guide",
            chunks=chunks,
            triplets=triplets,
            claims=claims,
            rules=rules,
            guardrails_md=guardrails_md,
            tier="T1",
        )

        assert zip_path.exists()

        # Inspect zip contents
        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()
            assert "manifest.yaml" in namelist
            assert "checksums.sha256" in namelist
            assert "signature.ed25519" in namelist
            assert "base/chunks.jsonl" in namelist
            assert "base/rules.jsonl" in namelist
            assert "base/guardrails.md" in namelist
            assert "base/chunks.sha256" in namelist
            assert "base/rules.sha256" in namelist
            assert "yacht/chunks.jsonl" in namelist
            assert "voyage/chunks.jsonl" in namelist
            assert "personal/chunks.jsonl" in namelist

            # Read and parse manifest.yaml
            manifest_raw = zf.read("manifest.yaml").decode("utf-8")
            manifest_data = yaml.safe_load(manifest_raw)
            assert manifest_data["bookpack_version"] == "0.3.0"
            assert manifest_data["generation"] == 1
            assert manifest_data["compatibility"]["min_server_version"] == "1.0.0"
            assert manifest_data["base"]["t1_version"] == "1.0.0"
            assert len(manifest_data["base"]["t1_hash"]) == 64

            # Verify signature
            sig_hex = zf.read("signature.ed25519").decode("utf-8").strip()
            checksums_raw = zf.read("checksums.sha256").decode("utf-8")
            payload = manifest_raw.encode("utf-8") + b"\n---CHECKSUMS---\n" + checksums_raw.encode("utf-8")
            assert verify_data_hex(payload, sig_hex) is True


def test_synthesize_rules_progress_callback():
    """Verify that on_progress callback is invoked for every cluster during synthesis."""
    from unittest.mock import MagicMock
    from mkp_builder.synthesize.synthesize import RuleSynthesizer

    mock_client = MagicMock()
    mock_client.generate.return_value = json.dumps({
        "rule": {
            "rule_id": "RULE_TRIM_TEST_01",
            "domain": "trim",
            "triggers": [{"ontology_field": "telemetry.tws", "operator": ">=", "value": 20.0, "unit": "kt"}],
            "actions": [{"action_id": "actions.reef", "description": "Reef"}],
            "severity": "warning",
        }
    })

    synthesizer = RuleSynthesizer(client=mock_client)

    src = RuleSource(doc_id="d1", page=1, chunk_id="c1", quote="wind 20 kt")
    claims = [
        Claim(claim_id=f"cl_{i}", text=f"claim {i}", type="procedural", subject="s", predicate="p", object="o", source=src)
        for i in range(3)
    ]
    clusters = [
        Cluster(cluster_id=f"clust_{i}", topic=f"topic_{i}", dominant_type="procedural", archetypes=["all_monohulls"], claims=[f"cl_{i}"])
        for i in range(3)
    ]

    progress_events = []
    def _cb(idx: int, total: int, rule: Rule | None) -> None:
        progress_events.append((idx, total, rule.rule_id if rule else None))

    rules = synthesizer.synthesize_rules(clusters=clusters, claims=claims, tier="T1", on_progress=_cb)

    assert len(progress_events) == 3
    assert progress_events[0] == (1, 3, "RULE_TRIM_TEST_01")
    assert progress_events[1] == (2, 3, "RULE_TRIM_TEST_01")
    assert progress_events[2] == (3, 3, "RULE_TRIM_TEST_01")
    assert len(rules) == 3
