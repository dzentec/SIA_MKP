import time
import json
import urllib.request
from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))
sys.path.insert(0, str(repo_root))

from mkp_server.server import MKPServerEngine

def test_model_speed(model_name="qwen2.5:7b"):
    storage_dir = repo_root / "data" / "live_server_storage"
    engine = MKPServerEngine(storage_dir)

    query = "How should the mainsail and headsail be adjusted when wind speed increases to 25 knots?"
    print(f"Testing model: {model_name}")
    print(f"Query: {query}\n")

    # 1. Retrieve context
    t0 = time.time()
    chunks = engine.search_chunks(query, top_k=2)
    gr = engine.get_guardrails()
    rules = list(engine.rules_store.rules.values())[:2]
    retrieval_ms = (time.time() - t0) * 1000
    print(f"Retrieval latency: {retrieval_ms:.1f}ms")

    # 2. Build prompt
    prompt_parts = [
        "You are MKP Maritime Assistant. Answer the question strictly using the excerpts.",
        f"Question: {query}\n",
        "MANUAL EXCERPTS:"
    ]
    for c in chunks:
        prompt_parts.append(f"[{c['book_id']}, p.{c['page_number']}]: {c['text_content'][:400]}")
    prompt_parts.append("\nAnswer concisely with citations:")
    prompt = "\n".join(prompt_parts)

    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 250
        }
    }

    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    t_gen_start = time.time()
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    gen_time = time.time() - t_gen_start

    eval_count = data.get("eval_count", 0)
    eval_duration_ns = data.get("eval_duration", 1)
    tok_per_sec = eval_count / (eval_duration_ns / 1e9) if eval_duration_ns else 0

    print(f"\n--- RESULTS FOR {model_name} ---")
    print(f"Total Generation Time: {gen_time:.2f} s")
    print(f"Tokens Generated: {eval_count}")
    print(f"Speed: {tok_per_sec:.2f} tokens/sec")
    print("---------------------------------")
    print("Generated Answer:\n")
    print(data.get("response", ""))
    print("---------------------------------\n")

if __name__ == "__main__":
    import sys
    m = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5:7b"
    test_model_speed(m)
