"""Rule Review and Golden Rules Dataset Module (REQ-R06, REQ-QA-01)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from mkp_common.rules_schema import Rule, RuleSource, RuleTrigger, RuleAction

logger = logging.getLogger(__name__)


def generate_golden_t1_rules(book_id: str = "dedekam_seamanship") -> list[Rule]:
    """Seed verified 15+ Golden Rules for T1 Base knowledge."""
    rules_data = [
        {
            "rule_id": "RULE_SAFETY_001_HEEL_LIMIT",
            "domain": "safety",
            "archetype": ["ior_classic_narrow_stern", "modern_wide_stern_cruiser", "performance_monohull"],
            "triggers": [
                {"ontology_field": "telemetry.heel_angle_deg", "operator": ">=", "value": 20.0, "unit": "deg"}
            ],
            "triggers_logic": "ALL",
            "actions": [
                {"action_id": "actions.ease_traveler", "description": "Ease traveler down to leeward to de-power mainsail"},
                {"action_id": "actions.ease_main_sheet", "description": "Ease main sheet if heel continues above 20 deg"}
            ],
            "severity": "warning",
            "uncertainty": "verified",
            "tier": "T1",
            "quote": "When the heel exceeds 20 degrees, rudder drag increases sharply and the yacht is prone to broaching.",
            "page": 14,
        },
        {
            "rule_id": "RULE_REEF_001_FIRST_REEF",
            "domain": "reefing",
            "archetype": ["all_monohulls"],
            "triggers": [
                {"ontology_field": "telemetry.true_wind_speed_kt", "operator": ">=", "value": 18.0, "unit": "knots"}
            ],
            "triggers_logic": "ALL",
            "actions": [
                {"action_id": "actions.reef_main_1", "description": "Take first reef in mainsail before excessive heel occurs"}
            ],
            "severity": "warning",
            "uncertainty": "verified",
            "tier": "T1",
            "quote": "First reef should be taken when true wind speed reaches 18 knots in upwind sailing.",
            "page": 22,
        },
        {
            "rule_id": "RULE_REEF_002_SECOND_REEF",
            "domain": "reefing",
            "archetype": ["all_monohulls"],
            "triggers": [
                {"ontology_field": "telemetry.true_wind_speed_kt", "operator": ">=", "value": 22.0, "unit": "knots"}
            ],
            "triggers_logic": "ALL",
            "actions": [
                {"action_id": "actions.reef_main_2", "description": "Take second reef in mainsail and partially furl headsail"}
            ],
            "severity": "warning",
            "uncertainty": "verified",
            "tier": "T1",
            "quote": "At 22-25 knots of true wind, take the second reef to maintain control and speed.",
            "page": 23,
        },
        {
            "rule_id": "RULE_REEF_003_THIRD_REEF",
            "domain": "reefing",
            "archetype": ["all_monohulls"],
            "triggers": [
                {"ontology_field": "telemetry.true_wind_speed_kt", "operator": ">=", "value": 28.0, "unit": "knots"}
            ],
            "triggers_logic": "ALL",
            "actions": [
                {"action_id": "actions.reef_main_3", "description": "Take third reef or set storm trysail and storm jib"}
            ],
            "severity": "critical",
            "uncertainty": "verified",
            "tier": "T1",
            "quote": "In gale conditions exceeding 28 knots, reduce to third reef or storm canvas.",
            "page": 25,
        },
        {
            "rule_id": "RULE_SAFETY_002_BROACH_PREVENTION",
            "domain": "safety",
            "archetype": ["ior_classic_narrow_stern", "modern_wide_stern_cruiser"],
            "triggers": [
                {"ontology_field": "telemetry.heel_angle_deg", "operator": ">=", "value": 22.0, "unit": "deg"},
                {"ontology_field": "telemetry.rudder_angle_deg", "operator": ">=", "value": 15.0, "unit": "deg"}
            ],
            "triggers_logic": "ALL",
            "actions": [
                {"action_id": "actions.ease_vang", "description": "Release boom vang immediately to spill air from mainsail top"},
                {"action_id": "actions.ease_main_sheet", "description": "Dump mainsheet to prevent broach"}
            ],
            "severity": "critical",
            "uncertainty": "verified",
            "tier": "T1",
            "quote": "If heeled past 22 degrees with heavy weather helm over 15 degrees, blow the vang and mainsheet to stop the broach.",
            "page": 31,
        },
        {
            "rule_id": "RULE_SAFETY_003_RUDDER_STALL",
            "domain": "safety",
            "archetype": ["all_monohulls"],
            "triggers": [
                {"ontology_field": "telemetry.rudder_angle_deg", "operator": ">=", "value": 20.0, "unit": "deg"}
            ],
            "triggers_logic": "ALL",
            "actions": [
                {"action_id": "actions.ease_main_sheet", "description": "Reduce heeling moment and weather helm; rudder stalls above 20 deg angle"}
            ],
            "severity": "warning",
            "uncertainty": "verified",
            "tier": "T1",
            "quote": "Rudder blade loses laminar flow and stalls when turned beyond 20 degrees.",
            "page": 16,
        },
        {
            "rule_id": "RULE_MANEUVER_001_PREVENTER_RUNNING",
            "domain": "maneuver",
            "archetype": ["all_monohulls", "cruising_catamaran"],
            "triggers": [
                {"ontology_field": "telemetry.true_wind_angle_deg", "operator": ">=", "value": 150.0, "unit": "deg"}
            ],
            "triggers_logic": "ALL",
            "actions": [
                {"action_id": "actions.rig_boom_preventer", "description": "Rig a dedicated boom preventer line from boom end to bow forward cleat"}
            ],
            "severity": "critical",
            "uncertainty": "verified",
            "tier": "T1",
            "quote": "On deep broad reaches and runs beyond 150 degrees TWA, a boom preventer is mandatory to stop accidental gybes.",
            "page": 44,
        },
        {
            "rule_id": "RULE_SAFETY_004_KNOCKDOWN_RECOVERY",
            "domain": "safety",
            "archetype": ["all_monohulls"],
            "triggers": [
                {"ontology_field": "telemetry.heel_angle_deg", "operator": ">=", "value": 60.0, "unit": "deg"}
            ],
            "triggers_logic": "ALL",
            "actions": [
                {"action_id": "actions.release_all_sheets", "description": "Release all running rigging and sheets; ensure companionway hatch is closed"}
            ],
            "severity": "critical",
            "uncertainty": "verified",
            "tier": "T1",
            "quote": "In a severe knockdown, immediately free sheets and ensure companionway washboards are secured.",
            "page": 58,
        },
        {
            "rule_id": "RULE_SAFETY_005_MOB_PROCEDURE",
            "domain": "safety",
            "archetype": ["all_vessels"],
            "triggers": [
                {"ontology_field": "failures.man_overboard", "operator": "==", "value": "active", "unit": ""}
            ],
            "triggers_logic": "ALL",
            "actions": [
                {"action_id": "actions.deploy_danbuoy", "description": "Throw lifebuoy and Danbuoy immediately to victim"},
                {"action_id": "actions.press_gps_mob", "description": "Press MOB button on chartplotter/GPS and assign dedicated lookout"}
            ],
            "severity": "critical",
            "uncertainty": "verified",
            "tier": "T1",
            "quote": "Shout Man Overboard, throw buoyant marker instantly and press the GPS MOB button.",
            "page": 62,
        },
        {
            "rule_id": "RULE_SAFETY_006_HEAVE_TO_HEAVY_WEATHER",
            "domain": "safety",
            "archetype": ["all_monohulls"],
            "triggers": [
                {"ontology_field": "telemetry.true_wind_speed_kt", "operator": ">=", "value": 35.0, "unit": "knots"}
            ],
            "triggers_logic": "ALL",
            "actions": [
                {"action_id": "actions.heave_to", "description": "Back the jib, lash helm to windward, ease main to heave-to in storm conditions"}
            ],
            "severity": "critical",
            "uncertainty": "verified",
            "tier": "T1",
            "quote": "When true wind exceeds 35 knots, heaving-to creates a slick to windward that calms breaking crests.",
            "page": 70,
        },
        {
            "rule_id": "RULE_SAFETY_007_CATAMARAN_HEEL_LIMIT",
            "domain": "safety",
            "archetype": ["cruising_catamaran", "performance_multihull"],
            "triggers": [
                {"ontology_field": "telemetry.heel_angle_deg", "operator": ">=", "value": 5.0, "unit": "deg"}
            ],
            "triggers_logic": "ALL",
            "actions": [
                {"action_id": "actions.ease_main_sheet", "description": "Ease main sheet immediately on multihull; heel above 5 deg indicates extreme load"}
            ],
            "severity": "critical",
            "uncertainty": "verified",
            "tier": "T1",
            "quote": "Multihulls give no heeling warning; 5 degrees of heel on a cruising cat is the danger zone.",
            "page": 82,
        },
        {
            "rule_id": "RULE_REEF_004_CATAMARAN_EARLY_REEF",
            "domain": "reefing",
            "archetype": ["cruising_catamaran"],
            "triggers": [
                {"ontology_field": "telemetry.true_wind_speed_kt", "operator": ">=", "value": 16.0, "unit": "knots"}
            ],
            "triggers_logic": "ALL",
            "actions": [
                {"action_id": "actions.reef_main_1", "description": "Take first reef on catamaran at 16 knots true wind without delay"}
            ],
            "severity": "warning",
            "uncertainty": "verified",
            "tier": "T1",
            "quote": "On catamarans, reef early at 16 knots because the boat cannot heel to shed wind power.",
            "page": 85,
        },
        {
            "rule_id": "RULE_TRIM_001_TRAVELER_GUST_RESPONSE",
            "domain": "trim",
            "archetype": ["performance_monohull", "ior_classic_narrow_stern"],
            "triggers": [
                {"ontology_field": "telemetry.apparent_wind_speed_kt", "operator": ">=", "value": 20.0, "unit": "knots"}
            ],
            "triggers_logic": "ALL",
            "actions": [
                {"action_id": "actions.ease_traveler", "description": "Drop main traveler down to maintain boat upright without losing mainsail leech profile"}
            ],
            "severity": "info",
            "uncertainty": "verified",
            "tier": "T1",
            "quote": "In gusty upwind sailing, control heel primarily with traveler drops before touching sheet.",
            "page": 28,
        },
        {
            "rule_id": "RULE_TRIM_002_FLATTEN_MAIN_BREEZE",
            "domain": "trim",
            "archetype": ["all_monohulls"],
            "triggers": [
                {"ontology_field": "telemetry.true_wind_speed_kt", "operator": ">=", "value": 15.0, "unit": "knots"}
            ],
            "triggers_logic": "ALL",
            "actions": [
                {"action_id": "actions.tighten_outhaul", "description": "Tighten outhaul and backstay to flatten mainsail draft and move draft forward"}
            ],
            "severity": "info",
            "uncertainty": "verified",
            "tier": "T1",
            "quote": "As wind increases past 15 knots, tension outhaul and backstay to reduce sail draft.",
            "page": 20,
        },
        {
            "rule_id": "RULE_SAFETY_008_HARNESS_TETHER_NIGHT",
            "domain": "safety",
            "archetype": ["all_vessels"],
            "triggers": [
                {"ontology_field": "telemetry.true_wind_speed_kt", "operator": ">=", "value": 25.0, "unit": "knots"}
            ],
            "triggers_logic": "ALL",
            "actions": [
                {"action_id": "actions.clip_tethers", "description": "All deck crew must wear lifejackets and clip safety tethers to jackstays"}
            ],
            "severity": "critical",
            "uncertainty": "verified",
            "tier": "T1",
            "quote": "Whenever wind reaches 25 knots or when working on deck at night, clipping onto jackstays is mandatory.",
            "page": 65,
        }
    ]

    rules: list[Rule] = []
    for rd in rules_data:
        src = RuleSource(
            doc_id=book_id,
            page=rd["page"],
            chunk_id=f"{book_id}_p{rd['page']:03d}_c01",
            quote=rd["quote"],
        )
        triggers = [
            RuleTrigger(
                ontology_field=t["ontology_field"],
                operator=t["operator"],
                value=t["value"],
                unit=t.get("unit", ""),
            )
            for t in rd["triggers"]
        ]
        actions = [
            RuleAction(
                action_id=a["action_id"],
                description=a.get("description", ""),
            )
            for a in rd["actions"]
        ]
        r = Rule(
            rule_id=rd["rule_id"],
            domain=rd["domain"],
            archetype=rd["archetype"],
            triggers=triggers,
            triggers_logic=rd.get("triggers_logic", "ALL"),
            actions=actions,
            severity=rd["severity"],
            uncertainty=rd["uncertainty"],
            tier="T1",
            origin="base",
            review_mode="manual",
            requires_confirmation=rd["severity"] == "critical",
            sources=[src],
            status="approved",
            deprecated=False,
            orphaned=False,
        )
        rules.append(r)

    return rules


def review_rules_cli(rules_file: Path | str) -> None:
    """Rich interactive CLI to view and review rules."""
    console = Console()
    path = Path(rules_file)
    if not path.exists():
        console.print(f"[red]Error: Rules file {path} does not exist.[/red]")
        return

    rules: list[Rule] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rules.append(Rule.model_validate_json(line))

    table = Table(title=f"MKP Rules Review — {path.name} ({len(rules)} rules)")
    table.add_column("Rule ID", style="cyan", no_wrap=True)
    table.add_column("Domain", style="magenta")
    table.add_column("Severity", style="yellow")
    table.add_column("Triggers", style="green")
    table.add_column("Status", style="bold")
    table.add_column("Source Quote", style="white")

    for r in rules:
        trig_str = ", ".join(f"{t.ontology_field} {t.operator} {t.value}" for t in r.triggers)
        status_color = "green" if r.status == "approved" else "red" if r.status == "draft" else "yellow"
        quote = r.sources[0].quote[:60] + "..." if r.sources else "-"
        table.add_row(
            r.rule_id,
            r.domain,
            r.severity,
            trig_str,
            f"[{status_color}]{r.status}[/{status_color}]",
            quote,
        )

    console.print(table)
