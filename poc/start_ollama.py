import os
import subprocess
import time
import httpx

def main():
    env = os.environ.copy()
    env["OLLAMA_MODELS"] = r"D:\AI_models\ollama"
    env["OLLAMA_FLASH_ATTENTION"] = "1"
    
    print("Launching Ollama with OLLAMA_MODELS=D:\\AI_models\\ollama ...")
    proc = subprocess.Popen(
        [r"D:\Ollama\ollama.exe", "serve"],
        env=env,
    )
    
    # Wait for ready
    for i in range(15):
        time.sleep(1)
        try:
            r = httpx.get("http://127.0.0.1:11434/api/tags", timeout=2.0)
            if r.status_code == 200:
                models = [m.get("name") for m in r.json().get("models", [])]
                print(f"Ollama ready! Available models: {models}")
                break
        except Exception:
            pass

if __name__ == "__main__":
    main()
