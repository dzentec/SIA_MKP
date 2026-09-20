"""
P0-02 — VLM: qwen2.5vl:7b stability test via Ollama
REQ: REQ-P0-02
Tests: JSON validity, diagram_type accuracy, hang detection, FLASH_ATTENTION speedup
Requires: Ollama installed and running, qwen2.5vl:7b pulled
"""

import os
import sys
import time
import json
import base64
import asyncio
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()

CROPS_DIR = Path(__file__).parent / "assets" / "crops"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
VLM_MODEL = "qwen2.5vl:7b"
TIMEOUT_SEC = 45
NUM_PREDICT = 512

# Prompt v2.0 - discriminated union JSON
SYSTEM_PROMPT = """You are a maritime diagram analyzer. 
Analyze the image and respond ONLY with valid JSON matching this schema exactly:
{
  "diagram_type": "<one of: maneuver|knot|equipment|polar|map|table_figure|other>",
  "description": "<brief description in English>",
  "maneuver": null,
  "knot": null,
  "equipment": null,
  "polar": null,
  "map": null,
  "table_figure": null
}
Only fill the field matching diagram_type; set all others to null.
Respond with JSON only, no extra text."""

REQUIRED_KEYS = ["diagram_type", "description", "maneuver", "knot", "equipment", "polar", "map", "table_figure"]
VALID_TYPES = {"maneuver", "knot", "equipment", "polar", "map", "table_figure", "other"}


def image_to_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_vlm(image_path: str) -> tuple[dict | None, float, str]:
    """Call Ollama VLM, return (parsed_json | None, elapsed_sec, raw_text)."""
    import httpx

    img_b64 = image_to_base64(image_path)
    payload = {
        "model": VLM_MODEL,
        "messages": [
            {
                "role": "user",
                "content": SYSTEM_PROMPT,
                "images": [img_b64],
            }
        ],
        "stream": False,
        "format": "json",
        "options": {
            "num_predict": NUM_PREDICT,
            "temperature": 0.1,
        },
    }

    start = time.time()
    try:
        with httpx.Client(timeout=TIMEOUT_SEC) as client:
            resp = client.post(f"{OLLAMA_HOST}/api/chat", json=payload)
            resp.raise_for_status()
            elapsed = time.time() - start

        data = resp.json()
        raw_text = data.get("message", {}).get("content", "")

        try:
            parsed = json.loads(raw_text)
            return parsed, elapsed, raw_text
        except json.JSONDecodeError:
            return None, elapsed, raw_text

    except httpx.TimeoutException:
        elapsed = time.time() - start
        return None, elapsed, "TIMEOUT"
    except Exception as e:
        elapsed = time.time() - start
        return None, elapsed, f"ERROR: {e}"


def validate_response(parsed: dict | None, raw: str) -> dict:
    """Validate response structure and return quality metrics."""
    if parsed is None:
        return {
            "json_valid": False,
            "has_all_keys": False,
            "valid_type": False,
            "null_others": False,
            "timed_out": "TIMEOUT" in raw,
        }

    has_all_keys = all(k in parsed for k in REQUIRED_KEYS)
    diagram_type = parsed.get("diagram_type", "")
    valid_type = diagram_type in VALID_TYPES

    # Check: only matching type is non-null
    null_others = True
    for key in REQUIRED_KEYS[2:]:  # skip diagram_type, description
        val = parsed.get(key)
        if key == diagram_type and val is None:
            null_others = False  # the matching type should ideally be filled
        elif key != diagram_type and val is not None:
            null_others = False  # others should be null

    return {
        "json_valid": True,
        "has_all_keys": has_all_keys,
        "valid_type": valid_type,
        "null_others": null_others,
        "diagram_type": diagram_type,
        "timed_out": False,
    }


