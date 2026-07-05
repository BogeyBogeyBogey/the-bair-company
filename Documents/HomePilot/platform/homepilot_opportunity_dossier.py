#!/usr/bin/env python3
"""
Build tenant-scoped opportunity dossiers from a HomePilot dashboard snapshot.

The dossier is the explainability layer for customers: why this property, which
evidence supports the score, what is missing, and what should sales do next.
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


def _safe_metric_drivers(module_key: str, assessment: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = assessment.get("metrics") if isinstance(assessment.get("metrics"), dict) else {}
    drivers = []
    for key, value in sorted(metrics.items()):
        if value in (None, "", [], {}):
            continue
        text = str(value)
        if "secret" in text.lower() or "raw_feature" in key.lower() or "internal" in key.lower():
            continue
        drivers.append({
            "metric_key": key,
            "value": value,
            "explanation": f"Visible {MODULE_LABELS.get(module_key, module_key)} signal used for customer prioritization.",
        })
    return drivers[:8]


def _evidence_summary(assessment: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = assessment.get("evidence", []) if isinstance(assessment.get("evidence"), list) else []
    rows = []
    for item in evidence[:8]:
        if not isinstance(item, dict):
            continue
        rows.append({
            "type": _first_text(item.get("type"), fallback="evidence"),
            "reference": _first_text(item.get("value"), item.get("url"), item.get("path"), fallback="available in source package"),
        })
    return rows


def _interaction_summary(prop: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for interaction in prop.get("interactions", []) if isinstance(prop.get("interactions"), list) else []:
        rows.append({
            "date": _first_text(interaction.get("date"), fallback="Queued"),
            "type": _first_text(interaction.get("type"), fallback="note"),
            "detail": _first_text(interaction.get("detail"), fallback="Interaction logged"),
        })
    return rows[:8]


def _review_gaps(prop: dict[str, Any], module_key: str, assessment: dict[str, Any]) -> list[str]:
    gaps = []
    if prop.get("lat") in (None, "") or prop.get("lon") in (None, ""):
        gaps.append("Missing map coordinates; verify address before territory routing.")
    if not _evidence_summary(assessment):
        gaps.append("No customer-visible evidence references; review source media before sales use.")
    if _number(assessment.get("confidence"), 0.0) < 0.7:
        gaps.append("Confidence below 0.70; request operator review before high-touch outreach.")
    if not _safe_metric_drivers(module_key, assessment):
        gaps.append("No visible metric drivers; add a customer-safe explanation before handoff.")
    if not prop.get("interactions"):
        gaps.append("No response history yet; treat this as opportunity evidence, not intent evidence.")
    return gaps


def _dossier_status(gaps: list[str], prop_status: str) -> str:
    if any("Confidence below" in gap or "No customer-visible evidence" in gap for gap in gaps):
        return "review"
    if prop_status in ENGAGED_STATUSES:
        return "sales_ready"
    return "campaign_ready"


def _property_dossiers(properties: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    rows = []
    for prop in properties:
        module_key, assessment = _best_assessment(prop)
        if not module_key:
            continue
        status = _first_text(prop.get("status"), fallback="generated")
        gaps = _review_gaps(prop, module_key, assessment)
        rows.append({
            "property_id": prop.get("id"),
            "address": prop.get("address"),
            "city": prop.get("city"),
            "module_key": module_key,
            "module_label": MODULE_LABELS.get(module_key, module_key),
            "score": int(round(_number(assessment.get("score")))),
            "grade": _first_text(assessment.get("grade"), fallback="B"),
            "confidence": round(_number(assessment.get("confidence")), 2),
            "estimated_value": int(round(_number(prop.get("estimatedValue")))),
            "campaign_status": status,
            "next_action": _first_text(prop.get("nextAction"), fallback="Review property"),
            "primary_reason": _first_text(assessment.get("label"), fallback=MODULE_LABELS.get(module_key, module_key)),
            "tags": list(prop.get("tags", []))[:6] if isinstance(prop.get("tags"), list) else [],
            "metric_drivers": _safe_metric_drivers(module_key, assessment),
            "evidence": _evidence_summary(assessment),
            "interactions": _interaction_summary(prop),
            "objections": list(prop.get("objections", []))[:5] if isinstance(prop.get("objections"), list) else [],
            "review_gaps": gaps,
            "dossier_status": _dossier_status(gaps, status),
        })
    rows.sort(key=lambda row: (row["score"], row["estimated_value"], len(row["evidence"])), reverse=True)
    return [{"rank": index + 1, **row} for index, row in enumerate(rows[:limit])]


def _summary(dossiers: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    module_counts: dict[str, int] = {}
    for dossier in dossiers:
        status_counts[dossier["dossier_status"]] = status_counts.get(dossier["dossier_status"], 0) + 1
        module = dossier["module_key"]
        module_counts[module] = module_counts.get(module, 0) + 1
    return {
        "dossiers": len(dossiers),
        "sales_ready": status_counts.get("sales_ready", 0),
        "campaign_ready": status_counts.get("campaign_ready", 0),
        "review_required": status_counts.get("review", 0),
        "status_counts": dict(sorted(status_counts.items())),
        "module_counts": dict(sorted(module_counts.items())),
    }


def build_opportunity_dossier(snapshot: dict[str, Any], limit: int = 12) -> dict[str, Any]:
    tenant = snapshot.get("tenant", {}) if isinstance(snapshot.get("tenant"), dict) else {}
    properties = snapshot.get("properties", []) if isinstance(snapshot.get("properties"), list) else []
    modules = list(tenant.get("modules", [])) if isinstance(tenant.get("modules"), list) else []
    if not modules:
        modules = sorted({module for prop in properties for module in (prop.get("assessments") or {})})
    dossiers = _property_dossiers(properties, limit=limit)
    issues = []
    if not properties:
        issues.append("No customer-visible properties available for opportunity dossiers.")
    if any(module not in PILOT_MODULES for module in modules):
        issues.append("Snapshot contains unknown module keys.")
    if dossiers and all(row["dossier_status"] == "review" for row in dossiers):
        issues.append("All generated dossiers require review before customer sales use.")

    return {
        "report_type": "homepilot_opportunity_dossier",
        "created_at": utc_now(),
        "status": "pass" if not issues else "review",
        "tenant": {
            "id": tenant.get("id"),
            "name": tenant.get("name"),
            "modules": modules,
        },
        "summary": _summary(dossiers),
        "dossiers": dossiers,
        "guardrails": {
            "source": "tenant-scoped HomePilot dashboard snapshot",
            "tenant_scoped": True,
            "module_scoped": True,
            "modules_selected": modules,
            "raw_internal_metrics_excluded": True,
            "opportunity_not_intent_without_response": True,
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
    summary = report["summary"]
    lines = [
        "# HomePilot Opportunity Dossier",
        "",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        f"Tenant: {_first_text(tenant.get('name'), tenant.get('id'), fallback='Unknown')}",
        f"Modules: {', '.join(tenant.get('modules', [])) or 'none'}",
        "",
        "## Summary",
        "",
        f"- Dossiers: {summary['dossiers']}",
        f"- Sales ready: {summary['sales_ready']}",
        f"- Campaign ready: {summary['campaign_ready']}",
        f"- Review required: {summary['review_required']}",
        "",
        "## Top Dossiers",
        "",
    ]
    for dossier in report["dossiers"]:
        evidence_count = len(dossier["evidence"])
        gap_count = len(dossier["review_gaps"])
        lines += [
            f"### #{dossier['rank']} {dossier['address']} ({dossier['city']})",
            "",
            f"- Module: {dossier['module_label']}",
            f"- Score: {dossier['score']} ({dossier['grade']})",
            f"- Confidence: {dossier['confidence']}",
            f"- Estimated value: {_money(dossier['estimated_value'])}",
            f"- Status: {dossier['campaign_status']} / {dossier['dossier_status']}",
            f"- Primary reason: {dossier['primary_reason']}",
            f"- Next action: {dossier['next_action']}",
            f"- Evidence: {evidence_count} {_plural(evidence_count, 'reference')}",
            f"- Review gaps: {gap_count} {_plural(gap_count, 'gap')}",
            "",
        ]
        if dossier["metric_drivers"]:
            lines.append("Metric drivers:")
            for driver in dossier["metric_drivers"][:4]:
                lines.append(f"- `{driver['metric_key']}`: {driver['value']}")
        if dossier["review_gaps"]:
            lines.append("")
            lines.append("Review gaps:")
            for gap in dossier["review_gaps"]:
                lines.append(f"- {gap}")
        lines.append("")
    if not report["dossiers"]:
        lines.append("- No opportunity dossiers available yet.")
    if lines and lines[-1] == "":
        lines += ["## Guardrails", ""]
    else:
        lines += ["", "## Guardrails", ""]
    for key, value in report["guardrails"].items():
        lines.append(f"- {key}: {_markdown_value(value)}")
    if report["issues"]:
        lines += ["", "## Issues", ""]
        for issue in report["issues"]:
            lines.append(f"- {issue}")
    lines.append("")
    return "\n".join(lines)


def build_opportunity_dossier_pack(out_dir: Path, snapshot: dict[str, Any], limit: int = 12) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = build_opportunity_dossier(snapshot, limit=limit)
    json_path = out_dir / "opportunity_dossier.json"
    markdown_path = out_dir / "OPPORTUNITY_DOSSIER.md"
    write_json(json_path, report)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return {
        "status": report["status"],
        "paths": {
            "opportunity_dossier": str(json_path),
            "markdown": str(markdown_path),
        },
        "report": report,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot opportunity dossier")
    parser.add_argument("--snapshot", required=True, type=Path, help="Tenant-scoped dashboard snapshot JSON")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    pack = build_opportunity_dossier_pack(args.out_dir, snapshot=snapshot, limit=args.limit)
    print(json.dumps({
        "status": pack["status"],
        "paths": pack["paths"],
        "tenant": pack["report"]["tenant"],
        "summary": pack["report"]["summary"],
        "issues": pack["report"]["issues"],
    }, indent=2, ensure_ascii=False))
    if pack["status"] == "review":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
