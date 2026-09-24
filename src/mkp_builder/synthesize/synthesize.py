"""Formalized Rule Synthesis Module (REQ-R04)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Literal
from pydantic import ValidationError

from mkp_common.cache import PersistentCache, make_cache_key, compute_sha256_bytes
from mkp_common.rules_schema import (
    Claim,
    Cluster,
    Rule,
    RuleTrigger,
    RuleAction,
    RuleSource,
)
from mkp_builder.vlm.client import OllamaClient

logger = logging.getLogger(__name__)

SYNTHESIZE_PROMPT_TEMPLATE = """You are a rule synthesis engine for maritime safety and sailing operations.

TASK: From a cluster of factual claims, synthesize an operational Rule for a sailing yacht advisory system.

CLUSTER TOPIC: {topic}
DOMINANT TYPE: {dominant_type}
ARCHETYPES: {archetypes}

CLAIMS IN CLUSTER:
{claims_text}

RULES:
1. Output ONLY valid JSON. No preamble, no markdown.
2. Trigger numerical values MUST COME DIRECTLY from the claims text/quotes. DO NOT invent numbers.
3. If claims contradict — document the conflict in "conflicts_with".
4. If only 1 source is present — uncertainty="hypothesis". If multiple sources confirm — uncertainty="verified".
5. Severity mapping:
   - safety + knockdown/broach/capsize/MOB → critical
   - reefing / heavy weather trim → warning
   - general sail trim / informational → info

SCHEMA:
{{
  "reasoning": "Brief explanation of trigger and action deduction (max 300 chars)",
  "rule": {{
    "rule_id": "RULE-...",
    "domain": "safety|trim|reefing|maneuver|predictive",
    "archetype": ["all_monohulls"],
    "triggers": [
      {{
        "ontology_field": "telemetry.true_wind_speed_kt",
        "operator": ">=",
        "value": 20.0,
        "unit": "knots"
      }}
    ],
    "triggers_logic": "ALL",
    "actions": [
      {{
        "action_id": "actions.reef_main_1",
        "params": {{}},
        "description": "Take first reef on mainsail"
      }}
    ],
    "severity": "critical|warning|info",
    "uncertainty": "verified|hypothesis",
    "status": "draft"
  }}
}}

