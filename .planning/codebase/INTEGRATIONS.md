# INTEGRATIONS — External Systems, Protocols & Cloud Services

## 1. Model Context Protocol (FastMCP)
- **Protocol:** Anthropic Model Context Protocol (MCP) specification.
- **Server Implementation:** `FastMCP` in `src/mkp_server/server.py`.
- **Transports Supported:**
  - `stdio`: Standard input/output for local desktop integration (Claude Desktop, Open WebUI, SIA onboard shell).
  - `http/sse`: Server-Sent Events / HTTP endpoint (`http://<host>:<port>/sse`) for networked access.
- **Namespaces & Tools Exposed (10 Tools):**
  - **`documents/`**: `search_chunks`, `get_diagram_image`, `get_related_entities`, `get_book_manifest`.
  - **`rules/`**: `query_rules`, `get_rule`, `get_rule_provenance`, `list_conflicts`, `get_guardrails`.
  - **`system/`**: `get_bookpack_info`.

## 2. Local Ollama LLM / VLM Service
- **Endpoint:** `http://localhost:11434` (Ollama REST API).
- **Client Implementation:** `src/mkp_builder/vlm/client.py` and `qa/offline_mcp_agent.py`.
- **API Endpoints Utilized:**
  - `/api/generate`: Vision + text prompts for diagram annotation (`qwen2.5vl:7b`).
  - `/api/chat`: Structured JSON generation for claim extraction, rule synthesis, and tool-calling agent loop.
- **Configuration & Optimizations:**
  - `OLLAMA_FLASH_ATTENTION=1` for accelerated multimodal processing.
  - Temperature controls (0.0 for deterministic evaluation, 0.2 for creative claim clustering).

## 3. RunPod Cloud GPU Infrastructure (`tools/runpod/`)
- **API Protocol:** RunPod GraphQL API (`https://api.runpod.io/graphql`).
- **Client Implementation:** `tools/runpod/runpod_api.py`, `tools/runpod/runpod_orchestrator.py`, `tools/runpod/runpod_manager.py`.
- **Hardware Profile:** NVIDIA RTX 4090 / RTX A5000 (24GB VRAM).
- **Image/Template:** `base_sia_mkp` (preconfigured with vLLM / Ollama and `Qwen2.5-VL 32B`).
- **Features:**
  - **Zero-Touch Provisioning:** Dynamic pod creation or reuse.
  - **Direct SSH / SCP:** Automated upload of source books and download of signed `.bookpack.zip` archives.
  - **Auto-Stop & Billing Protection:** Pods automatically execute shutdown via GraphQL API on completion or fatal error ($0/hour idle).
  - **Remote Orchestration Script:** `tools/runpod/run_build_32b.py`.

## 4. Vector DB & Embeddings Engine
- **Storage:** Local LanceDB directory (`storage/active/derived/lancedb`).
- **Search Capabilities:**
  - Dense vector similarity (Cosine distance on 1024-dim vectors).
  - BM25 Full-Text Search (FTS) index with Tantivy backend.
  - Reciprocal Rank Fusion (RRF) / hybrid scoring.
- **Prefix Requirement:** Strict E5 prefix enforcement (`passage:` during indexing, `query:` during retrieval).

## 5. File System & Cryptographic Integrations
- **Archive Format:** `.bookpack.zip` (and optional `.zst` compression) conforming to schema v0.3.0.
- **Integrity Checks:** Per-file `checksums.sha256` and per-artifact digests (`chunks.sha256`, `rules.sha256`).
- **Signature Scheme:** Pure-Python RFC 8032 Ed25519 asymmetric signature (`signature.ed25519`).
- **Transactional Storage & WAL:** Directory synchronization via POSIX `fsync` and atomic pointer swaps (`renameat2` / atomic `mv`).
