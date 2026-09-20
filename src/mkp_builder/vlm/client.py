"""Ollama HTTP client for VLM and Text LLM inferences."""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import time
from typing import Any
import requests

logger = logging.getLogger(__name__)


class OllamaClient:
    """Robust client for interacting with local Ollama instance."""

    def __init__(
        self,
        host: str = "http://127.0.0.1:11434",
        vlm_model: str = "qwen2.5vl:7b",
        text_model: str = "qwen2.5:7b",
        timeout: float = 45.0,
        max_retries: int = 2,
        ollama_bin_path: str = r"D:\Ollama\ollama.exe",
        models_dir: str = r"D:\AI_models\ollama",
    ):
        self.host = host.rstrip("/")
        self.vlm_model = vlm_model
        self.text_model = text_model
        self.timeout = timeout
        self.max_retries = max_retries
        self.ollama_bin_path = ollama_bin_path
        self.models_dir = models_dir

    def is_alive(self) -> bool:
        try:
            r = requests.get(f"{self.host}/api/version", timeout=3.0)
            return r.status_code == 200
        except Exception:
            return False

    def ensure_server(self) -> bool:
        """Check if server is running, or attempt to start it if binary exists."""
        if self.is_alive():
            return True

        if os.path.exists(self.ollama_bin_path):
            logger.info("Starting Ollama background process: %s", self.ollama_bin_path)
            env = os.environ.copy()
            env["OLLAMA_MODELS"] = self.models_dir
            env["OLLAMA_FLASH_ATTENTION"] = "1"
            subprocess.Popen(
                [self.ollama_bin_path, "serve"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Wait up to 10 seconds for startup
            for _ in range(20):
                time.sleep(0.5)
                if self.is_alive():
                    logger.info("Ollama server successfully started and responsive.")
                    return True

        logger.warning("Ollama server is not reachable at %s", self.host)
        return False

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        image_bytes: bytes | None = None,
        format_json: bool = True,
        num_predict: int = 512,
        temperature: float = 0.1,
    ) -> str:
        """Call Ollama /api/generate with retry and timeout."""
        target_model = model or (self.vlm_model if image_bytes else self.text_model)
        url = f"{self.host}/api/generate"

        payload: dict[str, Any] = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": num_predict,
                "temperature": temperature,
            },
        }

        if format_json:
            payload["format"] = "json"

        if image_bytes:
            b64_img = base64.b64encode(image_bytes).decode("utf-8")
            payload["images"] = [b64_img]

        last_error = None
        for attempt in range(1, self.max_retries + 2):
            try:
                resp = requests.post(url, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                return data.get("response", "")
            except Exception as e:
                last_error = e
                logger.warning(
                    "Ollama request attempt %d/%d failed for model %s: %s",
                    attempt,
                    self.max_retries + 1,
                    target_model,
                    e,
                )
                if attempt <= self.max_retries:
                    time.sleep(1.0 * attempt)

        raise RuntimeError(f"Ollama generation failed after {self.max_retries + 1} attempts: {last_error}")
