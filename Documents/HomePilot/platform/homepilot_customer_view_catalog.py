#!/usr/bin/env python3
"""
Build a customer-facing view catalog for HomePilot.

This is a buyer-review artifact, not an authorization engine. Runtime access is
still enforced by tenant/module/partner scope, Supabase RLS, and customer JWTs.
The catalog makes those scopes readable for DAW-style producer networks, partner
renovators, module-only customers, IT/security, and customer-success users.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_metric_access import ROLE_PERMISSIONS, build_product_access_matrix
from homepilot_platform import PILOT_MODULES


SECRET_PATTERNS = {
    "email_like": re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+"),
    "service_role_key_value": re.compile(r"service[-_ ]?role[-_ ]?key\s*[:=]\s*['\"][^'\"\n]{12,}['\"]", re.IGNORECASE),
    "jwt_like_token": re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}

CSV_FIELDS = [
    "view_key",
    "view_label",
    "audience",
    "default_role",
    "access_scope",
    "module_scope",
    "partner_scope",
    "visible_surfaces",
    "visible_metrics",
    "blocked_visibility",
    "export_policy",
    "live_gate",
    "evidence",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _modules_from_due_diligence(due_diligence: dict[str, Any] | None) -> list[str]:
    raw_modules = (due_diligence or {}).get("modules")
    if isinstance(raw_modules, list):
        modules = [str(module) for module in raw_modules if str(module) in PILOT_MODULES]
    else:
        modules = []
    return modules or ["facadepilot"]


def _module_labels(modules: list[str]) -> str:
    return ", ".join(PILOT_MODULES[module].label for module in modules if module in PILOT_MODULES)


def _module_keys(modules: list[str]) -> str:
    return ", ".join(modules)


def _metric_summary(matrix: dict[str, Any], *, limit_per_module: int = 5) -> str:
    parts = []
    for module in matrix.get("modules", []):
        labels = [str(metric.get("label") or metric.get("key")) for metric in module.get("visible_metrics", [])]
        visible = ", ".join(labels[:limit_per_module])
        suffix = "..." if len(labels) > limit_per_module else ""
        parts.append(f"{module.get('key')}: {visible}{suffix}")
    return "; ".join(parts) if parts else "no customer-visible metrics"


def _hidden_metric_summary(matrix: dict[str, Any], *, limit_per_module: int = 4) -> str:
    parts = []
    for module in matrix.get("modules", []):
        labels = [str(metric.get("label") or metric.get("key")) for metric in module.get("hidden_metrics", [])]
        if labels:
            hidden = ", ".join(labels[:limit_per_module])
            suffix = "..." if len(labels) > limit_per_module else ""
            parts.append(f"{module.get('key')}: {hidden}{suffix}")
    return "; ".join(parts) if parts else "no hidden catalog metrics on this surface"


def _production_verified(production_proof: dict[str, Any] | None) -> bool:
    if not production_proof:
        return False
    if production_proof.get("production_verified") is True:
        return True
    return bool((production_proof.get("production_gate") or {}).get("verified"))


def _partner_access_ready(partner_access_reconciliation: dict[str, Any] | None) -> bool:
    summary = (partner_access_reconciliation or {}).get("summary") or {}
    return (
        (partner_access_reconciliation or {}).get("production_ready") is True
        and int(summary.get("blockers") or 0) == 0
    )


def _portal_runtime_status(portal_manifest: dict[str, Any] | None) -> str:
    if not portal_manifest:
        return "missing_portal_manifest"
    live_runtime = portal_manifest.get("live_runtime") if isinstance(portal_manifest.get("live_runtime"), dict) else {}
    if live_runtime.get("enabled_by_default") is True:
        return "review_required_runtime_enabled"
    if live_runtime.get("status") == "ready_for_customer_auth_config":
        return "static_portal_ready_live_runtime_disabled"
    return str(live_runtime.get("status") or portal_manifest.get("status") or "unknown")


def _live_gate(production_verified: bool, partner_access_ready: bool, view_key: str) -> str:
    if production_verified and (partner_access_ready or view_key != "partner_renovator"):
        return "allowed_after_membership_scope_verified"
    if view_key == "partner_renovator":
        return "blocked_until_live_rls_customer_access_and_partner_reconciliation"
    return "blocked_until_live_schema_rls_customer_access_proof"


def _view(
    *,
    view_key: str,
    view_label: str,
    audience: str,
    default_role: str,
    access_scope: str,
    module_scope: str,
    partner_scope: str,
    visible_surfaces: list[str],
    visible_metrics: str,
    blocked_visibility: list[str],
    export_policy: str,
    live_gate: str,
    evidence: list[str],
) -> dict[str, Any]:
    return {
        "view_key": view_key,
        "view_label": view_label,
        "audience": audience,
        "default_role": default_role,
        "permissions": list(ROLE_PERMISSIONS.get(default_role, ())),
        "access_scope": access_scope,
        "module_scope": module_scope,
        "partner_scope": partner_scope,
        "visible_surfaces": visible_surfaces,
        "visible_metrics": visible_metrics,
        "blocked_visibility": blocked_visibility,
        "export_policy": export_policy,
        "live_gate": live_gate,
        "evidence": evidence,
    }


def build_customer_view_catalog(
    *,
    due_diligence: dict[str, Any] | None,
    readiness: dict[str, Any] | None = None,
    account_access_plan: dict[str, Any] | None = None,
    portal_manifest: dict[str, Any] | None = None,
    partner_access_reconciliation: dict[str, Any] | None = None,
    customer_signoff_reconciliation: dict[str, Any] | None = None,
    production_proof: dict[str, Any] | None = None,
    release_label: str = "local",
) -> dict[str, Any]:
    modules = _modules_from_due_diligence(due_diligence)
    dashboard_matrix = build_product_access_matrix(modules, role="viewer", surface="dashboard")
    export_matrix = build_product_access_matrix(modules, role="viewer", surface="export")
    benchmark_matrix = build_product_access_matrix(modules, role="viewer", surface="benchmark")
    module_keys = _module_keys(modules)
    module_labels = _module_labels(modules)
    dashboard_metrics = _metric_summary(dashboard_matrix)
    export_metrics = _metric_summary(export_matrix)
    benchmark_metrics = _metric_summary(benchmark_matrix)
    hidden_dashboard_metrics = _hidden_metric_summary(dashboard_matrix)
    production_ready = _production_verified(production_proof)
    partner_ready = _partner_access_ready(partner_access_reconciliation)
    signoff_summary = (customer_signoff_reconciliation or {}).get("summary") or {}
    portal_runtime = _portal_runtime_status(portal_manifest)
    account_summary = {
        "status": (account_access_plan or {}).get("status"),
        "review_status": (account_access_plan or {}).get("review_status"),
        "scope_counts": (account_access_plan or {}).get("scope_counts") or {},
        "role_counts": (account_access_plan or {}).get("role_counts") or {},
    }

    common_blocked = [
        "other tenants' raw rows",
        "modules outside the signed tenant entitlement",
        "raw secrets, passwords, tokens, and service-role keys",
        "homeowner intent claims without explicit response evidence",
        "unlicensed public-data fields or blocked owner/contact scraping lanes",
    ]
    views = [
        _view(
            view_key="producer_executive",
            view_label="Producer executive network view",
            audience="DAW executive sponsor, producer leadership, boardroom",
            default_role="owner",
            access_scope="tenant/network aggregate and drilldown inside one customer tenant",
            module_scope=module_keys,
            partner_scope="Can compare partner performance within the DAW tenant; partner raw rows stay partner-scoped.",
            visible_surfaces=[
                "market-readiness.html",
                "boardroom report",
                "executive dashboard",
                "value realization plan",
                "public-data provenance",
            ],
            visible_metrics=dashboard_metrics,
            blocked_visibility=common_blocked + ["raw records from another HomePilot tenant"],
            export_policy="Tenant-scoped exports are allowed after package access audit; partner-specific exports use partner cutdowns.",
            live_gate=_live_gate(production_ready, partner_ready, "producer_executive"),
            evidence=[
                "dashboard access matrix",
                "boardroom report",
                "customer signoff reconciliation",
                "production proof manifest",
            ],
        ),
        _view(
            view_key="network_manager",
            view_label="DAW network manager operating view",
            audience="DAW network manager, campaign owner, customer success",
            default_role="manager",
            access_scope="tenant/network campaign operations",
            module_scope=module_keys,
            partner_scope="Can allocate waves and compare partner queues inside the customer tenant; cannot expose another tenant.",
            visible_surfaces=[
                "DAW first campaign control room",
                "partner wave plan",
                "campaign action board",
                "response and no-response queues",
            ],
            visible_metrics=dashboard_metrics,
            blocked_visibility=common_blocked + ["live outreach before customer go/no-go"],
            export_policy="Operational CSVs are allowed for scoped campaign work; launch exports remain blocked until first-wave gate passes.",
            live_gate=_live_gate(production_ready, partner_ready, "network_manager"),
            evidence=[
                "DAW_FIRST_CAMPAIGN_CONTROL_ROOM.md",
                "FIRST_WAVE_LAUNCH_GATE.md",
                "CUSTOMER_SIGNOFF_RECONCILIATION.md",
            ],
        ),
        _view(
            view_key="partner_renovator",
            view_label="Partner renovator assigned-record view",
            audience="Partner renovator, local sales team, partner account owner",
            default_role="manager",
            access_scope="tenant plus partner_id sub-scope",
            module_scope=module_keys,
            partner_scope="Assigned records only for the partner_id on the membership, campaign, target, or property network metadata.",
            visible_surfaces=[
                "partner cutdown dashboard",
                "assigned property export",
                "own follow-up history",
                "own response backlog",
            ],
            visible_metrics=export_metrics,
            blocked_visibility=common_blocked + [
                "other partner raw addresses, responses, notes, exports, and campaign learnings",
                "producer-level commercial assumptions unless explicitly shared",
            ],
            export_policy="Partner exports must be pre-filtered by tenant_id, module_key, and partner_id before packaging.",
            live_gate=_live_gate(production_ready, partner_ready, "partner_renovator"),
            evidence=[
                "partner cutdown manifest",
                "partner access reconciliation",
                "partner Auth mapping",
                "live RLS customer-access proof",
            ],
        ),
        _view(
            view_key="module_only_customer",
            view_label="Module-only customer view",
            audience="WindowPilot-only, RoofPilot-only, or other single-module customers",
            default_role="viewer",
            access_scope="one tenant plus entitled module rows only",
            module_scope=f"Only the enabled module(s): {module_keys} ({module_labels})",
            partner_scope="No producer-network partner drilldown unless the tenant has partner-scoped memberships.",
            visible_surfaces=[
                "module dashboard",
                "module property export",
                "module campaign metrics",
                "module evidence/provenance",
            ],
            visible_metrics=dashboard_metrics,
            blocked_visibility=common_blocked + ["scores, evidence, campaign rows, and metrics from modules not bought by the customer"],
            export_policy="Exports must include the module_key filter and row count audit.",
            live_gate=_live_gate(production_ready, partner_ready, "module_only_customer"),
            evidence=[
                "homepilot_tenant_modules",
                "dashboard access matrix",
                "export access matrix",
                "customer package manifest",
            ],
        ),
        _view(
            view_key="it_security_reviewer",
            view_label="IT and security reviewer evidence view",
            audience="IT owner, security reviewer, procurement",
            default_role="admin",
            access_scope="evidence room and technical proof, not raw household operations by default",
            module_scope=module_keys,
            partner_scope="Reviews RLS, partner policies, and customer-access evidence without expanding partner data visibility.",
            visible_surfaces=[
                "data dictionary",
                "API contract",
                "processing register",
                "SQL apply plan",
                "production proof",
                "live readiness",
            ],
            visible_metrics="contract metadata, table/view definitions, access checks, redacted proof hashes",
            blocked_visibility=common_blocked + ["privileged credentials in files or browser assets"],
            export_policy="Technical artifacts are shareable when redacted; raw customer data exports require tenant/module/partner scope.",
            live_gate=_live_gate(production_ready, partner_ready, "it_security_reviewer"),
            evidence=[
                "PROCUREMENT_SECURITY_REVIEW.md",
                "API_CONTRACT.md",
                "PRODUCTION_PROOF.md",
                "schema verification report",
            ],
        ),
        _view(
            view_key="customer_success_operator",
            view_label="Customer-success and adoption view",
            audience="Customer success, training lead, HomePilot operator",
            default_role="manager",
            access_scope="tenant-scoped rollout and training operations",
            module_scope=module_keys,
            partner_scope="Can guide partners through assigned-record workflows without seeing or sharing blocked partner data.",
            visible_surfaces=[
                "customer rollout plan",
                "training guide",
                "role cheatsheet",
                "customer decision board",
                "support SLA plan",
            ],
            visible_metrics="adoption tasks, decision status, support owners, value-realization denominators, scoped campaign outcomes",
            blocked_visibility=common_blocked + ["secret values and raw personal contact details in templates"],
            export_policy="Training and decision CSVs are shareable; real contact data stays in approved customer systems or secret channels.",
            live_gate=_live_gate(production_ready, partner_ready, "customer_success_operator"),
            evidence=[
                "CUSTOMER_ROLLOUT_PLAN.md",
                "CUSTOMER_TRAINING_GUIDE.md",
                "ROLE_CHEATSHEET.csv",
                "CUSTOMER_SIGNOFF_INTAKE.md",
            ],
        ),
        _view(
            view_key="benchmark_reader",
            view_label="Benchmark-safe learning view",
            audience="Boardroom, analyst, product owner",
            default_role="viewer",
            access_scope="aggregate benchmark cohorts only",
            module_scope=module_keys,
            partner_scope="No partner raw rows; partner comparisons stay inside the same tenant unless anonymized cohort thresholds are met.",
            visible_surfaces=[
                "benchmark metric catalog",
                "aggregate cohort trends",
                "autoresearch evidence",
                "intelligence lab report",
            ],
            visible_metrics=benchmark_metrics,
            blocked_visibility=common_blocked + [
                hidden_dashboard_metrics,
                "raw cross-customer learnings below anonymization or cohort thresholds",
            ],
            export_policy="Benchmark exports must be aggregate-only and exclude direct tenant, partner, address, response, and note identifiers.",
            live_gate="blocked_until_benchmark_anonymization_thresholds_and_policy_are_approved",
            evidence=[
                "benchmark access matrix",
                "INTELLIGENCE_LAB.md",
                "metric visibility policy",
            ],
        ),
    ]

    live_access_ready = production_ready and partner_ready
    secret_scan_text = json.dumps(views, ensure_ascii=False)
    secret_findings = [
        {"pattern": label}
        for label, pattern in SECRET_PATTERNS.items()
        if pattern.search(secret_scan_text)
    ]
    status = (
        "production_access_catalog_ready"
        if live_access_ready and not secret_findings
        else "buyer_review_ready_live_access_blocked"
    )
    return {
        "report_type": "homepilot_customer_view_catalog",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": status,
        "modules": modules,
        "summary": {
            "view_count": len(views),
            "module_count": len(modules),
            "module_keys": modules,
            "production_verified": production_ready,
            "partner_access_ready": partner_ready,
            "live_access_ready": live_access_ready,
            "portal_runtime_status": portal_runtime,
            "customer_signoff_status": (customer_signoff_reconciliation or {}).get("status"),
            "signed_decision_count": int(signoff_summary.get("signed_decision_count") or 0),
            "decision_count": int(signoff_summary.get("decision_count") or 0),
            "account_access_status": account_summary["status"],
            "account_access_review_status": account_summary["review_status"],
        },
        "views": views,
        "metric_access": {
            "dashboard": dashboard_matrix,
            "export": export_matrix,
            "benchmark": benchmark_matrix,
        },
        "account_access": account_summary,
        "guardrails": {
            "tenant_id_required": True,
            "module_key_required": True,
            "partner_id_limits_partner_visibility": True,
            "unknown_metrics_hidden_from_customer_surfaces": True,
            "no_cross_tenant_raw_data": True,
            "no_cross_partner_raw_data_for_partner_users": True,
            "no_raw_contacts_or_secrets": True,
            "no_homeowner_intent_without_explicit_response": True,
            "live_rls_customer_access_proof_required": True,
            "catalog_is_not_runtime_authorization": True,
        },
        "secret_scan": {
            "status": "pass" if not secret_findings else "fail",
            "findings": secret_findings,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# HomePilot Customer View Catalog",
        "",
        f"Created: {report['created_at']}",
        f"Release: {report['release_label']}",
        f"Status: {report['status']}",
        f"Modules: {', '.join(report['modules'])}",
        "",
        "This catalog explains which customer-facing lens sees which HomePilot data. It is not a runtime authorization engine; Supabase RLS, customer JWTs, tenant/module entitlements, and partner_id scope remain authoritative.",
        "",
        "## Summary",
        "",
        f"- Views: {summary['view_count']}",
        f"- Live access ready: {str(summary['live_access_ready']).lower()}",
        f"- Production verified: {str(summary['production_verified']).lower()}",
        f"- Partner access ready: {str(summary['partner_access_ready']).lower()}",
        f"- Portal runtime: {summary['portal_runtime_status']}",
        f"- Customer signoff: {summary['signed_decision_count']}/{summary['decision_count']} decisions signed",
        "",
        "## View Matrix",
        "",
        "| View | Audience | Scope | Module Scope | Partner Scope | Live Gate |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["views"]:
        lines.append(
            f"| {row['view_label']} | {row['audience']} | {row['access_scope']} | {row['module_scope']} | {row['partner_scope']} | {row['live_gate']} |"
        )
    lines += [
        "",
        "## Blocked Visibility",
        "",
    ]
    for row in report["views"]:
        blocked = "; ".join(row["blocked_visibility"])
        lines.append(f"- {row['view_label']}: {blocked}")
    lines += [
        "",
        "## Metric Visibility",
        "",
    ]
    for surface, matrix in report["metric_access"].items():
        lines.append(f"### {surface.title()}")
        lines.append("")
        for module in matrix["modules"]:
            visible = ", ".join(metric["key"] for metric in module["visible_metrics"]) or "none"
            hidden = ", ".join(metric["key"] for metric in module["hidden_metrics"]) or "none"
            lines.append(f"- {module['key']}: visible `{visible}`; hidden `{hidden}`")
        lines.append("")
    lines += [
        "## Guardrails",
        "",
    ]
    for key, value in report["guardrails"].items():
        lines.append(f"- {key}: {str(value).lower()}")
    lines.append("")
    return "\n".join(lines)


def write_matrix_csv(path: Path, views: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in views:
            writer.writerow({
                "view_key": row["view_key"],
                "view_label": row["view_label"],
                "audience": row["audience"],
                "default_role": row["default_role"],
                "access_scope": row["access_scope"],
                "module_scope": row["module_scope"],
                "partner_scope": row["partner_scope"],
                "visible_surfaces": "; ".join(row["visible_surfaces"]),
                "visible_metrics": row["visible_metrics"],
                "blocked_visibility": "; ".join(row["blocked_visibility"]),
                "export_policy": row["export_policy"],
                "live_gate": row["live_gate"],
                "evidence": "; ".join(row["evidence"]),
            })


def build_customer_view_catalog_pack(
    *,
    out_dir: Path,
    due_diligence: dict[str, Any] | None,
    readiness: dict[str, Any] | None = None,
    account_access_plan: dict[str, Any] | None = None,
    portal_manifest: dict[str, Any] | None = None,
    partner_access_reconciliation: dict[str, Any] | None = None,
    customer_signoff_reconciliation: dict[str, Any] | None = None,
    production_proof: dict[str, Any] | None = None,
    release_label: str = "local",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = build_customer_view_catalog(
        due_diligence=due_diligence,
        readiness=readiness,
        account_access_plan=account_access_plan,
        portal_manifest=portal_manifest,
        partner_access_reconciliation=partner_access_reconciliation,
        customer_signoff_reconciliation=customer_signoff_reconciliation,
        production_proof=production_proof,
        release_label=release_label,
    )
    paths = {
        "customer_view_catalog": str(out_dir / "customer_view_catalog.json"),
        "customer_view_catalog_markdown": str(out_dir / "CUSTOMER_VIEW_CATALOG.md"),
        "customer_view_matrix": str(out_dir / "CUSTOMER_VIEW_MATRIX.csv"),
    }
    report["paths"] = paths
    write_json(Path(paths["customer_view_catalog"]), report)
    write_text(Path(paths["customer_view_catalog_markdown"]), render_markdown(report))
    write_matrix_csv(Path(paths["customer_view_matrix"]), report["views"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot customer view catalog")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--due-diligence-report", required=True, type=Path)
    parser.add_argument("--readiness-report", type=Path)
    parser.add_argument("--account-access-plan", type=Path)
    parser.add_argument("--portal-manifest", type=Path)
    parser.add_argument("--partner-access-reconciliation", type=Path)
    parser.add_argument("--customer-signoff-reconciliation", type=Path)
    parser.add_argument("--production-proof", type=Path)
    parser.add_argument("--release-label", default="local")
    args = parser.parse_args()
    report = build_customer_view_catalog_pack(
        out_dir=args.out_dir,
        due_diligence=load_json(args.due_diligence_report),
        readiness=load_json(args.readiness_report),
        account_access_plan=load_json(args.account_access_plan),
        portal_manifest=load_json(args.portal_manifest),
        partner_access_reconciliation=load_json(args.partner_access_reconciliation),
        customer_signoff_reconciliation=load_json(args.customer_signoff_reconciliation),
        production_proof=load_json(args.production_proof),
        release_label=args.release_label,
    )
    print(json.dumps({
        "status": report["status"],
        "modules": report["modules"],
        "view_count": report["summary"]["view_count"],
        "paths": report["paths"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
