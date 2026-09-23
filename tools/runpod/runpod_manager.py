"""Local manager CLI for interacting with RunPod GPU instance."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import os

DEFAULT_SSH_KEY = "C:/Users/User/.ssh/id_ed25519"
DEFAULT_IP = "69.30.85.227"
DEFAULT_PORT = "22049"


def run_ssh(cmd: str, ip: str = DEFAULT_IP, port: str = DEFAULT_PORT, key: str = DEFAULT_SSH_KEY) -> str:
    res = subprocess.run(
        [
            "ssh",
            "-p", port,
            "-i", key,
            "-o", "StrictHostKeyChecking=no",
            f"root@{ip}",
            cmd,
        ],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0 and not res.stdout:
        print(f"SSH Error ({res.returncode}): {res.stderr}", file=sys.stderr)
    return res.stdout


def check_status(ip: str, port: str, key: str) -> None:
    print("=== [1] NVIDIA-SMI & GPU Utilization ===")
    print(run_ssh("nvidia-smi", ip, port, key))
    
    print("\n=== [2] Active Python Processes ===")
    print(run_ssh("ps aux | grep python", ip, port, key))

    print("\n=== [3] Ollama Inference Log (Last 15 lines) ===")
    print(run_ssh("tail -n 15 /root/ollama.log", ip, port, key))

    print("\n=== [4] MKP Builder Log (Last 15 lines) ===")
    print(run_ssh("tail -n 15 /root/SIA_MKP/cloud_build/logs/*.log 2>/dev/null || echo 'No logs yet'", ip, port, key))


def download_bookpacks(ip: str, port: str, key: str, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"Downloading .bookpack.zip files to {target_dir}...")
    res = subprocess.run(
        [
            "scp",
            "-P", port,
            "-i", key,
            "-o", "StrictHostKeyChecking=no",
            f"root@{ip}:/root/SIA_MKP/cloud_build/out/*.bookpack.zip",
            str(target_dir.absolute()),
        ]
    )
    if res.returncode == 0:
        print("Download successful!")
        for f in target_dir.glob("*.bookpack.zip"):
            print(f"  - {f.name} ({f.stat().st_size} bytes)")
    else:
        print("Download failed or no archives found.")


def stop_pod(pod_id: str = "y5vnpb4pglin4p") -> None:
    from tools.runpod.runpod_api import RunPodClient
    client = RunPodClient()
    print(f"Stopping pod {pod_id} via RunPod API to save costs...")
    res = client.stop_pod(pod_id)
    print(f"Pod stop command sent! Result: {res}")


def watch_and_auto_stop(ip: str, port: str, key: str, pod_id: str = "y5vnpb4pglin4p") -> None:
    import time
    target_dir = Path("qa/bookpacks")
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"Watching build on {ip}:{port}... (Auto-Stop will trigger on completion)")
    
    while True:
        # Check active python build process
        ps_out = run_ssh("ps aux | grep 'run_build_32b.py' | grep -v grep", ip, port, key)
        if not ps_out.strip():
            print("\nBuild process has finished!")
            # Download bookpacks
            download_bookpacks(ip, port, key, target_dir)
            # Auto-stop pod
            stop_pod(pod_id)
            print("Done! Cost stopped.")
            break
            
        print(".", end="", flush=True)
        time.sleep(10.0)


def main() -> None:
    parser = argparse.ArgumentParser(description="RunPod MKP Manager")
    parser.add_argument("--ip", default=DEFAULT_IP, help="Pod Exposed IP")
    parser.add_argument("--port", default=DEFAULT_PORT, help="Pod Exposed Port")
    parser.add_argument("--key", default=DEFAULT_SSH_KEY, help="Path to SSH private key")
    parser.add_argument("--pod-id", default="y5vnpb4pglin4p", help="RunPod Pod ID")
    parser.add_argument("action", choices=["status", "logs", "download", "stop", "watch", "tail-ollama", "tail-builder"], help="Action to perform")

    args = parser.parse_args()

    if args.action == "status":
        check_status(args.ip, args.port, args.key)
    elif args.action == "logs":
        print(run_ssh("tail -n 30 /root/SIA_MKP/cloud_build/logs/*.log", args.ip, args.port, args.key))
    elif args.action == "tail-ollama":
        print(run_ssh("tail -n 30 /root/ollama.log", args.ip, args.port, args.key))
    elif args.action == "download":
        download_bookpacks(args.ip, args.port, args.key, Path("qa/bookpacks"))
    elif args.action == "stop":
        stop_pod(args.pod_id)
    elif args.action == "watch":
        watch_and_auto_stop(args.ip, args.port, args.key, args.pod_id)



if __name__ == "__main__":
    main()
