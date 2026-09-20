"""Knowledge Graph Triplet Extractor for GraphRAG (REQ-B06)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from pydantic import BaseModel, Field

from mkp_common.cache import PersistentCache, make_cache_key, compute_sha256_bytes
from mkp_common.models import TripletRecord, EntityNode, ChunkRecord
from mkp_builder.vlm.client import OllamaClient

logger = logging.getLogger(__name__)

ENTITY_TYPES = {
    "Парус",
    "Снасть",
    "Манёвр",
    "ВетровойРежим",
    "Узел",
    "Опасность",
    "Sail",
    "Rigging",
    "Maneuver",
    "WindRegime",
    "Knot",
    "Danger",
}

RELATION_TYPES = {
    "УПРАВЛЯЕТСЯ_С_ПОМОЩЬЮ",
    "ТРЕБУЕТ_ДЕЙСТВИЯ",
    "ПРИМЕНЯЕТСЯ_ПРИ",
    "СВЯЗАН_С",
    "CONTROLLED_BY",
    "REQUIRES_ACTION",
    "USED_IN",
    "RELATED_TO",
}

TRIPLET_PROMPT_V2 = """You are a maritime knowledge graph extractor. Extract maritime entities and relationships from the text below.
Taxonomy of Entity Types:
- Sail / Парус (e.g. mainsail, jib, spinnaker, грот, стаксель)
- Rigging / Снасть (e.g. mainsheet, halyard, vang, гика-шкот, фал, оттяжка)
- Maneuver / Манёвр (e.g. tacking, gybing, reefing, поворот оверштаг, фордевинд, рифление)
- WindRegime / ВетровойРежим (e.g. close-hauled, beam reach, gale, бейдевинд, шторм)
- Knot / Узел (e.g. bowline, clove hitch, беседочный, выбленочный)
- Danger / Опасность (e.g. broach, capsize, gybe risk, брочинг, оверкиль)

Taxonomy of Relation Types:
- CONTROLLED_BY / УПРАВЛЯЕТСЯ_С_ПОМОЩЬЮ
- REQUIRES_ACTION / ТРЕБУЕТ_ДЕЙСТВИЯ
- USED_IN / ПРИМЕНЯЕТСЯ_ПРИ
- RELATED_TO / СВЯЗАН_С

Text chunk:
\"\"\"{text}\"\"\"

