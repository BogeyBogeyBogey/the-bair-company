#!/usr/bin/env python3
"""
Build a customer intelligence brief from a tenant-scoped dashboard snapshot.

The dashboard is the interactive surface. This brief is the boardroom and sales
handoff artifact: compact, exportable, module-aware, and generated from exactly
the same scoped data the customer dashboard may show.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_platform import PILOT_MODULES


MODULE_LABELS = {key: definition.label for key, definition in PILOT_MODULES.items()}
ENGAGED_STATUSES = {"responded", "appointment", "customer"}
CONTACTED_STATUSES = {"sent", "scanned", "clicked", "responded", "appointment", "customer", "no_response", "rejected"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _number(value: Any, fallback: float = 0.0) -> float:
    if value in (None, ""):
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _money(value: Any) -> str:
    amount = int(round(_number(value)))
    return f"EUR {amount:,}".replace(",", " ")


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or f"{singular}s")


def _markdown_value(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "none"
    return str(value)


def _percent(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100, 1)


def _first_text(*values: Any, fallback: str = "") -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return fallback


def _best_assessment(prop: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    assessments = prop.get("assessments") if isinstance(prop.get("assessments"), dict) else {}
    if not assessments:
        return "", {}
    return sorted(
        assessments.items(),
        key=lambda item: (_number(item[1].get("score")), _number(prop.get("estimatedValue"))),
        reverse=True,
    )[0]


def _status_counts(properties: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for prop in properties:
        status = _first_text(prop.get("status"), fallback="generated")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _top_objections(properties: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for prop in properties:
        for objection in prop.get("objections", []) if isinstance(prop.get("objections"), list) else []:
            text = _first_text(objection)
            if text:
                counts[text] = counts.get(text, 0) + 1
    return [
        {"objection": key, "count": value}
        for key, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:6]
    ]


def _interaction_count(properties: list[dict[str, Any]]) -> int:
    return sum(len(prop.get("interactions", [])) for prop in properties)


def _evidence_count(prop: dict[str, Any]) -> int:
    total = 0
    assessments = prop.get("assessments") if isinstance(prop.get("assessments"), dict) else {}
    for assessment in assessments.values():
        total += len(assessment.get("evidence", []) if isinstance(assessment.get("evidence"), list) else [])
    return total


def _module_breakdown(properties: list[dict[str, Any]], modules: list[str]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {
        module: {
            "module_key": module,
            "label": MODULE_LABELS.get(module, module),
            "assessed_properties": 0,
            "top_opportunities": 0,
            "score_total": 0.0,
            "pipeline_value": 0,
            "engaged_properties": 0,
            "no_response_properties": 0,
            "signals": {},
        }
        for module in modules
    }
    for prop in properties:
        best_module, _best = _best_assessment(prop)
        status = _first_text(prop.get("status"), fallback="generated")
        assessments = prop.get("assessments") if isinstance(prop.get("assessments"), dict) else {}
        for module, assessment in assessments.items():
            row = rows.setdefault(module, {
                "module_key": module,
                "label": MODULE_LABELS.get(module, module),
                "assessed_properties": 0,
                "top_opportunities": 0,
                "score_total": 0.0,
                "pipeline_value": 0,
                "engaged_properties": 0,
                "no_response_properties": 0,
                "signals": {},
            })
            row["assessed_properties"] += 1
            row["score_total"] += _number(assessment.get("score"))
            signal = _first_text(assessment.get("label"), fallback="Opportunity signal")
            row["signals"][signal] = row["signals"].get(signal, 0) + 1
            if module == best_module:
                row["top_opportunities"] += 1
                row["pipeline_value"] += int(round(_number(prop.get("estimatedValue"))))
                if status in ENGAGED_STATUSES:
                    row["engaged_properties"] += 1
                if status == "no_response":
                    row["no_response_properties"] += 1

    clean_rows = []
    for row in rows.values():
        assessed = int(row.pop("assessed_properties"))
        score_total = float(row.pop("score_total"))
        signals = row.pop("signals")
        top_signal = ""
        if signals:
            top_signal = sorted(signals.items(), key=lambda item: (-item[1], item[0]))[0][0]
        clean_rows.append({
            **row,
            "assessed_properties": assessed,
            "average_score": round(score_total / assessed, 1) if assessed else 0.0,
            "top_signal": top_signal,
        })
    return sorted(clean_rows, key=lambda row: (row["pipeline_value"], row["average_score"]), reverse=True)


def _top_opportunities(properties: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    ranked = []
    for prop in properties:
        module, assessment = _best_assessment(prop)
        if not module:
            continue
        ranked.append({
            "property_id": prop.get("id"),
            "address": prop.get("address"),
            "city": prop.get("city"),
            "module_key": module,
            "module_label": MODULE_LABELS.get(module, module),
            "score": int(round(_number(assessment.get("score")))),
            "grade": _first_text(assessment.get("grade"), fallback="B"),
            "signal": _first_text(assessment.get("label"), fallback=MODULE_LABELS.get(module, module)),
            "estimated_value": int(round(_number(prop.get("estimatedValue")))),
            "status": _first_text(prop.get("status"), fallback="generated"),
            "next_action": _first_text(prop.get("nextAction"), fallback="Review property"),
            "evidence_count": _evidence_count(prop),
            "tags": list(prop.get("tags", []))[:6] if isinstance(prop.get("tags"), list) else [],
            "objections": list(prop.get("objections", []))[:3] if isinstance(prop.get("objections"), list) else [],
        })
    ranked.sort(key=lambda row: (row["score"], row["estimated_value"], row["evidence_count"]), reverse=True)
    return [{"rank": index + 1, **row} for index, row in enumerate(ranked[:limit])]


def _campaign_learnings(
    properties: list[dict[str, Any]],
    module_rows: list[dict[str, Any]],
    status_counts: dict[str, int],
) -> list[dict[str, Any]]:
    learnings: list[dict[str, Any]] = []
    if module_rows:
        top = module_rows[0]
        learnings.append({
            "theme": "Strongest entry point",
            "insight": f"{top['label']} currently carries the highest visible pipeline value.",
            "supporting_count": top["top_opportunities"],
            "recommendation": "Use this module as the first sales story for the highest-ranked properties.",
        })
    no_response = status_counts.get("no_response", 0)
    if no_response:
        learnings.append({
            "theme": "No-response memory",
            "insight": f"{no_response} properties have no response after outreach.",
            "supporting_count": no_response,
            "recommendation": "Retarget with a lower-friction message before expanding territory.",
        })
    engaged = sum(status_counts.get(status, 0) for status in ENGAGED_STATUSES)
    if engaged:
        noun = _plural(engaged, "property", "properties")
        verb = "shows" if engaged == 1 else "show"
        learnings.append({
            "theme": "Response evidence",
            "insight": f"{engaged} {noun} {verb} response or appointment evidence.",
            "supporting_count": engaged,
            "recommendation": "Use these cases to tune the next message variant and sales script.",
        })
    objections = _top_objections(properties)
    if objections:
        top_objection = objections[0]
        learnings.append({
            "theme": "Objection pattern",
            "insight": f"Most common objection: {top_objection['objection']}.",
            "supporting_count": top_objection["count"],
            "recommendation": "Create a response snippet and FAQ block for this objection.",
        })
    if not learnings:
        learnings.append({
            "theme": "First campaign baseline",
            "insight": "Import campaign responses to turn this property list into learning memory.",
            "supporting_count": len(properties),
            "recommendation": "Start with a controlled campaign batch and compare response statuses by module.",
        })
    return learnings[:5]


def _action_plan(scorecard: dict[str, Any], top_module: str, has_no_response: bool) -> list[dict[str, Any]]:
    label = MODULE_LABELS.get(top_module, top_module or "top module")
    actions = [
        {
            "priority": 1,
            "owner": "sales",
            "action": "Call or qualify the top-ranked properties first.",
            "rationale": "They combine the highest renovation score, value estimate, and evidence density.",
        },
        {
            "priority": 2,
            "owner": "marketing",
            "action": f"Lead the next message with the {label} story.",
            "rationale": "The current tenant snapshot points to this module as the strongest commercial entry point.",
        },
    ]
    if has_no_response:
        actions.append({
            "priority": 3,
            "owner": "marketing",
            "action": "Run a no-response retargeting segment.",
            "rationale": "No-response rows are not failed leads; they are campaign memory for a softer follow-up.",
        })
    else:
        actions.append({
            "priority": 3,
            "owner": "operations",
            "action": "Keep campaign response labels complete before the next export.",
            "rationale": "Clean response memory improves benchmark quality, prioritization, and sales handoff.",
        })
    if scorecard.get("pipeline_value", 0):
        actions.append({
            "priority": 4,
            "owner": "management",
            "action": "Review expected pipeline value against sales capacity.",
            "rationale": "A boardroom view is only useful when the next follow-up capacity is explicit.",
        })
    return actions


def _data_confidence(snapshot: dict[str, Any], properties: list[dict[str, Any]]) -> dict[str, Any]:
    evidence_total = sum(_evidence_count(prop) for prop in properties)
    with_evidence = sum(1 for prop in properties if _evidence_count(prop) > 0)
    interactions = _interaction_count(properties)
    warnings = []
    if not properties:
        warnings.append("No visible properties in the tenant-scoped snapshot.")
    if properties and with_evidence < len(properties):
        warnings.append("Some properties have no customer-visible evidence references.")
    if properties and interactions == 0:
        warnings.append("No campaign interactions are available yet; learnings are mostly scoring-based.")
    brain_stats = snapshot.get("brain", {}).get("stats", {}) if isinstance(snapshot.get("brain"), dict) else {}
    if not warnings and properties:
        status = "strong"
    elif properties:
        status = "review"
    else:
        status = "empty"
    return {
        "status": status,
        "evidence_references": evidence_total,
        "properties_with_evidence": with_evidence,
        "evidence_coverage_pct": _percent(with_evidence, len(properties)),
        "interaction_count": interactions,
        "objection_count": sum(len(prop.get("objections", [])) for prop in properties),
        "second_brain_nodes": int(brain_stats.get("nodes", 0) or 0),
        "second_brain_edges": int(brain_stats.get("edges", 0) or 0),
        "warnings": warnings,
    }


def build_customer_brief(snapshot: dict[str, Any]) -> dict[str, Any]:
    tenant = snapshot.get("tenant", {}) if isinstance(snapshot.get("tenant"), dict) else {}
    properties = snapshot.get("properties", []) if isinstance(snapshot.get("properties"), list) else []
    modules = list(tenant.get("modules", [])) if isinstance(tenant.get("modules"), list) else []
    if not modules:
        modules = sorted({module for prop in properties for module in (prop.get("assessments") or {})})

    status_counts = _status_counts(properties)
    engaged = sum(status_counts.get(status, 0) for status in ENGAGED_STATUSES)
    contacted = sum(status_counts.get(status, 0) for status in CONTACTED_STATUSES)
    pipeline_value = sum(int(round(_number(prop.get("estimatedValue")))) for prop in properties)
    scores = [_number(_best_assessment(prop)[1].get("score")) for prop in properties if _best_assessment(prop)[0]]
    module_rows = _module_breakdown(properties, modules)
    top_module = module_rows[0]["module_key"] if module_rows else (modules[0] if modules else "")
    top_opportunities = _top_opportunities(properties)
    data_confidence = _data_confidence(snapshot, properties)
    issues = []
    if not properties:
        issues.append("No customer-visible properties available for the brief.")
    if any(module not in PILOT_MODULES for module in modules):
        issues.append("Snapshot contains unknown module keys.")

    scorecard = {
        "property_count": len(properties),
        "campaign_count": len(snapshot.get("campaigns", []) if isinstance(snapshot.get("campaigns"), list) else []),
        "module_count": len(modules),
        "pipeline_value": pipeline_value,
        "average_best_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
        "engaged_properties": engaged,
        "contacted_properties": contacted,
        "no_response_properties": status_counts.get("no_response", 0),
        "engagement_rate_pct": _percent(engaged, contacted or len(properties)),
        "top_module": top_module,
        "top_module_label": MODULE_LABELS.get(top_module, top_module),
    }
    headline = (
        f"{_first_text(tenant.get('name'), tenant.get('id'), fallback='This tenant')} has "
        f"{scorecard['property_count']} visible renovation {_plural(scorecard['property_count'], 'opportunity', 'opportunities')} "
        f"across {scorecard['module_count']} enabled {_plural(scorecard['module_count'], 'module')}, "
        f"with {_money(pipeline_value)} in estimated tenant-private pipeline value."
    )
    return {
        "brief_type": "homepilot_customer_intelligence_brief",
        "created_at": utc_now(),
        "status": "pass" if not issues else "review",
        "tenant": {
            "id": tenant.get("id"),
            "name": tenant.get("name"),
            "modules": modules,
        },
        "executive_summary": {
            "headline": headline,
            "primary_entry_point": MODULE_LABELS.get(top_module, top_module),
            "answerable_questions": [
                "Which properties should we contact first?",
                "Which module is the strongest commercial entry point?",
                "What did the campaign learn from responses and non-responses?",
                "Which actions should sales, marketing, and operations take next?",
            ],
        },
        "scorecard": scorecard,
        "status_counts": status_counts,
        "module_breakdown": module_rows,
        "top_opportunities": top_opportunities,
        "campaign_learnings": _campaign_learnings(properties, module_rows, status_counts),
        "action_plan": _action_plan(scorecard, top_module, status_counts.get("no_response", 0) > 0),
        "data_confidence": data_confidence,
        "guardrails": {
            "source": "tenant-scoped HomePilot dashboard snapshot",
            "tenant_scoped": True,
            "module_scoped": True,
            "modules_selected": modules,
            "raw_internal_metrics_excluded": True,
            "cross_customer_learning": "aggregate-only outside this customer package",
        },
        "issues": issues,
    }


def render_markdown(brief: dict[str, Any]) -> str:
    scorecard = brief["scorecard"]
    tenant = brief["tenant"]
    lines = [
        "# HomePilot Customer Intelligence Brief",
        "",
        f"Created: {brief['created_at']}",
        f"Status: {brief['status']}",
        f"Tenant: {_first_text(tenant.get('name'), tenant.get('id'), fallback='Unknown')}",
        f"Modules: {', '.join(tenant.get('modules', [])) or 'none'}",
        "",
        "## Executive Summary",
        "",
        brief["executive_summary"]["headline"],
        "",
        "## Scorecard",
        "",
        f"- Properties: {scorecard['property_count']}",
        f"- Campaigns: {scorecard['campaign_count']}",
        f"- Pipeline value: {_money(scorecard['pipeline_value'])}",
        f"- Average best score: {scorecard['average_best_score']}",
        f"- Engagement rate: {scorecard['engagement_rate_pct']}%",
        f"- Strongest entry point: {scorecard['top_module_label']}",
        "",
        "## Top Opportunities",
        "",
    ]
    for row in brief["top_opportunities"]:
        lines.append(
            f"- #{row['rank']} {row['address']} ({row['city']}): {row['module_label']} score {row['score']} "
            f"({row['grade']}), {_money(row['estimated_value'])}, status `{row['status']}`, next: {row['next_action']}"
        )
    if not brief["top_opportunities"]:
        lines.append("- No opportunities available yet.")
    lines += ["", "## Module Breakdown", ""]
    for row in brief["module_breakdown"]:
        top_count = int(row["top_opportunities"])
        lines.append(
            f"- {row['label']}: {row['assessed_properties']} assessed, {top_count} {_plural(top_count, 'top opportunity', 'top opportunities')}, "
            f"avg score {row['average_score']}, {_money(row['pipeline_value'])}."
        )
    lines += ["", "## Campaign Learnings", ""]
    for learning in brief["campaign_learnings"]:
        lines.append(f"- {learning['theme']}: {learning['insight']} Recommendation: {learning['recommendation']}")
    lines += ["", "## Action Plan", ""]
    for action in brief["action_plan"]:
        lines.append(f"- P{action['priority']} {action['owner']}: {action['action']} {action['rationale']}")
    confidence = brief["data_confidence"]
    lines += [
        "",
        "## Data Confidence",
        "",
        f"- Status: {confidence['status']}",
        f"- Evidence coverage: {confidence['evidence_coverage_pct']}%",
        f"- Evidence references: {confidence['evidence_references']}",
        f"- Interactions: {confidence['interaction_count']}",
        f"- Second-brain graph: {confidence['second_brain_nodes']} nodes / {confidence['second_brain_edges']} edges",
        "",
        "## Guardrails",
        "",
    ]
    for key, value in brief["guardrails"].items():
        lines.append(f"- {key}: {_markdown_value(value)}")
    if brief["issues"]:
        lines += ["", "## Issues", ""]
        for issue in brief["issues"]:
            lines.append(f"- {issue}")
    lines.append("")
    return "\n".join(lines)


def build_customer_brief_pack(out_dir: Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    brief = build_customer_brief(snapshot)
    json_path = out_dir / "customer_brief.json"
    markdown_path = out_dir / "CUSTOMER_BRIEF.md"
    write_json(json_path, brief)
    markdown_path.write_text(render_markdown(brief), encoding="utf-8")
    return {
        "status": brief["status"],
        "paths": {
            "customer_brief": str(json_path),
            "markdown": str(markdown_path),
        },
        "brief": brief,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot customer intelligence brief")
    parser.add_argument("--snapshot", required=True, type=Path, help="Tenant-scoped dashboard snapshot JSON")
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    pack = build_customer_brief_pack(args.out_dir, snapshot=snapshot)
    print(json.dumps({
        "status": pack["status"],
        "paths": pack["paths"],
        "tenant": pack["brief"]["tenant"],
        "scorecard": pack["brief"]["scorecard"],
        "issues": pack["brief"]["issues"],
    }, indent=2, ensure_ascii=False))
    if pack["status"] == "review":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
