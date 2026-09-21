# INGEST CONFLICT & EVOLUTION REPORT — HLD MKP-R v3.1

**Date:** 2026-09-21  
**Sources Ingested:**
- [HLD_MKP-R_v3.1_1of2.md](file:///D:/Tasks/My/SIA/DB/Doc2Rag/.init_doc/HLD_MKP-R_v3.1_1of2.md)
- [HLD_MKP-R_v3.1_2of2.md](file:///D:/Tasks/My/SIA/DB/Doc2Rag/.init_doc/HLD_MKP-R_v3.1_2of2.md)
**Existing Baseline:** HLD v1.5 (`.init_doc/HLD_Tools_MCP_v1.5.md`) and `.planning/` v1

---

## 1. Executive Summary

HLD v3.1 evolution from v1.5 represents a major architectural upgrade from a pure **Document-to-RAG + Graph** pipeline to a **Rule-Driven Autonomous Yacht Advisor Engine (MKP-R)**.

The core document ingestion, figure extraction (VLM), chunking, and knowledge graph (triplets) from v1.5 are **100% preserved** as the foundational **T1 Base Document Layer**, upon which the **Rule Pipeline** is layered.

---

## 2. Ingested Architectural Additions (Auto-Resolved)

### 2.1. 4-Tier Content Model
- **T1: Base (🟢 MVP)** — General maritime books, COLREGs, physics, MDA-002 rules. Produces approved rules, static guardrails, and base chunks.
- **T2: Yacht (🟡 Stub in MVP)** — Specific yacht manuals (engine, electrical, rig). Produces hypothesis rules with `review_mode=auto_marked`. Empty implementation returning `[]` in MVP.
- **T2.5: Voyage (🟡 Stub in MVP)** — Cruising guides & regional almanacs. Filtered by `region`. Empty implementation returning `[]` in MVP.
- **T3: Personal (🟡 Stub in MVP)** — Handbooks, cookbooks, language phrasebooks. Search-only, no rules generated.

### 2.2. Rules Pipeline (`mkp-builder`)
- **Claims Extraction (`claims.py`)**: Extracts atomic claims from chunks with ontology validation and quote provenance.
- **Claims Clustering (`cluster.py`)**: Groups related claims by archetype, domain, and triggers.
- **Rule Synthesis (`synthesize.py`)**: Synthesizes formal `Rule` objects with triggers, actions, severity, and uncertainty.
- **Guardrails Compilation (`guardrails.py`)**: Compiles approved critical/warning T1 rules into `compiled_system_prompt.md` (≤ 8000 chars) for static injection into advisor prompts.

### 2.3. Extended Bookpack v0.2 Format
```
<book_id>.bookpack.zip
├── bookpack.json          # schema_version: "2.0" (or "0.2")
├── book_metadata.json
├── pages.jsonl
├── chunks.jsonl
├── triplets.jsonl
├── claims.jsonl           # [NEW]
├── rules.jsonl            # [NEW]
├── guardrails.md          # [NEW compiled prompt]
├── qa_review_queue.jsonl
└── assets/                # PNG diagrams
```

### 2.4. Extended MCP Server Tools (9 Tools)
- **Documents Namespace (🟢 MVP):**
  1. `search_chunks(query: str, top_k: int = 5, tier: Optional[str] = None) -> list[Chunk]`
  2. `get_diagram_image(doc_id: str, page: int) -> Image`
  3. `get_related_entities(entity_id: str) -> list[Entity]`
  4. `get_book_manifest(doc_id: str) -> Manifest`
- **Rules Namespace (🟢 MVP for T1 / 🟡 Stub for T2/T2.5):**
  5. `query_rules(archetype, telemetry, domain=None, tier=None, region=None, status="approved") -> list[Rule]`
  6. `get_rule(rule_id: str) -> Rule`
  7. `get_rule_provenance(rule_id: str) -> list[RuleSource]`
  8. `list_conflicts(rule_id: str) -> list[Rule]`
  9. `get_guardrails() -> str`

---

## 3. Conflict Analysis & Resolution

| Topic | Baseline v1.5 | HLD v3.1 | Resolution | Status |
|---|---|---|---|---|
| **Bookpack Schema** | Version `1.5` | Version `0.2` / `2.0` with `claims.jsonl`, `rules.jsonl`, `guardrails.md` | Non-breaking extension: v0.2 superset contains all v1.5 files | ✅ AUTO-RESOLVED |
| **MCP Tool Names** | `search_maritime_knowledge` | `search_chunks` + `query_rules` + 7 other tools | Align to v3.1 9-tool standard. Keep `search_maritime_knowledge` as alias if needed. | ✅ AUTO-RESOLVED |
| **Graph DB** | LadybugDB in v1.5, NetworkX in PoC | NetworkX / Cypher in v3.1 | PoC decision (NetworkX v1) upheld; `get_related_entities` backed by NetworkX | ✅ AUTO-RESOLVED |
| **Server Rules** | Pure chunk retrieval | Rules engine + static guardrails + chunk retrieval | Add Rules engine layer on top of LanceDB & NetworkX | ✅ AUTO-RESOLVED |
| **Stub Contract** | N/A | T2/T2.5/T3 return `[]` or search-only without crashing | Implement exact signatures with clean stub returns | ✅ AUTO-RESOLVED |

**Unresolved Blockers:** 0  
**Competing Variants:** 0  
**Auto-Resolved:** 5

---

## 4. Next Step Options

1. **Update `.planning/REQUIREMENTS.md` & `.planning/PROJECT.md`** with MKP-R v3.1 scope and requirement IDs (`REQ-R01..R10`).
2. **Harmonize `.planning/ROADMAP.md`**:
   - Complete current **Phase 3 (mkp-server)** incorporating the 9 MCP tools & stub contracts.
   - Add **Phase 5 (Ontology & Rule Schemas)**.
   - Add **Phase 6 (Claims Extraction & Pipeline)**.
   - Add **Phase 7 (Rule Synthesis & Guardrails Compiler)**.
   - Add **Phase 8 (Golden Rules & E2E Validation)**.
