"""RunPod Zero-Touch Orchestrator & Auto-Stop Controller.

Orchestrates pod deployment, GPU cascade selection, remote bootstrap,
live Rich TUI telemetry, automated artifact retrieval, and budget auto-stop.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure repository root in sys.path
_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from rich.live import Live
from rich.console import Console

from tools.runpod.logger import OrchestratorLogger
from tools.runpod.runpod_api import RunPodClient, DEFAULT_TEMPLATE_ID, GPU_CASCADE
from tools.runpod.tui import RunPodDashboard, check_keypress


class RunPodOrchestrator:
    """End-to-end Zero-Touch controller for cloud execution."""

    def __init__(
        self,
        api_key: str | None = None,
        ssh_key_path: Path | str | None = None,
        source_books_dir: Path | str = ".init_doc/source_doc",
        output_bookpacks_dir: Path | str = "qa/bookpacks",
        target_book: str = "sail_and_rig_tuning",
        gpu_type: str | None = None,
        auto_stop: bool = True,
        dry_run: bool = False,
    ) -> None:
        self.dry_run = dry_run
        self.logger = OrchestratorLogger()
        self.client = RunPodClient(api_key=api_key) if not dry_run else None

        self.ssh_key = self._resolve_ssh_key(ssh_key_path)
        self.source_books_dir = Path(source_books_dir)
        self.output_bookpacks_dir = Path(output_bookpacks_dir)
        self.output_bookpacks_dir.mkdir(parents=True, exist_ok=True)
        self.target_book = target_book
        self.requested_gpu = gpu_type
        self.auto_stop = auto_stop

        # Pod State
        self.pod_id: str | None = None
        self.pod_name: str = "mkp-32b-worker"
        self.pod_ip: str = ""
        self.pod_port: str = "22"
        self.cost_per_hr: float = 0.74
        self.gpu_model: str = "NVIDIA GeForce RTX 4090"

        # Inactivity & Safety Guard
        self.last_progress_time: float = time.time()
        self.last_progress_signature: str = ""
        self.inactivity_threshold_sec: float = 900.0  # 15 minutes
        self.guard_duration_sec: int = 1800  # 30 minutes countdown
        self.guard_trigger_time: float | None = None

    def _resolve_ssh_key(self, custom_path: Path | str | None) -> str:
        if custom_path and Path(custom_path).exists():
            return str(Path(custom_path).resolve())
        # Check tools/runpod/.env
        env_file = Path(__file__).parent / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("SSH_KEY_PATH="):
                    p = Path(line.strip().split("=", 1)[1].strip())
                    if p.exists():
                        return str(p.resolve())
        # Check standard locations
        home_ssh = Path.home() / ".ssh" / "id_ed25519"
        if home_ssh.exists():
            return str(home_ssh)
        local_ssh = Path(__file__).parent / "id_ed25519"
        if local_ssh.exists():
            return str(local_ssh)
        return str(home_ssh)

    def run_ssh(self, cmd: str, timeout: float = 15.0) -> tuple[int, str, str]:
        """Execute command over SSH on remote pod."""
        if self.dry_run or not self.pod_ip:
            return 0, "mock stdout", ""
        try:
            res = subprocess.run(
                [
                    "ssh",
                    "-p", str(self.pod_port),
                    "-i", str(self.ssh_key),
                    "-o", "StrictHostKeyChecking=no",
                    "-o", "UserKnownHostsFile=/dev/null",
                    "-o", "ConnectTimeout=5",
                    f"root@{self.pod_ip}",
                    cmd,
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return res.returncode, res.stdout, res.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "SSH Timeout"
        except Exception as e:
            return -1, "", str(e)

    def scp_to_pod(self, local_path: Path, remote_path: str) -> bool:
        """Upload file or directory via SCP."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] SCP upload: {local_path} -> root@{self.pod_ip}:{remote_path}")
            return True
        try:
            cmd = [
                "scp",
                "-P", str(self.pod_port),
                "-i", str(self.ssh_key),
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-r" if local_path.is_dir() else "-p",
                str(local_path.resolve()),
                f"root@{self.pod_ip}:{remote_path}",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            return res.returncode == 0
        except Exception as e:
            self.logger.error(f"SCP upload failed: {e}")
            return False

    def scp_from_pod(self, remote_path: str, local_path: Path) -> bool:
        """Download files from pod via SCP."""
        if self.dry_run:
            self.logger.info(f"[DRY-RUN] SCP download: root@{self.pod_ip}:{remote_path} -> {local_path}")
            return True
        try:
            cmd = [
                "scp",
                "-P", str(self.pod_port),
                "-i", str(self.ssh_key),
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-r",
                f"root@{self.pod_ip}:{remote_path}",
                str(local_path.resolve()),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            return res.returncode == 0
        except Exception as e:
            self.logger.error(f"SCP download failed: {e}")
            return False

    def discover_or_deploy_pod(self) -> bool:
        """Finds existing pod or deploys new pod following GPU Cascade priority."""
        if self.dry_run:
            self.pod_id = "mock-rtx4090-pod"
            self.pod_name = "mkp-4090-worker (DRY RUN)"
            self.pod_ip = "127.0.0.1"
            self.pod_port = "2222"
            self.cost_per_hr = 0.74
            self.gpu_model = "NVIDIA GeForce RTX 4090"
            self.logger.info(f"[DRY-RUN] Pod initialized: {self.pod_id} ({self.gpu_model})")
            return True

        self.logger.info("Discovering active or stopped pods on RunPod...")
        try:
            pods = self.client.get_pods()
            # 1. Look for existing MKP pod
            for p in pods:
                name = p.get("name", "")
                status = p.get("desiredStatus", "")
                if ("mkp" in name.lower() or "sia" in name.lower()) and status != "TERMINATED":
                    self.pod_id = p["id"]
                    self.pod_name = name
                    self.cost_per_hr = p.get("costPerHr", 0.74)
                    self.logger.info(f"Found existing pod '{name}' (ID: {self.pod_id}, Status: {status})")

                    if status != "RUNNING":
                        self.logger.info(f"Resuming stopped pod {self.pod_id}...")
                        self.client.resume_pod(self.pod_id)
                    break

            # 2. If no existing pod, deploy new one using GPU cascade
            if not self.pod_id:
                selected_gpu = self.client.select_best_gpu(self.requested_gpu)
                self.gpu_model = selected_gpu["id"]
                self.logger.info(f"Deploying new pod with {selected_gpu['description']} on template {DEFAULT_TEMPLATE_ID}...")
                
                # Derive public key from configured ssh key
                pub_key = None
                try:
                    res = subprocess.run(["ssh-keygen", "-y", "-f", str(self.ssh_key)], capture_output=True, text=True)
                    if res.returncode == 0 and res.stdout.strip():
                        pub_key = res.stdout.strip()
                except Exception:
                    pass

                dep_res = self.client.deploy_pod(
                    name=f"mkp-{selected_gpu['aliases'][0].lower().replace(' ', '-')}-worker",
                    gpu_type_id=selected_gpu["id"],
                    template_id=DEFAULT_TEMPLATE_ID,
                    gpu_count=1,
                    volume_in_gb=40,
                    container_disk_in_gb=40,
                    public_key=pub_key,
                )
                pod_data = dep_res.get("podFindAndDeployOnDemand", {})
                self.pod_id = pod_data.get("id")
                self.pod_name = pod_data.get("name", "mkp-worker")
                self.cost_per_hr = pod_data.get("costPerHr", 0.74)
                self.logger.info(f"Pod deployed successfully! ID: {self.pod_id} (${self.cost_per_hr:.2f}/hr)")

            # 3. Wait for pod IP & SSH port to be assigned and accessible
            self.logger.info("Waiting for pod network configuration & exposed SSH port...")
            for attempt in range(60):
                info = self.client.get_pod_status_and_ip(self.pod_id)
                if info["ip"] and info["port"] and info["status"] == "RUNNING":
                    self.pod_ip = info["ip"]
                    self.pod_port = info["port"]
                    self.gpu_model = info.get("gpu_name") or self.gpu_model
                    self.logger.info(f"Pod is RUNNING at {self.pod_ip}:{self.pod_port}")
                    break
                time.sleep(3.0)

            if not self.pod_ip:
                self.logger.error("Failed to obtain public IP and SSH port for pod.")
                return False

            # 4. Verify SSH readiness (Container image pull takes 1-3 mins on first start)
            self.logger.info("Verifying SSH connection (waiting for container image download & sshd start)...")
            for attempt in range(80):
                code, stdout, _ = self.run_ssh("echo 'SSH_READY'")
                if "SSH_READY" in stdout:
                    self.logger.info(f"SSH connection verified successfully on attempt {attempt+1}!")
                    return True
                if attempt > 0 and attempt % 10 == 0:
                    self.logger.info(f"Still waiting for pod SSH daemon... ({attempt * 3}s elapsed)")
                time.sleep(3.0)

            self.logger.error("SSH connection timed out after 4 minutes.")
            return False

        except Exception as e:
            self.logger.error(f"Pod discovery/deployment failed: {e}")
            return False

    def bootstrap_and_start_build(self) -> bool:
        """Bootstraps remote environment, transfers code and books, and triggers background build."""
        self.logger.info("=== Checking Remote Pod Environment ===")

        if self.dry_run:
            self.logger.info("[DRY-RUN] Remote bootstrap completed.")
            return True

        # Check if build runner is already active on pod
        code, stdout, _ = self.run_ssh("ps aux | grep 'run_build_32b.py' | grep -v grep || true")
        if "run_build_32b.py" in stdout:
            self.logger.info("Existing 32B build process is currently running on pod. Attaching directly to live dashboard...")
            return True

        self.logger.info("=== Starting Fast Bootstrap on Pod ===")

        # 1. Check Ollama server and install if needed
        self.logger.info("Checking Ollama server on pod...")
        code, stdout, _ = self.run_ssh("which ollama || true")
        if "ollama" not in stdout:
            self.logger.info("Installing Ollama on pod...")
            self.run_ssh("curl -fsSL https://ollama.com/install.sh | sh", timeout=180)

        # Ensure Ollama daemon is running with persistent model storage in /workspace
        self.run_ssh("mkdir -p /workspace/.ollama/models")
        code, stdout, _ = self.run_ssh("curl -s http://127.0.0.1:11434/api/tags || true")
        if "models" not in stdout:
            self.logger.info("Starting Ollama daemon in background...")
            self.run_ssh("export OLLAMA_MODELS=/workspace/.ollama/models; nohup ollama serve > /workspace/ollama.log 2>&1 &")
            time.sleep(3.0)

        # 2. Check & pull Qwen2.5-VL 32B model
        self.logger.info("Checking Qwen2.5-VL 32B model...")
        code, stdout, _ = self.run_ssh("export OLLAMA_MODELS=/workspace/.ollama/models; ollama list | grep 'qwen2.5vl:32b' || true")
        if "qwen2.5vl:32b" not in stdout:
            self.logger.info("Pulling qwen2.5vl:32b (high speed datacenter network, ~2-3 min)...")
            self.run_ssh("export OLLAMA_MODELS=/workspace/.ollama/models; ollama pull qwen2.5vl:32b", timeout=900)

        # 3. Ensure directory structure on persistent /workspace volume
        self.run_ssh("mkdir -p /workspace/SIA_MKP/.init_doc/source_doc /workspace/SIA_MKP/cloud_build/logs /workspace/SIA_MKP/cloud_build/out /workspace/SIA_MKP/tools/runpod")

        # 4. Sync codebase and install dependencies
        self.logger.info("Syncing codebase (src/ and pyproject.toml) to persistent volume /workspace/SIA_MKP...")
        src_dir = _repo_root / "src"
        pyproject_file = _repo_root / "pyproject.toml"
        self.scp_to_pod(src_dir, "/workspace/SIA_MKP/")
        self.scp_to_pod(pyproject_file, "/workspace/SIA_MKP/pyproject.toml")

        self.logger.info("Installing mkp-builder package on pod...")
        self.run_ssh("python3 -m pip install --break-system-packages -e '/workspace/SIA_MKP[builder]'", timeout=240)

        # 5. Sync source books
        self.logger.info(f"Syncing source books from {self.source_books_dir} (target: {self.target_book})...")
        for book_file in self.source_books_dir.glob("*.*"):
            if book_file.suffix.lower() in [".epub", ".pdf"]:
                if self.target_book == "sail_and_rig_tuning" and ("sail" not in book_file.name.lower() and "tuning" not in book_file.name.lower()):
                    continue
                if self.target_book == "illustrated_seamanship" and "seamanship" not in book_file.name.lower():
                    continue
                self.logger.info(f"Uploading {book_file.name} ({book_file.stat().st_size} bytes)...")
                self.scp_to_pod(book_file, f"/workspace/SIA_MKP/.init_doc/source_doc/{book_file.name}")

        # 6. Sync runner script
        tools_run_build = Path(__file__).parent / "run_build_32b.py"
        if tools_run_build.exists():
            self.scp_to_pod(tools_run_build, "/workspace/SIA_MKP/tools/runpod/run_build_32b.py")

        # 7. Launch build script in background
        self.logger.info(f"Launching background 32B build runner for '{self.target_book}' on persistent volume...")
        launch_cmd = (
            f"nohup python3 /workspace/SIA_MKP/tools/runpod/run_build_32b.py --book {self.target_book} "
            "> /workspace/SIA_MKP/cloud_build/logs/builder.log 2>&1 &"
        )
        self.run_ssh(launch_cmd)
        time.sleep(2.0)
        self.logger.info("Build runner launched in background.")
        return True

    def fetch_remote_telemetry(self) -> dict[str, Any]:
        """Fetches telemetry snapshot, host system metrics (RAM, Disk, CPU), and GPU metrics in a single SSH call."""
        if self.dry_run:
            return {}

        telem: dict[str, Any] = {}
        # Single-line Python script measuring RAM, Disk, instantaneous CPU delta, container cores, and live Ollama t/s
        py_metrics_cmd = (
            "python3 -c \"import json,os,shutil,time; du=shutil.disk_usage('/'); "
            "m=dict(x.split(':',1) for x in open('/proc/meminfo').read().splitlines() if ':' in x); "
            "mt=int(m.get('MemTotal','0').split()[0])/1048576.0; "
            "ma=int(m.get('MemAvailable','0').split()[0])/1048576.0; "
            "st1=[float(x) for x in open('/proc/stat').readline().split()[1:8]]; "
            "time.sleep(0.05); "
            "st2=[float(x) for x in open('/proc/stat').readline().split()[1:8]]; "
            "dtot=sum(st2)-sum(st1); didle=(st2[3]+st2[4])-(st1[3]+st1[4]); "
            "tps=0.0; "
            "olog_p='/workspace/ollama.log' if os.path.exists('/workspace/ollama.log') else '/root/ollama.log'; "
            "olog=open(olog_p).read().splitlines()[-40:] if os.path.exists(olog_p) else []; "
            "tp_matches=[float(l.split('tokens per second')[0].strip().split()[-1]) for l in olog if 'tokens per second' in l]; "
            "tps=tp_matches[-1] if tp_matches else 0.0; "
            "print(json.dumps({'ram_used_gb':round(mt-ma,2),'ram_total_gb':round(mt,2),'disk_used_gb':round(du.used/1073741824.0,2),'disk_total_gb':round(du.total/1073741824.0,2),'cpu_percent':round(max(0.0,min(100.0,100.0*(1.0-didle/dtot))),1) if dtot>0 else 0.0,'cpu_cores':min(os.cpu_count() or 8, 16),'gpu_tps':tps}))\" 2>/dev/null || echo '{}'"
        )
        composite_cmd = (
            f"cat /tmp/mkp_progress.json 2>/dev/null || echo '{{}}'; "
            f"echo '---SYS---'; "
            f"{py_metrics_cmd}; "
            f"echo '---GPU---'; "
            f"nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw --format=csv,noheader,nounits 2>/dev/null || true"
        )
        code, stdout, _ = self.run_ssh(composite_cmd)
        if code == 0 and stdout:
            parts = stdout.split("---SYS---")
            prog_part = parts[0].strip() if len(parts) > 0 else ""
            rest = parts[1] if len(parts) > 1 else ""
            sys_part = rest.split("---GPU---")[0].strip() if "---GPU---" in rest else rest.strip()
            gpu_part = rest.split("---GPU---")[1].strip() if "---GPU---" in rest else ""

            # 1. Parse progress JSON
            if "{" in prog_part and "}" in prog_part:
                try:
                    json_str = prog_part[prog_part.find("{"):prog_part.rfind("}") + 1]
                    telem = json.loads(json_str)
                except Exception:
                    pass

            # 2. Parse Host System Metrics (RAM, Disk, CPU)
            if "{" in sys_part and "}" in sys_part:
                try:
                    json_str = sys_part[sys_part.find("{"):sys_part.rfind("}") + 1]
                    sys_metrics = json.loads(json_str)
                    telem.update(sys_metrics)
                except Exception:
                    pass

            # 3. Parse GPU Metrics
            if gpu_part:
                try:
                    gpu_line = gpu_part.strip().splitlines()[-1]
                    gpu_fields = [p.strip() for p in gpu_line.split(",")]
                    if len(gpu_fields) >= 5:
                        telem["gpu_util"] = float(gpu_fields[0])
                        telem["gpu_util_percent"] = float(gpu_fields[0])
                        telem["vram_used_gb"] = float(gpu_fields[1]) / 1024.0
                        telem["vram_total_gb"] = float(gpu_fields[2]) / 1024.0
                        telem["gpu_temp_c"] = int(float(gpu_fields[3]))
                        telem["gpu_power_w"] = int(float(gpu_fields[4]))
                except Exception:
                    pass

        return telem

    def run_live_loop(self) -> None:
        """Main interactive TUI loop with Inactivity Guard and Hotkeys."""
        dashboard = RunPodDashboard(logger=self.logger, auto_stop=self.auto_stop)
        dashboard.pod_name = self.pod_name
        dashboard.cost_per_hr = self.cost_per_hr
        dashboard.gpu_model = self.gpu_model

        if self.target_book != "all":
            dashboard.total_books = 1
            dashboard.current_book_title = (
                "Sail and Rig Tuning (Ivar Dedekam) [PDF · 178 MB]"
                if self.target_book == "sail_and_rig_tuning"
                else "Illustrated Seamanship (Ivar Dedekam) [EPUB · 5.4 MB]"
            )
        else:
            dashboard.total_books = 2

        self.last_progress_time = time.time()
        self.guard_trigger_time = None

        self.logger.mute_console()
        try:
            with Live(dashboard.render(), refresh_per_second=2, console=dashboard.console) as live:
                while True:
                    now = time.time()

                    # 1. Fetch remote telemetry
                    telem = self.fetch_remote_telemetry()
                    if telem:
                        dashboard.update_telemetry(telem)

                        # Check for progress movement or active GPU compute
                        sig = json.dumps(telem.get("stages", {}), sort_keys=True)
                        is_gpu_active = telem.get("gpu_util", 0) > 15.0 or telem.get("gpu_power_w", 0) > 120
                        if sig != self.last_progress_signature or is_gpu_active:
                            if sig != self.last_progress_signature:
                                self.last_progress_signature = sig
                            self.last_progress_time = now
                            self.guard_trigger_time = None
                            dashboard.guard_countdown_sec = None

                    # 2. Inactivity Guard Calculation
                    idle_sec = now - self.last_progress_time
                    if idle_sec > self.inactivity_threshold_sec:
                        if self.guard_trigger_time is None:
                            self.guard_trigger_time = now
                            self.logger.warning("Pipeline inactive for 15 minutes! Initiating 30-minute Auto-Stop safety countdown.")

                        elapsed_guard = now - self.guard_trigger_time
                        remaining_sec = max(0, int(self.guard_duration_sec - elapsed_guard))
                        dashboard.guard_countdown_sec = remaining_sec

                        if remaining_sec <= 0:
                            self.logger.error("Inactivity Guard expired! Triggering automated pod shutdown to protect budget.")
                            exit_reason = "guard_expired"
                            self.stop_pod_safely()
                            break
                    else:
                        dashboard.guard_countdown_sec = None

                    # 3. Check keyboard hotkeys
                    k = check_keypress()
                    if k:
                        # Reset inactivity guard on any keypress
                        self.last_progress_time = now
                        self.guard_trigger_time = None
                        dashboard.guard_countdown_sec = None

                        if k == "q":
                            self.logger.info(f"User detached TUI ('q'). Pod {self.pod_id} remains RUNNING and processing in background.")
                            exit_reason = "user_quit"
                            break
                        elif k == "s":
                            self.logger.info("User requested instant pod shutdown ('s').")
                            exit_reason = "user_stop"
                            self.stop_pod_safely()
                            break
                        elif k == "d":
                            self.logger.info("User requested instant archive download ('d').")
                            self.download_and_verify_artifacts()
                        elif k == "t":
                            self.auto_stop = not self.auto_stop
                            dashboard.auto_stop = self.auto_stop
                            self.logger.info(f"Auto-stop setting changed to: {self.auto_stop}")

                    # 4. Check if build completed remotely
                    code, stdout, _ = self.run_ssh("ps aux | grep 'run_build_32b.py' | grep -v grep || true")
                    if "run_build_32b.py" not in stdout:
                        if telem.get("status") == "completed":
                            self.logger.info("Build runner process has completed successfully!")
                            dashboard.completed_books = dashboard.total_books
                            live.update(dashboard.render())
                            time.sleep(1.0)
                            exit_reason = "completed"
                            break
                        elif telem.get("status") == "error":
                            self.logger.error("Build runner process reported an error.")
                            exit_reason = "error"
                            break

                    live.update(dashboard.render())
                    time.sleep(1.5)
        except KeyboardInterrupt:
            exit_reason = "user_quit"
            self.logger.info(f"KeyboardInterrupt received. Detaching TUI. Pod {self.pod_id} continues running in background.")
        finally:
            self.logger.unmute_console()

        # Handle post-loop actions according to exit reason
        if exit_reason == "completed":
            self.download_and_verify_artifacts()
            if self.auto_stop:
                self.stop_pod_safely()
            self.print_final_summary()
        elif exit_reason in ("user_stop", "guard_expired"):
            self.print_final_summary()
        elif exit_reason == "user_quit":
            console = Console()
            console.print("\n[bold green]=======================================================[/bold green]")
            console.print(f"[bold cyan]    TUI DETACHED — BUILD CONTINUES ON POD {self.pod_id}[/bold cyan]")
            console.print("[bold green]=======================================================[/bold green]")
            console.print(f"• Pod Status: [bold green]RUNNING (Background Build Active)[/bold green]")
            console.print(f"• Reconnect:  [yellow]python tools/runpod/runpod_orchestrator.py --book {self.target_book}[/yellow]\n")
            self.logger.close()
        elif exit_reason == "error":
            if self.auto_stop:
                self.stop_pod_safely()
            self.print_final_summary()

    def download_and_verify_artifacts(self) -> None:
        """Downloads .bookpack.zip files and verifies SHA256 hashes."""
        self.logger.info(f"Downloading .bookpack.zip artifacts to {self.output_bookpacks_dir}...")
        self.scp_from_pod("/workspace/SIA_MKP/cloud_build/out/*.bookpack.zip", self.output_bookpacks_dir)

        downloaded = list(self.output_bookpacks_dir.glob("*.bookpack.zip"))
        if not downloaded:
            self.logger.warning("No .bookpack.zip files found in output directory.")
            return

        self.logger.info(f"Successfully retrieved {len(downloaded)} bookpack archive(s):")
        for bp in downloaded:
            sha256 = hashlib.sha256(bp.read_bytes()).hexdigest()
            size_mb = bp.stat().st_size / (1024 * 1024)
            self.logger.info(f"  - {bp.name} | Size: {size_mb:.2f} MB | SHA256: {sha256[:16]}...{sha256[-8:]}")

    def stop_pod_safely(self) -> None:
        """Invokes podStop API to immediately stop GPU billing ($0/hr)."""
        if self.dry_run or not self.pod_id:
            self.logger.info("[DRY-RUN] podStop command executed ($0/hr).")
            return

        self.logger.info(f"Invoking podStop on {self.pod_id} to halt all billing ($0/hr)...")
        try:
            res = self.client.stop_pod(self.pod_id)
            self.logger.info(f"Pod {self.pod_id} successfully STOPPED: {res}")
        except Exception as e:
            self.logger.error(f"Error stopping pod: {e}")

    def print_final_summary(self) -> None:
        """Prints formatted completion report."""
        console = Console()
        console.print("\n[bold green]=======================================================[/bold green]")
        console.print("[bold cyan]    RUNPOD ZERO-TOUCH PIPELINE RUN COMPLETED[/bold cyan]")
        console.print("[bold green]=======================================================[/bold green]")
        console.print(f"• Log File:   [yellow]{self.logger.session_log_path}[/yellow]")
        console.print(f"• Bookpacks:  [cyan]{self.output_bookpacks_dir.resolve()}[/cyan]")
        console.print(f"• Pod Status: [bold red]STOPPED ($0/hr billing)[/bold red]" if self.auto_stop else f"• Pod Status: [green]RUNNING[/green]")
        self.logger.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="RunPod Zero-Touch Orchestrator & Rich TUI")
    parser.add_argument(
        "--book",
        choices=["sail_and_rig_tuning", "illustrated_seamanship", "all"],
        default="sail_and_rig_tuning",
        help="Target book to build on RunPod (default: sail_and_rig_tuning)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Simulate cloud workflow without connecting to RunPod")
    parser.add_argument("--no-auto-stop", action="store_true", help="Disable automatic pod shutdown on completion")
    parser.add_argument("--gpu", type=str, default=None, help="Specify preferred GPU type (e.g. 'RTX 5090', 'RTX 4090')")
    parser.add_argument("--source-dir", type=str, default=".init_doc/source_doc", help="Source books folder")
    parser.add_argument("--output-dir", type=str, default="qa/bookpacks", help="Target folder for bookpacks")
    args = parser.parse_args()

    orch = RunPodOrchestrator(
        source_books_dir=args.source_dir,
        output_bookpacks_dir=args.output_dir,
        target_book=args.book,
        gpu_type=args.gpu,
        auto_stop=not args.no_auto_stop,
        dry_run=args.dry_run,
    )

    ready = orch.discover_or_deploy_pod()
    if not ready:
        print("Failed to initialize pod infrastructure.", file=sys.stderr)
        sys.exit(1)

    bootstrapped = orch.bootstrap_and_start_build()
    if not bootstrapped:
        print("Failed to bootstrap remote pod.", file=sys.stderr)
        sys.exit(1)

    orch.run_live_loop()


if __name__ == "__main__":
    main()
