# MKP — Maritime Knowledge Pack (GSD Project)

## Project Context
This project builds a 100% offline, Windows 11 document-to-RAG pipeline for illustrated maritime manuals.

**Two products:**
- `mkp-builder` — heavy pipeline: parsing → OCR → VLM annotation → verification → chunking → triplets → `.bookpack.zip` export
- `mkp-server` — database owner: import archives → build indexes → serve agents via MCP

**HLD source of truth:** `.init_doc/HLD_Tools_MCP_v1.5.md`  
**Planning:** `.planning/` directory (PROJECT.md, REQUIREMENTS.md, ROADMAP.md, STATE.md)

## GSD Workflow Rules

<!-- GSD:WORKFLOW-START -->
This project uses the GSD workflow. Follow these rules:

1. **Check STATE.md before starting any work.** Understand the current phase and open questions.
2. **Check ROADMAP.md** to understand which requirements belong to the current phase.
3. **All implementations must satisfy the requirements in REQUIREMENTS.md** — use REQ-IDs in commits and comments.
4. **Each phase commits its artifacts immediately** — don't batch across phases.
5. **Never skip Phase 0** — all 7 PoC checks must pass before Phase 1 begins.
<!-- GSD:WORKFLOW-END -->

## Architecture Constraints

- **No indexes in mkp-builder** — builder never creates LanceDB/LadybugDB indexes
- **Blue-green indexing** — MCP server must continue serving during rebuild
- **Artifact integrity** — always validate `files_sha256` before importing
- **Path traversal protection** — `get_diagram_image` must validate image_name against manifest
- **Mandatory e5 prefixes** — `passage:` on indexing, `query:` on search (non-negotiable)
- **Pinned dependencies** — LadybugDB and FastMCP must be pinned in pyproject.toml

## Technology Versions
- Python: 3.11
- Docling: ≥ 2.15
- LanceDB: ≥ 0.17
- FastMCP: ≥ 2.2 (pinned)
- FastEmbed model: intfloat/multilingual-e5-large (dim=1024)
- VLM: qwen2.5vl:7b Q4_K_M via Ollama
- Text LLM: qwen2.5:7b via Ollama
- Schema version: 1.5

## Current Status
See `.planning/STATE.md` — Phase 0 (PoC) not yet started.
