"""FastMCP Knowledge Engine Server with 10 tools and T1 isolation (REQ-S08, REQ-S09, REQ-S12, REQ-S13)."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Literal, Optional
import yaml

from mkp_common.models import ChunkRecord
from mkp_common.rules_schema import BookpackInfo, ManifestV3
from mkp_server.graph import KnowledgeGraph
from mkp_server.models import StorageConfig
from mkp_server.rules_store import RulesStore
from mkp_server.search import SearchEngine
from mkp_server.security import is_safe_path, sanitize_filename
from mkp_server.storage import StorageManager

logger = logging.getLogger(__name__)


class MKPServerEngine:
    """Core state engine holding SearchEngine, KnowledgeGraph, and RulesStore."""

    def __init__(self, storage_root: Path | str, server_version: str = "1.5.0"):
        self.storage_mgr = StorageManager(storage_root)
        self.config = self.storage_mgr.config
        self.server_version = server_version
        self.search_engine = SearchEngine(self.config.active_dir / "derived")
        self.graph = KnowledgeGraph()
        self.rules_store = RulesStore()
        self.manifest: ManifestV3 | None = None
        self.active_chunk_ids: set[str] = set()

        self.reload_active_state()

    def reload_active_state(self) -> None:
        """Load or reload all active chunks, rules, triplets and assets into memory."""
        active_bp = self.config.active_dir / "bookpack"
        if not active_bp.exists():
            return

        # 1. Load manifest if available
        manifest_file = active_bp / "manifest.yaml"
        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                self.manifest = ManifestV3.model_validate(data)
            except Exception as e:
                logger.warning("Could not parse active manifest.yaml: %s", e)

        # 2. Load Chunks across all layers
        self.active_chunk_ids.clear()
        for tier in ("base", "yacht", "voyage", "personal"):
            t_tier_label = {
                "base": "T1",
                "yacht": "T2",
                "voyage": "T2.5",
                "personal": "T3",
            }.get(tier, "T1")
            
            c_file = active_bp / tier / "chunks.jsonl"
            if c_file.exists():
                tier_chunks: list[ChunkRecord] = []
                with open(c_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                c = ChunkRecord.model_validate_json(line)
                                tier_chunks.append(c)
                                self.active_chunk_ids.add(c.chunk_id)
                            except Exception:
                                pass
                self.search_engine.index_chunks(tier_chunks, tier=t_tier_label)

        # 3. Load Triplets into Knowledge Graph
        for tier in ("base", "yacht", "voyage", "personal"):
            t_file = active_bp / tier / "triplets.jsonl"
            if t_file.exists():
                self.graph.load_triplets_file(t_file)

        # 4. Load Rules and Guardrails
        for tier in ("base", "yacht", "voyage", "personal"):
            t_tier_label = {
                "base": "T1",
                "yacht": "T2",
                "voyage": "T2.5",
                "personal": "T3",
            }.get(tier, "T1")
            
            r_file = active_bp / tier / "rules.jsonl"
            if r_file.exists():
                self.rules_store.load_rules_file(
                    r_file,
                    active_chunk_ids=self.active_chunk_ids,
                    default_tier=t_tier_label,  # type: ignore
                )

        # Load static guardrails from base/guardrails.md
        g_file = active_bp / "base" / "guardrails.md"
        if g_file.exists():
            self.rules_store.load_guardrails_file(g_file)

    # --- Tool 1: search_chunks ---
    def search_chunks(
        self,
        query: str,
        top_k: int = 5,
        tier: Optional[str] = None,
        book_id: Optional[str] = None,
        lang: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Semantic hybrid search across document chunks with tier filtering."""
        results = self.search_engine.search(
            query=query,
            top_k=top_k,
            tier=tier,
            book_id=book_id,
            lang=lang,
        )
        return [r.model_dump() for r in results]

    # --- Tool 2: get_diagram_image ---
    def get_diagram_image(
        self,
        doc_id: str,
        page: int,
        image_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Fetch visual diagram asset with Path Traversal protection (REQ-S08)."""
        assets_dir = self.config.active_dir / "bookpack" / "assets"
        if not assets_dir.exists():
            return {"error": "No assets directory found in active bookpack"}

        target_file = None
        if image_name:
            clean_name = sanitize_filename(image_name)
            candidate = assets_dir / clean_name
            if not is_safe_path(assets_dir, candidate):
                return {"error": "Path traversal detected: Access denied"}
            if candidate.exists() and candidate.is_file():
                target_file = candidate
        else:
            # 1. Check indexed chunks for doc_id and page
            for c in self.search_engine.chunks:
                if (c.get("book_id") == doc_id or not doc_id) and c.get("page_number") == page:
                    for diag in c.get("diagrams", []):
                        img_p = diag.get("image_path", "")
                        clean_n = sanitize_filename(img_p)
                        cand = assets_dir / clean_n
                        if cand.is_file():
                            target_file = cand
                            break
                if target_file:
                    break

            # 2. Search by filename pattern in assets
            if not target_file:
                for f in sorted(assets_dir.glob("*.png")):
                    if (doc_id and doc_id in f.name and f"p{page}" in f.name) or f"p{page}" in f.name or f"page_{page}" in f.name:
                        target_file = f
                        break

        if not target_file or not target_file.exists():
            return {"error": f"Image asset not found for doc '{doc_id}' page {page}"}

        # Safe read
        try:
            raw_bytes = target_file.read_bytes()
            b64_data = base64.b64encode(raw_bytes).decode("ascii")
            return {
                "doc_id": doc_id,
                "page": page,
                "filename": target_file.name,
                "size_bytes": len(raw_bytes),
                "mime_type": "image/png",
                "base64_data": b64_data,
            }
        except Exception as e:
            return {"error": f"Failed to read image asset: {e}"}

    # --- Tool 3: get_related_entities ---
    def get_related_entities(self, entity_id: str) -> list[dict[str, Any]]:
        """Retrieve connected knowledge graph nodes, relations and provenance."""
        return self.graph.get_related_entities(entity_id)

    # --- Tool 4: get_book_manifest ---
    def get_book_manifest(self, doc_id: str) -> dict[str, Any]:
        """Retrieve book registration metadata and manifest details."""
        reg = self.storage_mgr.load_registry()
        book = reg.books.get(doc_id)
        if book:
            return book.model_dump()
        if self.manifest:
            return self.manifest.model_dump()
        return {"error": f"Book manifest for '{doc_id}' not found"}

    # --- Tool 5: query_rules ---
    def query_rules(
        self,
        archetype: str,
        telemetry: dict[str, float],
        domain: Optional[str] = None,
        tier: Optional[Literal["T1", "T2", "T2.5"]] = None,
        region: Optional[str] = None,
        status: str = "approved",
    ) -> list[dict[str, Any]]:
        """Find matching operational rules according to telemetry conditions."""
        rules = self.rules_store.query_rules(
            archetype=archetype,
            telemetry=telemetry,
            domain=domain,
            tier=tier,
            region=region,
            status=status,
        )
        return [r.model_dump() for r in rules]

    # --- Tool 6: get_rule ---
    def get_rule(self, rule_id: str) -> dict[str, Any] | None:
        """Lookup full rule card by rule_id."""
        r = self.rules_store.get_rule(rule_id)
        return r.model_dump() if r else None

    # --- Tool 7: get_rule_provenance ---
    def get_rule_provenance(self, rule_id: str) -> list[dict[str, Any]]:
        """Retrieve array of RuleSource with verbatim quotations from source manuals."""
        sources = self.rules_store.get_rule_provenance(rule_id)
        return [s.model_dump() for s in sources]

    # --- Tool 8: list_conflicts ---
    def list_conflicts(self, rule_id: str) -> list[dict[str, Any]]:
        """List rules in contradiction or conflict with rule_id."""
        conflicts = self.rules_store.list_conflicts(rule_id)
        return [c.model_dump() for c in conflicts]

    # --- Tool 9: get_guardrails ---
    def get_guardrails(self) -> str:
        """Retrieve static T1 guardrails markdown text (≤ 8000 characters)."""
        return self.rules_store.get_guardrails()

    # --- Tool 10: get_bookpack_info ---
    def get_bookpack_info(self) -> dict[str, Any]:
        """System metadata: generation, versions, layer hashes, and updates (HLD v3.3 §H.5)."""
        reg = self.storage_mgr.load_registry()
        
        gen = self.manifest.generation if self.manifest else reg.active_generation
        bp_ver = self.manifest.bookpack_version if self.manifest else "0.3.0"
        t1_v = self.manifest.base.t1_version if self.manifest else "1.0.0"
        t1_h = self.manifest.base.t1_hash if self.manifest else ""
        user_l = (
            {
                "t2_hash": self.manifest.user.t2_hash,
                "t25_hash": self.manifest.user.t25_hash,
                "t3_hash": self.manifest.user.t3_hash,
            }
            if self.manifest
            else {}
        )

        info = BookpackInfo(
            generation=gen,
            bookpack_version=bp_ver,
            server_version=self.server_version,
            t1_version=t1_v,
            t1_hash=t1_h,
            user_layers=user_l,
            created_at=self.manifest.created_at if self.manifest else datetime.now(timezone.utc).isoformat(),
            merged_at=self.manifest.base.merged_at if self.manifest else datetime.now(timezone.utc).isoformat(),
            available_updates=[],
        )
        return info.model_dump()


def create_fastmcp_server(storage_root: Path | str) -> Any:
    """Instantiate and register all 10 MCP tools on FastMCP server."""
    from fastmcp import FastMCP

    server = FastMCP("mkp-server")
    engine = MKPServerEngine(storage_root)

    @server.tool()
    def search_chunks(
        query: str,
        top_k: int = 5,
        tier: Optional[str] = None,
        book_id: Optional[str] = None,
        lang: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Hybrid vector and full-text search across chunks."""
        return engine.search_chunks(query, top_k=top_k, tier=tier, book_id=book_id, lang=lang)

    @server.tool()
    def get_diagram_image(
        doc_id: str,
        page: int,
        image_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """Fetch diagram illustration with Path Traversal protection."""
        return engine.get_diagram_image(doc_id, page, image_name)

    @server.tool()
    def get_related_entities(entity_id: str) -> list[dict[str, Any]]:
        """Retrieve connected knowledge graph relations for entity."""
        return engine.get_related_entities(entity_id)

    @server.tool()
    def get_book_manifest(doc_id: str) -> dict[str, Any]:
        """Retrieve manifest and provenance for a book."""
        return engine.get_book_manifest(doc_id)

    @server.tool()
    def query_rules(
        archetype: str,
        telemetry: dict[str, float],
        domain: Optional[str] = None,
        tier: Optional[Literal["T1", "T2", "T2.5"]] = None,
        region: Optional[str] = None,
        status: str = "approved",
    ) -> list[dict[str, Any]]:
        """Find matching operational rules according to telemetry conditions."""
        return engine.query_rules(
            archetype=archetype,
            telemetry=telemetry,
            domain=domain,
            tier=tier,
            region=region,
            status=status,
        )

    @server.tool()
    def get_rule(rule_id: str) -> dict[str, Any] | None:
        """Lookup operational rule by rule_id."""
        return engine.get_rule(rule_id)

    @server.tool()
    def get_rule_provenance(rule_id: str) -> list[dict[str, Any]]:
        """Retrieve array of RuleSource with verbatim quotations from source manuals."""
        return engine.get_rule_provenance(rule_id)

    @server.tool()
    def list_conflicts(rule_id: str) -> list[dict[str, Any]]:
        """List rules in contradiction or conflict with rule_id."""
        return engine.list_conflicts(rule_id)

    @server.tool()
    def get_guardrails() -> str:
        """Retrieve static T1 guardrails markdown text (≤ 8000 characters)."""
        return engine.get_guardrails()

    @server.tool()
    def get_bookpack_info() -> dict[str, Any]:
        """System metadata: generation, versions, layer hashes, and updates."""
        return engine.get_bookpack_info()

    return server
