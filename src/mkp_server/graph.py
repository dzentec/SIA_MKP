"""Knowledge Graph engine with NetworkX and full provenance (REQ-S06)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
import networkx as nx

from mkp_common.models import TripletRecord

logger = logging.getLogger(__name__)


class KnowledgeGraph:
    """NetworkX MultiDiGraph manager for maritime ontology triplets."""

    def __init__(self):
        self.graph = nx.MultiDiGraph()

    def load_triplets_file(self, file_path: Path | str) -> int:
        """Load TripletRecord items from a jsonl file into the graph."""
        file_p = Path(file_path)
        if not file_p.is_file():
            return 0

        count = 0
        with open(file_p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    triplet = TripletRecord.model_validate(data)
                    self.add_triplet(triplet)
                    count += 1
                except Exception as e:
                    logger.warning("Failed to parse triplet line: %s (%s)", line, e)
        return count

    def add_triplet(self, triplet: TripletRecord) -> None:
        """Add a single TripletRecord to the MultiDiGraph."""
        u = triplet.subject.name
        v = triplet.object.name

        # Node attributes
        if not self.graph.has_node(u):
            self.graph.add_node(u, type=triplet.subject.type, lang=triplet.subject.lang)
        if not self.graph.has_node(v):
            self.graph.add_node(v, type=triplet.object.type, lang=triplet.object.lang)

        # Edge with predicate and provenance
        self.graph.add_edge(
            u,
            v,
            predicate=triplet.predicate,
            provenance=triplet.provenance,
            model=triplet.model,
        )

    def get_related_entities(self, entity_id: str, max_depth: int = 1) -> list[dict[str, Any]]:
        """Find all directly related entities and connecting triplets for a given entity name."""
        entity_clean = entity_id.strip().lower()
        
        # Match node case-insensitively
        matched_node = None
        for node in self.graph.nodes:
            if str(node).strip().lower() == entity_clean:
                matched_node = node
                break

        if not matched_node:
            return []

        results = []
        
        # Outbound edges
        for _, target, edge_data in self.graph.out_edges(matched_node, data=True):
            results.append({
                "subject": matched_node,
                "predicate": edge_data.get("predicate", "related_to"),
                "object": target,
                "provenance": edge_data.get("provenance", {}),
                "direction": "outbound",
            })

        # Inbound edges
        for source, _, edge_data in self.graph.in_edges(matched_node, data=True):
            results.append({
                "subject": source,
                "predicate": edge_data.get("predicate", "related_to"),
                "object": matched_node,
                "provenance": edge_data.get("provenance", {}),
                "direction": "inbound",
            })

        return results
