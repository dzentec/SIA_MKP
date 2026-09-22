"""Atomic Claims Extractor for MKP Rules Pipeline (REQ-R02)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal
from pydantic import ValidationError

from mkp_common.cache import PersistentCache, make_cache_key, compute_sha256_bytes
from mkp_common.models import ChunkRecord
from mkp_common.rules_schema import (
    Claim,
    RuleSource,
    load_ontology,
    load_relations,
    load_mappings,
)
from mkp_builder.vlm.client import OllamaClient

logger = logging.getLogger(__name__)

CLAIMS_PROMPT_TEMPLATE = """You are a precise knowledge extraction engine for sailing literature.

TASK: Extract atomic claims from the provided text chunk.

RULES:
1. Output ONLY valid JSON. No markdown, no explanation, no preamble.
2. Follow the schema exactly. Do not add fields.
3. Each claim must be atomic — one fact, one relationship.
4. Use ontology IDs where possible. If no ID matches, set mapped=false.
5. Include exact source quote (max 200 chars) for each claim.
6. Do not invent numbers. If text says "fresh breeze", extract as-is with type="empirical".
7. type must be one of: "physical", "empirical", "procedural", "normative".

SCHEMA:
{{
  "claims": [
    {{
      "claim_id": "c01",
      "text": "Brief statement of the fact",
      "type": "physical|empirical|procedural|normative",
      "subject": "ontology_id or descriptive subject",
      "predicate": "REQUIRES_ACTION|TRIGGERS_AT|APPLIES_TO_ARCHETYPE|PREVENTS_FAILURE|CAUSES_FAILURE|ASSOCIATED_WITH",
      "object": "target value or action",
      "context": {{"sailing_point": "broad_reach", "wind": "strong"}},
      "quote": "exact quote from text (max 200 chars)",
      "confidence": 0.95,
      "mapped": true
    }}
  ]
}}

ONTOLOGY HINTS:
- Archetypes: ior_classic_narrow_stern, modern_wide_stern_cruiser, performance_monohull, cruising_catamaran, performance_multihull
- Signals: telemetry.true_wind_speed_kt, telemetry.apparent_wind_speed_kt, telemetry.heel_angle_deg, telemetry.rudder_angle_deg
- Actions: actions.reef_main_1, actions.reef_main_2, actions.ease_main_sheet, actions.ease_traveler, actions.bear_away, actions.heave_to
- Failures: failures.broach, failures.knockdown, failures.pitchpole, failures.rudder_stall

SOURCE: {doc_id}, page {page}, chunk {chunk_id}

TEXT:
\"\"\"{text}\"\"\"

Extract all claims. Return JSON only.
"""


class ClaimsExtractor:
    """Extracts atomic factual claims from chunks with ontology linking."""

    def __init__(
        self,
        client: OllamaClient,
        cache: PersistentCache | None = None,
        model: str = "qwen2.5:7b",
        prompt_ver: str = "1.0",
        ontology_dir: str | None = None,
    ):
        self.client = client
        self.cache = cache
        self.model = model
        self.prompt_ver = prompt_ver
        self.ontology = load_ontology(ontology_dir)
        self.relations = load_relations(ontology_dir)
        self.mappings = load_mappings(ontology_dir)
        self._build_mapping_index()

    def _build_mapping_index(self) -> None:
        """Build normalized term-to-ID lookup dictionary."""
        self.term_lookup: dict[str, str] = {}
        for item in self.mappings.get("mappings", []):
            term = item.get("term", "").strip().lower()
            onto_id = item.get("ontology_id", "").strip()
            if term and onto_id:
                self.term_lookup[term] = onto_id

    def map_term(self, raw_term: str) -> tuple[str, bool]:
        """Map raw term to ontology ID if match exists."""
        cleaned = raw_term.strip().lower()
        if cleaned in self.term_lookup:
            return self.term_lookup[cleaned], True
        for term, onto_id in self.term_lookup.items():
            if term in cleaned or cleaned in term:
                return onto_id, True
        return raw_term, False

    def extract_from_chunk(
        self,
        chunk: ChunkRecord,
        tier: Literal["T1", "T2", "T2.5", "T3"] = "T1",
    ) -> list[Claim]:
        """Extract atomic claims from a single chunk."""
        # REQ-R02: Skip claims extraction for T3: Personal
        if tier == "T3":
            return []

        text = chunk.text_content.strip()
        if not text or len(text) < 30:
            return []

        text_sha = compute_sha256_bytes(text.encode("utf-8"))
        cache_key = make_cache_key(text_sha, self.model, f"claims_{self.prompt_ver}")

        raw_claims: list[dict[str, Any]] = []

        if self.cache and self.cache.contains(cache_key):
            raw_claims = self.cache.get(cache_key) or []
        else:
            prompt = CLAIMS_PROMPT_TEMPLATE.format(
                doc_id=chunk.book_id,
                page=chunk.page_number,
                chunk_id=chunk.chunk_id,
                text=text,
            )
            try:
                response = self.client.generate(
                    prompt=prompt,
                    model=self.model,
                    format_json=True,
                    num_predict=2048,
                )
                data = json.loads(response)
                raw_claims = data.get("claims", [])
                if self.cache:
                    self.cache.set(cache_key, raw_claims)
                    self.cache.flush()
            except Exception as e:
                logger.warning("Claims extraction failed for %s: %s", chunk.chunk_id, e)
                return []

        claims_list: list[Claim] = []
        for idx, item in enumerate(raw_claims, start=1):
            try:
                cid = f"{chunk.chunk_id}_cl{idx:02d}"
                raw_quote = str(item.get("quote", "")).strip()
                if not raw_quote:
                    # fallback quote from text
                    raw_quote = text[:150]
                quote = raw_quote[:200]

                raw_subj = str(item.get("subject", ""))
                mapped_subj, is_mapped = self.map_term(raw_subj)

                claim_type = item.get("type", "empirical")
                if claim_type not in ("physical", "empirical", "procedural", "normative"):
                    claim_type = "empirical"

                predicate = str(item.get("predicate", "ASSOCIATED_WITH")).upper().replace(" ", "_")

                src = RuleSource(
                    doc_id=chunk.book_id,
                    page=chunk.page_number,
                    chunk_id=chunk.chunk_id,
                    quote=quote,
                )

                claim = Claim(
                    claim_id=cid,
                    text=str(item.get("text", "")).strip() or quote,
                    type=claim_type,
                    subject=mapped_subj,
                    predicate=predicate,
                    object=item.get("object", ""),
                    context=item.get("context", {}) if isinstance(item.get("context"), dict) else {},
                    source=src,
                    confidence=float(item.get("confidence", 0.9)),
                    mapped=is_mapped or bool(item.get("mapped", False)),
                    tier=tier,
                )
                claims_list.append(claim)
            except ValidationError as ve:
                logger.debug("Claim validation error: %s", ve)
            except Exception as e:
                logger.debug("Failed parsing claim item: %s (%s)", item, e)

        return claims_list

    def extract_from_chunks(
        self,
        chunks: list[ChunkRecord],
        tier: Literal["T1", "T2", "T2.5", "T3"] = "T1",
    ) -> list[Claim]:
        """Extract claims across all document chunks."""
        all_claims: list[Claim] = []
        for chunk in chunks:
            claims = self.extract_from_chunk(chunk, tier=tier)
            all_claims.extend(claims)
        logger.info("Extracted %d claims from %d chunks (tier=%s)", len(all_claims), len(chunks), tier)
        return all_claims
