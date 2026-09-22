"""Claims Clustering Module (REQ-R03)."""

from __future__ import annotations

from collections import defaultdict
import logging
import re
from typing import Any, Literal

from mkp_common.rules_schema import Claim, Cluster

logger = logging.getLogger(__name__)


def infer_domain(topic: str, text: str) -> str:
    """Infer rule domain from topic and text content."""
    combined = (topic + " " + text).lower()
    if any(k in combined for k in ("reef", "риф", "ветр", "tws", "knots", "узл")):
        return "reefing"
    if any(k in combined for k in ("broach", "knockdown", "mob", "overboard", "danger", "опасн", "авар", "безопасн")):
        return "safety"
    if any(k in combined for k in ("trim", "sheet", "vang", "traveler", "шкот", "настройк", "пузо")):
        return "trim"
    if any(k in combined for k in ("tack", "gybe", "maneuver", "поворот", "манёвр", "привод", "увал")):
        return "maneuver"
    return "safety"


class ClaimsClusterer:
    """Groups claims by domain, archetype, and signals, detecting contradictions."""

    def __init__(self, book_id: str = "book"):
        self.book_id = book_id

    def cluster_claims(
        self,
        claims: list[Claim],
        tier: Literal["T1", "T2", "T2.5"] = "T1",
    ) -> list[Cluster]:
        """Group claims into coherent clusters for rule synthesis."""
        if not claims:
            return []

        # Group by topic / normalized subject
        groups: dict[str, list[Claim]] = defaultdict(list)

        for c in claims:
            # normalize subject to topic key
            subj = c.subject.lower()
            if "." in subj:
                topic_key = subj.split(".")[-1]
            else:
                topic_key = re.sub(r"[^\w\s-]", "", subj).strip() or "general"
            groups[topic_key].append(c)

        clusters: list[Cluster] = []
        cluster_idx = 1

        for topic, group_claims in groups.items():
            claim_ids = [c.claim_id for c in group_claims]
            archetypes_set = set()
            types_count: dict[str, int] = defaultdict(int)

            for c in group_claims:
                types_count[c.type] += 1
                ctx_arch = c.context.get("archetype")
                if ctx_arch:
                    if isinstance(ctx_arch, list):
                        archetypes_set.update(ctx_arch)
                    else:
                        archetypes_set.add(str(ctx_arch))

            dominant_type = max(types_count.items(), key=lambda x: x[1])[0] if types_count else "empirical"

            # Contradiction detection: check for contrasting actions / values on similar signals
            contradictions: list[dict[str, Any]] = []
            if len(group_claims) >= 2:
                for i in range(len(group_claims)):
                    for j in range(i + 1, len(group_claims)):
                        c1, c2 = group_claims[i], group_claims[j]
                        if c1.predicate != c2.predicate and c1.object != c2.object and c1.source.chunk_id != c2.source.chunk_id:
                            # Possible nuance or contradiction
                            contradictions.append({
                                "claim1": c1.claim_id,
                                "claim2": c2.claim_id,
                                "reason": f"Different recommendations: '{c1.text}' vs '{c2.text}'"
                            })

            cluster = Cluster(
                cluster_id=f"clst_{self.book_id}_{cluster_idx:03d}",
                topic=topic,
                claims=claim_ids,
                dominant_type=dominant_type,
                archetypes=list(archetypes_set) or ["all_monohulls"],
                contradictions=contradictions,
                coverage=min(1.0, len(claim_ids) / 5.0),
                tier=tier,
            )
            clusters.append(cluster)
            cluster_idx += 1

        logger.info("Clustered %d claims into %d clusters", len(claims), len(clusters))
        return clusters
