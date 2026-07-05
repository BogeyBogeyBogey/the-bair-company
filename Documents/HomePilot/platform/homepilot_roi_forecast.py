#!/usr/bin/env python3
"""
Build tenant-scoped ROI and business-case forecasts from a dashboard snapshot.

The forecast is not accounting advice. It gives enterprise buyers a transparent
scenario model that translates visible opportunities into pipeline value,
capacity needs, and expected outcomes using explicit assumptions.
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
CONVERSION_STATUSES = {"appointment", "customer"}

DEFAULT_ASSUMPTIONS = {
    "batch_size": 50,
    "contact_cost_per_property_eur": 4.5,
    "sales_hours_per_contact": 0.12,
    "sales_hours_per_engaged_property": 0.75,
    "gross_margin_pct": 32.0,
    "scenario_rates": {
        "conservative": {"engagement_rate_pct": 3.0, "close_rate_pct": 12.0, "average_deal_capture_pct": 45.0},
        "base": {"engagement_rate_pct": 6.0, "close_rate_pct": 18.0, "average_deal_capture_pct": 55.0},
        "upside": {"engagement_rate_pct": 10.0, "close_rate_pct": 25.0, "average_deal_capture_pct": 65.0},
    },
}


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


def _status_counts(properties: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for prop in properties:
        status = _first_text(prop.get("status"), fallback="generated")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _merge_assumptions(assumptions: dict[str, Any] | None) -> dict[str, Any]:
    merged = json.loads(json.dumps(DEFAULT_ASSUMPTIONS))
    for key, value in (assumptions or {}).items():
        if key == "scenario_rates" and isinstance(value, dict):
            for scenario, rates in value.items():
                if isinstance(rates, dict):
                    merged["scenario_rates"].setdefault(scenario, {}).update(rates)
        else:
            merged[key] = value
    return merged


def _module_mix(properties: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for prop in properties:
        module_key, assessment = _best_assessment(prop)
        if not module_key:
            continue
        row = rows.setdefault(module_key, {
            "module_key": module_key,
            "module_label": MODULE_LABELS.get(module_key, module_key),
            "property_count": 0,
            "score_total": 0.0,
            "pipeline_value": 0,
        })
        row["property_count"] += 1
        row["score_total"] += _number(assessment.get("score"))
        row["pipeline_value"] += int(round(_number(prop.get("estimatedValue"))))
    clean = []
    for row in rows.values():
        count = int(row.pop("property_count"))
        score_total = float(row.pop("score_total"))
        clean.append({
            **row,
            "property_count": count,
            "average_score": round(score_total / count, 1) if count else 0.0,
        })
    return sorted(clean, key=lambda row: (row["pipeline_value"], row["average_score"]), reverse=True)


def _scenario_rows(
    properties: list[dict[str, Any]],
    assumptions: dict[str, Any],
) -> list[dict[str, Any]]:
    total_properties = len(properties)
    visible_pipeline = sum(int(round(_number(prop.get("estimatedValue")))) for prop in properties)
    average_value = visible_pipeline / total_properties if total_properties else 0.0
    contact_cost = _number(assumptions.get("contact_cost_per_property_eur"))
    sales_hours_contact = _number(assumptions.get("sales_hours_per_contact"))
    sales_hours_engaged = _number(assumptions.get("sales_hours_per_engaged_property"))
    gross_margin = _number(assumptions.get("gross_margin_pct")) / 100.0
    rows = []
    for scenario, rates in assumptions["scenario_rates"].items():
        engagement_rate = _number(rates.get("engagement_rate_pct")) / 100.0
        close_rate = _number(rates.get("close_rate_pct")) / 100.0
        capture_rate = _number(rates.get("average_deal_capture_pct")) / 100.0
        expected_engaged = total_properties * engagement_rate
        expected_jobs = expected_engaged * close_rate
        expected_revenue = expected_jobs * average_value * capture_rate
        expected_gross_profit = expected_revenue * gross_margin
        estimated_campaign_cost = total_properties * contact_cost
        estimated_sales_hours = total_properties * sales_hours_contact + expected_engaged * sales_hours_engaged
        net_after_contact_cost = expected_gross_profit - estimated_campaign_cost
        rows.append({
            "scenario": scenario,
            "engagement_rate_pct": round(engagement_rate * 100, 1),
            "close_rate_pct": round(close_rate * 100, 1),
            "average_deal_capture_pct": round(capture_rate * 100, 1),
            "expected_engaged_properties": round(expected_engaged, 2),
            "expected_jobs": round(expected_jobs, 3),
            "expected_revenue": int(round(expected_revenue)),
            "expected_gross_profit": int(round(expected_gross_profit)),
            "estimated_campaign_cost": int(round(estimated_campaign_cost)),
            "estimated_sales_hours": round(estimated_sales_hours, 1),
            "net_after_contact_cost": int(round(net_after_contact_cost)),
        })
    return sorted(rows, key=lambda row: row["expected_revenue"])


def _capacity_plan(properties: list[dict[str, Any]], assumptions: dict[str, Any]) -> dict[str, Any]:
    batch_size = int(_number(assumptions.get("batch_size"), 50)) or 50
    total = len(properties)
    batches = (total + batch_size - 1) // batch_size if total else 0
    base_rates = assumptions["scenario_rates"].get("base", {})
    expected_engaged_per_batch = batch_size * (_number(base_rates.get("engagement_rate_pct")) / 100.0)
    sales_hours = batch_size * _number(assumptions.get("sales_hours_per_contact")) + expected_engaged_per_batch * _number(assumptions.get("sales_hours_per_engaged_property"))
    return {
        "recommended_batch_size": batch_size,
        "estimated_batches": batches,
        "expected_engaged_per_batch_base": round(expected_engaged_per_batch, 1),
        "sales_hours_per_batch_base": round(sales_hours, 1),
        "operational_note": "Review sales capacity before increasing batch size; response memory is only useful when follow-up is timely.",
    }


def build_roi_forecast(snapshot: dict[str, Any], assumptions: dict[str, Any] | None = None) -> dict[str, Any]:
    tenant = snapshot.get("tenant", {}) if isinstance(snapshot.get("tenant"), dict) else {}
    properties = snapshot.get("properties", []) if isinstance(snapshot.get("properties"), list) else []
    modules = list(tenant.get("modules", [])) if isinstance(tenant.get("modules"), list) else []
    if not modules:
        modules = sorted({module for prop in properties for module in (prop.get("assessments") or {})})
    merged_assumptions = _merge_assumptions(assumptions)
    status_counts = _status_counts(properties)
    visible_pipeline = sum(int(round(_number(prop.get("estimatedValue")))) for prop in properties)
    scores = [_number(_best_assessment(prop)[1].get("score")) for prop in properties if _best_assessment(prop)[0]]
    contacted = sum(status_counts.get(status, 0) for status in CONTACTED_STATUSES)
    engaged = sum(status_counts.get(status, 0) for status in ENGAGED_STATUSES)
    converted = sum(status_counts.get(status, 0) for status in CONVERSION_STATUSES)
    issues = []
    if not properties:
        issues.append("No customer-visible properties available for ROI forecast.")
    if any(module not in PILOT_MODULES for module in modules):
        issues.append("Snapshot contains unknown module keys.")

    return {
        "report_type": "homepilot_roi_forecast",
        "created_at": utc_now(),
        "status": "pass" if not issues else "review",
        "not_financial_advice": True,
        "tenant": {
            "id": tenant.get("id"),
            "name": tenant.get("name"),
            "modules": modules,
        },
        "business_case": {
            "properties": len(properties),
            "visible_pipeline_value": visible_pipeline,
            "average_opportunity_value": int(round(visible_pipeline / len(properties))) if properties else 0,
            "average_best_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
            "contacted_properties": contacted,
            "engaged_properties": engaged,
            "converted_properties": converted,
            "observed_engagement_rate_pct": _percent(engaged, contacted or len(properties)),
            "observed_conversion_rate_pct": _percent(converted, contacted or len(properties)),
            "status_counts": status_counts,
        },
        "module_mix": _module_mix(properties),
        "scenario_forecast": _scenario_rows(properties, merged_assumptions),
        "capacity_plan": _capacity_plan(properties, merged_assumptions),
        "assumptions": merged_assumptions,
        "guardrails": {
            "source": "tenant-scoped HomePilot dashboard snapshot",
            "tenant_scoped": True,
            "module_scoped": True,
            "modules_selected": modules,
            "raw_internal_metrics_excluded": True,
            "forecast_requires_customer_review": True,
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
    business = report["business_case"]
    capacity = report["capacity_plan"]
    lines = [
        "# HomePilot ROI Forecast",
        "",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        f"Tenant: {_first_text(tenant.get('name'), tenant.get('id'), fallback='Unknown')}",
        f"Modules: {', '.join(tenant.get('modules', [])) or 'none'}",
        "Not financial advice: yes",
        "",
        "## Business Case",
        "",
        f"- Properties: {business['properties']}",
        f"- Visible pipeline value: {_money(business['visible_pipeline_value'])}",
        f"- Average opportunity value: {_money(business['average_opportunity_value'])}",
        f"- Average best score: {business['average_best_score']}",
        f"- Observed engagement rate: {business['observed_engagement_rate_pct']}%",
        "",
        "## Scenario Forecast",
        "",
    ]
    for row in report["scenario_forecast"]:
        jobs = row["expected_jobs"]
        lines.append(
            f"- {row['scenario']}: {jobs} expected job-equivalents, "
            f"{_money(row['expected_revenue'])} revenue, {_money(row['expected_gross_profit'])} gross profit, "
            f"{row['estimated_sales_hours']} sales hours."
        )
    lines += ["", "## Module Mix", ""]
    for row in report["module_mix"]:
        count = int(row["property_count"])
        lines.append(
            f"- {row['module_label']}: {count} {_plural(count, 'property', 'properties')}, avg score {row['average_score']}, {_money(row['pipeline_value'])}."
        )
    if not report["module_mix"]:
        lines.append("- No module mix available yet.")
    lines += [
        "",
        "## Capacity Plan",
        "",
        f"- Recommended batch size: {capacity['recommended_batch_size']}",
        f"- Estimated batches: {capacity['estimated_batches']}",
        f"- Expected engaged per batch: {capacity['expected_engaged_per_batch_base']}",
        f"- Sales hours per batch: {capacity['sales_hours_per_batch_base']}",
        f"- Note: {capacity['operational_note']}",
        "",
        "## Guardrails",
        "",
    ]
    for key, value in report["guardrails"].items():
        lines.append(f"- {key}: {_markdown_value(value)}")
    if report["issues"]:
        lines += ["", "## Issues", ""]
        for issue in report["issues"]:
            lines.append(f"- {issue}")
    lines.append("")
    return "\n".join(lines)


def build_roi_forecast_pack(
    out_dir: Path,
    snapshot: dict[str, Any],
    assumptions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = build_roi_forecast(snapshot, assumptions=assumptions)
    json_path = out_dir / "roi_forecast.json"
    markdown_path = out_dir / "ROI_FORECAST.md"
    write_json(json_path, report)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return {
        "status": report["status"],
        "paths": {
            "roi_forecast": str(json_path),
            "markdown": str(markdown_path),
        },
        "report": report,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot ROI forecast")
    parser.add_argument("--snapshot", required=True, type=Path, help="Tenant-scoped dashboard snapshot JSON")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--assumptions", type=Path, help="Optional JSON file overriding forecast assumptions")
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    assumptions = json.loads(args.assumptions.read_text(encoding="utf-8")) if args.assumptions else None
    pack = build_roi_forecast_pack(args.out_dir, snapshot=snapshot, assumptions=assumptions)
    print(json.dumps({
        "status": pack["status"],
        "paths": pack["paths"],
        "tenant": pack["report"]["tenant"],
        "business_case": pack["report"]["business_case"],
        "scenarios": len(pack["report"]["scenario_forecast"]),
        "issues": pack["report"]["issues"],
    }, indent=2, ensure_ascii=False))
    if pack["status"] == "review":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
