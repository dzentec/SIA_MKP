"""Pydantic v2 data models for Claims, Clusters, Rules and Bookpack v0.3 (HLD v3.3.1)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
import yaml
from pydantic import BaseModel, ConfigDict, Field


class RuleSource(BaseModel):
    """Source provenance linking directly to text chunk and exact quote."""
    doc_id: str
    page: int
    chunk_id: str
    quote: str = Field(..., max_length=500, description="Exact quotation from text chunk")


class Claim(BaseModel):
    """Atomic factual statement extracted from document."""
    claim_id: str
    text: str
    type: Literal["physical", "empirical", "procedural", "normative"]
    subject: str
    predicate: str
    object: Any
    context: dict[str, Any] = Field(default_factory=dict)
    source: RuleSource
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    mapped: bool = False
    tier: Literal["T1", "T2", "T2.5", "T3"] = "T1"


class Cluster(BaseModel):
    """Group of related claims for rule synthesis."""
    cluster_id: str
    topic: str
    claims: list[str] = Field(default_factory=list, description="List of claim_ids")
    dominant_type: str = "empirical"
    archetypes: list[str] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    coverage: float = Field(default=1.0, ge=0.0, le=1.0)
    tier: Literal["T1", "T2", "T2.5"] = "T1"


class RuleTrigger(BaseModel):
    """Conditional trigger for dynamic rule evaluation."""
    ontology_field: str
    operator: Literal[">", ">=", "<", "<=", "==", "!=", "between"]
    value: float | list[float] | str
    unit: str = ""


class RuleAction(BaseModel):
    """Action recommendation resulting from rule trigger."""
    action_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    description: str = ""


class Rule(BaseModel):
    """Formalized operational rule (HLD v3.3.1)."""
    rule_id: str
    domain: Literal["safety", "trim", "reefing", "maneuver", "predictive"]
    archetype: list[str] = Field(default_factory=list)
    triggers: list[RuleTrigger] = Field(default_factory=list)
    triggers_logic: Literal["ALL", "ANY"] = "ALL"
    actions: list[RuleAction] = Field(default_factory=list)
    severity: Literal["info", "warning", "critical"]
    uncertainty: Literal["verified", "hypothesis", "todo"] = "verified"
    tier: Literal["T1", "T2", "T2.5"] = "T1"
    region: str | None = None
    origin: Literal["base", "user"] = "base"
    review_mode: Literal["manual", "auto_marked", "auto_confirmed"] = "manual"
    requires_confirmation: bool = False
    sources: list[RuleSource] = Field(default_factory=list)
    conflicts_with: list[str] = Field(default_factory=list)
    status: Literal["draft", "review", "approved", "deprecated"] = "draft"
    deprecated: bool = False
    orphaned: bool = False
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class CompatibilityInfo(BaseModel):
    """Compatibility matrix metadata (Invariant I14)."""
    min_server_version: str = "1.0.0"
    max_server_version: str = "2.x.x"
    bookpack_schema: str = "1.0"
    supported_bookpack_schemas: list[str] = Field(
        default_factory=lambda: ["0.1", "0.2", "0.3", "1.0"]
    )


class ManifestBase(BaseModel):
    """T1 Base layer metadata in Bookpack v0.3.0."""
    t1_version: str = "1.0.0"
    t1_hash: str = ""
    merged_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ManifestUser(BaseModel):
    """User layers metadata in Bookpack v0.3.0."""
    t2_hash: str | None = None
    t25_hash: str | None = None
    t3_hash: str | None = None
    merged_at: str | None = None


class ManifestArtifact(BaseModel):
    """Detailed artifact counter and per-artifact hash."""
    count: int = 0
    sha256: str = ""
    per_artifact: str | None = None
    size_bytes: int | None = None


class ManifestV3(BaseModel):
    """Bookpack v0.3.0 manifest schema (HLD v3.3.1)."""
    bookpack_version: str = "0.3.0"
    schema_version: str = "1.0"
    ontology_version: str = "0.1.0"
    generation: int = 1
    parent_hash: str | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    user_id: str = "local"
    base: ManifestBase = Field(default_factory=ManifestBase)
    user: ManifestUser = Field(default_factory=ManifestUser)
    compatibility: CompatibilityInfo = Field(default_factory=CompatibilityInfo)
    content: dict[str, Any] = Field(default_factory=dict)


class BookpackInfo(BaseModel):
    """System information returned by get_bookpack_info MCP tool."""
    generation: int
    bookpack_version: str
    server_version: str
    t1_version: str
    t1_hash: str
    user_layers: dict[str, str | None]
    created_at: str
    merged_at: str
    available_updates: list[dict[str, Any]] = Field(default_factory=list)


# Ontology Loaders Helper
def get_ontology_path() -> Path:
    """Resolve project ontology root directory."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "ontology",
        Path("ontology"),
    ]
    for c in candidates:
        if c.exists() and (c / "sia_ontology.yaml").exists():
            return c
    return candidates[0]


def load_ontology(ontology_dir: Path | str | None = None) -> dict[str, Any]:
    """Load core SIA ontology YAML."""
    base = Path(ontology_dir) if ontology_dir else get_ontology_path()
    onto_file = base / "sia_ontology.yaml"
    if not onto_file.exists():
        return {}
    with open(onto_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_relations(ontology_dir: Path | str | None = None) -> dict[str, Any]:
    """Load relations/predicates ontology YAML."""
    base = Path(ontology_dir) if ontology_dir else get_ontology_path()
    rel_file = base / "sia_relations.yaml"
    if not rel_file.exists():
        return {}
    with open(rel_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_mappings(ontology_dir: Path | str | None = None) -> dict[str, Any]:
    """Load keyword-to-ontology mapping YAML."""
    base = Path(ontology_dir) if ontology_dir else get_ontology_path()
    map_file = base / "mapping.yaml"
    if not map_file.exists():
        return {}
    with open(map_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
