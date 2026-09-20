import time
import json
from pathlib import Path
from mkp_builder.vlm.client import OllamaClient
from mkp_builder.vlm.annotator import VLMAnnotator

def test():
    img_path = Path("work/demo/books/dedekam_seamanship/assets/dedekam_seamanship_s010_fig10.png")
    if not img_path.exists():
        print(f"Image not found at {img_path}")
        return
    
    print(f"Testing VLM on {img_path.name} ({img_path.stat().st_size} bytes)...")
    client = OllamaClient()
    annotator = VLMAnnotator(client=client)
    
    img_bytes = img_path.read_bytes()
    
    t0 = time.time()
    vlm_data, cache_hit = annotator.annotate(img_bytes)
    dt = time.time() - t0
    
    print(f"\nElapsed time: {dt:.2f}s (cache_hit={cache_hit})")
    print(f"Status: {vlm_data.status}")
    print(f"Diagram Type: {vlm_data.diagram_type}")
    print("\n--- VLM Output JSON ---")
    print(json.dumps(vlm_data.model_dump(), indent=2, ensure_ascii=False))

if __name__ == "__main__":
    test()