Return a JSON object with this schema:
{{
  "triplets": [
    {{
      "subject": {{"name": "...", "type": "Sail|Rigging|Maneuver|WindRegime|Knot|Danger", "lang": "en|ru"}},
      "predicate": "CONTROLLED_BY|REQUIRES_ACTION|USED_IN|RELATED_TO|УПРАВЛЯЕТСЯ_С_ПОМОЩЬЮ|ТРЕБУЕТ_ДЕЙСТВИЯ|ПРИМЕНЯЕТСЯ_ПРИ|СВЯЗАН_С",
      "object": {{"name": "...", "type": "Sail|Rigging|Maneuver|WindRegime|Knot|Danger", "lang": "en|ru"}}
    }}
  ]
}}
If no relevant maritime triplets are found, return {{"triplets": []}}.
Return ONLY valid JSON."""


def normalize_entity_name(name: str) -> str:
    """Canonicalize entity name: strip, lowercase, collapse whitespaces."""
    cleaned = re.sub(r"\s+", " ", name.strip().lower())
    return cleaned


def normalize_predicate(pred: str) -> str:
    """Normalize relation predicate to canonical uppercase form."""
    raw = pred.strip().upper().replace(" ", "_")
    mapping = {
        "CONTROLLED_BY": "УПРАВЛЯЕТСЯ_С_ПОМОЩЬЮ",
        "REQUIRES_ACTION": "ТРЕБУЕТ_ДЕЙСТВИЯ",
        "USED_IN": "ПРИМЕНЯЕТСЯ_ПРИ",
        "RELATED_TO": "СВЯЗАН_С",
    }
    return mapping.get(raw, raw)


class TripletExtractor:
    """Extracts, normalizes and deduplicates knowledge triplets from text chunks."""

    def __init__(
        self,
        client: OllamaClient,
        cache: PersistentCache | None = None,
        model: str = "qwen2.5:7b",
        prompt_ver: str = "2.0",
    ):
        self.client = client
        self.cache = cache
        self.model = model
        self.prompt_ver = prompt_ver

    def extract_from_text(
        self,
        text: str,
        chunk_id: str,
        book_id: str,
        page_number: int,
        location_ref: str,
    ) -> list[TripletRecord]:
        """Extract triplets from a text string with provenance."""
        if not text.strip() or len(text.strip()) < 30:
            return []

        text_sha = compute_sha256_bytes(text.encode("utf-8"))
        cache_key = make_cache_key(text_sha, self.model, f"triplets_{self.prompt_ver}")

        raw_triplets: list[dict[str, Any]] = []

        if self.cache and self.cache.contains(cache_key):
            raw_triplets = self.cache.get(cache_key) or []
        else:
            try:
                prompt = TRIPLET_PROMPT_V2.format(text=text)
                response = self.client.generate(
                    prompt=prompt,
                    model=self.model,
                    format_json=True,
                    num_predict=512,
                )
                data = json.loads(response)
                raw_triplets = data.get("triplets", [])
                if self.cache:
                    self.cache.set(cache_key, raw_triplets)
                    self.cache.flush()
            except Exception as e:
                logger.warning("Triplet extraction failed for chunk %s: %s", chunk_id, e)
                return []

        # Normalize and build TripletRecords
        provenance = {
            "book_id": book_id,
            "page_number": page_number,
            "chunk_id": chunk_id,
            "location_ref": location_ref,
        }

        results: list[TripletRecord] = []
        seen_keys = set()

        for item in raw_triplets:
            try:
                sub_dict = item.get("subject", {})
                obj_dict = item.get("object", {})
                pred_raw = item.get("predicate", "СВЯЗАН_С")

                sub_name = normalize_entity_name(sub_dict.get("name", ""))
                obj_name = normalize_entity_name(obj_dict.get("name", ""))
                predicate = normalize_predicate(pred_raw)

                if not sub_name or not obj_name:
                    continue

                # Deduplication key within chunk
                dedup_key = (sub_name, predicate, obj_name)
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                sub_node = EntityNode(
                    name=sub_name,
                    type=sub_dict.get("type", "Other"),
                    lang=sub_dict.get("lang", "en"),
                )
                obj_node = EntityNode(
                    name=obj_name,
                    type=obj_dict.get("type", "Other"),
                    lang=obj_dict.get("lang", "en"),
                )

                rec = TripletRecord(
                    subject=sub_node,
                    predicate=predicate,
                    object=obj_node,
                    provenance=provenance,
                    model=self.model,
                    prompt_ver=self.prompt_ver,
                )
                results.append(rec)
            except Exception as e:
                logger.debug("Skipping malformed triplet: %s (%s)", item, e)

        return results

    def extract_from_chunks(self, chunks: list[ChunkRecord]) -> list[TripletRecord]:
        """Extract triplets across a list of chunks with overall deduplication."""
        all_triplets: list[TripletRecord] = []
        seen_global = set()

        for chunk in chunks:
            chunk_triplets = self.extract_from_text(
                text=chunk.text_content,
                chunk_id=chunk.chunk_id,
                book_id=chunk.book_id,
                page_number=chunk.page_number,
                location_ref=chunk.location_ref,
            )
            for t in chunk_triplets:
                # Global deduplication key (subject, predicate, object, chunk_id)
                g_key = (t.subject.name, t.predicate, t.object.name, t.provenance.get("chunk_id"))
                if g_key not in seen_global:
                    seen_global.add(g_key)
                    all_triplets.append(t)

        logger.info("Extracted %d triplets from %d chunks", len(all_triplets), len(chunks))
        return all_triplets
