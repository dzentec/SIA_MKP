# CONVENTIONS — Code Style, Typing, Error Handling & Logging

## Python Code Style & Version
- **Target Python Version:** `>= 3.11` (compatible up to Python `3.14`).
- **Formatting:** PEP 8 standard formatting with 4-space indentation.
- **Naming Conventions:**
  - Modules and packages: `snake_case` (e.g. `rules_schema.py`, `pdf_parser.py`).
  - Classes and Pydantic models: `PascalCase` (e.g. `Rule`, `VisualAsset`, `StorageManager`).
  - Functions and methods: `snake_case` (e.g. `search_chunks`, `verify_signature`).
  - Constants: `UPPER_SNAKE_CASE` (e.g. `MAX_GUARDRAILS_CHARS`, `E5_PASSAGE_PREFIX`).
  - Requirement IDs: `REQ-<PHASE>-<NUM>` (e.g. `REQ-BLD-01`, `REQ-SRV-04`) referenced in docstrings.

## Typing & Schema Enforcement
- **Strict Pydantic V2 Models:** All shared data contracts in `src/mkp_common/` must subclass `pydantic.BaseModel` with explicit field types and default factories:
  ```python
  from pydantic import BaseModel, Field
  from typing import List, Optional

  class Trigger(BaseModel):
      parameter: str
      operator: str
      threshold: float
      unit: str
  ```
- **Type Annotations:** All public functions and FastMCP tools must have complete type annotations including return types.
- **Pyright Compliance:** Configured via `pyproject.toml` with `extraPaths = [".", "src"]`.

## Error Handling & Resiliency
- **Zero Silent Failures:** Errors during parsing, VLM extraction, or import must be explicitly caught, logged with structured context, and recorded in manifests or error logs.
- **Defensive Path Resolution:**
  - Diagram access strictly uses `resolve_asset_path(doc_id, filename)` preventing Path Traversal (`..` or absolute paths outside the package).
- **Atomic Operations:**
  - All disk mutations in `mkp_server` must write to temporary or staging directories first, execute `fsync`, and finalize via atomic rename (`renameat2` or `shutil.move`).

## Logging & Telemetry
- **Structured Logging:** Centralized logger in `src/mkp_common/logger.py` producing contextual console and file logs.
- **RunPod Session Logs:** Recorded in `tools/runpod/logs/session_<timestamp>.log` with GPU memory, execution duration, and token throughput (t/s).
- **Audit Trails:** Every package import generates entries in `apply.wal` to allow deterministic crash recovery.
