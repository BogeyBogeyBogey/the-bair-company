#!/usr/bin/env python3
"""
Build tenant-scoped territory plans from a HomePilot dashboard snapshot.

The dashboard answers which properties look interesting. The territory plan
answers where to focus the next campaign batch: which city/segment/module cell,
which properties to start with, and what proof supports that decision.
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
CONTACTED_STATUSES = {"sent", "scanned", "clicked", "responded", "appointment", "customer", "rejected", "no_response"}


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


def _customer_tags(prop: dict[str, Any]) -> list[str]:
    tags = prop.get("tags", []) if isinstance(prop.get("tags"), list) else []
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


def _status_counts(properties: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for prop in properties:
        status = _first_text(prop.get("status"), fallback="generated")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _map_bounds(properties: list[dict[str, Any]]) -> dict[str, float] | None:
    coords = [
        (_number(prop.get("lat")), _number(prop.get("lon")))
        for prop in properties
        if prop.get("lat") not in (None, "") and prop.get("lon") not in (None, "")
    ]
    if not coords:
        return None
    lats = [lat for lat, _lon in coords]
    lons = [lon for _lat, lon in coords]
    return {
        "min_lat": round(min(lats), 6),
        "max_lat": round(max(lats), 6),
        "min_lon": round(min(lons), 6),
        "max_lon": round(max(lons), 6),
    }


def _territory_key(prop: dict[str, Any], module_key: str) -> tuple[str, str, str]:
    city = _first_text(prop.get("city"), fallback="Unknown")
    tags = _customer_tags(prop)
    segment = tags[0] if tags else "general"
    return city, segment, module_key or "unknown"


def _territory_cells(properties: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cells: dict[tuple[str, str, str], dict[str, Any]] = {}
    cell_properties: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for prop in properties:
        module_key, assessment = _best_assessment(prop)
        if not module_key:
            continue
        key = _territory_key(prop, module_key)
        city, segment, module = key
        row = cells.setdefault(key, {
            "city": city,
            "segment": segment,
            "module_key": module,
            "module_label": MODULE_LABELS.get(module, module),
            "property_count": 0,
            "score_total": 0.0,
            "pipeline_value": 0,
            "engaged": 0,
            "contacted": 0,
            "no_response": 0,
            "evidence_references": 0,
            "signals": {},
        })
        status = _first_text(prop.get("status"), fallback="generated")
        signal = _first_text(assessment.get("label"), fallback=MODULE_LABELS.get(module, module))
        row["property_count"] += 1
        row["score_total"] += _number(assessment.get("score"))
        row["pipeline_value"] += int(round(_number(prop.get("estimatedValue"))))
        row["evidence_references"] += len(assessment.get("evidence", []) if isinstance(assessment.get("evidence"), list) else [])
        row["signals"][signal] = row["signals"].get(signal, 0) + 1
        if status in ENGAGED_STATUSES:
            row["engaged"] += 1
        if status in CONTACTED_STATUSES:
            row["contacted"] += 1
        if status == "no_response":
            row["no_response"] += 1
        cell_properties.setdefault(key, []).append(prop)

    clean = []
    for key, row in cells.items():
        count = int(row.pop("property_count"))
        score_total = float(row.pop("score_total"))
        signals = row.pop("signals")
        top_signal = ""
        if signals:
            top_signal = sorted(signals.items(), key=lambda item: (-item[1], item[0]))[0][0]
        priority_score = round((score_total / max(count, 1)) + min(row["pipeline_value"] / 5000, 30) + row["engaged"] * 5, 1)
        clean.append({
            **row,
            "property_count": count,
            "average_score": round(score_total / count, 1) if count else 0.0,
            "engagement_rate_pct": _percent(row["engaged"], row["contacted"] or count),
            "no_response_rate_pct": _percent(row["no_response"], row["contacted"] or count),
            "top_signal": top_signal,
            "map_bounds": _map_bounds(cell_properties[key]),
            "priority_score": priority_score,
        })
    return sorted(clean, key=lambda row: (row["priority_score"], row["pipeline_value"], row["average_score"]), reverse=True)


def _property_queue(properties: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    rows = []
    for prop in properties:
        module_key, assessment = _best_assessment(prop)
        if not module_key:
            continue
        city, segment, _module = _territory_key(prop, module_key)
        score = int(round(_number(assessment.get("score"))))
        value = int(round(_number(prop.get("estimatedValue"))))
        rows.append({
            "property_id": prop.get("id"),
            "address": prop.get("address"),
            "city": city,
            "segment": segment,
            "module_key": module_key,
            "module_label": MODULE_LABELS.get(module_key, module_key),
            "score": score,
            "grade": _first_text(assessment.get("grade"), fallback="B"),
            "estimated_value": value,
            "status": _first_text(prop.get("status"), fallback="generated"),
            "next_action": _first_text(prop.get("nextAction"), fallback="Review property"),
            "reason": _first_text(assessment.get("label"), fallback=MODULE_LABELS.get(module_key, module_key)),
            "lat": prop.get("lat"),
            "lon": prop.get("lon"),
        })
    rows.sort(key=lambda row: (row["score"], row["estimated_value"]), reverse=True)
    return [{"rank": index + 1, **row} for index, row in enumerate(rows[:limit])]


def _next_batch(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, cell in enumerate(cells[:5], start=1):
        rows.append({
            "priority": index,
            "territory": f"{cell['city']} / {cell['segment']}",
            "module_key": cell["module_key"],
            "module_label": cell["module_label"],
            "property_count": cell["property_count"],
            "pipeline_value": cell["pipeline_value"],
            "average_score": cell["average_score"],
            "recommended_batch_size": min(max(cell["property_count"], 10), 75),
            "why_now": f"High {cell['module_label']} score density with {_money(cell['pipeline_value'])} visible pipeline value.",
        })
    return rows


def build_territory_plan(snapshot: dict[str, Any]) -> dict[str, Any]:
    tenant = snapshot.get("tenant", {}) if isinstance(snapshot.get("tenant"), dict) else {}
    properties = snapshot.get("properties", []) if isinstance(snapshot.get("properties"), list) else []
    modules = list(tenant.get("modules", [])) if isinstance(tenant.get("modules"), list) else []
    if not modules:
        modules = sorted({module for prop in properties for module in (prop.get("assessments") or {})})
    status_counts = _status_counts(properties)
    cells = _territory_cells(properties)
    queue = _property_queue(properties)
    mapped = sum(1 for prop in properties if prop.get("lat") not in (None, "") and prop.get("lon") not in (None, ""))
    pipeline_value = sum(int(round(_number(prop.get("estimatedValue")))) for prop in properties)
    scores = [_number(_best_assessment(prop)[1].get("score")) for prop in properties if _best_assessment(prop)[0]]
    issues = []
    if not properties:
        issues.append("No customer-visible properties available for territory planning.")
    if any(module not in PILOT_MODULES for module in modules):
        issues.append("Snapshot contains unknown module keys.")

    return {
        "report_type": "homepilot_territory_plan",
        "created_at": utc_now(),
        "status": "pass" if not issues else "review",
        "tenant": {
            "id": tenant.get("id"),
            "name": tenant.get("name"),
            "modules": modules,
        },
        "market_overview": {
            "properties": len(properties),
            "mapped_properties": mapped,
            "mapped_coverage_pct": _percent(mapped, len(properties)),
            "module_count": len(modules),
            "pipeline_value": pipeline_value,
            "average_best_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
            "contacted_properties": sum(status_counts.get(status, 0) for status in CONTACTED_STATUSES),
            "engaged_properties": sum(status_counts.get(status, 0) for status in ENGAGED_STATUSES),
            "status_counts": status_counts,
            "map_bounds": _map_bounds(properties),
        },
        "territory_cells": cells,
        "next_batch_plan": _next_batch(cells),
        "property_queue": queue,
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


def render_markdown(plan: dict[str, Any]) -> str:
    tenant = plan["tenant"]
    overview = plan["market_overview"]
    lines = [
        "# HomePilot Territory Plan",
        "",
        f"Created: {plan['created_at']}",
        f"Status: {plan['status']}",
        f"Tenant: {_first_text(tenant.get('name'), tenant.get('id'), fallback='Unknown')}",
        f"Modules: {', '.join(tenant.get('modules', [])) or 'none'}",
        "",
        "## Market Overview",
        "",
        f"- Properties: {overview['properties']}",
        f"- Mapped coverage: {overview['mapped_coverage_pct']}%",
        f"- Pipeline value: {_money(overview['pipeline_value'])}",
        f"- Average best score: {overview['average_best_score']}",
        f"- Engaged properties: {overview['engaged_properties']}",
        "",
        "## Priority Territories",
        "",
    ]
    for cell in plan["territory_cells"][:8]:
        count = int(cell["property_count"])
        lines.append(
            f"- {cell['city']} / {cell['segment']} / {cell['module_label']}: {count} {_plural(count, 'property', 'properties')}, "
            f"avg score {cell['average_score']}, {_money(cell['pipeline_value'])}, priority {cell['priority_score']}."
        )
    if not plan["territory_cells"]:
        lines.append("- No territory cells available yet.")
    lines += ["", "## Next Batch Plan", ""]
    for row in plan["next_batch_plan"]:
        lines.append(
            f"- P{row['priority']} {row['territory']} with {row['module_label']}: batch {row['recommended_batch_size']}, "
            f"avg score {row['average_score']}. {row['why_now']}"
        )
    if not plan["next_batch_plan"]:
        lines.append("- Import a first scored campaign to generate the next batch plan.")
    lines += ["", "## Property Queue", ""]
    for row in plan["property_queue"][:10]:
        lines.append(
            f"- #{row['rank']} {row['address']} ({row['city']}): {row['module_label']} score {row['score']} "
            f"({_money(row['estimated_value'])}), next: {row['next_action']}"
        )
    if not plan["property_queue"]:
        lines.append("- No property queue available yet.")
    lines += ["", "## Guardrails", ""]
    for key, value in plan["guardrails"].items():
        lines.append(f"- {key}: {_markdown_value(value)}")
    if plan["issues"]:
        lines += ["", "## Issues", ""]
        for issue in plan["issues"]:
            lines.append(f"- {issue}")
    lines.append("")
    return "\n".join(lines)


def build_territory_plan_pack(out_dir: Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = build_territory_plan(snapshot)
    json_path = out_dir / "territory_plan.json"
    markdown_path = out_dir / "TERRITORY_PLAN.md"
    write_json(json_path, plan)
    markdown_path.write_text(render_markdown(plan), encoding="utf-8")
    return {
        "status": plan["status"],
        "paths": {
            "territory_plan": str(json_path),
            "markdown": str(markdown_path),
        },
        "plan": plan,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot territory plan")
    parser.add_argument("--snapshot", required=True, type=Path, help="Tenant-scoped dashboard snapshot JSON")
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    pack = build_territory_plan_pack(args.out_dir, snapshot=snapshot)
    print(json.dumps({
        "status": pack["status"],
        "paths": pack["paths"],
        "tenant": pack["plan"]["tenant"],
        "market_overview": pack["plan"]["market_overview"],
        "territories": len(pack["plan"]["territory_cells"]),
        "issues": pack["plan"]["issues"],
    }, indent=2, ensure_ascii=False))
    if pack["status"] == "review":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
