# CONCERNS — Technical Debt, Potential Bottlenecks & Security Considerations

## 1. Performance & Hardware Dependencies
- **Local VLM Inference Latency:** Running Qwen2.5-VL 7B locally on consumer GPUs (e.g. 8GB-12GB VRAM) requires `OLLAMA_FLASH_ATTENTION=1` and 4-bit quantization (Q4_K_M). Complex illustrated manuals with 100+ diagrams can take 20–40 minutes locally.
  - *Mitigation:* The cloud pipeline (`tools/runpod/`) allows offloading heavy books to RTX 4090/A5000 instances running Qwen2.5-VL 32B in ~3–5 minutes per book.
- **LanceDB Index Memory Footprint:** While LanceDB is disk-based and lightweight, high-volume indexing of dozens of books requires monitoring RAM usage on small onboard embedded devices (e.g., Raspberry Pi 5 or yacht mini-PCs with 8GB RAM).

## 2. Model Evolution & Backward Compatibility
- **Ontology Alignment Drift:** As new books are ingested, terms may emerge that are not present in `sia_ontology.yaml` or `mapping.yaml`.
  - *Mitigation:* Unmapped terms are logged during claim extraction and fall back to generic maritime concepts without crashing the pipeline.
- **T1 Deprecations & Tombstones:** When upgrading T1 Base packs, outdated rules and entities must be maintained as tombstones (`deprecated: true`) for 2 releases so downstream user rules don't abruptly break at sea.

## 3. Security & Operational Hardening
- **Physical Media Attacks (USB Delivery):** When books are transferred via USB flash drives at sea, corrupt or tampered archives must be rejected.
  - *Enforcement:* Strictly verified via RFC 8032 Ed25519 digital signature (`signature.ed25519`) and per-artifact SHA-256 digests prior to staging.
- **Path Traversal Protection:** FastMCP `get_diagram_image` endpoint accepts arbitrary `doc_id` and `page` parameters.
  - *Enforcement:* Path sanitizer validates that the resolved file resides strictly within the active bookpack's `assets/` folder and is indexed in `manifest.yaml`.
- **Power Cuts & Incomplete Writes at Sea:** Yacht electrical systems can experience abrupt power drops.
  - *Enforcement:* All write operations use Write-Ahead Logging (`apply.wal`) with directory-level `fsync` and atomic pointer replacement (`renameat2` / atomic `mv`).

## 4. Current Stubs (T2, T2.5, T3)
- **Status of Higher Tiers:** T1 Base is fully production-ready (Chunks, Triplets, Claims, Golden Rules, Guardrails). T2 (Yacht manuals), T2.5 (Voyage guides), and T3 (Personal manuals) are implemented as stubs in the current schema v0.3.0 and will be progressively expanded in subsequent milestones.
