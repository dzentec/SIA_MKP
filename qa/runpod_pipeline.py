"""Automated RunPod Pipeline Runner for MKP-Builder with qwen2.5vl:14b on RTX A5000."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import time
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("runpod_pipeline")

SSH_HOST = "y5vnpb4pglin4p-644113a9@ssh.runpod.io"
PORT = 9876


class PodSession:
    """Manages an SSH session with PTY and port forwarding to RunPod."""

    stdin: Any
    stdout: Any

    def __init__(self, host: str = SSH_HOST, local_port: int = PORT):
        self.host = host
        self.local_port = local_port
        logger.info("Connecting to RunPod (%s) with port forwarding -L %d:127.0.0.1:%d...", host, local_port, local_port)
        self.proc = subprocess.Popen(
            [
                "ssh",
                "-tt",
                "-o", "StrictHostKeyChecking=no",
                "-L", f"{local_port}:127.0.0.1:{local_port}",
                host,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        if self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError("Failed to attach pipes to SSH process")
        self.stdin = self.proc.stdin
        self.stdout = self.proc.stdout
        self._wait_ready()

    def _wait_ready(self) -> None:
        buf = ""
        while True:
            char = self.stdout.read(1)
            if not char:
                break
            buf += char
            if "# " in buf or "$ " in buf:
                break
        logger.info("RunPod shell connected and ready!")

    def exec(self, cmd: str, timeout: float = 180.0) -> str:
        marker = f"__CMD_DONE_{int(time.time()*1000)}__"
        full_cmd = f"{cmd}\necho {marker}\n"
        self.stdin.write(full_cmd)
        self.stdin.flush()
        buf = []
        start = time.time()
        while time.time() - start < timeout:
            line = self.stdout.readline()
            if not line:
                break
            if marker in line:
                break
            line_str = line.rstrip()
            buf.append(line_str)
        return "\n".join(buf)

    def stream_exec(self, cmd: str, timeout: float = 7200.0) -> str:
        marker = f"__STREAM_DONE_{int(time.time()*1000)}__"
        full_cmd = f"{cmd}\necho {marker}\n"
        self.stdin.write(full_cmd)
        self.stdin.flush()
        buf = []
        start = time.time()
        while time.time() - start < timeout:
            line = self.stdout.readline()
            if not line:
                break
            if marker in line:
                break
            line_str = line.rstrip()
            if line_str and not line_str.startswith("echo __STREAM"):
                print(f"[A5000] {line_str}")
                buf.append(line_str)
        return "\n".join(buf)

    def close(self) -> None:
        try:
            self.stdin.write("exit\n")
            self.stdin.flush()
            self.proc.terminate()
        except Exception:
            pass


def start_remote_file_daemon(session: PodSession, port: int = PORT) -> None:
    """Start raw TCP file transfer daemon on RunPod."""
    logger.info("Starting raw TCP file transfer daemon on RunPod port %d...", port)
    daemon_code = f"""cat << 'EOF' > /root/tcp_file_daemon.py
import socket, struct, os, sys

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('127.0.0.1', {port}))
s.listen(5)

while True:
    conn, _ = s.accept()
    mode = conn.recv(4)
    if mode == b'SEND':
        raw_name_len = conn.recv(4)
        name_len = struct.unpack('!I', raw_name_len)[0]
        filename = conn.recv(name_len).decode('utf-8')
        raw_file_len = conn.recv(8)
        file_len = struct.unpack('!Q', raw_file_len)[0]
        
        target_dir = '/root/SIA_MKP/.init_doc/source_doc'
        os.makedirs(target_dir, exist_ok=True)
        dest_file = os.path.join(target_dir, filename)
        
        received = 0
        with open(dest_file, 'wb') as f:
            while received < file_len:
                chunk = conn.recv(min(65536, file_len - received))
                if not chunk:
                    break
                f.write(chunk)
                received += len(chunk)
        conn.sendall(b'OK')
        conn.close()
    elif mode == b'RECV':
        raw_name_len = conn.recv(4)
        name_len = struct.unpack('!I', raw_name_len)[0]
        filename = conn.recv(name_len).decode('utf-8')
        source_file = os.path.join('/root/SIA_MKP/cloud_build/out', filename)
        
        if not os.path.isfile(source_file):
            conn.sendall(struct.pack('!Q', 0))
            conn.close()
            continue
            
        file_size = os.path.getsize(source_file)
        conn.sendall(struct.pack('!Q', file_size))
        with open(source_file, 'rb') as f:
            while chunk := f.read(65536):
                conn.sendall(chunk)
        conn.close()
