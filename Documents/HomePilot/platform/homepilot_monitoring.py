#!/usr/bin/env python3
"""
Build HomePilot monitoring and alerting evidence.

This is the operating contract for a live customer workspace: which signals are
watched, which evidence source proves them, who owns the response, and what
still blocks production monitoring. It is intentionally safe to run locally and
does not read or write live credentials.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _gate_map(readiness: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not readiness:
        return {}
    return {str(gate.get("name")): gate for gate in readiness.get("gates", [])}


def _gate_status(gates: dict[str, dict[str, Any]], name: str) -> str:
    gate = gates.get(name)
    if not gate:
        return "missing"
    return str(gate.get("status") or "missing")


def _gate_path(gates: dict[str, dict[str, Any]], name: str) -> str | None:
    gate = gates.get(name) or {}
    for key in ("output", "manifest", "launch_report", "readme"):
        if gate.get(key):
            return str(gate[key])
    return None


def _live_verified(
    schema_verification: dict[str, Any] | None,
    launch: dict[str, Any] | None,
    customer_access: dict[str, Any] | None,
) -> bool:
    return bool(
        schema_verification
        and schema_verification.get("production_verified") is True
        and launch
        and launch.get("production_verified") is True
        and customer_access
        and customer_access.get("production_verified") is True
    )


def _read_json_if_exists(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    source = Path(path)
    if not source.exists() or not source.is_file():
        return None
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _watch(
    key: str,
    label: str,
    source_gate: str,
    gates: dict[str, dict[str, Any]],
    owner: str,
    severity: str,
    cadence: str,
    alert_condition: str,
    remediation: str,
    production_required: bool = False,
    production_status: str = "ready",
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gate_status = _gate_status(gates, source_gate)
    current_status = "pass" if gate_status == "pass" else "warn" if gate_status in {"skipped", "missing"} else "fail"
    return {
        "key": key,
        "label": label,
        "owner": owner,
        "severity": severity,
        "cadence": cadence,
        "source_gate": source_gate,
        "source_status": gate_status,
        "source_path": _gate_path(gates, source_gate),
        "current_status": current_status,
        "production_required": production_required,
        "production_status": production_status,
        "alert_condition": alert_condition,
        "remediation": remediation,
        "metrics": metrics or {},
    }


def _csv_rows(watches: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for watch in watches:
        rows.append({
            "key": watch["key"],
            "label": watch["label"],
            "owner": watch["owner"],
            "severity": watch["severity"],
            "cadence": watch["cadence"],
            "source_gate": watch["source_gate"],
            "current_status": watch["current_status"],
            "production_status": watch["production_status"],
            "alert_condition": watch["alert_condition"],
            "remediation": watch["remediation"],
        })
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "key",
        "label",
        "owner",
        "severity",
        "cadence",
        "source_gate",
        "current_status",
        "production_status",
        "alert_condition",
        "remediation",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _secret_scan(paths: list[Path]) -> list[str]:
    markers = ["service-role", "secret-token", "authorization: bearer", "supabase_service_role"]
    findings = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        body = path.read_text(encoding="utf-8", errors="ignore").lower()
        for marker in markers:
            if marker in body:
                findings.append(f"{path}: contains {marker}")
    return findings


def build_monitoring_plan(
    readiness: dict[str, Any] | None,
    schema_verification: dict[str, Any] | None = None,
    launch: dict[str, Any] | None = None,
    customer_access: dict[str, Any] | None = None,
    release_label: str = "local",
) -> dict[str, Any]:
    gates = _gate_map(readiness)
    production_verified = _live_verified(schema_verification, launch, customer_access)
    sync_report = _read_json_if_exists(_gate_path(gates, "sales_integration_sync_smoke"))
    sync_live_calls = bool(sync_report and sync_report.get("summary", {}).get("live_api_calls_made"))
    sync_failures = int(sync_report.get("summary", {}).get("failed", 0)) if sync_report else None

    production_status = "verified" if production_verified else "blocked_until_live_schema_rls_and_customer_access_proof"
    watches = [
        _watch(
            "live_schema_contract",
            "Live database schema and RLS policy contract",
            "schema_verification_smoke",
            gates,
            owner="Platform Ops",
            severity="critical",
            cadence="after every schema migration and before every production launch",
            alert_condition="Live metadata misses expected HomePilot tables, columns, security-invoker views, functions, RLS enablement, or policies.",
            remediation="Pause production launch, apply/review SQL migrations, rerun live schema verification, and archive schema_verification.json.",
            production_required=True,
            production_status="verified" if schema_verification and schema_verification.get("production_verified") is True else "requires_live_schema_verification",
            metrics={
                "schema_verification_status": schema_verification.get("status") if schema_verification else None,
                "schema_contract_status": schema_verification.get("contract_status") if schema_verification else None,
                "schema_live_status": schema_verification.get("live_status") if schema_verification else None,
            },
        ),
        _watch(
            "tenant_access_rls",
            "Tenant and module RLS isolation",
            "customer_access_verification_smoke",
            gates,
            owner="Platform Ops",
            severity="critical",
            cadence="before launch, after membership changes, weekly in production",
            alert_condition="Any customer JWT can read another tenant, disabled module, or hidden metric.",
            remediation="Disable customer access, revoke affected membership, rerun RLS probe, and archive incident evidence.",
            production_required=True,
            production_status=production_status,
            metrics={
                "schema_production_verified": bool(schema_verification and schema_verification.get("production_verified") is True),
                "launch_production_verified": bool(launch and launch.get("production_verified") is True),
                "customer_access_production_verified": bool(customer_access and customer_access.get("production_verified") is True),
            },
        ),
        _watch(
            "portal_auth_runtime",
            "Customer portal Auth/RLS runtime",
            "customer_portal_smoke",
            gates,
            owner="Platform Ops",
            severity="critical",
            cadence="before each deploy and after runtime config changes",
            alert_condition="Portal bundle misses live config, live loader, security headers, or tenant-scoped assets.",
            remediation="Rebuild portal bundle from the scoped customer package and rerun readiness.",
            production_required=True,
            production_status="verified" if production_verified else "ready_for_customer_auth_config",
        ),
        _watch(
            "portal_hosting_exposure",
            "Customer portal hosting and access control",
            "portal_hosting_smoke",
            gates,
            owner="Platform Ops",
            severity="critical",
            cadence="before every hosted release and after access-control changes",
            alert_condition="Static tenant snapshot is hosted without private access control, no-store cache policy, or hosted customer access verification.",
            remediation="Disable public route, deploy reviewed hosting bundle, verify cache headers, and rerun customer access verification against the hosted URL.",
            production_required=True,
            production_status="blocked_until_hosted_access_control_and_url_proof",
        ),
        _watch(
            "crm_webhook_delivery",
            "CRM/webhook delivery health",
            "sales_integration_sync_smoke",
            gates,
            owner="Revenue Ops",
            severity="high",
            cadence="per campaign batch and daily while campaigns are active",
            alert_condition="Dead letters, failed webhook attempts, duplicate idempotency keys, or missing live CRM sync report.",
            remediation="Pause CRM handoff, inspect dead_letter.jsonl, replay by idempotency key after customer CRM owner approves.",
            production_required=True,
            production_status="verified" if sync_live_calls and sync_failures == 0 else "needs_live_customer_crm_run",
            metrics={
                "dry_run_or_live_status": sync_report.get("mode") if sync_report else None,
                "live_api_calls_made": sync_live_calls,
                "failed_deliveries": sync_failures,
                "dead_letters": sync_report.get("summary", {}).get("dead_letters") if sync_report else None,
            },
        ),
        _watch(
            "data_quality_freshness",
            "Property data quality and freshness",
            "data_quality_smoke",
            gates,
            owner="Data Ops",
            severity="high",
            cadence="per import, per enrichment refresh, and before customer handoff",
            alert_condition="Missing coordinates, missing evidence, duplicate properties, stale source run, or low target coverage.",
            remediation="Quarantine affected import batch, rebuild source ledger, and rerun data quality before export.",
        ),
        _watch(
            "source_provenance",
            "Evidence source ledger and provenance",
            "source_ledger_smoke",
            gates,
            owner="Data Ops",
            severity="high",
            cadence="per package and after every vendor/source refresh",
            alert_condition="Missing source run, confidence, timestamp, evidence reference, or safe lead-claim guardrail.",
            remediation="Mark affected records review_required and remove them from outreach exports until provenance is restored.",
        ),
        _watch(
            "compliance_retention",
            "Outreach compliance and retention lifecycle",
            "compliance_smoke",
            gates,
            owner="Compliance Ops",
            severity="critical",
            cadence="before outreach activation and monthly while records are retained",
            alert_condition="Missing contact basis, opt-out method, unsafe intent claim, or do-not-contact propagation failure.",
            remediation="Pause outreach for affected tenant/module, apply suppression list, and rebuild compliance and retention reports.",
        ),
        _watch(
            "retention_reviews",
            "Retention review schedule",
            "retention_smoke",
            gates,
            owner="Compliance Ops",
            severity="medium",
            cadence="weekly review of due retention actions",
            alert_condition="Contacted records exceed retention review date or delete-plan triggers are overdue.",
            remediation="Generate delete plans, confirm customer retention policy, and archive export/audit evidence.",
        ),
        _watch(
            "vendor_enrichment_backlog",
            "Vendor enrichment backlog",
            "data_vendor_enrichment_smoke",
            gates,
            owner="Data Partnerships",
            severity="medium",
            cadence="before territory expansion and after vendor contract changes",
            alert_condition="Required parcel, geocode, imagery, energy, permit, pricing, or contact-provenance source is missing.",
            remediation="Keep missing sources out of automated scoring, update backlog owner, and rerun enrichment pack.",
        ),
        _watch(
            "vendor_refresh_delivery",
            "Vendor/API enrichment refresh delivery",
            "data_vendor_refresh_smoke",
            gates,
            owner="Data Partnerships",
            severity="high",
            cadence="per enrichment batch and after vendor/API contract changes",
            alert_condition="Refresh run has failed delivery attempts, dead letters, missing idempotency, or live endpoint not approved.",
            remediation="Pause enrichment merge, inspect dead_letter.jsonl, replay by idempotency key after vendor/customer approval.",
            production_required=True,
            production_status="needs_live_vendor_refresh_run",
        ),
        _watch(
            "visual_scale_readiness",
            "Map clusters and second-brain render budget",
            "visual_intelligence_smoke",
            gates,
            owner="Product Ops",
            severity="medium",
            cadence="before enterprise demos, before large territory imports, and after dashboard visual changes",
            alert_condition="Visual scale smoke missing, graph exceeds render budget, or map cannot switch from points to clusters.",
            remediation="Rebuild visual intelligence pack, review top clusters/hubs, and keep large territories on clustered map view.",
        ),
        _watch(
            "export_audit_trail",
            "Customer exports and audit trail",
            "audit_trail_smoke",
            gates,
            owner="Customer Ops",
            severity="medium",
            cadence="per export and before external sharing",
            alert_condition="Export lacks audit event, export log, access audit, or tenant/module scoped manifest.",
            remediation="Regenerate package with audit_payload enabled and share only the new package.",
        ),
        _watch(
            "benchmark_privacy",
            "Aggregate benchmark privacy",
            "benchmark_privacy_smoke",
            gates,
            owner="Data Ops",
            severity="medium",
            cadence="per benchmark refresh",
            alert_condition="Aggregate row leaks tenant, property, address, or cohort below minimum sample threshold.",
            remediation="Suppress benchmark output and rebuild with thresholded cohorts only.",
        ),
    ]

    counts = {
        "watches": len(watches),
        "pass": sum(1 for watch in watches if watch["current_status"] == "pass"),
        "warn": sum(1 for watch in watches if watch["current_status"] == "warn"),
        "fail": sum(1 for watch in watches if watch["current_status"] == "fail"),
        "production_required": sum(1 for watch in watches if watch["production_required"]),
        "production_verified": sum(1 for watch in watches if watch["production_status"] == "verified"),
    }
    production_blockers = [
        watch["key"]
        for watch in watches
        if watch["production_required"] and watch["production_status"] != "verified"
    ]
    if counts["fail"]:
        status = "action_required"
    elif production_verified and not production_blockers:
        status = "production_monitoring_ready"
    else:
        status = "buyer_review_monitoring_ready"

    return {
        "report_type": "homepilot_monitoring_plan",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": status,
        "production_gate": {
            "verified": production_verified,
            "blockers": production_blockers,
            "required": "Live schema verification, live Supabase RLS proof, customer access verification, and customer CRM sync report before production monitoring is complete.",
        },
        "summary": counts,
        "watches": watches,
    }


def render_runbook(plan: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Monitoring Runbook",
        "",
        f"Release: {plan['release_label']}",
        f"Created: {plan['created_at']}",
        f"Status: {plan['status']}",
        f"Production verified: {str(plan['production_gate']['verified']).lower()}",
        "",
        "## Monitoring Contract",
        "",
    ]
    for watch in plan["watches"]:
        lines.extend([
            f"### {watch['label']}",
            "",
            f"- Key: {watch['key']}",
            f"- Owner: {watch['owner']}",
            f"- Severity: {watch['severity']}",
            f"- Cadence: {watch['cadence']}",
            f"- Source gate: {watch['source_gate']} ({watch['source_status']})",
            f"- Current status: {watch['current_status']}",
            f"- Production status: {watch['production_status']}",
            f"- Alert condition: {watch['alert_condition']}",
            f"- Remediation: {watch['remediation']}",
            "",
        ])
    lines += ["## Production Blockers", ""]
    blockers = plan["production_gate"]["blockers"]
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- None.")
    lines.append("")
    return "\n".join(lines)


def build_monitoring_pack(
    out_dir: Path,
    readiness: dict[str, Any],
    schema_verification: dict[str, Any] | None = None,
    launch: dict[str, Any] | None = None,
    customer_access: dict[str, Any] | None = None,
    release_label: str = "local",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = build_monitoring_plan(
        readiness=readiness,
        schema_verification=schema_verification,
        launch=launch,
        customer_access=customer_access,
        release_label=release_label,
    )
    plan_path = out_dir / "monitoring_plan.json"
    runbook_path = out_dir / "MONITORING_RUNBOOK.md"
    alert_matrix_path = out_dir / "alert_matrix.csv"
    write_json(plan_path, plan)
    write_text(runbook_path, render_runbook(plan))
    write_csv(alert_matrix_path, _csv_rows(plan["watches"]))
    findings = _secret_scan([plan_path, runbook_path, alert_matrix_path])
    if findings:
        plan["status"] = "action_required"
        plan["secret_scan"] = {"status": "fail", "findings": findings}
        write_json(plan_path, plan)
        write_text(runbook_path, render_runbook(plan))
    else:
        plan["secret_scan"] = {"status": "pass", "findings": []}
        write_json(plan_path, plan)
    return {
        "status": plan["status"],
        "paths": {
            "monitoring_plan": str(plan_path),
            "runbook": str(runbook_path),
            "alert_matrix": str(alert_matrix_path),
        },
        "plan": plan,
    }


def build_monitoring_pack_from_files(
    out_dir: Path,
    readiness_report_path: Path,
    schema_verification_report_path: Path | None = None,
    launch_report_path: Path | None = None,
    customer_access_report_path: Path | None = None,
    release_label: str = "local",
) -> dict[str, Any]:
    return build_monitoring_pack(
        out_dir=out_dir,
        readiness=load_json(readiness_report_path) or {},
        schema_verification=load_json(schema_verification_report_path),
        launch=load_json(launch_report_path),
        customer_access=load_json(customer_access_report_path),
        release_label=release_label,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HomePilot monitoring and alerting evidence")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--readiness-report", required=True, type=Path)
    parser.add_argument("--schema-verification-report", type=Path)
    parser.add_argument("--launch-report", type=Path)
    parser.add_argument("--customer-access-report", type=Path)
    parser.add_argument("--release-label", default="local")
    args = parser.parse_args()
    pack = build_monitoring_pack_from_files(
        out_dir=args.out_dir,
        readiness_report_path=args.readiness_report,
        schema_verification_report_path=args.schema_verification_report,
        launch_report_path=args.launch_report,
        customer_access_report_path=args.customer_access_report,
        release_label=args.release_label,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": pack["status"],
        "production_gate": pack["plan"]["production_gate"],
        "monitoring_plan": pack["paths"]["monitoring_plan"],
        "runbook": pack["paths"]["runbook"],
        "alert_matrix": pack["paths"]["alert_matrix"],
    }, indent=2, ensure_ascii=False))
    if pack["status"] == "action_required":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
