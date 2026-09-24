# ARCHITECTURE — Architectural Design & Invariants (HLD v3.3.1)

## High-Level Design Overview
The **Maritime Knowledge Pipeline with Rules (MKP-R)** is an offline-first, dual-subsystem monorepo designed for yacht navigation and autonomous decision support (SIA Advisor).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      mkp-builder (Offline Pipeline / Shore)                 │
│                                                                             │
│  [Parsers] ──► [OCR / Layout] ──► [VLM Annotator] ──► [3-Stage Verifier]   │
│       │                                                      │              │
│       ▼                                                      ▼              │
│  [Semantic Chunker] ───────────────► [Knowledge Graph Triplets]             │
│       │                                                      │              │
│       ▼                                                      ▼              │
│  [Claim Extractor] ──► [Synthesize Rules] ──► [Guardrails Markdown]         │
│       │                                                      │              │
│       └──────────────────────┬───────────────────────────────┘              │
│                              ▼                                              │
│             [RFC 8032 Ed25519 Signer] ──► [.bookpack.zip v0.3.0]            │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Physical Transfer (USB / Local Sync)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      mkp-server (Onboard Storage & FastMCP)                 │
│                                                                             │
│  • Storage: active/ (N), backup/ (N-1), fallback/ (R/O), staging/, failed/  │
│  • Transactional WAL (`apply.wal`) + Directory fsync + Atomic Swap          │
│  • LanceDB (Hybrid Vector + BM25 FTS, passage:/query: E5 embeddings)        │
│  • NetworkX Knowledge Graph (Entities, Relations, Provenance)               │
│  • RuleStore Engine (Telemetry match: TWS, Heel, Sails, Boat Archetype)     │
│  • FastMCP Service (10 Tools across documents/, rules/, system/)            │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ MCP Protocol
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      SIA Advisor (Onboard Local LLM)                        │
│                                                                             │
│  1. Static Guardrails (≤ 8000 chars in prompt, zero MCP dependency)        │
│  2. Dynamic Rules (query_rules for telemetry triggers & actions)            │
│  3. Deep Search (search_chunks for verbatim citations and explanations)     │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Content Hierarchy: 4-Tier Model
1. **`T1: Base` (`base/`)**: Official maritime regulations, seamanship classics, physics, COLREGs. Read-only for users. Produces approved Golden Rules, Knowledge Graph, and Static Guardrails.
2. **`T2: Yacht` (`yacht/`)**: Vessel-specific manuals (engines, rigging, electrical). Produces hypothesis rules marked `auto_marked: true`.
3. **`T2.5: Voyage` (`voyage/`)**: Cruising guides, pilots, regional regulations. Produces region-scoped rules (`region: caribbean`).
4. **`T3: Personal` (`personal/`)**: Cookbooks, leisure reading, personal logs. Produces search chunks only (rule synthesis skipped).

## Architectural Invariants (I0–I14)
- **I0 (Zero Native Crypto Deps):** Ed25519 signing implemented in pure Python (RFC 8032) for deterministic cross-platform operation.
- **I1 (Zero Hallucination / Non-Lie Policy):** Every rule condition and threshold must have verbatim quotes and pointers (`doc_id`, `page`, `chunk_id`, `quote`). Unverified thresholds are rejected.
- **I2 (Mandatory E5 Prefixes):** All embeddings must strictly use `passage:` for document indexing and `query:` for search.
- **I3 (No Indexes in Builder):** `mkp-builder` outputs raw structured artifacts (`.jsonl`, `.png`, `.md`); `mkp-server` builds LanceDB and graph indices on import.
- **I4 (Blue-Green Storage & Atomic Swap):** Server maintains `active/` and `backup/` with atomic directory exchange (`renameat2` or atomic rename) and directory `fsync`.
- **I5 (One-Command Rollback):** Instant rollback to $N-1$ state without service degradation (`mkp-server rollback`).
- **I6 (WAL Durability):** All import/swap steps logged to `apply.wal` with mandatory `fsync`.
- **I7 (Path Traversal Hardening):** Asset requests (`get_diagram_image`) strictly validated against `manifest.yaml` and resolved canonical paths.
- **I8 (Fallback SquashFS/Static Layer):** Fail-safe fallback directory initialized for catastrophic recovery.
- **I9 (Static Guardrails Constraint):** `guardrails.md` must not exceed 8000 characters and must contain only approved T1 safety rules.
- **I10 (Zero Loss Visual Layer):** High-resolution diagram extraction (scale=2.0) with 3-stage validation.
- **I11 (Tombstones & Orphan Protection):** Deleted T1 entities kept as tombstones for 2 minor versions; user rules marked `orphaned=true` rather than deleted.
- **I12 (No Force-Updates at Sea):** All updates require explicit skipper confirmation.
- **I13 (Cryptographic Signature Verification):** Unsigned or tampered bookpacks are rejected before staging.
- **I14 (Per-Artifact Checksums):** Individual `.sha256` files per artifact prevent partial corruptions.
