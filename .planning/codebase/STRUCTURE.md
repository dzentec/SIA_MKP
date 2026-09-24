# STRUCTURE — Directory Map & Module Responsibilities

```
Doc2Rag/
├── .planning/                  # GSD Project Management & Phase Artifacts
│   ├── PROJECT.md              # Vision, scope, requirements summary
│   ├── ROADMAP.md              # Phase definitions and progress milestones
│   ├── REQUIREMENTS.md         # Formal requirement IDs (REQ-*) & Invariants (I0–I14)
│   ├── STATE.md                # Real-time execution status and decisions
│   ├── codebase/               # Codebase Knowledge Map (STACK, ARCH, STRUCTURE, etc.)
│   └── phase-[0-5]/            # Phase plans (PLAN.md), reviews, and UAT acceptance reports
│
├── ontology/                   # Domain Knowledge & Maritime Taxonomies
│   ├── sia_ontology.yaml       # Class hierarchies (Vessel, Maneuver, Weather, Rigging, etc.)
│   ├── sia_relations.yaml      # Allowed relationship types (e.g. `requires_action`, `affects`)
│   ├── mapping.yaml            # Synonym and normalization dictionary
│   └── README.md               # Ontology specifications
│
├── src/                        # Core Application Source Code
│   ├── mkp_common/             # Shared Types & Infrastructure
│   │   ├── models.py           # Chunk, VisualAsset, BBox, DocumentMetadata schemas
│   │   ├── rules_schema.py     # Rule, Trigger, Action, Claim, ManifestV3 schemas
│   │   ├── location.py         # Standardized LocationRef (page, chapter, bbox)
│   │   ├── logger.py           # Structured JSON and console logging
│   │   └── cache.py            # Local disk cache for parser and LLM outputs
│   │
│   ├── mkp_builder/            # Knowledge Extraction & Bookpack Compilation Pipeline
│   │   ├── cli.py              # CLI entry point (`mkp-builder`)
│   │   ├── tui.py              # Interactive Rich TUI for category selection & monitoring
│   │   ├── pipeline.py         # Main pipeline orchestrator
│   │   ├── ocr.py              # RapidOCR integration for raster/scanned content
│   │   ├── chunker.py          # Semantic hierarchy-aware text chunker
│   │   ├── triplets.py         # Knowledge graph triplet extraction
│   │   ├── review.py           # Rich TUI table viewer for synthesized rules
│   │   ├── parsers/            # Document format parsers
│   │   │   ├── base.py         # BaseDocumentParser abstract interface
│   │   │   ├── pdf_parser.py   # Docling PDF parser (layout, tables, figures)
│   │   │   ├── epub_parser.py  # EPUB/XHTML structural parser
│   │   │   └── docx_parser.py  # DOCX structural parser
│   │   ├── vlm/                # Vision-Language Model subsystem
│   │   │   ├── client.py       # Ollama VLM API client
│   │   │   ├── annotator.py    # Diagram description and value extractor
│   │   │   └── verifier.py     # 3-stage validation (syntax, visual match, domain)
│   │   ├── extract/            # Claim extraction
│   │   │   └── claims.py       # Atomic factual statement extractor
│   │   ├── synthesize/         # Rule generation
│   │   │   ├── cluster.py      # Semantic claim clustering
│   │   │   └── synthesize.py   # Rule synthesis with strict threshold citation check
│   │   ├── compile/            # Static Guardrails compiler
│   │   │   └── guardrails.py   # Markdown generator (≤ 8000 chars limit)
│   │   └── export/             # Packaging and crypto signing
│   │       ├── bookpack.py     # Zip/Zst bookpack archiver with per-artifact checksums
│   │       └── signer.py       # Pure-Python RFC 8032 Ed25519 signer and verifier
│   │
│   └── mkp_server/             # Onboard FastMCP Knowledge Server
│       ├── cli.py              # CLI entry point (`mkp-server`)
│       ├── server.py           # FastMCP server exposing 10 tools
│       ├── storage.py          # 4-tier storage manager (active, backup, fallback, staging, failed)
│       ├── wal.py              # Write-Ahead Log engine with directory fsync
│       ├── importer.py         # Transactional bookpack import with signature check & swap
│       ├── rollback.py         # One-command / automatic rollback engine
│       ├── search.py           # LanceDB hybrid vector + BM25 search engine
│       ├── graph.py            # NetworkX knowledge graph engine
│       ├── rules_store.py      # Telemetry-based rule evaluation & conflict engine
│       ├── security.py         # Path traversal sanitizer for diagrams
│       ├── verifier.py         # Storage integrity verifier
│       ├── lifecycle.py        # System health and diagnostic queries
│       └── models.py           # MCP server request/response models
│
├── qa/                         # Quality Assurance, Benchmarking & Evaluation (Phase 4 & 5)
│   ├── config.yaml             # Benchmark thresholds and judge configurations
│   ├── rubrics.py              # Formal evaluation rubrics (M1–M8, M4 agreement, 5-point scale)
│   ├── golden_dataset.json     # 30 stratified questions for Phase 4 acceptance
│   ├── golden_full_dataset.json # 114 comprehensive benchmark questions for Phase 5
│   ├── golden_rules.json       # 15 ground-truth verified maritime rules
│   ├── regression_pool.json    # Regression test suite
│   ├── offline_mcp_agent.py    # Autonomous tool-calling agent (local LLM via 10 MCP tools)
│   ├── eval_judge.py           # Multi-judge LLM-as-a-Judge engine with Wilson/Bootstrap CI
│   ├── evaluator.py            # Aggregate metrics calculator
│   ├── full_eval_runner.py     # Multi-run evaluation orchestrator (N=3, median scoring)
│   ├── run_full_live_benchmark.py # Live benchmark execution script
│   ├── run_real_books_test.py  # Dual-book evaluation on real manuals
│   ├── run_acceptance.py       # Phase 4 acceptance suite runner
│   ├── baseline_runner.py      # Direct LLM baseline comparison runner
│   ├── leakage_check.py        # Train/test dataset contamination checker
│   ├── demo_e2e.py             # Interactive E2E MCP tool suite demonstration
│   ├── reports/                # Evaluation reports and failure taxonomy
│   │   ├── full_eval_report.md # Phase 5 complete evaluation report
│   │   ├── live_full_eval_report.md # Live full dataset evaluation results
│   │   ├── real_books_eval_report.md # Real books benchmark results
│   │   └── failures_detail.md  # Detailed failure categorization
│   └── raw/                    # Raw JSONL agent responses and logs
│
├── tools/                      # Tooling & Infrastructure Automation
│   └── runpod/                 # Zero-Touch RunPod Cloud GPU Pipeline (Qwen2.5-VL 32B)
│       ├── runpod_orchestrator.py # Pod provisioning, SSH/SCP orchestration, remote build
│       ├── runpod_api.py       # GraphQL API client for pod and billing management
│       ├── runpod_manager.py   # High-level pod lifecycle and status manager
│       ├── run_build_32b.py    # Autonomous 32B VLM builder script
│       ├── tui.py              # Rich TUI real-time dashboard (GPU/VRAM/progress)
│       ├── logger.py           # Session logger with generation speed tracking (t/s)
│       ├── AGENT_GUIDE.md      # AI agent operational guide
│       └── RUNPOD_TUI_PLAN.md  # TUI architecture and design specification
│
├── tests/                      # Automated Unit & Integration Tests (45 Tests)
│   ├── test_builder.py         # Parsers, OCR, chunker tests
│   ├── test_export.py          # Bookpack creation and Ed25519 signature tests
│   ├── test_rules_pipeline.py  # Claims extraction, clustering, rule synthesis tests
│   ├── test_server.py          # FastMCP tools, LanceDB search, and graph tests
│   ├── test_invariants.py      # Invariants I0–I14 compliance tests
│   ├── test_qa_invariants_stress.py # WAL crash, power cut, and rollback stress tests
│   ├── test_eval_dataset.py    # Dataset stratification and schema integrity tests
│   ├── test_eval_judge.py      # Judge rubric calibration and scoring tests
│   └── test_runpod_orchestrator.py # RunPod API client and orchestrator unit tests
│
├── poc/                        # Phase 0 Proof-of-Concept Validation Scripts
│   ├── p0_01_docling_crop.py   # Docling figure cropping validation
│   ├── p0_02_vlm_stability.py  # Qwen2.5-VL structured output stability
│   ├── p0_03_lancedb_fts.py    # LanceDB FTS & hybrid retrieval
│   ├── p0_04_e5_embeddings.py  # Multilingual-E5-large embedding checks
│   ├── p0_05_ocr_compare.py    # RapidOCR vs Tesseract comparison
│   ├── p0_06_ladybugdb.py      # NetworkX graph structure checks
│   ├── p0_07_epub_geometry.py  # EPUB image coordinate extraction
│   └── start_ollama.py         # Ollama launch helper with Flash Attention
│
├── pyproject.toml              # Build config, package metadata, dependencies
└── README.md                   # Main project documentation
```