OUTPUT JSON ONLY.
"""


def extract_numbers_from_text(text: str) -> set[float]:
    """Extract all integer and floating point numbers from a text string."""
    nums = set()
    for match in re.finditer(r"\b(\d+(?:\.\d+)?)\b", text):
        try:
            nums.add(float(match.group(1)))
        except ValueError:
            pass
    return nums


class RuleSynthesizer:
    """Synthesizes structured Rules from Claim clusters with strict threshold validation."""

    def __init__(
        self,
        client: OllamaClient,
        cache: PersistentCache | None = None,
        model: str = "qwen2.5:7b",
        prompt_ver: str = "1.0",
    ):
        self.client = client
        self.cache = cache
        self.model = model
        self.prompt_ver = prompt_ver

    def validate_triggers_against_quotes(self, triggers: list[RuleTrigger], allowed_numbers: set[float]) -> bool:
        """Strict verification: ensure all trigger numeric values exist in claim quotes."""
        for t in triggers:
            val = t.value
            if isinstance(val, (int, float)):
                if float(val) not in allowed_numbers:
                    # Allow 0.0 or standard small integers if context permits, but flag unknown thresholds
                    if float(val) not in (0.0, 1.0) and float(val) not in allowed_numbers:
                        logger.warning("Trigger value %s not found in source claims quotes!", val)
                        return False
            elif isinstance(val, list):
                for sub_v in val:
                    if isinstance(sub_v, (int, float)) and float(sub_v) not in allowed_numbers:
                        logger.warning("Trigger list value %s not found in source claims quotes!", sub_v)
                        return False
        return True

    def synthesize_rule_from_cluster(
        self,
        cluster: Cluster,
        claims_map: dict[str, Claim],
        tier: Literal["T1", "T2", "T2.5"] = "T1",
        region: str | None = None,
    ) -> Rule | None:
        """Synthesize a single Rule from a cluster."""
        cluster_claims = [claims_map[cid] for cid in cluster.claims if cid in claims_map]
        if not cluster_claims:
            return None

        # Format claims and collect allowed numbers from quotes
        claims_text_lines = []
        all_quotes_text = []
        sources: list[RuleSource] = []

        for c in cluster_claims:
            claims_text_lines.append(f"- [{c.claim_id}] ({c.type}) {c.text} | Quote: \"{c.source.quote}\"")
            all_quotes_text.append(c.text + " " + c.source.quote)
            sources.append(c.source)

        allowed_numbers = extract_numbers_from_text(" ".join(all_quotes_text))
        claims_text = "\n".join(claims_text_lines)

        cluster_hash = compute_sha256_bytes(claims_text.encode("utf-8"))
        cache_key = make_cache_key(cluster_hash, self.model, f"synthesize_{self.prompt_ver}")

        raw_rule_data: dict[str, Any] = {}

        if self.cache and self.cache.contains(cache_key):
            raw_rule_data = self.cache.get(cache_key) or {}
        else:
            prompt = SYNTHESIZE_PROMPT_TEMPLATE.format(
                topic=cluster.topic,
                dominant_type=cluster.dominant_type,
                archetypes=", ".join(cluster.archetypes),
                claims_text=claims_text,
            )
            try:
                response = self.client.generate(
                    prompt=prompt,
                    model=self.model,
                    format_json=True,
                    num_predict=2048,
                )
                raw_rule_data = json.loads(response)
                if self.cache:
                    self.cache.set(cache_key, raw_rule_data)
                    self.cache.flush()
            except Exception as e:
                logger.warning("Rule synthesis failed for cluster %s: %s", cluster.cluster_id, e)
                return None

        rule_dict = raw_rule_data.get("rule", {})
        if not rule_dict:
            return None

        try:
            # Build triggers
            triggers = [
                RuleTrigger(
                    ontology_field=t.get("ontology_field", "telemetry.true_wind_speed_kt"),
                    operator=t.get("operator", ">="),
                    value=t.get("value", 20.0),
                    unit=t.get("unit", ""),
                )
                for t in rule_dict.get("triggers", [])
            ]

            # Build actions
            actions = [
                RuleAction(
                    action_id=a.get("action_id", "actions.reef_main_1"),
                    params=a.get("params", {}),
                    description=a.get("description", ""),
                )
                for a in rule_dict.get("actions", [])
            ]

            # Validate triggers
            is_valid_triggers = self.validate_triggers_against_quotes(triggers, allowed_numbers)
            status_val = "draft" if is_valid_triggers else "review"
            uncertainty_val = "verified" if len(sources) >= 2 and is_valid_triggers else "hypothesis"

            domain = rule_dict.get("domain", "safety")
            if domain not in ("safety", "trim", "reefing", "maneuver", "predictive"):
                domain = "safety"

            severity = rule_dict.get("severity", "warning")
            if severity not in ("info", "warning", "critical"):
                severity = "warning"

            rule_id = rule_dict.get("rule_id") or f"RULE_{cluster.topic.upper()}_{cluster.cluster_id}"
            if not rule_id.startswith("RULE_"):
                rule_id = f"RULE_{rule_id}"

            rule = Rule(
                rule_id=rule_id,
                domain=domain,
                archetype=rule_dict.get("archetype") or cluster.archetypes or ["all_monohulls"],
                triggers=triggers,
                triggers_logic=rule_dict.get("triggers_logic", "ALL"),
                actions=actions,
                severity=severity,
                uncertainty=uncertainty_val,
                tier=tier,
                region=region,
                origin="base" if tier == "T1" else "user",
                review_mode="manual",
                requires_confirmation=severity == "critical",
                sources=sources,
                conflicts_with=rule_dict.get("conflicts_with", []),
                status=status_val,
                deprecated=False,
                orphaned=False,
            )
            return rule
        except ValidationError as ve:
            logger.warning("Pydantic validation error in synthesized rule: %s", ve)
            return None
        except Exception as e:
            logger.warning("Unexpected error building Rule: %s", e)
            return None

    def synthesize_rules(
        self,
        clusters: list[Cluster],
        claims: list[Claim],
        tier: Literal["T1", "T2", "T2.5"] = "T1",
        region: str | None = None,
        on_progress: Callable[[int, int, Rule | None], None] | None = None,
    ) -> list[Rule]:
        """Synthesize rules for all clusters with real-time progress reporting."""
        claims_map = {c.claim_id: c for c in claims}
        rules: list[Rule] = []
        total_clusters = len(clusters)

        logger.info(
            "Starting rule synthesis for %d clusters from %d claims (tier=%s)",
            total_clusters,
            len(claims),
            tier,
        )

        for idx, cluster in enumerate(clusters, start=1):
            rule = self.synthesize_rule_from_cluster(
                cluster=cluster,
                claims_map=claims_map,
                tier=tier,
                region=region,
            )
            if rule:
                rules.append(rule)

            if on_progress:
                on_progress(idx, total_clusters, rule)

        logger.info("Successfully synthesized %d rules from %d clusters (tier=%s)", len(rules), total_clusters, tier)
        return rules
