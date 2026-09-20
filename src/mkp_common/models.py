"""Pydantic v2 data models for MKP (Schema v1.5)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DiagramType(str, Enum):
    MANEUVER = "maneuver"
    KNOT = "knot"
    EQUIPMENT = "equipment"
    POLAR = "polar"
    MAP = "map"
    TABLE_FIGURE = "table_figure"
    OTHER = "other"


class TermsBilingual(BaseModel):
    ru: list[str] = Field(default_factory=list)
    en: list[str] = Field(default_factory=list)


class ManeuverBlock(BaseModel):
    maneuver_type: str | None = None
    course_to_wind: str | None = None
    wind_conditions: str | None = None
    rigging: dict[str, Any] | None = None
    crew_steps: list[str] = Field(default_factory=list)


class KnotBlock(BaseModel):
    knot_name: str | None = None
    purpose: str | None = None
    tying_steps: list[str] = Field(default_factory=list)
    load_direction: str | None = None
    security_notes: list[str] = Field(default_factory=list)


class EquipmentBlock(BaseModel):
    equipment_name: str | None = None
    parts: list[dict[str, str]] = Field(default_factory=list)
    function: str | None = None
    adjustment_steps: list[str] = Field(default_factory=list)


class PolarBlock(BaseModel):
    axes: str | None = None
    conditions: str | None = None
    readable_values: list[dict[str, Any]] = Field(default_factory=list)
    values_confidence: Literal["estimated", "exact"] = "estimated"


class MapBlock(BaseModel):
    area: str | None = None
    symbols: list[str] = Field(default_factory=list)
    route_or_notes: str | None = None


class TableFigureBlock(BaseModel):
    caption: str | None = None
    rows_via_ocr: list[str] = Field(default_factory=list)


class OtherBlock(BaseModel):
    free_note: str | None = None


class VerificationResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_status: Literal["pass", "fail"] = Field(default="pass", alias="schema")
    text_check: Literal["pass", "fail", "skipped"] = "pass"
    visual_check: Literal["pass", "mismatch", "skipped"] = "pass"
    flags: list[str] = Field(default_factory=list)
    needs_review: bool = False
    issues: list[str] = Field(default_factory=list)


class VlmData(BaseModel):
    model: str = "qwen2.5vl:7b"
    prompt_ver: str = "2.0"
    status: Literal["ok", "unrecognized", "error"] = "ok"
    diagram_type: DiagramType
    description: str = ""
    structured: dict[str, Any] | None = None
    terms: TermsBilingual = Field(default_factory=TermsBilingual)
    verification: VerificationResult = Field(default_factory=VerificationResult)


class VisualAsset(BaseModel):
    image_path: str
    image_sha256: str
    vlm_data: VlmData | None = None
    bbox: list[float] | None = None  # [l, t, r, b] normalized or physical


class TableItem(BaseModel):
    table_id: str
    markdown_repr: str
    caption: str | None = None


class ChunkRecord(BaseModel):
    chunk_id: str
    book_id: str
    lang: str = "en"
    page_number: int
    location_ref: str
    section_path: str = ""
    text_content: str = ""
    ocr_text: str | None = None
    ocr_confidence_low: bool = False
    visual_assets: list[VisualAsset] = Field(default_factory=list)
    tables: list[TableItem] = Field(default_factory=list)
    n_tokens: int = 0
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class PageRecord(BaseModel):
    book_id: str
    lang: str = "en"
    page_number: int
    pagination: Literal["physical", "virtual_spine"] = "physical"
    location_ref: str
    spine_href: str | None = None
    title: str | None = None
    full_page_markdown: str = ""
    ocr_text: str | None = None
    assets_list: list[str] = Field(default_factory=list)
    tables_list: list[str] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)


class QaReviewItem(BaseModel):
    book_id: str
    image_path: str
    image_sha256: str
    diagram_type: str
    reasons: list[str] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class BookMetadata(BaseModel):
    book_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    lang: list[str] = Field(default_factory=lambda: ["en"])
    pagination: Literal["physical", "virtual_spine"] = "physical"
    pipeline_profile: Literal["digital", "scanned", "mixed"] = "digital"
    ocr_engine: str = "rapidocr"
    spine_map: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class BuilderInfo(BaseModel):
    product: str = "mkp-builder"
    version: str = "1.5.0"
    vlm: str = "qwen2.5vl:7b@prompt2.0"
    ocr: str = "rapidocr[ru,en]"


class EmbedModelInfo(BaseModel):
    name: str = "intfloat/multilingual-e5-large"
    dim: int = 1024


class ManifestCounts(BaseModel):
    pages: int = 0
    chunks: int = 0
    figures: int = 0
    triples: int = 0
    needs_review: int = 0


class BookpackManifest(BaseModel):
    artifact: Literal["bookpack"] = "bookpack"
    schema_version: str = "1.5"
    book_id: str
    title: str
    lang: list[str] = Field(default_factory=lambda: ["en"])
    pagination: Literal["physical", "virtual_spine"] = "physical"
    pipeline_profile: Literal["digital", "scanned", "mixed"] = "digital"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    builder: BuilderInfo = Field(default_factory=BuilderInfo)
    embed_model: EmbedModelInfo = Field(default_factory=EmbedModelInfo)
    counts: ManifestCounts = Field(default_factory=ManifestCounts)
    files_sha256: dict[str, str] = Field(default_factory=dict)


class EntityNode(BaseModel):
    name: str
    type: str
    lang: str = "en"


class TripletRecord(BaseModel):
    subject: EntityNode
    predicate: str
    object: EntityNode
    provenance: dict[str, Any]  # book_id, page_number, chunk_id, location_ref
    model: str = "qwen2.5:7b"
    prompt_ver: str = "2.0"
