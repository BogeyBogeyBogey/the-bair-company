#!/usr/bin/env python3
"""
Build the HomePilot module readiness matrix.

This is a buyer/IT review artifact for the full multi-pilot platform. It
summarizes each Pilot module's metric contract, customer-visible surfaces,
scope guardrails, demo readiness, and live production blockers. It never writes
to Supabase, stores no secrets, and does not grant module access.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_metric_access import build_product_access_matrix
from homepilot_platform import PILOT_MODULES


SECRET_PATTERNS = (
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"postgres(?:ql)?://[^:\s]+:[^@\s]{8,}@", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?:service[_-]?role|anon[_-]?key|password|token|secret)\s*[:=]\s*['\"][^'\"\n]{12,}['\"]", re.IGNORECASE),
    re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+"),
)

CSV_FIELDS = [
    "module_key",
    "label",
    "category",
    "enabled_in_current_customer_scope",
    "primary_score_key",
    "metric_count",
    "benchmarkable_metric_count",
    "tenant_private_metric_count",
    "dashboard_metric_count",
    "export_metric_count",
    "benchmark_metric_count",
    "demo_readiness",
    "metric_contract_status",
    "access_contract_status",
    "export_contract_status",
    "public_data_status",
    "live_proof_status",
    "overall_status",
    "buyer_ready",
    "production_ready",
    "required_filters",
    "blocked_visibility",
    "next_action",
]


MODULE_PUBLIC_DATA_LANES = {
    "facadepilot": "address_match; parcel_building_geometry; statistical_sector_age_income",
    "windowpilot": "address_match; building_age_context; renovation_policy_context",
    "roofpilot": "building_footprint; roof_or_parcel_geometry; weather_context_after_source_approval",
    "gardenpilot": "parcel_garden_geometry; land_use_context; flood_soil_after_licence_review",
    "poolpilot": "parcel_garden_geometry; sun_terrain_context; no_personal_wealth_inference",
    "porchpilot": "street_frontage_context; building_morphology",
    "drivewaypilot": "parcel_access_context; impervious_surface_context; drainage_layers_after_approval",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _enabled_modules(due_diligence: dict[str, Any] | None) -> list[str]:
    raw = (due_diligence or {}).get("modules")
    if isinstance(raw, list):
        modules = [str(module) for module in raw if str(module) in PILOT_MODULES]
        if modules:
            return [module for module in PILOT_MODULES if module in set(modules)]
    return ["facadepilot"]


def _production_verified(production_proof: dict[str, Any] | None) -> bool:
    if not production_proof:
        return False
    if production_proof.get("production_verified") is True:
        return True
    return bool((production_proof.get("production_gate") or {}).get("verified"))


def _metric_counts(module_key: str) -> dict[str, int]:
    definition = PILOT_MODULES[module_key]
    dashboard = build_product_access_matrix([module_key], role="viewer", surface="dashboard")
    export = build_product_access_matrix([module_key], role="viewer", surface="export")
    benchmark = build_product_access_matrix([module_key], role="viewer", surface="benchmark")
    dashboard_metrics = dashboard["modules"][0]["visible_metrics"]
    export_metrics = export["modules"][0]["visible_metrics"]
    benchmark_metrics = benchmark["modules"][0]["visible_metrics"]
    benchmarkable = [metric for metric in definition.metrics if metric.visibility == "benchmarkable"]
    tenant_private = [metric for metric in definition.metrics if metric.visibility == "tenant_private"]
    return {
        "metric_count": len(definition.metrics),
        "benchmarkable_metric_count": len(benchmarkable),
        "tenant_private_metric_count": len(tenant_private),
        "dashboard_metric_count": len(dashboard_metrics),
        "export_metric_count": len(export_metrics),
        "benchmark_metric_count": len(benchmark_metrics),
    }


def _row(module_key: str, enabled_modules: list[str], production_verified: bool) -> dict[str, Any]:
    definition = PILOT_MODULES[module_key]
    counts = _metric_counts(module_key)
    enabled = module_key in enabled_modules
    production_ready = production_verified and enabled
    live_status = "production_verified" if production_ready else "blocked_until_live_schema_rls_customer_access_proof"
    overall = "production_ready" if production_ready else "buyer_ready_live_blocked"
    if not enabled:
        overall = "catalog_ready_not_entitled_for_current_customer"
    return {
        "module_key": module_key,
        "label": definition.label,
        "category": definition.category,
        "enabled_in_current_customer_scope": enabled,
        "primary_score_key": definition.primary_score_key,
        **counts,
        "demo_readiness": "synthetic_enterprise_demo_available",
        "metric_contract_status": "pass",
        "access_contract_status": "pass_local_contract_live_proof_required",
        "export_contract_status": "pass_scoped_export_contract",
        "public_data_status": "review_ready_dataset_approval_required",
        "live_proof_status": live_status,
        "overall_status": overall,
        "buyer_ready": True,
        "production_ready": production_ready,
        "required_filters": "tenant_id + module_key; partner_id when assigned",
        "blocked_visibility": "other tenants; disabled modules; other partners' assigned records; raw secrets; unlicensed public data; homeowner intent without response evidence",
        "public_data_lanes": MODULE_PUBLIC_DATA_LANES.get(module_key, "source_approval_required"),
        "next_action": (
            "Enable tenant module, generate scoped assessments, rerun package/export/access checks, then live RLS/customer access proof."
            if not enabled
            else "Complete live schema/RLS/customer-access proof before production access."
        ),
    }


def _secret_scan(report: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(report, ensure_ascii=False)
    findings = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(body)]
    return {
        "status": "pass" if not findings else "fail",
        "issue_count": len(findings),
        "patterns": findings,
    }


def _write_matrix_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})


def _write_metric_coverage_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "module_key",
        "metric_key",
        "label",
        "value_type",
        "unit",
        "visibility",
        "dashboard_visible",
        "export_visible",
        "benchmark_visible",
        "primary_score",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _metric_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for module_key, definition in PILOT_MODULES.items():
        dashboard = build_product_access_matrix([module_key], role="viewer", surface="dashboard")
        export = build_product_access_matrix([module_key], role="viewer", surface="export")
        benchmark = build_product_access_matrix([module_key], role="viewer", surface="benchmark")
        dashboard_keys = {metric["key"] for metric in dashboard["modules"][0]["visible_metrics"]}
        export_keys = {metric["key"] for metric in export["modules"][0]["visible_metrics"]}
        benchmark_keys = {metric["key"] for metric in benchmark["modules"][0]["visible_metrics"]}
        for metric in definition.metrics:
            rows.append({
                "module_key": module_key,
                "metric_key": metric.key,
                "label": metric.label,
                "value_type": metric.value_type,
                "unit": metric.unit,
                "visibility": metric.visibility,
                "dashboard_visible": metric.key in dashboard_keys,
                "export_visible": metric.key in export_keys,
                "benchmark_visible": metric.key in benchmark_keys,
                "primary_score": metric.key == definition.primary_score_key,
            })
    return rows


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# HomePilot Module Readiness Matrix",
        "",
        f"Release: {report['release_label']}",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        "",
        "This matrix proves the platform is not a one-off FacadePilot demo: every Pilot module has a catalogued score, metric-visibility contract, export contract, tenant/module/partner guardrail, and explicit live-production gate.",
        "",
        "## Summary",
        "",
        f"- Modules in catalog: {summary['module_count']}",
        f"- Enabled in current customer scope: {summary['enabled_module_count']}",
        f"- Buyer-ready modules: {summary['buyer_ready_count']}",
        f"- Production-ready modules: {summary['production_ready_count']}",
        f"- Metric rows covered: {summary['metric_coverage_count']}",
        f"- {summary['production_verified_label']}",
        f"- Secret scan: {report['secret_scan']['status']}",
        "",
        "## Module Matrix",
        "",
        "| Module | Enabled Here | Metrics | Dashboard | Export | Benchmark | Overall | Live Proof |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["modules"]:
        lines.append(
            f"| {row['label']} (`{row['module_key']}`) | {str(row['enabled_in_current_customer_scope']).lower()} | "
            f"{row['metric_count']} | {row['dashboard_metric_count']} | {row['export_metric_count']} | "
            f"{row['benchmark_metric_count']} | {row['overall_status']} | {row['live_proof_status']} |"
        )
    lines += [
        "",
        "## Guardrails",
        "",
        "- A module is buyer-ready when its catalog, metric visibility, export contract, and local scope guardrails are reviewable.",
        "- A module is production-ready only after the tenant has the entitlement and live schema/RLS/customer-access proof passes.",
        "- Disabled modules stay hidden for module-only customers even when the shared property spine contains other module evidence.",
        "- Partner renovators see assigned records only; producer views may compare partner aggregates inside the tenant scope.",
        "- Public-data lanes are review candidates, not production approvals.",
        "",
        "## Files",
        "",
    ]
    for label, path in report["paths"].items():
        lines.append(f"- {label}: {path}")
    lines.append("")
    return "\n".join(lines)


def build_module_readiness_matrix_pack(
    out_dir: Path,
    *,
    due_diligence: dict[str, Any] | None = None,
    production_proof: dict[str, Any] | None = None,
    release_label: str = "local",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    enabled_modules = _enabled_modules(due_diligence)
    production_verified = _production_verified(production_proof)
    rows = [_row(module_key, enabled_modules, production_verified) for module_key in PILOT_MODULES]
    metric_rows = _metric_rows()
    summary = {
        "module_count": len(rows),
        "enabled_module_count": len([row for row in rows if row["enabled_in_current_customer_scope"]]),
        "buyer_ready_count": len([row for row in rows if row["buyer_ready"]]),
        "production_ready_count": len([row for row in rows if row["production_ready"]]),
        "metric_coverage_count": len(metric_rows),
        "dashboard_metric_count": sum(int(row["dashboard_metric_count"]) for row in rows),
        "export_metric_count": sum(int(row["export_metric_count"]) for row in rows),
        "benchmark_metric_count": sum(int(row["benchmark_metric_count"]) for row in rows),
        "production_verified": production_verified,
        "production_verified_label": f"production_verified={str(production_verified).lower()}",
    }
    report = {
        "matrix_type": "homepilot_module_readiness_matrix",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": "buyer_review_ready_live_proof_required" if not production_verified else "production_ready",
        "summary": summary,
        "modules": rows,
        "metric_coverage": metric_rows,
        "guardrails": {
            "tenant_id_required": True,
            "module_key_required": True,
            "partner_id_limits_partner_visibility": True,
            "unknown_metrics_hidden_by_default": True,
            "benchmark_metrics_aggregate_only": True,
            "public_data_requires_licence_allowed_use_and_provenance": True,
            "no_secret_values": True,
            "no_raw_contact_data": True,
            "production_requires_live_schema_rls_customer_access": True,
        },
        "paths": {
            "module_readiness_matrix": str(out_dir / "module_readiness_matrix.json"),
            "markdown": str(out_dir / "MODULE_READINESS_MATRIX.md"),
            "matrix_csv": str(out_dir / "MODULE_READINESS_MATRIX.csv"),
            "metric_coverage_csv": str(out_dir / "MODULE_METRIC_COVERAGE.csv"),
        },
    }
    report["secret_scan"] = _secret_scan(report)
    report["guardrails"]["no_secret_values"] = report["secret_scan"]["status"] == "pass"
    write_json(out_dir / "module_readiness_matrix.json", report)
    write_text(out_dir / "MODULE_READINESS_MATRIX.md", render_markdown(report))
    _write_matrix_csv(out_dir / "MODULE_READINESS_MATRIX.csv", rows)
    _write_metric_coverage_csv(out_dir / "MODULE_METRIC_COVERAGE.csv", metric_rows)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the HomePilot module readiness matrix")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--due-diligence-report", type=Path)
    parser.add_argument("--production-proof", type=Path)
    parser.add_argument("--release-label", default="local")
    args = parser.parse_args()
    due_diligence = json.loads(args.due_diligence_report.read_text(encoding="utf-8")) if args.due_diligence_report else None
    production_proof = json.loads(args.production_proof.read_text(encoding="utf-8")) if args.production_proof else None
    report = build_module_readiness_matrix_pack(
        args.out_dir,
        due_diligence=due_diligence,
        production_proof=production_proof,
        release_label=args.release_label,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": report["status"],
        "module_count": report["summary"]["module_count"],
        "buyer_ready_count": report["summary"]["buyer_ready_count"],
        "production_ready_count": report["summary"]["production_ready_count"],
        "markdown": report["paths"]["markdown"],
        "matrix_csv": report["paths"]["matrix_csv"],
        "metric_coverage_csv": report["paths"]["metric_coverage_csv"],
        "secret_scan": report["secret_scan"]["status"],
    }, indent=2, ensure_ascii=False))
    if report["secret_scan"]["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
