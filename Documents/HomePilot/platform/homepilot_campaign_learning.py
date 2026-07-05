#!/usr/bin/env python3
"""
Build customer-safe campaign learning reports from a dashboard snapshot.

HomePilot should not feel like a static lead list. This report turns contacted,
responded, and no-response properties into a learning loop for sales and
marketing: funnel health, segment signals, objection patterns, and the next
controlled experiments to run.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_platform import PILOT_MODULES


MODULE_LABELS = {key: definition.label for key, definition in PILOT_MODULES.items()}
CONTACTED_STATUSES = {"sent", "scanned", "clicked", "responded", "appointment", "customer", "rejected", "no_response"}
ENGAGED_STATUSES = {"responded", "appointment", "customer"}
CONVERSION_STATUSES = {"appointment", "customer"}


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


def _percent(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator) * 100, 1)


def _first_text(*values: Any, fallback: str = "") -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return fallback


def _money(value: Any) -> str:
    amount = int(round(_number(value)))
    return f"EUR {amount:,}".replace(",", " ")


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or f"{singular}s")


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


def _count_statuses(status_counts: dict[str, int], statuses: set[str]) -> int:
    return sum(status_counts.get(status, 0) for status in statuses)


def _funnel(properties: list[dict[str, Any]], campaigns: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = _status_counts(properties)
    total = len(properties)
    contacted = _count_statuses(status_counts, CONTACTED_STATUSES)
    engaged = _count_statuses(status_counts, ENGAGED_STATUSES)
    converted = _count_statuses(status_counts, CONVERSION_STATUSES)
    no_response = status_counts.get("no_response", 0)
    return {
        "properties": total,
        "campaigns": len(campaigns),
        "contacted": contacted,
        "engaged": engaged,
        "converted": converted,
        "no_response": no_response,
        "status_counts": status_counts,
        "contact_rate_pct": _percent(contacted, total),
        "engagement_rate_pct": _percent(engaged, contacted or total),
        "conversion_rate_pct": _percent(converted, contacted or total),
        "no_response_rate_pct": _percent(no_response, contacted or total),
    }


def _objection_patterns(properties: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for prop in properties:
        for objection in prop.get("objections", []) if isinstance(prop.get("objections"), list) else []:
            text = _first_text(objection)
            if text:
                counts[text] = counts.get(text, 0) + 1
    return [
        {"objection": objection, "count": count, "share_pct": _percent(count, len(properties))}
        for objection, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    ]


def _module_learnings(properties: list[dict[str, Any]], modules: list[str]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {
        module: {
            "module_key": module,
            "label": MODULE_LABELS.get(module, module),
            "assessed": 0,
            "best_entry_count": 0,
            "score_total": 0.0,
            "pipeline_value": 0,
            "engaged": 0,
            "no_response": 0,
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
                "assessed": 0,
                "best_entry_count": 0,
                "score_total": 0.0,
                "pipeline_value": 0,
                "engaged": 0,
                "no_response": 0,
                "signals": {},
            })
            row["assessed"] += 1
            row["score_total"] += _number(assessment.get("score"))
            signal = _first_text(assessment.get("label"), fallback=MODULE_LABELS.get(module, module))
            row["signals"][signal] = row["signals"].get(signal, 0) + 1
            if module == best_module:
                row["best_entry_count"] += 1
                row["pipeline_value"] += int(round(_number(prop.get("estimatedValue"))))
                if status in ENGAGED_STATUSES:
                    row["engaged"] += 1
                if status == "no_response":
                    row["no_response"] += 1

    clean = []
    for row in rows.values():
        assessed = int(row.pop("assessed"))
        score_total = float(row.pop("score_total"))
        signals = row.pop("signals")
        top_signals = [
            {"signal": signal, "count": count}
            for signal, count in sorted(signals.items(), key=lambda item: (-item[1], item[0]))[:3]
        ]
        clean.append({
            **row,
            "assessed": assessed,
            "average_score": round(score_total / assessed, 1) if assessed else 0.0,
            "engagement_rate_pct": _percent(row["engaged"], row["best_entry_count"] or assessed),
            "top_signals": top_signals,
        })
    return sorted(clean, key=lambda row: (row["best_entry_count"], row["pipeline_value"], row["average_score"]), reverse=True)


def _segment_key(prop: dict[str, Any], tag: str) -> str:
    city = _first_text(prop.get("city"), fallback="Unknown")
    return f"{city} / {tag}"


def _customer_segment_tags(tags: list[Any]) -> list[str]:
    clean = []
    for tag in tags:
        text = str(tag or "").strip()
        key = text.lower()
        if not text:
            continue
        if "fixture" in key or key in PILOT_MODULES:
            continue
        clean.append(text)
    return clean


def _segment_learnings(properties: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segments: dict[str, dict[str, Any]] = {}
    for prop in properties:
        tags = prop.get("tags", []) if isinstance(prop.get("tags"), list) else []
        usable_tags = _customer_segment_tags(tags)[:4] or ["untagged"]
        status = _first_text(prop.get("status"), fallback="generated")
        best_module, best = _best_assessment(prop)
        for tag in usable_tags:
            key = _segment_key(prop, tag)
            row = segments.setdefault(key, {
                "segment": key,
                "property_count": 0,
                "score_total": 0.0,
                "pipeline_value": 0,
                "engaged": 0,
                "no_response": 0,
                "top_module_counts": {},
            })
            row["property_count"] += 1
            row["score_total"] += _number(best.get("score"))
            row["pipeline_value"] += int(round(_number(prop.get("estimatedValue"))))
            if status in ENGAGED_STATUSES:
                row["engaged"] += 1
            if status == "no_response":
                row["no_response"] += 1
            if best_module:
                row["top_module_counts"][best_module] = row["top_module_counts"].get(best_module, 0) + 1

    clean = []
    for row in segments.values():
        count = int(row.pop("property_count"))
        score_total = float(row.pop("score_total"))
        module_counts = row.pop("top_module_counts")
        top_module = ""
        if module_counts:
            top_module = sorted(module_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
        clean.append({
            **row,
            "property_count": count,
            "average_score": round(score_total / count, 1) if count else 0.0,
            "engagement_rate_pct": _percent(row["engaged"], count),
            "top_module": top_module,
            "top_module_label": MODULE_LABELS.get(top_module, top_module),
        })
    return sorted(clean, key=lambda row: (row["property_count"], row["pipeline_value"], row["average_score"]), reverse=True)[:10]


def _experiment_backlog(
    funnel: dict[str, Any],
    module_rows: list[dict[str, Any]],
    objections: list[dict[str, Any]],
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    experiments = []
    top_module = module_rows[0] if module_rows else None
    if top_module:
        experiments.append({
            "priority": 1,
            "hypothesis": f"Leading with the {top_module['label']} story will improve response quality in the next batch.",
            "target_segment": segments[0]["segment"] if segments else "highest-score properties",
            "measure": "response_rate_pct and appointment_count",
            "minimum_sample": max(20, min(100, int(funnel.get("properties", 0)) or 20)),
            "recommended_change": "Use the top module signal in headline, call script, and follow-up reason.",
        })
    if funnel.get("no_response", 0):
        experiments.append({
            "priority": 2,
            "hypothesis": "A lower-friction retargeting message will recover part of the no-response segment.",
            "target_segment": "no-response properties",
            "measure": "scan/click/responded movement after retargeting",
            "minimum_sample": max(20, int(funnel["no_response"])),
            "recommended_change": "Switch from sales-heavy wording to a visual before/after or savings-oriented prompt.",
        })
    if objections:
        top = objections[0]
        experiments.append({
            "priority": 3,
            "hypothesis": f"Addressing the '{top['objection']}' objection earlier will reduce drop-off.",
            "target_segment": "properties with repeated objection evidence",
            "measure": "objection recurrence and qualified response rate",
            "minimum_sample": max(10, top["count"]),
            "recommended_change": "Add a proof point, FAQ snippet, or financing answer to the next sales touch.",
        })
    if not experiments:
        experiments.append({
            "priority": 1,
            "hypothesis": "A controlled first campaign batch will establish the baseline response curve.",
            "target_segment": "top-scoring properties",
            "measure": "contact_rate_pct, response_rate_pct, appointment_count",
            "minimum_sample": 20,
            "recommended_change": "Start with one module story and keep response labels complete.",
        })
    return experiments[:5]


def build_campaign_learning_report(snapshot: dict[str, Any]) -> dict[str, Any]:
    tenant = snapshot.get("tenant", {}) if isinstance(snapshot.get("tenant"), dict) else {}
    properties = snapshot.get("properties", []) if isinstance(snapshot.get("properties"), list) else []
    campaigns = snapshot.get("campaigns", []) if isinstance(snapshot.get("campaigns"), list) else []
    modules = list(tenant.get("modules", [])) if isinstance(tenant.get("modules"), list) else []
    if not modules:
        modules = sorted({module for prop in properties for module in (prop.get("assessments") or {})})

    funnel = _funnel(properties, campaigns)
    module_rows = _module_learnings(properties, modules)
    objections = _objection_patterns(properties)
    segments = _segment_learnings(properties)
    issues = []
    if not properties:
        issues.append("No customer-visible properties available for campaign learning.")
    if any(module not in PILOT_MODULES for module in modules):
        issues.append("Snapshot contains unknown module keys.")

    return {
        "report_type": "homepilot_campaign_learning_report",
        "created_at": utc_now(),
        "status": "pass" if not issues else "review",
        "tenant": {
            "id": tenant.get("id"),
            "name": tenant.get("name"),
            "modules": modules,
        },
        "learning_positioning": "Every campaign touchpoint becomes tenant-scoped memory for the next targeting, message, and sales action.",
        "funnel": funnel,
        "module_learnings": module_rows,
        "segment_learnings": segments,
        "objection_patterns": objections,
        "experiment_backlog": _experiment_backlog(funnel, module_rows, objections, segments),
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


def _markdown_value(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "none"
    return str(value)


def render_markdown(report: dict[str, Any]) -> str:
    tenant = report["tenant"]
    funnel = report["funnel"]
    lines = [
        "# HomePilot Campaign Learning Report",
        "",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        f"Tenant: {_first_text(tenant.get('name'), tenant.get('id'), fallback='Unknown')}",
        f"Modules: {', '.join(tenant.get('modules', [])) or 'none'}",
        "",
        "## Learning Positioning",
        "",
        report["learning_positioning"],
        "",
        "## Funnel",
        "",
        f"- Properties: {funnel['properties']}",
        f"- Campaigns: {funnel['campaigns']}",
        f"- Contacted: {funnel['contacted']} ({funnel['contact_rate_pct']}%)",
        f"- Engaged: {funnel['engaged']} ({funnel['engagement_rate_pct']}%)",
        f"- Converted: {funnel['converted']} ({funnel['conversion_rate_pct']}%)",
        f"- No response: {funnel['no_response']} ({funnel['no_response_rate_pct']}%)",
        "",
        "## Module Learnings",
        "",
    ]
    for row in report["module_learnings"]:
        best_entry_count = int(row["best_entry_count"])
        lines.append(
            f"- {row['label']}: {row['assessed']} assessed, {best_entry_count} {_plural(best_entry_count, 'best-entry property', 'best-entry properties')}, "
            f"avg score {row['average_score']}, {_money(row['pipeline_value'])}, engagement {row['engagement_rate_pct']}%."
        )
    if not report["module_learnings"]:
        lines.append("- No module learnings available yet.")
    lines += ["", "## Segment Learnings", ""]
    for row in report["segment_learnings"]:
        property_count = int(row["property_count"])
        lines.append(
            f"- {row['segment']}: {property_count} {_plural(property_count, 'property', 'properties')}, avg score {row['average_score']}, "
            f"{_money(row['pipeline_value'])}, top module {row['top_module_label'] or 'unknown'}."
        )
    if not report["segment_learnings"]:
        lines.append("- No segment learnings available yet.")
    lines += ["", "## Objection Patterns", ""]
    for row in report["objection_patterns"]:
        count = int(row["count"])
        lines.append(f"- {row['objection']}: {count} {_plural(count, 'occurrence')}, {row['share_pct']}% of visible properties.")
    if not report["objection_patterns"]:
        lines.append("- No repeated objections captured yet.")
    lines += ["", "## Experiment Backlog", ""]
    for row in report["experiment_backlog"]:
        lines.append(
            f"- P{row['priority']}: {row['hypothesis']} Target: {row['target_segment']}. "
            f"Measure: {row['measure']}. Minimum sample: {row['minimum_sample']}."
        )
    lines += ["", "## Guardrails", ""]
    for key, value in report["guardrails"].items():
        lines.append(f"- {key}: {_markdown_value(value)}")
    if report["issues"]:
        lines += ["", "## Issues", ""]
        for issue in report["issues"]:
            lines.append(f"- {issue}")
    lines.append("")
    return "\n".join(lines)


def build_campaign_learning_pack(out_dir: Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = build_campaign_learning_report(snapshot)
    json_path = out_dir / "campaign_learning.json"
    markdown_path = out_dir / "CAMPAIGN_LEARNING.md"
    write_json(json_path, report)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return {
        "status": report["status"],
        "paths": {
            "campaign_learning": str(json_path),
            "markdown": str(markdown_path),
        },
        "report": report,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot campaign learning report")
    parser.add_argument("--snapshot", required=True, type=Path, help="Tenant-scoped dashboard snapshot JSON")
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    pack = build_campaign_learning_pack(args.out_dir, snapshot=snapshot)
    print(json.dumps({
        "status": pack["status"],
        "paths": pack["paths"],
        "tenant": pack["report"]["tenant"],
        "funnel": pack["report"]["funnel"],
        "experiments": len(pack["report"]["experiment_backlog"]),
        "issues": pack["report"]["issues"],
    }, indent=2, ensure_ascii=False))
    if pack["status"] == "review":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
