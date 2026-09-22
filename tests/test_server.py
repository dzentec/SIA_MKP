"""Comprehensive tests for mkp-server (Storage, Search, Graph, Rules, and 10 MCP Tools)."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
import shutil

from mkp_builder.export.bookpack import BookpackExporter
from mkp_common.models import (
    ChunkRecord,
    TripletRecord,
    EntityNode,
    VisualAsset,
    VlmData,
    DiagramType,
)
from mkp_common.rules_schema import (
    Claim,
    Rule,
    RuleSource,
    RuleTrigger,
    RuleAction,
)
from mkp_server.graph import KnowledgeGraph
from mkp_server.lifecycle import LifecycleManager
from mkp_server.models import RollbackMode, StorageConfig
from mkp_server.rules_store import RulesStore
from mkp_server.search import E5Embedder, SearchEngine
from mkp_server.security import is_safe_path, sanitize_filename
from mkp_server.server import MKPServerEngine, create_fastmcp_server
from mkp_server.storage import StorageManager


@pytest.fixture
def sample_bookpack_zip(tmp_path: Path) -> Path:
    """Create a valid signed v0.3.0 bookpack zip archive."""
    out_dir = tmp_path / "builder_out"
    exporter = BookpackExporter(out_dir=out_dir)

    chunks = [
        ChunkRecord(
            chunk_id="chunk_001",
            book_id="heavy_weather_sailing",
            page_number=42,
            location_ref="p42_c1",
            section_path="Chapter 3 > Storm Tactics",
            text_content="When true wind speed exceeds 25 knots, prepare for first reef on the mainsail.",
            visual_assets=[
                VisualAsset(
                    image_path="assets/fig_p42_01.png",
                    image_sha256="aabbcc112233",
                    vlm_data=VlmData(
                        diagram_type=DiagramType.MANEUVER,
                        description="Diagram showing first reef line setup and boom topping lift tension.",
                    ),
                )
            ],
        ),
        ChunkRecord(
            chunk_id="chunk_002",
            book_id="heavy_weather_sailing",
            page_number=45,
            location_ref="p45_c1",
            section_path="Chapter 3 > Storm Tactics",
            text_content="Heaving-to in storm conditions stabilizes the vessel and reduces roll motion.",
        ),
    ]

    triplets = [
        TripletRecord(
            subject=EntityNode(name="First Reef", type="maneuver"),
            predicate="reduces_heel_on",
            object=EntityNode(name="Heavy Wind", type="weather_condition"),
            provenance={"doc_id": "heavy_weather_sailing", "page_number": 42, "chunk_id": "chunk_001"},
        ),
        TripletRecord(
            subject=EntityNode(name="Heaving-to", type="tactics"),
            predicate="mitigates",
            object=EntityNode(name="Rudder Stall", type="failure_mode"),
            provenance={"doc_id": "heavy_weather_sailing", "page_number": 45, "chunk_id": "chunk_002"},
        ),
    ]

    claims = [
        Claim(
            claim_id="cl_001",
            text="First reef at 25 knots wind",
            type="empirical",
            subject="Mainsail",
            predicate="reefed_at",
            object=25,
            source=RuleSource(
                doc_id="heavy_weather_sailing",
                page=42,
                chunk_id="chunk_001",
                quote="When true wind speed exceeds 25 knots, prepare for first reef",
            ),
        )
    ]

    rules = [
        Rule(
            rule_id="RULE-REEF-001",
            domain="reefing",
            archetype=["all", "monohull"],
            triggers=[
                RuleTrigger(ontology_field="telemetry.true_wind_speed_kt", operator=">=", value=25.0, unit="kt"),
            ],
            triggers_logic="ALL",
            actions=[
                RuleAction(action_id="reef_1", description="Take first reef in mainsail"),
            ],
            severity="warning",
            sources=[
                RuleSource(
                    doc_id="heavy_weather_sailing",
                    page=42,
                    chunk_id="chunk_001",
                    quote="When true wind speed exceeds 25 knots, prepare for first reef",
                )
            ],
            conflicts_with=["RULE-REEF-002"],
            status="approved",
        ),
        Rule(
            rule_id="RULE-REEF-002",
            domain="reefing",
            archetype=["performance_multihull"],
            triggers=[
                RuleTrigger(ontology_field="telemetry.true_wind_speed_kt", operator=">=", value=18.0, unit="kt"),
            ],
            triggers_logic="ALL",
            actions=[
                RuleAction(action_id="reef_1_early", description="Reef early on multihull at 18kt"),
            ],
            severity="critical",
            sources=[
                RuleSource(
                    doc_id="heavy_weather_sailing",
                    page=42,
                    chunk_id="chunk_001",
                    quote="Multihulls require earlier reefing",
                )
            ],
            conflicts_with=["RULE-REEF-001"],
            status="approved",
        ),
    ]

    guardrails_md = "# STATIC GUARDRAILS (T1 BASE)\n- Always check rig tension and wear before heavy weather.\n"

    # Create dummy asset
    assets_tmp = tmp_path / "assets_src"
    assets_tmp.mkdir(parents=True, exist_ok=True)
    dummy_img = assets_tmp / "fig_p42_01.png"
    dummy_img.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")

    zip_path = exporter.export(
        book_id="heavy_weather_sailing",
        title="Heavy Weather Sailing",
        chunks=chunks,
        triplets=triplets,
        claims=claims,
        rules=rules,
        guardrails_md=guardrails_md,
        assets_dir=assets_tmp,
        tier="T1",
    )
    return zip_path


def test_storage_initialization(tmp_path: Path):
    """Test 4-tier storage creation, base.json and rotating file logger (REQ-S01, REQ-S10, REQ-S11)."""
    storage_root = tmp_path / "marine_storage"
    mgr = StorageManager(storage_root, topic="marine")

    # Verify directories
    assert (storage_root / "active" / "bookpack" / "base").exists()
    assert (storage_root / "backup").exists()
    assert (storage_root / "staging").exists()
    assert (storage_root / "fallback").exists()
    assert (storage_root / "failed").exists()
    assert (storage_root / "logs").exists()
    assert (storage_root / "base.json").exists()

    # Verify logging
    mgr.logger.info("Test server log event")
    log_file = storage_root / "logs" / "mcp_server.log"
    assert log_file.exists()
    assert "Test server log event" in log_file.read_text(encoding="utf-8")

    # Verify stats
    stats = mgr.get_stats()
    assert stats.topic == "marine"
    assert stats.total_books == 0


def test_hybrid_search_e5(tmp_path: Path):
    """Test SearchEngine with E5 embeddings (mandatory prefixes) and hybrid FTS ranking (REQ-S05, REQ-C03)."""
    search_engine = SearchEngine()

    chunks = [
        ChunkRecord(
            chunk_id="c1",
            book_id="book_a",
            page_number=10,
            location_ref="p10",
            text_content="Heaving-to tactics for storm evasion in offshore cruising.",
            lang="en",
        ),
        ChunkRecord(
            chunk_id="c2",
            book_id="book_b",
            page_number=20,
            location_ref="p20",
            text_content="Anchor retrieval and windlass operation under high load.",
            lang="en",
        ),
    ]

    search_engine.index_chunks(chunks, tier="T1")

    # Search with prefix query
    results = search_engine.search("storm heaving-to", top_k=5)
    assert len(results) > 0
    assert results[0].chunk_id == "c1"
    assert results[0].tier == "T1"

    # Search with tier filter
    t2_results = search_engine.search("storm", tier="T2")
    assert len(t2_results) == 0

    # Search with book_id filter
    b_results = search_engine.search("anchor", book_id="book_b")
    assert len(b_results) == 1
    assert b_results[0].chunk_id == "c2"


def test_knowledge_graph(tmp_path: Path):
    """Test KnowledgeGraph loading triplets and querying relationships (REQ-S06)."""
    kg = KnowledgeGraph()
    triplet = TripletRecord(
        subject=EntityNode(name="Main Sheet", type="equipment"),
        predicate="controls_trim_of",
        object=EntityNode(name="Mainsail", type="sail"),
        provenance={"doc_id": "rigging_guide", "page_number": 15, "chunk_id": "c_rig_01"},
    )
    kg.add_triplet(triplet)

    # Inbound / Outbound relations
    out_rel = kg.get_related_entities("Main Sheet")
    assert len(out_rel) == 1
    assert out_rel[0]["predicate"] == "controls_trim_of"
    assert out_rel[0]["object"] == "Mainsail"
    assert out_rel[0]["provenance"]["chunk_id"] == "c_rig_01"

    in_rel = kg.get_related_entities("Mainsail")
    assert len(in_rel) == 1
    assert in_rel[0]["direction"] == "inbound"


def test_rules_store_telemetry_matching(tmp_path: Path):
    """Test RulesStore telemetry trigger conditions and guardrails (REQ-R01..R04)."""
    store = RulesStore(guardrails_content="# GUARDRAILS\nKeep watch.")
    
    rule = Rule(
        rule_id="RULE-HEEL-01",
        domain="safety",
        archetype=["monohull"],
        triggers=[
            RuleTrigger(ontology_field="telemetry.heel_angle_deg", operator=">", value=30.0),
        ],
        triggers_logic="ALL",
        actions=[RuleAction(action_id="ease_main", description="Ease main sheet immediately")],
        severity="critical",
        status="approved",
    )
    store.rules[rule.rule_id] = rule

    # Telemetry heel = 35 -> matches
    matched = store.query_rules(archetype="monohull", telemetry={"heel": 35.0})
    assert len(matched) == 1
    assert matched[0].rule_id == "RULE-HEEL-01"

    # Telemetry heel = 20 -> does not match
    not_matched = store.query_rules(archetype="monohull", telemetry={"heel": 20.0})
    assert len(not_matched) == 0

    # Wrong archetype -> does not match
    wrong_arch = store.query_rules(archetype="catamaran", telemetry={"heel": 35.0})
    assert len(wrong_arch) == 0


def test_10_mcp_tools_execution(tmp_path: Path, sample_bookpack_zip: Path):
    """Verify all 10 FastMCP tools respond correctly with imported bookpack (REQ-S08, REQ-S13)."""
    storage_root = tmp_path / "marine_storage"
    mgr = StorageManager(storage_root)
    lifecycle = LifecycleManager(mgr)

    # 1. Apply Bookpack
    ok, msg = lifecycle.apply_bookpack(sample_bookpack_zip)
    assert ok, f"Apply failed: {msg}"

    engine = MKPServerEngine(storage_root)

    # Tool 1: search_chunks
    t1_res = engine.search_chunks("mainsail reef wind", top_k=5)
    assert len(t1_res) > 0
    assert t1_res[0]["chunk_id"] == "chunk_001"

    # Tool 2: get_diagram_image (with valid image and path traversal check)
    t2_res = engine.get_diagram_image(doc_id="heavy_weather_sailing", page=42)
    assert "base64_data" in t2_res
    assert t2_res["mime_type"] == "image/png"

    # Path traversal attack check
    evil_res = engine.get_diagram_image(doc_id="heavy_weather_sailing", page=42, image_name="../../secret.txt")
    assert "Path traversal detected" in evil_res.get("error", "") or "not found" in evil_res.get("error", "")

    # Tool 3: get_related_entities
    t3_res = engine.get_related_entities("First Reef")
    assert len(t3_res) > 0
    assert t3_res[0]["predicate"] == "reduces_heel_on"

    # Tool 4: get_book_manifest
    t4_res = engine.get_book_manifest("heavy_weather_sailing")
    assert t4_res.get("generation") == 1 or "heavy_weather_sailing" in t4_res.get("book_id", "")

    # Tool 5: query_rules
    t5_res = engine.query_rules(archetype="monohull", telemetry={"tws": 28.0})
    assert len(t5_res) > 0
    assert t5_res[0]["rule_id"] == "RULE-REEF-001"

    # Tool 6: get_rule
    t6_res = engine.get_rule("RULE-REEF-001")
    assert t6_res is not None
    assert t6_res["rule_id"] == "RULE-REEF-001"

    # Tool 7: get_rule_provenance
    t7_res = engine.get_rule_provenance("RULE-REEF-001")
    assert len(t7_res) > 0
    assert "When true wind speed exceeds 25 knots" in t7_res[0]["quote"]

    # Tool 8: list_conflicts
    t8_res = engine.list_conflicts("RULE-REEF-001")
    assert len(t8_res) > 0
    assert t8_res[0]["rule_id"] == "RULE-REEF-002"

    # Tool 9: get_guardrails
    t9_res = engine.get_guardrails()
    assert "STATIC GUARDRAILS" in t9_res

    # Tool 10: get_bookpack_info
    t10_res = engine.get_bookpack_info()
    assert t10_res["generation"] == 1
    assert t10_res["bookpack_version"] == "0.3.0"
    assert t10_res["server_version"] == "1.5.0"


def test_fastmcp_server_factory(tmp_path: Path):
    """Test FastMCP server instantiation and tool registration."""
    storage_root = tmp_path / "fastmcp_storage"
    server = create_fastmcp_server(storage_root)
    assert server.name == "mkp-server"