def check_ollama() -> bool:
    """Check if Ollama is reachable and model is available."""
    import httpx
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{OLLAMA_HOST}/api/tags")
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                available = any(VLM_MODEL in n or VLM_MODEL.split(":")[0] in n for n in model_names)
                if available:
                    console.print(f"[green]✓ Ollama running, {VLM_MODEL} available[/green]")
                else:
                    console.print(f"[yellow]⚠ Ollama running but {VLM_MODEL} not in: {model_names[:5]}[/yellow]")
                    console.print(f"[yellow]  Run: ollama pull {VLM_MODEL}[/yellow]")
                return available
    except Exception as e:
        console.print(f"[red]✗ Ollama not reachable at {OLLAMA_HOST}: {e}[/red]")
        return False


def ensure_ollama_running() -> bool:
    """Start Ollama serve as a subprocess and wait until it's ready."""
    import subprocess, httpx

    ollama_exe = r"D:\Ollama\ollama.exe"
    env = os.environ.copy()
    env["OLLAMA_MODELS"] = r"D:\AI_models\ollama"
    env["OLLAMA_HOST"] = "127.0.0.1:11434"

    # Check if already running
    try:
        with httpx.Client(timeout=3) as c:
            r = c.get("http://127.0.0.1:11434/api/tags")
            if r.status_code == 200:
                console.print("[green]✓ Ollama already running[/green]")
                return True
    except Exception:
        pass

    console.print("[yellow]Starting Ollama serve...[/yellow]")
    try:
        proc = subprocess.Popen(
            [ollama_exe, "serve"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        # Store so Python keeps it alive
        main._ollama_proc = proc

        # Wait up to 15s for it to come up
        for i in range(30):
            time.sleep(0.5)
            try:
                with httpx.Client(timeout=2) as c:
                    r = c.get("http://127.0.0.1:11434/api/tags")
                    if r.status_code == 200:
                        console.print(f"[green]✓ Ollama ready (after {(i+1)*0.5:.1f}s)[/green]")
                        return True
            except Exception:
                pass
            if proc.poll() is not None:
                console.print(f"[red]✗ Ollama exited early (code {proc.returncode})[/red]")
                return False

        console.print("[red]✗ Ollama did not become ready in 15s[/red]")
        return False
    except Exception as e:
        console.print(f"[red]✗ Failed to start Ollama: {e}[/red]")
        return False


def ensure_model_pulled() -> bool:
    """Pull VLM model if not already available."""
    import httpx

    console.print(f"[yellow]Checking if {VLM_MODEL} is available...[/yellow]")
    try:
        with httpx.Client(timeout=10) as c:
            tags = c.get("http://127.0.0.1:11434/api/tags").json()
            model_names = [m.get("name", "") for m in tags.get("models", [])]
            if any(VLM_MODEL in n or VLM_MODEL.split(":")[0] in n for n in model_names):
                console.print(f"[green]✓ {VLM_MODEL} already pulled[/green]")
                return True

        # Pull it
        console.print(f"[yellow]Pulling {VLM_MODEL} (this may take several minutes)...[/yellow]")
        with httpx.Client(timeout=None) as c:
            last_pct = -1
            with c.stream("POST", "http://127.0.0.1:11434/api/pull", json={"name": VLM_MODEL}) as resp:
                for line in resp.iter_lines():
                    if line:
                        data = json.loads(line)
                        status = data.get("status", "")
                        completed = data.get("completed", 0)
                        total = data.get("total", 0)
                        if total > 0:
                            pct = int(completed / total * 100)
                            if pct != last_pct and (pct % 10 == 0 or pct >= 99):
                                mb = completed // 1024 // 1024
                                mb_total = total // 1024 // 1024
                                console.print(f"  {pct}%  {mb}/{mb_total} MB")
                                last_pct = pct
                        elif status and status not in ("", last_pct):
                            console.print(f"  {status}")
                            last_pct = status

        console.print(f"[green]✓ {VLM_MODEL} pulled successfully[/green]")
        return True
    except Exception as e:
        console.print(f"[red]✗ Pull failed: {e}[/red]")
        return False


def main():
    main._ollama_proc = None  # will hold the subprocess if we start it
    console.print("\n[bold cyan]═══ T0-02: VLM Stability Test (qwen2.5vl:7b) ═══[/bold cyan]\n")
    console.print(f"Ollama host: {OLLAMA_HOST}")
    console.print(f"Model: {VLM_MODEL}")
    console.print(f"Timeout: {TIMEOUT_SEC}s | num_predict: {NUM_PREDICT}")

    # ─── Step 1: Ensure Ollama is running ───
    if not ensure_ollama_running():
        console.print("\n[red]BLOCKED: Cannot start Ollama.[/red]")
        console.print(f"  Make sure D:\\Ollama\\ollama.exe exists")
        return {"pass": False, "blocked": True, "reason": "Ollama failed to start"}

    # ─── Step 1b: Ensure model is pulled ───
    if not ensure_model_pulled():
        return {"pass": False, "blocked": True, "reason": f"{VLM_MODEL} pull failed"}


    # ─── Step 2: Find test images ───
    image_files = sorted(CROPS_DIR.glob("*.png"))
    if len(image_files) < 5:
        console.print(f"[yellow]⚠ Only {len(image_files)} crops found in {CROPS_DIR}[/yellow]")
        console.print("[yellow]  Run p0_01_docling_crop.py first to generate images[/yellow]")
        if not image_files:
            return {"pass": False, "blocked": True, "reason": "No crops, run T0-01 first"}

    # Use up to 10 images
    test_images = image_files[:10]
    console.print(f"\nTesting on {len(test_images)} images from {CROPS_DIR}")

    # ─── Step 3: Test WITHOUT FLASH_ATTENTION ───
    console.print("\n[yellow]Phase A: Without FLASH_ATTENTION...[/yellow]")
    os.environ.pop("OLLAMA_FLASH_ATTENTION", None)

    results_a = []
    for img_path in test_images[:5]:  # 5 images without FA
        parsed, elapsed, raw = call_vlm(str(img_path))
        quality = validate_response(parsed, raw)
        quality["image"] = img_path.name
        quality["elapsed"] = elapsed
        quality["raw_sample"] = raw[:100] if raw else ""
        results_a.append(quality)
        status = "✓" if quality["json_valid"] else "✗"
        console.print(f"  [{status}] {img_path.name}: {elapsed:.1f}s | JSON: {quality['json_valid']} | type: {quality.get('diagram_type', 'N/A')}")

    avg_time_no_fa = sum(r["elapsed"] for r in results_a) / len(results_a) if results_a else 0

    # ─── Step 4: Test WITH FLASH_ATTENTION=1 ───
    console.print("\n[yellow]Phase B: With OLLAMA_FLASH_ATTENTION=1...[/yellow]")
    os.environ["OLLAMA_FLASH_ATTENTION"] = "1"

    results_b = []
    for img_path in test_images[:5]:
        parsed, elapsed, raw = call_vlm(str(img_path))
        quality = validate_response(parsed, raw)
        quality["image"] = img_path.name
        quality["elapsed"] = elapsed
        results_b.append(quality)
        status = "✓" if quality["json_valid"] else "✗"
        console.print(f"  [{status}] {img_path.name}: {elapsed:.1f}s | JSON: {quality['json_valid']} | type: {quality.get('diagram_type', 'N/A')}")

    avg_time_fa = sum(r["elapsed"] for r in results_b) / len(results_b) if results_b else 0

    # ─── Step 5: Full run (10 images, with FA) ───
    console.print("\n[yellow]Phase C: Full 10-image run (with FA)...[/yellow]")
    all_results = results_b[:]
    for img_path in test_images[5:]:
        parsed, elapsed, raw = call_vlm(str(img_path))
        quality = validate_response(parsed, raw)
        quality["image"] = img_path.name
        quality["elapsed"] = elapsed
        all_results.append(quality)
        console.print(f"  [{('✓' if quality['json_valid'] else '✗')}] {img_path.name}: {elapsed:.1f}s")

    # ─── Results ───
    n = len(all_results)
    json_valid_rate = sum(1 for r in all_results if r["json_valid"]) / n if n > 0 else 0
    valid_type_rate = sum(1 for r in all_results if r.get("valid_type")) / n if n > 0 else 0
    null_others_rate = sum(1 for r in all_results if r.get("null_others")) / n if n > 0 else 0
    timeout_count = sum(1 for r in all_results if r.get("timed_out"))
    avg_time_all = sum(r["elapsed"] for r in all_results) / n if n > 0 else 0
    fa_speedup = (avg_time_no_fa - avg_time_fa) / avg_time_no_fa if avg_time_no_fa > 0 else 0

    table = Table(title="VLM Stability Results")
    table.add_column("Image", style="cyan")
    table.add_column("Time(s)", justify="center")
    table.add_column("JSON", justify="center")
    table.add_column("Type", justify="center")
    table.add_column("Nulls OK", justify="center")
    table.add_column("diagram_type")

    for r in all_results:
        table.add_row(
            r["image"][:30],
            f"{r['elapsed']:.1f}",
            "[green]✓[/green]" if r["json_valid"] else "[red]✗[/red]",
            "[green]✓[/green]" if r.get("valid_type") else "[red]✗[/red]",
            "[green]✓[/green]" if r.get("null_others") else "[yellow]⚠[/yellow]",
            r.get("diagram_type", "?"),
        )
    console.print(table)

    console.print("\n[bold]Summary:[/bold]")
    console.print(f"  JSON valid rate:   {json_valid_rate:.1%} (n={n})")
    console.print(f"  diagram_type valid: {valid_type_rate:.1%}")
    console.print(f"  Null-others rate:  {null_others_rate:.1%}")
    console.print(f"  Timeouts:          {timeout_count}/{n}")
    console.print(f"  Avg time no FA:    {avg_time_no_fa:.1f}s")
    console.print(f"  Avg time with FA:  {avg_time_fa:.1f}s  (speedup: {fa_speedup:.1%})")

    console.print("\n[bold]Acceptance Criteria:[/bold]")
    ac1 = json_valid_rate >= 0.95
    ac2 = valid_type_rate >= 0.95
    ac3 = null_others_rate >= 0.95
    ac4 = timeout_count == 0 or timeout_count / n <= 0.1
    console.print(f"  [{'green' if ac1 else 'red'}]{'✓' if ac1 else '✗'}[/] JSON parse rate >= 95%: {json_valid_rate:.1%}")
    console.print(f"  [{'green' if ac2 else 'red'}]{'✓' if ac2 else '✗'}[/] diagram_type valid >= 95%: {valid_type_rate:.1%}")
    console.print(f"  [{'green' if ac3 else 'yellow'}]{'✓' if ac3 else '⚠'}[/] Null-others rate >= 95%: {null_others_rate:.1%}")
    console.print(f"  [{'green' if ac4 else 'red'}]{'✓' if ac4 else '✗'}[/] No hangs > 45s: {timeout_count} timeouts")
    console.print(f"  [cyan]ℹ[/cyan] FLASH_ATTENTION speedup: {fa_speedup:.1%}")

    return {
        "json_valid_rate": json_valid_rate,
        "type_valid_rate": valid_type_rate,
        "null_others_rate": null_others_rate,
        "timeout_count": timeout_count,
        "avg_time_sec": avg_time_all,
        "fa_speedup_pct": fa_speedup * 100,
        "pass": ac1 and ac4,
    }


if __name__ == "__main__":
    result = main()
    sys.exit(0 if result.get("pass") else 1)
