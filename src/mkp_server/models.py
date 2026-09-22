"""Data models for mkp-server (Storage, Registry, Search, WAL and MCP)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

from mkp_common.models import (
    ChunkRecord,
    TripletRecord,
    EntityNode,
    VisualAsset,
    TableItem,
    BookMetadata,
    BookpackManifest,
)
from mkp_common.rules_schema import (
    Claim,
    Cluster,
    Rule,
    RuleSource,
    RuleTrigger,
    RuleAction,
    ManifestV3,
    ManifestBase,
    ManifestUser,
    CompatibilityInfo,
    BookpackInfo,
)


class RollbackMode(str, Enum):
    AUTO = "auto"
    BASE_RESET = "base-reset"
    FACTORY = "factory"


class BookRecord(BaseModel):
    """Metadata record of an imported book in the base registry."""
    book_id: str
    title: str
    lang: list[str] = Field(default_factory=lambda: ["en"])
    generation: int = 1
    t1_version: str = "1.0.0"
    t1_hash: str = ""
    imported_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    counts: dict[str, int] = Field(default_factory=dict)
    files: list[str] = Field(default_factory=list)


class BaseRegistry(BaseModel):
    """Schema for base.json registry inside storage."""
    topic: str = "marine"
    schema_version: str = "1.5"
    server_version: str = "1.5.0"
    active_generation: int = 1
    last_updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    books: dict[str, BookRecord] = Field(default_factory=dict)


class StorageConfig(BaseModel):
    """Path configuration for the 4-tier storage lifecycle."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    storage_root: Path
    topic: str = "marine"

    @property
    def active_dir(self) -> Path:
        return self.storage_root / "active"

    @property
    def backup_dir(self) -> Path:
        return self.storage_root / "backup"

    @property
    def staging_dir(self) -> Path:
        return self.storage_root / "staging"

    @property
    def fallback_dir(self) -> Path:
        return self.storage_root / "fallback"

    @property
    def failed_dir(self) -> Path:
        return self.storage_root / "failed"

    @property
    def logs_dir(self) -> Path:
        return self.storage_root / "logs"

    @property
    def wal_file(self) -> Path:
        return self.storage_root / "apply.wal"

    @property
    def base_registry_file(self) -> Path:
        return self.storage_root / "base.json"


class StorageStats(BaseModel):
    """Detailed storage statistics and telemetry preview."""
    topic: str
    storage_path: str
    total_books: int = 0
    total_chunks: int = 0
    total_rules: int = 0
    total_triplets: int = 0
    active_generation: int = 1
    disk_usage_bytes: int = 0
    has_backup: bool = False
    has_fallback: bool = False
    wal_status: str = "idle"


class SearchResult(BaseModel):
    """Result item returned by search_chunks."""
    chunk_id: str
    book_id: str
    page_number: int
    location_ref: str
    section_path: str = ""
    text_content: str = ""
    score: float = 0.0
    tier: str = "T1"
    lang: str = "en"
    diagrams: list[dict[str, Any]] = Field(default_factory=list)


class UpdateInfo(BaseModel):
    """Metadata about available bookpack updates."""
    version: str
    release_date: str
    tier: str
    changelog: str = ""
    download_url: str | None = None
