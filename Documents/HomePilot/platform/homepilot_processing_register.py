#!/usr/bin/env python3
"""
Build the HomePilot data processing and privacy register.

This is not legal advice. It is a structured enterprise review artifact that
summarizes processing purposes, data categories, retention controls, risks, and
technical safeguards for the HomePilot property intelligence platform.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_data_dictionary import PRIVACY_RULES, TABLE_CATALOG
from homepilot_metric_access import SURFACE_VISIBILITY
from homepilot_platform import PILOT_MODULES


DATA_CATEGORIES: tuple[dict[str, Any], ...] = (
    {
        "key": "tenant_account",
        "label": "Tenant account and product scope",
        "examples": ["tenant id", "tenant name", "enabled modules", "subscription tier", "data region"],
        "personal_data": False,
        "customer_visible": True,
    },
    {
        "key": "membership_access",
        "label": "User membership and role metadata",
        "examples": ["auth user id", "role", "tenant membership"],
        "personal_data": True,
        "customer_visible": "admin surfaces only",
    },
    {
        "key": "property_identity",
        "label": "Property identity and location",
        "examples": ["address", "postcode", "city", "lat", "lon", "property type"],
        "personal_data": "context-dependent",
        "customer_visible": True,
    },
    {
        "key": "renovation_signals",
        "label": "Renovation opportunity signals",
        "examples": ["scores", "grades", "visible counts", "recommended renovation type", "evidence references"],
        "personal_data": "context-dependent",
        "customer_visible": True,
    },
    {
        "key": "campaign_memory",
        "label": "Campaign and response memory",
        "examples": ["campaign status", "interaction type", "response status", "sentiment", "objection code", "next action"],
        "personal_data": True,
        "customer_visible": True,
    },
    {
        "key": "commercial_estimates",
        "label": "Commercial opportunity estimates",
        "examples": ["estimated value", "pipeline value", "project value", "deal value"],
        "personal_data": False,
        "customer_visible": True,
    },
    {
        "key": "audit_and_exports",
        "label": "Audit, export, and operator evidence",
        "examples": ["export log", "row count", "filters", "audit event", "access audit outcome"],
        "personal_data": "limited operator metadata possible",
        "customer_visible": "tenant-scoped reports only",
    },
    {
        "key": "aggregate_benchmarks",
        "label": "Aggregate benchmark cohorts",
        "examples": ["module", "region", "score averages", "response rates", "sample size"],
        "personal_data": False,
        "customer_visible": "aggregate only",
    },
)


PROCESSING_ACTIVITIES: tuple[dict[str, Any], ...] = (
    {
        "key": "tenant_access_management",
        "purpose": "Provision tenants, enabled modules, user memberships, roles, and product entitlements.",
        "tables": ["homepilot_tenants", "homepilot_tenant_modules", "homepilot_memberships"],
        "data_categories": ["tenant_account", "membership_access"],
        "lawful_basis_review": "customer contract, account administration, and explicit tenant membership configuration",
        "retention": "retain while tenant is active; remove memberships when access ends",
        "customer_surface": "admin handoff manifests and access matrices",
    },
    {
        "key": "property_intelligence",
        "purpose": "Score and explain renovation opportunities across enabled Pilot modules.",
        "tables": ["homepilot_properties", "homepilot_assessments", "homepilot_property_media"],
        "data_categories": ["property_identity", "renovation_signals", "commercial_estimates"],
        "lawful_basis_review": "customer-supplied data, public/business record review, customer request, or legitimate interest review depending on source",
        "retention": "retain while useful for active customer campaigns; review contacted records through retention controls",
        "customer_surface": "dashboard, property profile, exports, API read models",
    },
    {
        "key": "campaign_outreach_memory",
        "purpose": "Track campaign targeting, touchpoints, responses, objections, and next actions.",
        "tables": ["homepilot_campaigns", "homepilot_campaign_targets", "homepilot_interactions", "homepilot_response_insights"],
        "data_categories": ["campaign_memory", "property_identity", "commercial_estimates"],
        "lawful_basis_review": "must be reviewed per campaign using contact_basis/source_provenance/opt_out metadata",
        "retention": "contacted rows require retention_review_at or delete_after metadata",
        "customer_surface": "campaign intelligence, property timelines, exports, API read models",
    },
    {
        "key": "customer_exports_and_audit",
        "purpose": "Generate customer handoff packages, export logs, access audit reports, and audit trails.",
        "tables": ["homepilot_exports", "homepilot_audit_events"],
        "data_categories": ["audit_and_exports", "tenant_account"],
        "lawful_basis_review": "accountability, customer contract, security review, and operational auditability",
        "retention": "retain as review evidence during customer contract and audit window",
        "customer_surface": "customer packages, due-diligence packs, release evidence bundles",
    },
    {
        "key": "aggregate_learning",
        "purpose": "Publish privacy-safe platform benchmarks and cross-customer learnings.",
        "tables": ["homepilot_platform_benchmarks"],
        "data_categories": ["aggregate_benchmarks"],
        "lawful_basis_review": "aggregate-only analytics with minimum cohort thresholds and identifier validation",
        "retention": "retain aggregate cohorts while thresholds and validation remain satisfied",
        "customer_surface": "benchmark surfaces only",
    },
)


CONTROL_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "key": "tenant_rls",
        "control": "Tenant isolation is enforced by RLS and homepilot_has_tenant_access.",
        "evidence": ["supabase_schema.sql", "dashboard_views.sql", "homepilot_rls_probe.py"],
    },
    {
        "key": "module_entitlements",
        "control": "Module visibility is enforced by tenant module entitlements and homepilot_has_module_access.",
        "evidence": ["homepilot_entitlements.py", "homepilot_metric_access.py", "dashboard_views.sql"],
    },
    {
        "key": "metric_visibility",
        "control": "Customer metrics are filtered by visibility; unknown keys are hidden by default.",
        "evidence": ["homepilot_metric_access.py", "homepilot_metrics_for_customer", "access_audit.json"],
    },
    {
        "key": "outreach_compliance",
        "control": "Outreach records are audited for contact basis, source provenance, opt-out handling, retention metadata, and safe claim language.",
        "evidence": ["homepilot_compliance.py", "compliance_report.json"],
    },
    {
        "key": "retention_lifecycle",
        "control": "Contacted rows are audited for retention schedules and delete-plan triggers.",
        "evidence": ["homepilot_retention.py", "homepilot_privacy.py"],
    },
    {
        "key": "aggregate_thresholds",
        "control": "Cross-customer benchmarks require aggregate rows, minimum sample sizes, and no direct identifiers.",
        "evidence": ["homepilot_benchmarks.py", "homepilot_platform_benchmarks sample_size >= 10"],
    },
    {
        "key": "handoff_auditability",
        "control": "Customer packages include access audits, export logs, and audit trails.",
        "evidence": ["homepilot_customer_package.py", "homepilot_audit_trail.py"],
    },
    {
        "key": "credential_hygiene",
        "control": "Environment templates are checked and generated evidence is scanned for credential-like patterns.",
        "evidence": ["homepilot_healthcheck.py", "homepilot_due_diligence.py", ".env.example"],
    },
)


RISK_REGISTER: tuple[dict[str, Any], ...] = (
    {
        "risk": "Cross-tenant data leakage",
        "impact": "A customer could see another customer's properties, responses, or campaign learnings.",
        "controls": ["tenant_rls", "module_entitlements", "handoff_auditability"],
        "residual_status": "requires live RLS probe before production",
    },
    {
        "risk": "Internal/raw model data exposed to customers",
        "impact": "Raw prompts, debug data, or internal scoring details could leak through dashboards or exports.",
        "controls": ["metric_visibility", "handoff_auditability"],
        "residual_status": "local controls pass; live RLS still required for production",
    },
    {
        "risk": "Outreach claims overstate homeowner intent",
        "impact": "Sales teams could treat visible signals as ready-to-buy intent without response evidence.",
        "controls": ["outreach_compliance"],
        "residual_status": "campaign payloads must pass compliance audit before handoff",
    },
    {
        "risk": "Contacted records are kept too long",
        "impact": "Customer outreach memory may exceed the intended retention window.",
        "controls": ["retention_lifecycle"],
        "residual_status": "retention reports and delete plans required for live customer imports",
    },
    {
        "risk": "Benchmark re-identification",
        "impact": "Aggregate learnings could reveal a tenant, address, or campaign if cohort size is too small.",
        "controls": ["aggregate_thresholds"],
        "residual_status": "benchmarks below the minimum threshold are skipped or rejected",
    },
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _normalize_modules(modules: list[str] | None) -> list[str]:
    if not modules:
        return list(PILOT_MODULES)
    unknown = sorted(set(modules) - set(PILOT_MODULES))
    if unknown:
        raise ValueError(f"Unknown module(s): {unknown}")
    return [module for module in PILOT_MODULES if module in set(modules)]


def _issues() -> list[str]:
    issues = []
    known_categories = {category["key"] for category in DATA_CATEGORIES}
    known_controls = {control["key"] for control in CONTROL_CATALOG}
    known_tables = {table["table"] for table in TABLE_CATALOG} | {"homepilot_memberships", "homepilot_property_media", "homepilot_response_insights"}
    for activity in PROCESSING_ACTIVITIES:
        missing_categories = sorted(set(activity["data_categories"]) - known_categories)
        missing_tables = sorted(set(activity["tables"]) - known_tables)
        if missing_categories:
            issues.append(f"{activity['key']} references unknown data categories: {missing_categories}")
        if missing_tables:
            issues.append(f"{activity['key']} references unknown tables: {missing_tables}")
    for risk in RISK_REGISTER:
        missing_controls = sorted(set(risk["controls"]) - known_controls)
        if missing_controls:
            issues.append(f"Risk {risk['risk']} references unknown controls: {missing_controls}")
    if "benchmark" not in SURFACE_VISIBILITY:
        issues.append("Metric access policy is missing benchmark surface visibility.")
    return issues


def build_processing_register(modules: list[str] | None = None) -> dict[str, Any]:
    selected_modules = _normalize_modules(modules)
    issues = _issues()
    return {
        "report_type": "homepilot_data_processing_register",
        "created_at": utc_now(),
        "status": "pass" if not issues else "fail",
        "not_legal_advice": True,
        "modules_selected": selected_modules,
        "processing_activities": list(PROCESSING_ACTIVITIES),
        "data_categories": list(DATA_CATEGORIES),
        "controls": list(CONTROL_CATALOG),
        "risk_register": list(RISK_REGISTER),
        "privacy_rules": list(PRIVACY_RULES),
        "data_subject_workflows": [
            "Use homepilot_privacy.py delete-plan for property-level deletion review.",
            "Use homepilot_retention.py before customer handoff and before production deletes.",
            "Use homepilot_access_audit.py before sharing dashboards, snapshots, or exports.",
            "Use homepilot_release_audit.py with live launch evidence before production access.",
        ],
        "counts": {
            "modules": len(selected_modules),
            "processing_activities": len(PROCESSING_ACTIVITIES),
            "data_categories": len(DATA_CATEGORIES),
            "controls": len(CONTROL_CATALOG),
            "risks": len(RISK_REGISTER),
        },
        "issues": issues,
    }


def render_markdown(register: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Data Processing Register",
        "",
        "This register is an operational review artifact, not legal advice.",
        "",
        f"Created: {register['created_at']}",
        f"Status: {register['status']}",
        "",
        "## Processing Activities",
        "",
    ]
    for activity in register["processing_activities"]:
        lines += [
            f"### {activity['key']}",
            "",
            activity["purpose"],
            "",
            f"- Tables: {', '.join(activity['tables'])}",
            f"- Data categories: {', '.join(activity['data_categories'])}",
            f"- Lawful-basis review: {activity['lawful_basis_review']}",
            f"- Retention: {activity['retention']}",
            f"- Customer surface: {activity['customer_surface']}",
            "",
        ]
    lines += ["## Controls", ""]
    for control in register["controls"]:
        lines.append(f"- `{control['key']}`: {control['control']}")
    lines += ["", "## Risks", ""]
    for risk in register["risk_register"]:
        lines.append(f"- {risk['risk']}: {risk['residual_status']}")
    lines += ["", "## Data Subject Workflows", ""]
    for workflow in register["data_subject_workflows"]:
        lines.append(f"- {workflow}")
    if register["issues"]:
        lines += ["", "## Issues", ""]
        lines.extend(f"- {issue}" for issue in register["issues"])
    lines.append("")
    return "\n".join(lines)


def build_processing_register_pack(out_dir: Path, modules: list[str] | None = None) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    register = build_processing_register(modules=modules)
    json_path = out_dir / "processing_register.json"
    markdown_path = out_dir / "PROCESSING_REGISTER.md"
    write_json(json_path, register)
    markdown_path.write_text(render_markdown(register), encoding="utf-8")
    return {
        "status": register["status"],
        "paths": {
            "processing_register": str(json_path),
            "markdown": str(markdown_path),
        },
        "register": register,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the HomePilot data processing/privacy register")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--module", dest="modules", action="append", default=None)
    args = parser.parse_args()
    pack = build_processing_register_pack(args.out_dir, modules=args.modules)
    print(json.dumps({
        "status": pack["status"],
        "paths": pack["paths"],
        "modules": pack["register"]["modules_selected"],
        "counts": pack["register"]["counts"],
        "issues": pack["register"]["issues"],
    }, indent=2, ensure_ascii=False))
    if pack["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
