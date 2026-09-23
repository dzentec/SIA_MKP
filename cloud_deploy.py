"""Cloud Orchestrator for MKP-Builder on RunPod RTX 4090."""

from __future__ import annotations

import base64
import io
import json
import logging
import os
from pathlib import Path
import subprocess
import tarfile
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cloud_deploy")


class PodSession:
    """Manages persistent SSH session to RunPod with marker synchronization."""

    def __init__(self, host: str = "nosnfxec0q4fwl-64411a5c@ssh.runpod.io"):
        logger.info("Connecting to RunPod at %s...", host)
        self.proc = subprocess.Popen(
            ["ssh", "-tt", "-o", "StrictHostKeyChecking=no", host],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._wait_ready()

    def _wait_ready(self) -> None:
        buf = ""
        while True:
            char = self.proc.stdout.read(1)
            if not char:
                break
            buf += char
            if "# " in buf or "$ " in buf:
                break
        logger.info("RunPod shell connected successfully!")

    def exec(self, cmd: str, timeout: float = 120.0) -> str:
        marker = f"__CMD_DONE_{int(time.time()*1000)}__"
        full_cmd = f"{cmd}\necho {marker}\n"
        self.proc.stdin.write(full_cmd)
        self.proc.stdin.flush()
        buf = ""
        start = time.time()
        while time.time() - start < timeout:
            line = self.proc.stdout.readline()
            if marker in line:
                break
            buf += line
        return buf

    def stream_exec(self, cmd: str, timeout: float = 1800.0) -> str:
        marker = f"__STREAM_DONE_{int(time.time()*1000)}__"
        full_cmd = f"{cmd}\necho {marker}\n"
        self.proc.stdin.write(full_cmd)
        self.proc.stdin.flush()
        buf = []
        start = time.time()
        while time.time() - start < timeout:
            line = self.proc.stdout.readline()
            if not line:
                break
            if marker in line:
                break
            line_str = line.rstrip()
            if line_str and not line_str.startswith("echo __STREAM"):
                print(f"[RunPod] {line_str}")
                buf.append(line_str)
        return "\n".join(buf)

    def close(self) -> None:
        try:
            self.proc.stdin.write("exit\n")
            self.proc.stdin.flush()
            self.proc.terminate()
        except Exception:
            pass


def pack_codebase() -> bytes:
    """Create in-memory tar.gz archive of source code, configs, and source books."""
    logger.info("Packaging local codebase and source books into tarball...")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        # Add src/
        tar.add("src", arcname="src")
        # Add pyproject.toml
        if Path("pyproject.toml").exists():
            tar.add("pyproject.toml", arcname="pyproject.toml")
        # Add source books
        src_books = Path(".init_doc/source_doc")
        if src_books.exists():
            tar.add(str(src_books), arcname="source_doc")
    data = buf.getvalue()
    logger.info("Packed archive size: %.2f MB", len(data) / (1024 * 1024))
    return data


def upload_archive(session: PodSession, archive_bytes: bytes) -> None:
    """Upload tar.gz archive to Pod via chunked base64 stream."""
    logger.info("Uploading codebase archive to RunPod...")
    b64_data = base64.b64encode(archive_bytes).decode("ascii")
    chunk_size = 32768  # 32 KB chunks

    session.exec("mkdir -p /root/mkp")
    session.exec("rm -f /root/mkp/archive.tar.gz.b64 /root/mkp/archive.tar.gz")

    total_chunks = (len(b64_data) + chunk_size - 1) // chunk_size
    logger.info("Sending %d chunks (total %d characters base64)...", total_chunks, len(b64_data))

    for i in range(total_chunks):
        chunk = b64_data[i * chunk_size : (i + 1) * chunk_size]
        session.exec(f"printf '%s' '{chunk}' >> /root/mkp/archive.tar.gz.b64")
        if (i + 1) % 100 == 0 or i == total_chunks - 1:
            logger.info("Uploaded chunk %d / %d", i + 1, total_chunks)

    # Decode and unpack
    logger.info("Unpacking archive on Pod...")
    res = session.exec("base64 -d /root/mkp/archive.tar.gz.b64 > /root/mkp/archive.tar.gz && cd /root/mkp && tar -xzf archive.tar.gz && ls -la /root/mkp")
    logger.info("Unpack result:\n%s", res)


def download_file(session: PodSession, remote_path: str, local_path: Path) -> None:
    """Download a file from Pod via base64 encoding."""
    logger.info("Downloading %s to %s...", remote_path, local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Get base64 string
    b64_file = f"{remote_path}.b64"
    session.exec(f"base64 -w 0 {remote_path} > {b64_file}")
    
    # Read size
    size_out = session.exec(f"wc -c < {b64_file}").strip()
    try:
        total_chars = int(size_out.split()[-1])
    except Exception:
        total_chars = 0

    logger.info("Remote base64 size: %d characters", total_chars)

    # Stream read in chunks using python on remote
    stream_cmd = f"python3 -c \"import sys; f=open('{b64_file}', 'r'); sys.stdout.write(f.read())\""
    marker = f"__DL_DONE_{int(time.time()*1000)}__"
    
    session.proc.stdin.write(f"{stream_cmd}\necho {marker}\n")
    session.proc.stdin.flush()
    
    b64_chunks = []
    while True:
        line = session.proc.stdout.readline()
        if not line:
            break
        if marker in line:
            break
        if not line.startswith("python3 -c"):
            b64_chunks.append(line.rstrip("\r\n"))

    raw_b64 = "".join(b64_chunks).strip()
    data = base64.b64decode(raw_b64)
    local_path.write_bytes(data)
    logger.info("Successfully downloaded %s (%.2f MB)", local_path.name, len(data) / (1024 * 1024))


def main():
    session = PodSession()

    try:
        # Step 1: Install Ollama if needed
        logger.info("=== STEP 1: Checking Ollama Installation on RunPod ===")
        check_ollama = session.exec("which ollama").strip()
        if "ollama" not in check_ollama:
            logger.info("Installing Ollama on RunPod...")
            session.stream_exec("curl -fsSL https://ollama.com/install.sh | sh", timeout=120)
        
        # Start Ollama service
        logger.info("Starting Ollama background daemon...")
        session.exec("nohup ollama serve > /root/ollama.log 2>&1 &")
        time.sleep(3)

        # Pull qwen2.5vl:14b
        logger.info("=== STEP 2: Pulling qwen2.5vl:14b on RTX 4090 ===")
        check_models = session.exec("ollama list")
        if "qwen2.5vl:14b" not in check_models:
            logger.info("Pulling qwen2.5vl:14b model weights (high-speed datacenter connection)...")
            session.stream_exec("ollama pull qwen2.5vl:14b", timeout=600)
        else:
            logger.info("Model qwen2.5vl:14b is already downloaded!")

        # Step 3: Upload Codebase & Books
        logger.info("=== STEP 3: Uploading Project Codebase & Source Books ===")
        archive_bytes = pack_codebase()
        upload_archive(session, archive_bytes)

        # Step 4: Install Python Dependencies on Pod
        logger.info("=== STEP 4: Installing Python Dependencies on RunPod ===")
        session.stream_exec(
            "pip install -q click rich pyyaml pydantic lancedb pymupdf rapidocr-onnxruntime ebooklib beautifulsoup4",
            timeout=180,
        )

        # Step 5: Execute Heavy Builder on Both Books with 14B VLM
        logger.info("=== STEP 5: Building Bookpacks with qwen2.5vl:14b ===")

        # Build runner script on Pod
        pod_runner = """
import sys, time
from pathlib import Path
sys.path.insert(0, '/root/mkp/src')

from mkp_builder.pipeline import BuilderPipeline

epub_path = Path('/root/mkp/source_doc/Illustrated Seamanship (Ivar Dedekam) (z-library.sk, 1lib.sk, z-lib.sk).epub')
pdf_path = Path('/root/mkp/source_doc/Sail and Rig Tuning (Ivar Dedekam) (z-library.sk, 1lib.sk, z-lib.sk).pdf')

work_dir = Path('/root/mkp/cloud_build')
work_dir.mkdir(parents=True, exist_ok=True)

pipeline = BuilderPipeline(
    work_dir=work_dir,
    ollama_host='http://127.0.0.1:11434',
    vlm_model='qwen2.5vl:14b',
    text_model='qwen2.5vl:14b',
    force=True,
    headless=True,
)

print('>>> [1/2] Processing Illustrated Seamanship (EPUB) with 14B VLM...')
t0 = time.time()
bp1 = pipeline.build_book(
    book_path=epub_path,
    book_id='illustrated_seamanship',
    tier='T1',
    title='Illustrated Seamanship',
    lang='en',
    skip_vlm=False,
    skip_triplets=False,
    skip_rules=False,
    seed_golden_rules=True,
)
print(f'>>> [1/2] Illustrated Seamanship built in {time.time()-t0:.2f}s: {bp1}')

print('>>> [2/2] Processing Sail and Rig Tuning (PDF) with 14B VLM...')
t1 = time.time()
bp2 = pipeline.build_book(
    book_path=pdf_path,
    book_id='sail_and_rig_tuning',
    tier='T1',
    title='Sail and Rig Tuning',
    lang='en',
    skip_vlm=False,
    skip_triplets=False,
    skip_rules=False,
    seed_golden_rules=True,
)
print(f'>>> [2/2] Sail and Rig Tuning built in {time.time()-t1:.2f}s: {bp2}')
"""
        session.exec(f"cat << 'EOF' > /root/mkp/run_build.py\n{pod_runner}\nEOF")

        logger.info("Launching full 14B builder execution on RTX 4090 GPU...")
        session.stream_exec("python3 /root/mkp/run_build.py", timeout=3600)

        # Step 6: Download Generated Bookpacks
        logger.info("=== STEP 6: Downloading Signed Bookpacks ===")
        out_dir = Path("qa/bookpacks")
        out_dir.mkdir(parents=True, exist_ok=True)

        download_file(
            session,
            "/root/mkp/cloud_build/out/illustrated_seamanship.bookpack.zip",
            out_dir / "illustrated_seamanship.bookpack.zip",
        )
        download_file(
            session,
            "/root/mkp/cloud_build/out/sail_and_rig_tuning.bookpack.zip",
            out_dir / "sail_and_rig_tuning.bookpack.zip",
        )

        logger.info("=== ALL STEPS COMPLETED SUCCESSFULLY! ===")

    finally:
        session.close()


if __name__ == "__main__":
    main()
