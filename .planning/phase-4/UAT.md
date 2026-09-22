# User Acceptance Testing (UAT) Report — MKP-R

**Date:** 2026-09-23  
**Status:** ✅ **VERIFIED & ACCEPTED (100% PASS)**  
**Target Specification:** HLD MKP-R v3.3.1 & REQUIREMENTS.md (REQ-S01..S13, REQ-QA-01, REQ-QA-02)

---

## 1. End-to-End Workflow Verification Results

| Step | Component | Status | Details |
|------|-----------|--------|---------|
| **1. Export** | `mkp-builder` | ✅ PASS | Created `.bookpack.zip` v0.3.0 with SHA-256 integrity and Ed25519 digital signature. |
| **2. Storage & WAL** | `mkp-server` | ✅ PASS | 4-tier storage initialized (`active/`, `backup/`, `staging/`, `fallback/`), safe atomic swap, directory `fsync`. |
| **3. Engine Load** | FastMCP Engine | ✅ PASS | Initialized LanceDB vector index (`multilingual-e5-large`), NetworkX Knowledge Graph, SQLite Rules Store with T1 isolation. |

---

## 2. FastMCP 10 Production Tools UAT

| # | Tool Name | Scope | Verification Result |
|---|-----------|-------|---------------------|
| 1 | [`get_bookpack_info`](file:///d:/Tasks/My/SIA/DB/Doc2Rag/src/mkp_server/server.py#L248) | System | Verified active generation, server version 1.5.0, T1 hash, and layer status. |
| 2 | [`search_chunks`](file:///d:/Tasks/My/SIA/DB/Doc2Rag/src/mkp_server/server.py#L110) | Documents | Verified semantic hybrid search with e5 passage/query embeddings, section hierarchy and metadata. |
| 3 | [`get_diagram_image`](file:///d:/Tasks/My/SIA/DB/Doc2Rag/src/mkp_server/server.py#L129) | Documents | Verified diagram retrieval with Path Traversal protection and safe Base64 streaming. |
| 4 | [`get_related_entities`](file:///d:/Tasks/My/SIA/DB/Doc2Rag/src/mkp_server/server.py#L188) | Documents | Verified NetworkX multi-directional graph traversal and relation extraction. |
| 5 | [`query_rules`](file:///d:/Tasks/My/SIA/DB/Doc2Rag/src/mkp_server/server.py#L204) | Rules | Verified real-time telemetry condition matching (`heel_angle_deg >= 20.0`) and action retrieval. |
| 6 | [`get_rule`](file:///d:/Tasks/My/SIA/DB/Doc2Rag/src/mkp_server/server.py#L225) | Rules | Verified structured operational rule card lookup with severity, actions and metadata. |
| 7 | [`get_rule_provenance`](file:///d:/Tasks/My/SIA/DB/Doc2Rag/src/mkp_server/server.py#L231) | Rules | Verified verbatim source quotation retrieval from original maritime manuals. |
| 8 | [`list_conflicts`](file:///d:/Tasks/My/SIA/DB/Doc2Rag/src/mkp_server/server.py#L237) | Rules | Verified conflict detection engine across operational rules. |
| 9 | [`get_guardrails`](file:///d:/Tasks/My/SIA/DB/Doc2Rag/src/mkp_server/server.py#L243) | Rules | Verified static T1 guardrails text retrieval (340 chars $\le$ 8000 max limit). |
| 10 | [`get_book_manifest`](file:///d:/Tasks/My/SIA/DB/Doc2Rag/src/mkp_server/server.py#L193) | Documents | Verified book registration metadata and chapter structure inspection. |

---

## 3. Reliability & Invariants Summary (I0–I14)

- **Crash Resistance:** 11 WAL crash injection points tested — zero corruption.
- **Rollback:** Verified 1-command rollback when backup valid; 3 safe recovery options (I5) when backup damaged.
- **Immutability:** T1 Read-Only isolation verified; custom rules placed in user layers (T2/T3) without modifying T1.
