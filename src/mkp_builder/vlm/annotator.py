"""VLM Annotation Engine (Prompt 2.0 with discriminated union taxonomy)."""

from __future__ import annotations

import json
import logging
from typing import Any

from mkp_common.cache import PersistentCache, make_cache_key, compute_sha256_bytes
from mkp_common.models import DiagramType, VlmData, TermsBilingual
from mkp_builder.vlm.client import OllamaClient

logger = logging.getLogger(__name__)

VLM_PROMPT_V2 = """You are a maritime diagram analysis expert. Analyze this image from a maritime manual.
Return a valid JSON object matching this schema:
{
  "diagram_type": "maneuver" | "knot" | "equipment" | "polar" | "map" | "table_figure" | "other",
  "status": "ok" | "unrecognized",
  "description": "Detailed description in Russian or English explaining the diagram",
  "terms": {
    "ru": ["term1", "term2"],
    "en": ["term1", "term2"]
  },
  "structured": {
    <EXACTLY ONE key matching diagram_type, with relevant details>:
    - for "knot": {"knot_name": str, "purpose": str, "tying_steps": [str], "load_direction": str, "security_notes": [str]}
    - for "maneuver": {"maneuver_type": str, "course_to_wind": str, "wind_conditions": str, "rigging": dict, "crew_steps": [str]}
    - for "equipment": {"equipment_name": str, "parts": [{"name": str, "role": str}], "function": str, "adjustment_steps": [str]}
    - for "polar": {"axes": str, "conditions": str, "readable_values": [{"course": str, "boat_speed_kn": float}], "values_confidence": "estimated"}
    - for "map": {"area": str, "symbols": [str], "route_or_notes": str}
    - for "table_figure": {"caption": str, "rows_via_ocr": [str]}
    - for "other": {"free_note": str}
  }
}
All other diagram types must NOT be present in structured. Return ONLY valid JSON."""


class VLMAnnotator:
    """Annotates figures using Qwen2.5-VL with Prompt 2.0 and SHA-256 caching."""

    def __init__(
        self,
        client: OllamaClient,
        cache: PersistentCache | None = None,
        model: str = "qwen2.5vl:7b",
        prompt_ver: str = "2.0",
    ):
        self.client = client
        self.cache = cache
        self.model = model
        self.prompt_ver = prompt_ver

    def annotate(self, image_bytes: bytes, image_sha256: str | None = None) -> tuple[VlmData, bool]:
        """Annotate a figure image. Returns (VlmData, is_cache_hit)."""
        img_sha = image_sha256 or compute_sha256_bytes(image_bytes)
        cache_key = make_cache_key(img_sha, self.model, self.prompt_ver)

        if self.cache and self.cache.contains(cache_key):
            cached_data = self.cache.get(cache_key)
            try:
                vlm_data = VlmData.model_validate(cached_data)
                return vlm_data, True
            except Exception as e:
                logger.warning("Invalid cache payload for key %s: %s", cache_key, e)

        # Call Ollama
        try:
            raw_response = self.client.generate(
                prompt=VLM_PROMPT_V2,
                model=self.model,
                image_bytes=image_bytes,
                format_json=True,
                num_predict=512,
            )
            parsed_json = json.loads(raw_response)

            diag_type_raw = parsed_json.get("diagram_type", "other")
            try:
                diag_type = DiagramType(diag_type_raw)
            except ValueError:
                diag_type = DiagramType.OTHER

            terms_raw = parsed_json.get("terms", {})
            terms = TermsBilingual(
                ru=terms_raw.get("ru", []),
                en=terms_raw.get("en", []),
            )

            vlm_data = VlmData(
                model=self.model,
                prompt_ver=self.prompt_ver,
                status=parsed_json.get("status", "ok"),
                diagram_type=diag_type,
                description=parsed_json.get("description", ""),
                structured=parsed_json.get("structured"),
                terms=terms,
            )

        except Exception as e:
            logger.error("VLM annotation failed for image %s: %s", img_sha[:12], e)
            vlm_data = VlmData(
                model=self.model,
                prompt_ver=self.prompt_ver,
                status="error",
                diagram_type=DiagramType.OTHER,
                description=f"Annotation error: {e}",
            )

        if self.cache and vlm_data.status == "ok":
            self.cache.set(cache_key, vlm_data.model_dump(by_alias=True))
            self.cache.flush()

        return vlm_data, False
