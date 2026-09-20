"""Persistent SHA-256 cache for VLM annotations, OCR results, and verifications."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def compute_sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 hex digest for given bytes."""
    return hashlib.sha256(data).hexdigest()


def compute_sha256_file(filepath: Path | str) -> str:
    """Compute SHA-256 hex digest for a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def make_cache_key(content_sha256: str, model_tag: str, prompt_ver: str, extra: str = "") -> str:
    """Create a unique cache key combining content hash, model, and prompt version."""
    raw = f"{content_sha256}:{model_tag}:{prompt_ver}:{extra}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class PersistentCache:
    """File-backed persistent key-value cache."""

    def __init__(self, cache_file: Path | str):
        self.cache_file = Path(cache_file)
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = {}
        self._dirty = False
        self._load()

    def _load(self) -> None:
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}
        else:
            self._data = {}

    def get(self, key: str) -> Any | None:
        return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._dirty = True

    def contains(self, key: str) -> bool:
        return key in self._data

    def flush(self) -> None:
        """Atomic write back to cache file."""
        if not self._dirty:
            return
        temp_dir = self.cache_file.parent
        with tempfile.NamedTemporaryFile("w", dir=temp_dir, delete=False, encoding="utf-8") as tmp:
            json.dump(self._data, tmp, ensure_ascii=False, indent=2)
            temp_name = tmp.name
        # Atomic replace on Windows/Linux
        os.replace(temp_name, self.cache_file)
        self._dirty = False

    def clear(self) -> None:
        self._data.clear()
        self._dirty = True
        self.flush()

    def __len__(self) -> int:
        return len(self._data)
