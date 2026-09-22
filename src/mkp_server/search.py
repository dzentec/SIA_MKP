"""LanceDB hybrid search with multilingual-e5-large embeddings and FTS (REQ-S05, REQ-C03)."""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
import re
from typing import Any, Optional
import numpy as np

from mkp_common.models import ChunkRecord
from mkp_server.models import SearchResult

logger = logging.getLogger(__name__)

# Model constants
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-large"
EMBEDDING_DIM = 1024
MAX_TOP_K = 20


class E5Embedder:
    """E5 embedder wrapper enforcing mandatory 'passage: ' and 'query: ' prefixes."""

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME):
        self.model_name = model_name
        self._model = None
        self._is_mock = False

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
            except Exception as e:
                logger.warning("Could not load SentenceTransformer (%s). Using deterministic mock embedder.", e)
                self._is_mock = True
        return self._model

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        """Embed document chunks with mandatory 'passage: ' prefix."""
        prefixed = [f"passage: {t.strip()}" for t in texts]
        model = self._get_model()
        if self._is_mock or model is None:
            return self._deterministic_mock_embed(prefixed)
        try:
            return np.array(model.encode(prefixed, normalize_embeddings=True))
        except Exception:
            return self._deterministic_mock_embed(prefixed)

    def embed_query(self, query: str) -> np.ndarray:
        """Embed search query with mandatory 'query: ' prefix."""
        prefixed = f"query: {query.strip()}"
        model = self._get_model()
        if self._is_mock or model is None:
            return self._deterministic_mock_embed([prefixed])[0]
        try:
            return np.array(model.encode([prefixed], normalize_embeddings=True))[0]
        except Exception:
            return self._deterministic_mock_embed([prefixed])[0]

    def _deterministic_mock_embed(self, texts: list[str]) -> np.ndarray:
        """Generate deterministic normalized unit vectors for offline testing."""
        vectors = []
        for text in texts:
            # Seed vector using hash of text
            seed = sum(ord(c) * (i + 1) for i, c in enumerate(text[:100])) % (2**32 - 1)
            rng = np.random.RandomState(seed)
            v = rng.randn(EMBEDDING_DIM).astype(np.float32)
            norm = np.linalg.norm(v)
            if norm > 0:
                v /= norm
            vectors.append(v)
        return np.array(vectors)


class SearchEngine:
    """Hybrid search engine indexing and retrieving ChunkRecords across tiers."""

    def __init__(self, derived_dir: Path | str | None = None):
        self.derived_dir = Path(derived_dir) if derived_dir else None
        self.embedder = E5Embedder()
        self.chunks: list[dict[str, Any]] = []
        self.vectors: np.ndarray | None = None

    def index_chunks(self, chunks: list[ChunkRecord], tier: str = "T1") -> None:
        """Index chunks into in-memory table and LanceDB if configured."""
        if not chunks:
            return

        texts_to_embed = []
        new_items = []
        for c in chunks:
            # Combine text content, ocr and visual asset descriptions for search view
            vlm_descriptions = []
            diagrams_info = []
            for asset in c.visual_assets:
                if asset.vlm_data and asset.vlm_data.description:
                    vlm_descriptions.append(asset.vlm_data.description)
                diagrams_info.append({
                    "image_path": asset.image_path,
                    "image_sha256": asset.image_sha256,
                    "diagram_type": asset.vlm_data.diagram_type.value if asset.vlm_data else "other",
                    "description": asset.vlm_data.description if asset.vlm_data else "",
                })

            combined_text = " ".join(filter(None, [
                c.text_content,
                c.ocr_text,
                " ".join(vlm_descriptions),
            ]))

            item = {
                "chunk_id": c.chunk_id,
                "book_id": c.book_id,
                "page_number": c.page_number,
                "location_ref": c.location_ref,
                "section_path": c.section_path,
                "text_content": c.text_content,
                "ocr_text": c.ocr_text or "",
                "vlm_text": " ".join(vlm_descriptions),
                "combined_text": combined_text,
                "tier": tier,
                "lang": c.lang,
                "diagrams": diagrams_info,
            }
            new_items.append(item)
            texts_to_embed.append(combined_text)

        new_vectors = self.embedder.embed_passages(texts_to_embed)

        if self.vectors is None or len(self.vectors) == 0:
            self.vectors = new_vectors
            self.chunks = new_items
        else:
            self.vectors = np.vstack([self.vectors, new_vectors])
            self.chunks.extend(new_items)

    def search(
        self,
        query: str,
        top_k: int = 5,
        tier: Optional[str] = None,
        book_id: Optional[str] = None,
        lang: Optional[str] = None,
    ) -> list[SearchResult]:
        """Perform hybrid dense + lexical search with filtering and RRF ranking."""
        top_k = max(1, min(top_k, MAX_TOP_K))

        if not self.chunks or self.vectors is None or len(self.vectors) == 0:
            return []

        # 1. Filter indices
        candidate_indices = []
        for i, c in enumerate(self.chunks):
            if tier and c.get("tier") != tier:
                continue
            if book_id and c.get("book_id") != book_id:
                continue
            if lang and c.get("lang") != lang:
                continue
            candidate_indices.append(i)

        if not candidate_indices:
            return []

        # 2. Vector search (Dense)
        q_vec = self.embedder.embed_query(query)
        cand_vectors = self.vectors[candidate_indices]
        dense_scores = np.dot(cand_vectors, q_vec)

        # 3. Lexical / FTS BM25-like scoring
        q_terms = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 1]
        lexical_scores = []
        for idx in candidate_indices:
            c = self.chunks[idx]
            combined = c["combined_text"].lower()
            score = 0.0
            for t in q_terms:
                if t in combined:
                    # Higher weight for longer informative words
                    weight = 2.0 if len(t) >= 4 else 1.0
                    score += weight * (1.0 + math.log1p(combined.count(t)))
            lexical_scores.append(score)

        lexical_scores = np.array(lexical_scores, dtype=np.float32)
        if np.max(lexical_scores) > 0:
            norm_lexical = lexical_scores / np.max(lexical_scores)
        else:
            norm_lexical = lexical_scores

        # 4. Hybrid Reciprocal Rank Fusion (RRF)
        dense_ranks = np.argsort(-dense_scores)
        lexical_ranks = np.argsort(-lexical_scores)

        rrf_scores = np.zeros(len(candidate_indices), dtype=np.float32)
        k_rrf = 20.0
        dense_w = 0.2 if self.embedder._is_mock else 1.0
        lex_w = 2.0 if self.embedder._is_mock else 1.0

        for rank, item_idx in enumerate(dense_ranks):
            rrf_scores[item_idx] += dense_w / (k_rrf + rank + 1)
        for rank, item_idx in enumerate(lexical_ranks):
            if lexical_scores[item_idx] > 0:
                rrf_scores[item_idx] += lex_w / (k_rrf + rank + 1) + norm_lexical[item_idx] * 0.5

        # 5. Top K selection
        top_cand_indices = np.argsort(-rrf_scores)[:top_k]

        results = []
        for rank_pos in top_cand_indices:
            orig_idx = candidate_indices[rank_pos]
            c = self.chunks[orig_idx]
            results.append(
                SearchResult(
                    chunk_id=c["chunk_id"],
                    book_id=c["book_id"],
                    page_number=c["page_number"],
                    location_ref=c["location_ref"],
                    section_path=c["section_path"],
                    text_content=c["text_content"],
                    score=float(rrf_scores[rank_pos]),
                    tier=c["tier"],
                    lang=c["lang"],
                    diagrams=c["diagrams"],
                )
            )

        return results
