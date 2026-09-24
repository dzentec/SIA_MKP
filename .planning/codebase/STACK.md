# STACK — Technology Stack & Dependencies

## Core Runtime & Language
- **Language:** Python `>=3.11` (tested and verified on Python `3.11+` and `3.14`)
- **Packaging & Build System:** `setuptools>=68.0`, `wheel` (PEP 517 / PEP 621 in `pyproject.toml`)
- **Package Name:** `mkp` (version: `1.5.0`)
- **CLI Entrypoints:**
  - `mkp-builder` -> `mkp_builder.cli:main`
  - `mkp-server` -> `mkp_server.cli:main`

## Core Frameworks & Libraries
- **Data Validation & Schemas:** `pydantic>=2.7.0` (V2 BaseModel, strict schema validation, JSON serialization)
- **CLI Framework:** `typer>=0.12.0`, `click>=8.1.0`
- **TUI & Terminal Formatting:** `rich>=13.7.0`, `tqdm>=4.66.0`
- **Knowledge Graph Engine:** `networkx>=3.2.0` (In-memory entity graph with query traversals)
- **Cryptography & Signatures:** Pure Python Ed25519 (RFC 8032 implementation, zero native C-deps, 100% offline)

## mkp-builder Stack (`[project.optional-dependencies.builder]`)
- **PDF & Document Layout Analysis:** `docling>=2.15.0` (RapidOCR engine, figure bbox extraction, table parsing)
- **OCR Engine:** `rapidocr-onnxruntime>=1.3.0`
- **EPUB Parser:** `ebooklib>=0.18`
- **DOCX Parser:** `python-docx>=1.1.0`
- **PDF Manipulation & Fallbacks:** `pypdf>=4.0.0`, `pdfplumber>=0.11.0`
- **Image Processing:** `pillow>=10.2.0` (image cropping, scale factor 2.0 rendering, PNG export)
- **HTTP / Inference Clients:** `requests>=2.31.0`, `httpx>=0.27.0` (Ollama local REST API & RunPod API)

## mkp-server Stack (`[project.optional-dependencies.server]`)
- **Vector Database:** `lancedb>=0.17.0` (hybrid dense vector + BM25 FTS index)
- **Embeddings & Representations:** `sentence-transformers>=3.0.0` / FastEmbed (`intfloat/multilingual-e5-large`, 1024-dim)
- **MCP Server Protocol:** `fastmcp>=2.2.0` (pinned, implements Model Context Protocol over stdio / HTTP-SSE)

## Testing & QA Stack (`[project.optional-dependencies.dev]`)
- **Test Runner:** `pytest>=8.0.0`, `pytest-asyncio>=0.23.0`
- **Type Checking:** `pyright` (configured for `src`, `qa`, `tests`)
- **Evaluation & Benchmarking:**
  - `qa/eval_judge.py`: Multi-judge LLM-as-a-Judge (Gemini 2.5/Flash & local models)
  - `qa/offline_mcp_agent.py`: Autonomous tool-calling agent simulation
  - Wilson Score and Bootstrap 95% Confidence Interval calculations

## Local AI Infrastructure & Models
- **Local LLM/VLM Host:** Ollama (binary: `D:\ollama\ollama.exe`, models: `D:\AI_models\ollama`)
- **Vision-Language Model (VLM):** `qwen2.5vl:7b Q4_K_M` (with `OLLAMA_FLASH_ATTENTION=1`)
- **Text LLM:** `qwen2.5:7b Q4_K_M` (via Ollama)
- **Embedding Model:** `intfloat/multilingual-e5-large` (dim: 1024, prefix conventions: `passage:` on indexing, `query:` on search)
