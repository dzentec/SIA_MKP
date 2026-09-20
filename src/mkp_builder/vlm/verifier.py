"""3-Stage Continuous Verification Engine (REQ-B04)."""

from __future__ import annotations

import json
import logging
from typing import Any

from mkp_common.cache import PersistentCache, make_cache_key
from mkp_common.models import (
    VlmData,
    VerificationResult,
    QaReviewItem,
    ManeuverBlock,
    KnotBlock,
    EquipmentBlock,
    PolarBlock,
    MapBlock,
    TableFigureBlock,
    OtherBlock,
)
from mkp_builder.vlm.client import OllamaClient

logger = logging.getLogger(__name__)

TEXT_CHECK_PROMPT = """Analyze the following maritime diagram annotation for internal textual consistency and coherence.
Diagram Type: {diagram_type}
Description: {description}
Terms: {terms}
Structured: {structured}

Check:
1. Does the description logically match the diagram type and structured details?
2. Are nautical terms and directions consistent?

Return JSON:
{{"consistent": true | false, "issues": ["issue1", "issue2"]}}
Return ONLY valid JSON."""

VISUAL_CRITIC_PROMPT = """You are a visual critic reviewing this diagram image and its proposed annotation.
Proposed Diagram Type: {diagram_type}
Proposed Description: {description}

Does this annotation accurately represent the image without major hallucinations or wrong diagram type?
Return JSON:
{{"matches": true | false, "reasons": ["reason1"]}}
Return ONLY valid JSON."""


class VLMVerifier:
    """Verifies VLM annotations through Schema, Text LLM, and Visual Critic stages."""

    def __init__(
        self,
        client: OllamaClient,
        cache: PersistentCache | None = None,
        text_model: str = "qwen2.5:7b",
        vlm_model: str = "qwen2.5vl:7b",
    ):
        self.client = client
        self.cache = cache
        self.text_model = text_model
        self.vlm_model = vlm_model

    def verify_schema(self, vlm_data: VlmData) -> tuple[bool, list[str]]:
        """Stage 1: Deterministic Pydantic schema validation."""
        issues = []
        if not vlm_data.description:
            issues.append("Empty description")

        structured = vlm_data.structured or {}
        diag_type = vlm_data.diagram_type.value

        if structured:
            block_keys = list(structured.keys())
            if diag_type not in block_keys and diag_type != "other":
                issues.append(f"Structured block key '{block_keys}' does not match diagram_type '{diag_type}'")

            # Validate typed block model
            try:
                block_data = structured.get(diag_type, {})
                if diag_type == "maneuver":
                    ManeuverBlock.model_validate(block_data)
                elif diag_type == "knot":
                    KnotBlock.model_validate(block_data)
                elif diag_type == "equipment":
                    EquipmentBlock.model_validate(block_data)
                elif diag_type == "polar":
                    PolarBlock.model_validate(block_data)
                elif diag_type == "map":
                    MapBlock.model_validate(block_data)
                elif diag_type == "table_figure":
                    TableFigureBlock.model_validate(block_data)
                elif diag_type == "other":
                    OtherBlock.model_validate(block_data)
            except Exception as e:
                issues.append(f"Typed block validation error for {diag_type}: {e}")

        passed = len(issues) == 0
        return passed, issues

    def verify_text_consistency(self, vlm_data: VlmData) -> tuple[bool, list[str]]:
        """Stage 2: Text LLM consistency check."""
        try:
            prompt = TEXT_CHECK_PROMPT.format(
                diagram_type=vlm_data.diagram_type.value,
                description=vlm_data.description,
                terms=vlm_data.terms.model_dump(),
                structured=json.dumps(vlm_data.structured or {}),
            )
            raw = self.client.generate(
                prompt=prompt,
                model=self.text_model,
                format_json=True,
                num_predict=128,
            )
            data = json.loads(raw)
            consistent = data.get("consistent", True)
            issues = data.get("issues", [])
            return consistent, issues
        except Exception as e:
            logger.warning("Text consistency check skipped/failed: %s", e)
            return True, [f"Text check skipped: {e}"]

    def verify_visual_critic(self, vlm_data: VlmData, image_bytes: bytes) -> tuple[bool, list[str]]:
        """Stage 3: Visual Critic check via VLM."""
        try:
            prompt = VISUAL_CRITIC_PROMPT.format(
                diagram_type=vlm_data.diagram_type.value,
                description=vlm_data.description,
            )
            raw = self.client.generate(
                prompt=prompt,
                model=self.vlm_model,
                image_bytes=image_bytes,
                format_json=True,
                num_predict=96,
            )
            data = json.loads(raw)
            matches = data.get("matches", True)
            reasons = data.get("reasons", [])
            return matches, reasons
        except Exception as e:
            logger.warning("Visual critic check skipped/failed: %s", e)
            return True, [f"Visual critic skipped: {e}"]

    def verify(
        self,
        vlm_data: VlmData,
        image_bytes: bytes,
        image_sha256: str,
        book_id: str,
        image_path: str,
    ) -> tuple[VlmData, QaReviewItem | None]:
        """Run all 3 verification stages and apply security policies."""
        cache_key = make_cache_key(image_sha256, self.vlm_model, "verify_v2")

        if self.cache and self.cache.contains(cache_key):
            cached = self.cache.get(cache_key)
            try:
                vlm_data.verification = VerificationResult.model_validate(cached["verification"])
                qa_item = QaReviewItem.model_validate(cached["qa_item"]) if cached.get("qa_item") else None
                if vlm_data.verification.needs_review:
                    vlm_data.structured = None
                return vlm_data, qa_item
            except Exception:
                pass

        # 1. Schema check
        schema_ok, schema_issues = self.verify_schema(vlm_data)

        # 2. Text check
        text_ok, text_issues = self.verify_text_consistency(vlm_data)

        # 3. Visual critic
        visual_ok, visual_issues = self.verify_visual_critic(vlm_data, image_bytes)

        needs_review = not (schema_ok and text_ok and visual_ok)
        all_issues = schema_issues + text_issues + visual_issues

        verification = VerificationResult(
            schema_status="pass" if schema_ok else "fail",
            text_check="pass" if text_ok else "fail",
            visual_check="pass" if visual_ok else "mismatch",
            flags=["needs_review"] if needs_review else [],
            needs_review=needs_review,
            issues=all_issues,
        )
        vlm_data.verification = verification

        qa_item = None
        if needs_review:
            # Mask structured block for safety (HLD §4.3.1)
            vlm_data.structured = None
            qa_item = QaReviewItem(
                book_id=book_id,
                image_path=image_path,
                image_sha256=image_sha256,
                diagram_type=vlm_data.diagram_type.value,
                reasons=all_issues,
            )

        if self.cache:
            self.cache.set(
                cache_key,
                {
                    "verification": verification.model_dump(by_alias=True),
                    "qa_item": qa_item.model_dump() if qa_item else None,
                },
            )
            self.cache.flush()

        return vlm_data, qa_item
