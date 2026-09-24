# Local Ollama & Local Model Architecture Specification

> **CRITICAL RULE FOR ALL AI AGENTS & SCRIPTS:**  
> Ollama is **installed and fully functional** on this machine.  
> Never claim Ollama is missing, and never look for it in default `C:\Users\...\AppData\` paths.

---

## 1. System Paths & Storage Locations

| Component | Absolute Path | Notes |
| :--- | :--- | :--- |
| **Ollama Executable** | `D:\ollama\ollama.exe` | Main daemon and CLI binary |
| **Ollama Internal Libs** | `D:\ollama\lib\ollama\` | Contains `llama-server.exe` and CUDA DLLs |
| **Model Repository** | `D:\AI_models\ollama` | Manifests and GGUF blobs |
| **Ollama Blobs Storage**| `D:\AI_models\ollama\blobs` | Heavy model weight layers |

---

## 2. Mandatory Environment Variables

Before starting or communicating with the Ollama daemon via shell or Python subprocesses, **`OLLAMA_MODELS` MUST be set**:

### PowerShell (Windows 11):
```powershell
$env:OLLAMA_MODELS = "D:\AI_models\ollama"
```

### Command Prompt (CMD):
```cmd
set OLLAMA_MODELS=D:\AI_models\ollama
```

### Python:
```python
import os
os.environ["OLLAMA_MODELS"] = r"D:\AI_models\ollama"
```

---

## 3. Installed Models

| Model Name | Model ID | Quantization / Architecture | Size on Disk |
| :--- | :--- | :--- | :--- |
| **`qwen2.5vl:7b`** | `5ced39dfa4ba` | Q4_K_M (Qwen2.5-VL with mmproj vision) | 6.0 GB |

---

## 4. Hardware Acceleration & Inference Performance

* **GPU**: NVIDIA GeForce RTX 2060 (6.0 GiB VRAM, Compute 7.5, CUDA 13.0 driver)
* **Offloading**: Automatically offloads **14 of 29 layers** into GPU VRAM (~2.45 GiB VRAM allocated), remaining layers execute in system RAM (32 GB).
* **Generation Throughput**: **~7.5 – 8.9 tokens/second**.
* **Prompt Processing**:
  * For prompts < 1 000 tokens: ~1.5–2.5 seconds.
  * For 350-token output: ~40–45 seconds total inference time.

---

## 5. Starting, Checking & Managing the Daemon

### Start Daemon (PowerShell):
```powershell
$env:OLLAMA_MODELS="D:\AI_models\ollama"
D:\ollama\ollama.exe serve
```

### Check Available Models:
```powershell
$env:OLLAMA_MODELS="D:\AI_models\ollama"
D:\ollama\ollama.exe list
```

### Health Check (REST API):
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -Method Get
```

---

## 6. Python Agent Integration Guidelines

When invoking local inference from Python scripts (`qa/offline_mcp_agent.py`, `tools/run_live_qa.py`, etc.):

1. **Endpoint**: `http://127.0.0.1:11434/api/generate` or `http://127.0.0.1:11434/api/chat`
2. **Mandatory HTTP Timeout**: **Minimum `timeout=180`** (3 minutes). Never use default 60s timeout, as local GPU/CPU generation of full answers takes 45–100 seconds.
3. **Model Selection**: Always use `model="qwen2.5vl:7b"`.
4. **Context Management**: To optimize speed on the 6 GB RTX 2060, limit input prompt context to `top_k=2` chunks and concise rules (~600–900 prompt tokens).

```python
import urllib.request
import json

payload = {
    "model": "qwen2.5vl:7b",
    "prompt": prompt_text,
    "stream": False,
    "options": {
        "temperature": 0.1,
        "num_predict": 350
    }
}

req = urllib.request.Request(
    "http://127.0.0.1:11434/api/generate",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)

with urllib.request.urlopen(req, timeout=180) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    answer = data.get("response", "")
```
