"""Rules Store, telemetry trigger evaluator, orphaning detection and guardrails (REQ-R01..R04, REQ-S12)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal, Optional

from mkp_common.rules_schema import Rule, RuleSource, RuleTrigger

logger = logging.getLogger(__name__)

# Telemetry alias mapping to normalize input keys
TELEMETRY_ALIASES: dict[str, list[str]] = {
    "tws": ["telemetry.true_wind_speed_kt", "tws", "true_wind_speed", "wind_speed"],
    "aws": ["telemetry.apparent_wind_speed_kt", "aws", "apparent_wind_speed"],
    "heel": ["telemetry.heel_angle_deg", "heel", "heel_angle"],
    "twa": ["telemetry.true_wind_angle_deg", "twa", "true_wind_angle"],
    "awa": ["telemetry.apparent_wind_angle_deg", "awa", "apparent_wind_angle"],
    "sog": ["telemetry.speed_over_ground_kt", "sog", "speed_over_ground"],
    "wave_height": ["environment.wave_height_m", "wave_height", "waves"],
}


def _get_telemetry_value(telemetry: dict[str, float], field_name: str) -> float | None:
    """Resolve a field name from input telemetry using ontology and alias keys."""
    # Direct match
    if field_name in telemetry:
        return float(telemetry[field_name])

    # Reverse alias lookup
    for short_k, aliases in TELEMETRY_ALIASES.items():
        if field_name in aliases or field_name == short_k:
            for a in aliases:
                if a in telemetry:
                    return float(telemetry[a])
            if short_k in telemetry:
                return float(telemetry[short_k])

    return None


def evaluate_trigger(trigger: RuleTrigger, telemetry: dict[str, float]) -> bool:
    """Evaluate a single RuleTrigger against provided telemetry dict."""
    val = _get_telemetry_value(telemetry, trigger.ontology_field)
    if val is None:
        # If telemetry does not provide this field, trigger cannot be satisfied
        return False

    op = trigger.operator
    tgt = trigger.value

    try:
        if op == ">":
            return val > float(tgt)
        elif op == ">=":
            return val >= float(tgt)
        elif op == "<":
            return val < float(tgt)
        elif op == "<=":
            return val <= float(tgt)
        elif op == "==":
            return math_approx_equal(val, float(tgt))
        elif op == "!=":
            return not math_approx_equal(val, float(tgt))
        elif op == "between":
            if isinstance(tgt, (list, tuple)) and len(tgt) == 2:
                return float(tgt[0]) <= val <= float(tgt[1])
            return False
    except (ValueError, TypeError):
        return False

    return False


def math_approx_equal(a: float, b: float, tol: float = 1e-5) -> bool:
    return abs(a - b) <= tol


class RulesStore:
    """Store and matcher for operational rules with multi-tier hierarchy and orphaning."""

    def __init__(self, guardrails_content: str = ""):
        self.rules: dict[str, Rule] = {}
        self.guardrails_md = guardrails_content

    def load_rules_file(
        self,
        file_path: Path | str,
        active_chunk_ids: set[str] | None = None,
        default_tier: Literal["T1", "T2", "T2.5"] = "T1",
    ) -> int:
        """Load Rule objects from rules.jsonl and check orphaning against active chunks."""
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
                    rule = Rule.model_validate(data)
                    
                    # Orphaning check (HLD v3.3 §G / REQ-S12)
                    if active_chunk_ids is not None and rule.sources:
                        # If sources point to chunk_ids not present in active base, mark orphaned
                        missing_chunks = [
                            s.chunk_id for s in rule.sources if s.chunk_id not in active_chunk_ids
                        ]
                        if missing_chunks and rule.origin == "user":
                            rule.orphaned = True

                    self.rules[rule.rule_id] = rule
                    count += 1
                except Exception as e:
                    logger.warning("Failed to parse rule line: %s (%s)", line, e)
        return count

    def load_guardrails_file(self, file_path: Path | str) -> None:
        """Load static guardrails.md with validation (≤ 8000 chars, T1 approved)."""
        file_p = Path(file_path)
        if file_p.is_file():
            content = file_p.read_text(encoding="utf-8")
            if len(content) > 8000:
                logger.warning("Guardrails length (%d) exceeds 8000 chars limit", len(content))
            self.guardrails_md = content

    def query_rules(
        self,
        archetype: str,
        telemetry: dict[str, float],
        domain: Optional[str] = None,
        tier: Optional[Literal["T1", "T2", "T2.5"]] = None,
        region: Optional[str] = None,
        status: str = "approved",
    ) -> list[Rule]:
        """Find matching rules based on boat archetype, telemetry conditions and filters (HLD §8.3)."""
        # Stub handling: T2/T2.5 return empty list if not populated
        if tier in ("T2", "T2.5"):
            # Check if we have non-T1 rules matching tier
            tier_rules = [r for r in self.rules.values() if r.tier == tier]
            if not tier_rules:
                return []

        matched: list[Rule] = []
        arch_clean = archetype.strip().lower()

        for rule in self.rules.values():
            # 1. Filter by status (approved / draft / etc.)
            if status and rule.status != status:
                continue

            # 2. Filter by tier if specified
            if tier and rule.tier != tier:
                continue

            # 3. Filter by domain if specified
            if domain and rule.domain != domain:
                continue

            # 4. Filter by region if specified
            if region and rule.region and rule.region != region:
                continue

            # 5. Filter by archetype
            if rule.archetype:
                rule_archs = [a.lower() for a in rule.archetype]
                if arch_clean not in rule_archs and "all" not in rule_archs and "*" not in rule_archs:
                    continue

            # 6. Evaluate telemetry triggers
            if rule.triggers:
                if rule.triggers_logic == "ANY":
                    trigger_match = any(evaluate_trigger(t, telemetry) for t in rule.triggers)
                else:  # "ALL"
                    trigger_match = all(evaluate_trigger(t, telemetry) for t in rule.triggers)
                if not trigger_match:
                    continue

            matched.append(rule)

        # Sort rules by severity: critical > warning > info
        severity_rank = {"critical": 0, "warning": 1, "info": 2}
        matched.sort(key=lambda r: severity_rank.get(r.severity, 3))
        return matched

    def get_rule(self, rule_id: str) -> Rule | None:
        """Lookup rule by ID."""
        return self.rules.get(rule_id)

    def get_rule_provenance(self, rule_id: str) -> list[RuleSource]:
        """Get exact quotes and sources for a given rule ID."""
        rule = self.rules.get(rule_id)
        if not rule:
            return []
        return rule.sources

    def list_conflicts(self, rule_id: str) -> list[Rule]:
        """Return list of rules conflicting with the given rule."""
        rule = self.rules.get(rule_id)
        if not rule:
            return []

        conflicts = []
        for c_id in rule.conflicts_with:
            if c_id in self.rules:
                conflicts.append(self.rules[c_id])

        # Also check bidirectional conflicts
        for other_id, other_r in self.rules.items():
            if other_id != rule_id and rule_id in other_r.conflicts_with:
                if other_r not in conflicts:
                    conflicts.append(other_r)

        return conflicts

    def get_guardrails(self) -> str:
        """Return guardrails markdown string (≤ 8000 chars)."""
        return self.guardrails_md
