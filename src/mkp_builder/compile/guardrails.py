"""Static Guardrails Compiler for MKP Builder (REQ-R05)."""

from __future__ import annotations

import logging
from mkp_common.rules_schema import Rule

logger = logging.getLogger(__name__)

MAX_GUARDRAILS_CHARS = 8000


class GuardrailsCompiler:
    """Compiles approved critical and warning T1 rules into static markdown guardrails."""

    def compile(
        self,
        rules: list[Rule],
        include_draft: bool = False,
    ) -> str:
        """Compile rules into markdown system prompt section (≤ 8000 chars)."""
        # Filter T1 rules
        filtered = [
            r for r in rules
            if r.tier == "T1"
            and r.severity in ("critical", "warning")
            and (r.status == "approved" or (include_draft and r.status in ("draft", "approved", "review")))
        ]

        # Sort: critical first, then warning
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        filtered.sort(key=lambda r: (severity_order.get(r.severity, 3), r.domain, r.rule_id))

        lines: list[str] = [
            "# SIA MARITIME STATIC SAFETY GUARDRAILS (T1 BASE)",
            "",
            "> MANDATORY SAFETY CONSTRAINTS FOR ON-BOARD ADVISOR. DO NOT OVERRIDE.",
            "",
        ]

        # Group by domain
        by_domain: dict[str, list[Rule]] = {}
        for r in filtered:
            by_domain.setdefault(r.domain, []).append(r)

        for domain, d_rules in sorted(by_domain.items()):
            lines.append(f"## Domain: {domain.upper()}")
            lines.append("")
            for r in d_rules:
                # Trigger conditions
                trig_strs = []
                for t in r.triggers:
                    unit_str = f" {t.unit}" if t.unit else ""
                    trig_strs.append(f"{t.ontology_field} {t.operator} {t.value}{unit_str}")
                trig_formatted = f" {r.triggers_logic} ".join(trig_strs) if trig_strs else "Always active"

                # Actions
                act_strs = [a.description or a.action_id for a in r.actions]
                act_formatted = "; ".join(act_strs) if act_strs else "Maintain alert"

                # Provenance
                quote_ref = f" ({r.sources[0].doc_id}, p.{r.sources[0].page})" if r.sources else ""

                sev_tag = "🔴 CRITICAL" if r.severity == "critical" else "🟡 WARNING"

                rule_line = f"- **[{r.rule_id}]** {sev_tag} IF `{trig_formatted}` THEN **{act_formatted}**{quote_ref}"
                lines.append(rule_line)
            lines.append("")

        content = "\n".join(lines).strip()

        # Enforce character limit
        if len(content) > MAX_GUARDRAILS_CHARS:
            logger.warning(
                "Guardrails length (%d chars) exceeds limit of %d. Truncating safely.",
                len(content),
                MAX_GUARDRAILS_CHARS,
            )
            content = content[:MAX_GUARDRAILS_CHARS - 50] + "\n\n... [TRUNCATED DUE TO 8000 CHAR LIMIT]"

        return content