EOF
pkill -f tcp_file_daemon.py 2>/dev/null || true
nohup python3 /root/tcp_file_daemon.py > /root/daemon.log 2>&1 &
sleep 2
ps aux | grep tcp_file_daemon
"""
    res = session.exec(daemon_code)
    logger.info("Transfer daemon active:\n%s", res)


def upload_file(local_path: Path, port: int = PORT) -> None:
    """Stream upload a local file via TCP socket."""
    filename = local_path.name
    filesize = local_path.stat().st_size
    logger.info("Uploading %s (%.2f MB)...", filename, filesize / (1024 * 1024))

    t0 = time.time()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("127.0.0.1", port))
    
    s.sendall(b"SEND")
    name_bytes = filename.encode("utf-8")
    s.sendall(struct.pack("!I", len(name_bytes)) + name_bytes)
    s.sendall(struct.pack("!Q", filesize))

    uploaded = 0
    with open(local_path, "rb") as f:
        while chunk := f.read(65536):
            s.sendall(chunk)
            uploaded += len(chunk)
            if uploaded % (20 * 1024 * 1024) < 65536:
                logger.info("Uploaded %.1f / %.1f MB (%.1f%%)", uploaded / (1024 * 1024), filesize / (1024 * 1024), (uploaded / filesize) * 100)

    resp = s.recv(2)
    s.close()
    if resp == b"OK":
        logger.info("Uploaded %s in %.2f s (%.2f MB/s)!", filename, time.time() - t0, (filesize / (1024 * 1024)) / max(time.time() - t0, 0.1))
    else:
        raise RuntimeError(f"Upload failed: daemon response {resp!r}")


def download_file(remote_filename: str, local_dest: Path, port: int = PORT) -> None:
    """Stream download a file via TCP socket."""
    logger.info("Downloading %s from RunPod...", remote_filename)
    local_dest.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("127.0.0.1", port))
    s.sendall(b"RECV")
    name_bytes = remote_filename.encode("utf-8")
    s.sendall(struct.pack("!I", len(name_bytes)) + name_bytes)

    raw_len = s.recv(8)
    if len(raw_len) < 8:
        raise RuntimeError(f"Failed to read file length for {remote_filename}")
    filesize = struct.unpack("!Q", raw_len)[0]
    if filesize == 0:
        raise FileNotFoundError(f"Remote file not found: {remote_filename}")

    received = 0
    with open(local_dest, "wb") as f:
        while received < filesize:
            chunk = s.recv(min(65536, filesize - received))
            if not chunk:
                break
            f.write(chunk)
            received += len(chunk)

    s.close()
    logger.info("Downloaded %s (%.2f MB) in %.2f s!", local_dest.name, local_dest.stat().st_size / (1024 * 1024), time.time() - t0)


def main():
    session = PodSession(host=SSH_HOST, local_port=PORT)

    try:
        # Step 1: Install Ollama & Pull qwen2.5vl:14b
        logger.info("=== 1. Checking Ollama and Pulling qwen2.5vl:14b ===")
        check_ollama = session.exec("which ollama").strip()
        if "ollama" not in check_ollama:
            logger.info("Installing Ollama on RTX A5000 pod...")
            session.stream_exec("curl -fsSL https://ollama.com/install.sh | sh", timeout=180)
        
        session.exec("pkill -f 'ollama serve' 2>/dev/null || true; nohup ollama serve > /root/ollama.log 2>&1 &")
        time.sleep(4)

        check_models = session.exec("ollama list")
        if "qwen2.5vl:14b" not in check_models:
            logger.info("Pulling qwen2.5vl:14b on A5000 pod (datacenter speed)...")
            session.stream_exec("ollama pull qwen2.5vl:14b", timeout=600)
        else:
            logger.info("Model qwen2.5vl:14b is already ready on pod!")

        # Step 2: Clone repository & install dependencies
        logger.info("=== 2. Setting Up SIA_MKP Repository ===")
        session.exec("rm -rf /root/SIA_MKP && git clone https://github.com/dzentec/SIA_MKP.git /root/SIA_MKP")
        session.stream_exec("pip install -q click rich pyyaml pydantic lancedb pymupdf rapidocr-onnxruntime ebooklib beautifulsoup4 sentence-transformers", timeout=180)
        session.exec("pip install -e /root/SIA_MKP")

        # Step 3: Start TCP transfer daemon & upload source books
        logger.info("=== 3. Uploading Source Books via Fast Port-Forwarded TCP Stream ===")
        start_remote_file_daemon(session, PORT)

        src_dir = Path(".init_doc/source_doc")
        epub_file = src_dir / "Illustrated Seamanship (Ivar Dedekam) (z-library.sk, 1lib.sk, z-lib.sk).epub"
        pdf_file = src_dir / "Sail and Rig Tuning (Ivar Dedekam) (z-library.sk, 1lib.sk, z-lib.sk).pdf"

        upload_file(epub_file, PORT)
        upload_file(pdf_file, PORT)

        # Verify books on remote
        verify_ls = session.exec("ls -lh /root/SIA_MKP/.init_doc/source_doc")
        logger.info("Source books on Pod:\n%s", verify_ls)

        # Step 4: Run Heavy Builder Pipeline on both books
        logger.info("=== 4. Launching Full MKP-Builder with qwen2.5vl:14b ===")
        builder_script = """cat << 'EOF' > /root/SIA_MKP/run_build_14b.py
import sys, time
from pathlib import Path

from mkp_builder.pipeline import BuilderPipeline

epub_path = Path('/root/SIA_MKP/.init_doc/source_doc/Illustrated Seamanship (Ivar Dedekam) (z-library.sk, 1lib.sk, z-lib.sk).epub')
pdf_path = Path('/root/SIA_MKP/.init_doc/source_doc/Sail and Rig Tuning (Ivar Dedekam) (z-library.sk, 1lib.sk, z-lib.sk).pdf')

work_dir = Path('/root/SIA_MKP/cloud_build')
work_dir.mkdir(parents=True, exist_ok=True)

pipeline = BuilderPipeline(
    work_dir=work_dir,
    ollama_host='http://127.0.0.1:11434',
    vlm_model='qwen2.5vl:14b',
    text_model='qwen2.5vl:14b',
    force=True,
    headless=True,
)

print('>>> [1/2] Building Illustrated Seamanship (EPUB) with 14B VLM...')
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
print(f'>>> [1/2] Completed in {time.time()-t0:.2f}s: {bp1}')

print('>>> [2/2] Building Sail and Rig Tuning (PDF) with 14B VLM...')
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
print(f'>>> [2/2] Completed in {time.time()-t1:.2f}s: {bp2}')
EOF
python3 /root/SIA_MKP/run_build_14b.py
"""
        session.stream_exec(builder_script, timeout=7200)

        # Step 5: Download generated Bookpacks
        logger.info("=== 5. Downloading Signed 14B Bookpacks ===")
        out_dir = Path("qa/bookpacks")
        out_dir.mkdir(parents=True, exist_ok=True)

        download_file("illustrated_seamanship.bookpack.zip", out_dir / "illustrated_seamanship.bookpack.zip", PORT)
        download_file("sail_and_rig_tuning.bookpack.zip", out_dir / "sail_and_rig_tuning.bookpack.zip", PORT)

        logger.info("=== 6. All Cloud Tasks Completed Successfully! ===")

    finally:
        session.close()


if __name__ == "__main__":
    main()
