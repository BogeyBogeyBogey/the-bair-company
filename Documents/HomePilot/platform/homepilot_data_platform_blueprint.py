#!/usr/bin/env python3
"""
Build the HomePilot data platform blueprint.

This is a buyer/IT review artifact. It explains the shared HomePilot database
spine across pilots, tenants, partners, campaigns, exports, public-data lanes,
and live-proof gates. It does not write to Supabase, store secrets, authorize
outreach, or replace live RLS/customer-access proof.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_platform import PILOT_MODULES


SECRET_PATTERNS = (
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"postgres(?:ql)?://[^:\s]+:[^@\s]{8,}@", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?:service[_-]?role|anon[_-]?key|password|token|secret)\s*[:=]\s*['\"][^'\"\n]{12,}['\"]", re.IGNORECASE),
    re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+"),
)

SCOPE_FIELDS = [
    "section",
    "key",
    "label",
    "grain_or_scope",
    "required_keys",
    "customer_visibility",
    "export_policy",
    "live_gate",
    "guardrail",
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


def _production_verified(production_proof: dict[str, Any] | None) -> bool:
    if not production_proof:
        return False
    if production_proof.get("production_verified") is True:
        return True
    return bool((production_proof.get("production_gate") or {}).get("verified"))


def _enabled_modules(due_diligence: dict[str, Any] | None) -> list[str]:
    raw_modules = (due_diligence or {}).get("modules")
    if isinstance(raw_modules, list):
        modules = [str(module) for module in raw_modules if str(module) in PILOT_MODULES]
        if modules:
            return modules
    return ["facadepilot"]


def _readiness_gate_names(readiness: dict[str, Any] | None) -> list[str]:
    return [str(gate.get("name")) for gate in (readiness or {}).get("gates", []) if gate.get("name")]


def _module_rows(enabled_modules: list[str]) -> list[dict[str, Any]]:
    rows = []
    enabled = set(enabled_modules)
    for key, definition in PILOT_MODULES.items():
        metrics = [asdict(metric) for metric in definition.metrics]
        benchmarkable = [metric for metric in metrics if metric.get("visibility") == "benchmarkable"]
        rows.append({
            "module_key": key,
            "label": definition.label,
            "category": definition.category,
            "primary_score_key": definition.primary_score_key,
            "enabled_in_current_customer_scope": key in enabled,
            "metric_count": len(metrics),
            "benchmarkable_metric_count": len(benchmarkable),
            "grain": "one assessment per tenant/property/module",
            "required_filter": "tenant_id + module_key; partner_id when assigned",
            "customer_visibility": "visible only when tenant has this module entitlement",
        })
    return rows


def _data_layers() -> list[dict[str, Any]]:
    return [
        {
            "key": "tenant_account",
            "label": "Tenant account boundary",
            "tables": ["homepilot_tenants", "homepilot_memberships", "homepilot_tenant_modules"],
            "grain": "tenant, membership, enabled module",
            "required_keys": ["tenant_id", "user_id", "module_key"],
            "customer_visibility": "only own tenant memberships and enabled modules",
            "export_policy": "not exported as raw admin data",
            "live_gate": "live RLS membership probe",
            "guardrail": "tenant_id is mandatory on customer-owned rows",
        },
        {
            "key": "property_spine",
            "label": "Shared property spine",
            "tables": ["homepilot_properties", "homepilot_property_media"],
            "grain": "one tenant-scoped property/address identity",
            "required_keys": ["tenant_id", "property_id"],
            "customer_visibility": "visible only when an entitled module has assessment, target, or interaction evidence",
            "export_policy": "export only through tenant/module/partner scoped read models",
            "live_gate": "live RLS plus module-entitlement probe",
            "guardrail": "no universal cross-tenant household profile",
        },
        {
            "key": "module_assessments",
            "label": "Pilot opportunity assessments",
            "tables": ["homepilot_assessments"],
            "grain": "one tenant/property/module assessment",
            "required_keys": ["tenant_id", "property_id", "module_key", "assessment_id"],
            "customer_visibility": "visible for entitled modules and allowed metric visibility only",
            "export_policy": "dashboard/export surfaces expose benchmarkable plus tenant_private metrics",
            "live_gate": "module access function and hidden-metric checks",
            "guardrail": "scores are opportunity signals, not homeowner purchase intent",
        },
        {
            "key": "campaign_funnel",
            "label": "Campaign funnel and partner routing",
            "tables": ["homepilot_campaigns", "homepilot_campaign_targets"],
            "grain": "campaign and targeted property per tenant/module/partner",
            "required_keys": ["tenant_id", "module_key", "campaign_id", "property_id", "partner_id"],
            "customer_visibility": "producer sees network aggregate; partner sees assigned campaign records only",
            "export_policy": "partner cutdowns must be filtered before package/export generation",
            "live_gate": "partner membership and customer-access verification",
            "guardrail": "response rates must keep contacted denominator explicit",
        },
        {
            "key": "interaction_learning",
            "label": "Interactions and response learning",
            "tables": ["homepilot_interactions", "homepilot_response_insights"],
            "grain": "one interaction event or summarized insight",
            "required_keys": ["tenant_id", "module_key", "campaign_id", "property_id"],
            "customer_visibility": "tenant/module/partner scoped; summarized learnings do not expose other tenants",
            "export_policy": "free-form details stay tenant-scoped and are redacted from generic benchmark surfaces",
            "live_gate": "customer access verification with planned roles",
            "guardrail": "no cross-tenant raw responses, notes, or campaign learnings",
        },
        {
            "key": "public_context",
            "label": "Licensed public-data enrichment",
            "tables": ["homepilot_source_runs", "homepilot_geographies", "homepilot_public_features", "homepilot_property_enrichments"],
            "grain": "source run, geography feature, and property-linked enrichment",
            "required_keys": ["tenant_id", "source_run_id", "geography_id", "property_id"],
            "customer_visibility": "approved fields only, with licence, allowed use, attribution, retrieval date, and provenance",
            "export_policy": "blocked owner/contact scraping lanes stay out of dashboards and exports",
            "live_gate": "public-data approval checklist and reconciliation",
            "guardrail": "public does not automatically mean reusable",
        },
        {
            "key": "exports_audit",
            "label": "Exports, audit, and recovery evidence",
            "tables": ["homepilot_exports", "homepilot_audit_events"],
            "grain": "one export or audit event",
            "required_keys": ["tenant_id", "module_key", "export_id"],
            "customer_visibility": "customer sees scoped export outputs and proof rows, not platform admin internals",
            "export_policy": "each export records filters, row count, surface, and scope",
            "live_gate": "package smoke plus live access proof before portal access",
            "guardrail": "portable data room redacts local paths and never stores secret values",
        },
        {
            "key": "benchmark_learning",
            "label": "Benchmark-safe platform learning",
            "tables": ["homepilot_platform_benchmarks"],
            "grain": "aggregate cohort only",
            "required_keys": ["module_key", "cohort_key"],
            "customer_visibility": "aggregate-only after anonymization, minimum cohort thresholds, and raw-identifier validation",
            "export_policy": "never export address-level, customer-name, or exact campaign content as benchmark data",
            "live_gate": "future benchmark read policy and cohort threshold verifier",
            "guardrail": "private customer learnings stay tenant-scoped by default",
        },
    ]


def _access_lenses(production_verified: bool) -> list[dict[str, Any]]:
    live_gate = "allowed_after_live_schema_rls_customer_access_proof" if production_verified else "blocked_until_live_schema_rls_customer_access_proof"
    return [
        {
            "key": "producer_executive",
            "label": "Producer executive",
            "scope": "tenant-wide producer network aggregate plus partner drilldown",
            "required_filters": ["tenant_id", "module_key"],
            "visible_surfaces": ["boardroom report", "dashboard", "partner matrix", "exports"],
            "blocked_visibility": ["other tenants", "raw partner-only follow-up notes outside scoped records", "secret values"],
            "export_policy": "network exports aggregate partner performance without leaking cross-tenant records",
            "live_gate": live_gate,
        },
        {
            "key": "network_manager",
            "label": "Network manager",
            "scope": "tenant/module network operations and partner capacity",
            "required_filters": ["tenant_id", "module_key"],
            "visible_surfaces": ["campaign cockpit", "partner routing", "response backlog", "training/action boards"],
            "blocked_visibility": ["unlicensed public data", "homeowner intent claims without response evidence"],
            "export_policy": "campaign exports preserve contacted denominator and partner assignment",
            "live_gate": live_gate,
        },
        {
            "key": "partner_renovator",
            "label": "Partner renovator",
            "scope": "assigned campaign records and own follow-up history only",
            "required_filters": ["tenant_id", "module_key", "partner_id"],
            "visible_surfaces": ["partner cutdown", "assigned property list", "own response tasks"],
            "blocked_visibility": ["other partners' records", "producer-only network summaries", "cross-tenant learnings"],
            "export_policy": "partner package is generated after partner filter and leakage scan",
            "live_gate": "blocked_until_partner_auth_mapping_and_customer_access_reconciliation" if not production_verified else live_gate,
        },
        {
            "key": "module_only_customer",
            "label": "Module-only customer",
            "scope": "single tenant plus paid module, for example WindowPilot-only",
            "required_filters": ["tenant_id", "module_key"],
            "visible_surfaces": ["dashboard", "property profile", "module export", "campaign metrics"],
            "blocked_visibility": ["disabled modules", "other tenants", "raw internal/debug/model metrics"],
            "export_policy": "properties appear only when the enabled module has evidence",
            "live_gate": live_gate,
        },
        {
            "key": "it_security",
            "label": "IT/security",
            "scope": "proof artifacts, schema/RLS metadata, audit logs, and non-secret launch evidence",
            "required_filters": ["tenant_id", "module_key", "proof artifact"],
            "visible_surfaces": ["SQL apply plan", "live proof plan", "acceptance matrix", "access lens proof"],
            "blocked_visibility": ["database URLs", "service-role keys", "JWTs", "fixture passwords"],
            "export_policy": "proof artifacts list env var names only, never values",
            "live_gate": "review_required_before_live_cutover",
        },
        {
            "key": "benchmark_safe",
            "label": "Benchmark-safe aggregate",
            "scope": "aggregate cohort by module and coarse segment",
            "required_filters": ["module_key", "cohort_key", "minimum_sample_size"],
            "visible_surfaces": ["future benchmark report", "market comparison", "learning summary"],
            "blocked_visibility": ["addresses", "customer names", "exact campaign text", "raw notes"],
            "export_policy": "benchmarkable metrics only after anonymization and threshold checks",
            "live_gate": "blocked_until_benchmark_policy_and_threshold_verifier",
        },
    ]


def _export_surfaces() -> list[dict[str, Any]]:
    return [
        {
            "key": "property_export",
            "label": "Excel-style property export",
            "scope": "tenant/module/partner scoped property, score, safe metrics, status, next action",
            "source_view": "homepilot_property_export",
            "required_filters": ["tenant_id", "module_key", "partner_id when scoped"],
            "blocked_fields": ["secret values", "other tenants", "disabled modules", "raw internal/debug/model metrics"],
        },
        {
            "key": "campaign_metrics",
            "label": "Campaign metrics export",
            "scope": "tenant/module/partner funnel, contacted denominator, response, appointment, no-response backlog",
            "source_view": "homepilot_campaign_metrics",
            "required_filters": ["tenant_id", "module_key", "campaign_id or partner_id"],
            "blocked_fields": ["cross-tenant raw responses", "unlabelled target-response denominator"],
        },
        {
            "key": "partner_cutdown",
            "label": "Partner cutdown package",
            "scope": "one partner_id inside a producer tenant",
            "source_view": "scoped customer package and partner manifest",
            "required_filters": ["tenant_id", "module_key", "partner_id"],
            "blocked_fields": ["other partner IDs/names/records", "producer-only notes"],
        },
        {
            "key": "public_context",
            "label": "Public-data context export",
            "scope": "approved source-run/geography/public-feature/property-enrichment fields",
            "source_view": "homepilot_property_public_enrichment",
            "required_filters": ["tenant_id", "source_run_id", "allowed_use", "field_allowlist"],
            "blocked_fields": ["owner data", "contact scraping", "unlicensed EPC/private data"],
        },
        {
            "key": "portable_data_room",
            "label": "Portable boardroom data room",
            "scope": "evidence package with relative links, checksums, redaction, and no raw secrets",
            "source_view": "generated evidence artifacts",
            "required_filters": ["customer-facing artifact allowlist", "local-path redaction"],
            "blocked_fields": ["absolute local paths", "tokens", "passwords", "service-role keys"],
        },
    ]


def _live_gates(production_verified: bool) -> list[dict[str, Any]]:
    status = "pass" if production_verified else "blocked"
    return [
        {
            "key": "schema_contract",
            "label": "Live schema contract",
            "status": status,
            "required_evidence": ["schema_verification.json", "contract_status=pass", "live_status=pass", "production_verified=true"],
        },
        {
            "key": "rls_launch",
            "label": "Live RLS launch",
            "status": status,
            "required_evidence": ["launch_report.json", "rls_probe_report.json", "tenant/module/partner probe pass"],
        },
        {
            "key": "customer_access",
            "label": "Customer access verification",
            "status": status,
            "required_evidence": ["customer_access_verification.json", "planned users", "production_verified=true"],
        },
        {
            "key": "partner_access",
            "label": "Partner access reconciliation",
            "status": status,
            "required_evidence": ["partner Auth mapping", "membership rows", "customer-access proof"],
        },
        {
            "key": "first_wave_authorization",
            "label": "First-wave launch authorization",
            "status": status,
            "required_evidence": ["customer go/no-go", "source approval", "suppression proof", "live proof"],
        },
    ]


def build_data_platform_blueprint(
    *,
    due_diligence: dict[str, Any] | None = None,
    readiness: dict[str, Any] | None = None,
    production_proof: dict[str, Any] | None = None,
    release_label: str = "local",
) -> dict[str, Any]:
    enabled_modules = _enabled_modules(due_diligence)
    production_verified = _production_verified(production_proof)
    modules = _module_rows(enabled_modules)
    layers = _data_layers()
    access_lenses = _access_lenses(production_verified)
    exports = _export_surfaces()
    live_gates = _live_gates(production_verified)
    return {
        "blueprint_type": "homepilot_data_platform_blueprint",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": "buyer_review_ready_live_proof_required" if not production_verified else "production_verified",
        "architecture_rule": "tenant -> modules -> campaigns -> properties -> assessments -> interactions",
        "current_customer_scope": {
            "enabled_modules": enabled_modules,
            "module_labels": [PILOT_MODULES[module].label for module in enabled_modules if module in PILOT_MODULES],
            "producer_network_supported": True,
            "partner_scope_supported": True,
        },
        "summary": {
            "shared_database_model": "one HomePilot platform database with tenant/module/partner scoped read surfaces",
            "module_count": len(modules),
            "enabled_module_count": len(enabled_modules),
            "data_layer_count": len(layers),
            "access_lens_count": len(access_lenses),
            "export_surface_count": len(exports),
            "live_gate_count": len(live_gates),
            "readiness_gate_count": len(_readiness_gate_names(readiness)),
            "production_verified": production_verified,
            "production_verified_label": f"production_verified={str(production_verified).lower()}",
        },
        "modules": modules,
        "data_layers": layers,
        "access_lenses": access_lenses,
        "export_surfaces": exports,
        "live_gates": live_gates,
        "guardrails": {
            "tenant_id_required": True,
            "module_key_required_for_module_rows": True,
            "partner_id_limits_partner_visibility": True,
            "no_cross_tenant_raw_learning": True,
            "no_homeowner_intent_without_explicit_response": True,
            "public_data_requires_licence_allowed_use_and_provenance": True,
            "no_live_database_writes": True,
            "no_secret_values": True,
            "production_requires_live_schema_rls_customer_access": True,
        },
        "caveats": [
            "This blueprint is an architecture and review artifact, not a live database probe.",
            "Production access remains no-go until live schema, RLS launch, and customer-access verification all pass with production_verified=true.",
            "Synthetic DAW/demo records are useful for buyer review but are not live customer performance.",
        ],
    }


def _scan_for_secrets(*values: str) -> dict[str, Any]:
    text = "\n".join(values)
    hits = []
    for pattern in SECRET_PATTERNS:
        hits.extend(pattern.findall(text))
    return {
        "status": "fail" if hits else "pass",
        "hit_count": len(hits),
    }


def render_blueprint_markdown(blueprint: dict[str, Any]) -> str:
    summary = blueprint["summary"]
    current_scope = blueprint["current_customer_scope"]
    lines = [
        "# HomePilot Data Platform Blueprint",
        "",
        f"Release: {blueprint['release_label']}",
        f"Created: {blueprint['created_at']}",
        f"Status: {blueprint['status']}",
        f"Architecture rule: `{blueprint['architecture_rule']}`",
        f"Current enabled modules: {', '.join(current_scope['module_labels'])}",
        f"Production proof: {summary['production_verified_label']}",
        "",
        "This document explains the shared HomePilot property-intelligence database model for buyer and IT review. It is not a live database probe and it does not authorize outreach.",
        "",
        "## Executive Summary",
        "",
        f"- Shared model: {summary['shared_database_model']}",
        f"- Pilot modules in catalog: {summary['module_count']}",
        f"- Current customer enabled modules: {summary['enabled_module_count']}",
        f"- Data layers: {summary['data_layer_count']}",
        f"- Access lenses: {summary['access_lens_count']}",
        f"- Export surfaces: {summary['export_surface_count']}",
        "",
        "## Pilot Modules",
        "",
        "| Module | Category | Enabled Here | Primary Score | Metrics | Required Filter |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in blueprint["modules"]:
        lines.append(
            f"| {row['label']} (`{row['module_key']}`) | {row['category']} | {str(row['enabled_in_current_customer_scope']).lower()} | "
            f"`{row['primary_score_key']}` | {row['metric_count']} | {row['required_filter']} |"
        )
    lines += [
        "",
        "## Data Layers",
        "",
        "| Layer | Tables | Grain | Required Keys | Customer Visibility | Export Policy | Live Gate |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in blueprint["data_layers"]:
        lines.append(
            f"| {row['label']} | {', '.join(row['tables'])} | {row['grain']} | {', '.join(row['required_keys'])} | "
            f"{row['customer_visibility']} | {row['export_policy']} | {row['live_gate']} |"
        )
    lines += [
        "",
        "## Access Lenses",
        "",
        "| Lens | Scope | Required Filters | Blocked Visibility | Export Policy | Live Gate |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in blueprint["access_lenses"]:
        lines.append(
            f"| {row['label']} | {row['scope']} | {', '.join(row['required_filters'])} | "
            f"{'; '.join(row['blocked_visibility'])} | {row['export_policy']} | {row['live_gate']} |"
        )
    lines += [
        "",
        "## Export Surfaces",
        "",
        "| Export | Scope | Source | Required Filters | Blocked Fields |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in blueprint["export_surfaces"]:
        lines.append(
            f"| {row['label']} | {row['scope']} | {row['source_view']} | "
            f"{', '.join(row['required_filters'])} | {'; '.join(row['blocked_fields'])} |"
        )
    lines += [
        "",
        "## Live Gates",
        "",
        "| Gate | Status | Required Evidence |",
        "| --- | --- | --- |",
    ]
    for row in blueprint["live_gates"]:
        lines.append(f"| {row['label']} | {row['status']} | {', '.join(row['required_evidence'])} |")
    lines += [
        "",
        "## Guardrails",
        "",
    ]
    for key, value in blueprint["guardrails"].items():
        lines.append(f"- {key}: {str(value).lower()}")
    lines += [
        "",
        "## Caveats",
        "",
    ]
    for caveat in blueprint["caveats"]:
        lines.append(f"- {caveat}")
    lines.append("")
    return "\n".join(lines)


def _scope_rows(blueprint: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in blueprint["data_layers"]:
        rows.append({
            "section": "data_layer",
            "key": row["key"],
            "label": row["label"],
            "grain_or_scope": row["grain"],
            "required_keys": "; ".join(row["required_keys"]),
            "customer_visibility": row["customer_visibility"],
            "export_policy": row["export_policy"],
            "live_gate": row["live_gate"],
            "guardrail": row["guardrail"],
        })
    for row in blueprint["access_lenses"]:
        rows.append({
            "section": "access_lens",
            "key": row["key"],
            "label": row["label"],
            "grain_or_scope": row["scope"],
            "required_keys": "; ".join(row["required_filters"]),
            "customer_visibility": "; ".join(row["visible_surfaces"]),
            "export_policy": row["export_policy"],
            "live_gate": row["live_gate"],
            "guardrail": "blocked: " + "; ".join(row["blocked_visibility"]),
        })
    for row in blueprint["export_surfaces"]:
        rows.append({
            "section": "export_surface",
            "key": row["key"],
            "label": row["label"],
            "grain_or_scope": row["scope"],
            "required_keys": "; ".join(row["required_filters"]),
            "customer_visibility": row["source_view"],
            "export_policy": "reviewable export surface",
            "live_gate": "requires scoped source plus package/access proof",
            "guardrail": "blocked fields: " + "; ".join(row["blocked_fields"]),
        })
    return rows


def write_scope_matrix_csv(path: Path, blueprint: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SCOPE_FIELDS)
        writer.writeheader()
        for row in _scope_rows(blueprint):
            writer.writerow({field: row.get(field, "") for field in SCOPE_FIELDS})


def build_data_platform_blueprint_pack(
    out_dir: Path,
    *,
    due_diligence: dict[str, Any] | None = None,
    readiness: dict[str, Any] | None = None,
    production_proof: dict[str, Any] | None = None,
    release_label: str = "local",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    blueprint = build_data_platform_blueprint(
        due_diligence=due_diligence,
        readiness=readiness,
        production_proof=production_proof,
        release_label=release_label,
    )
    markdown = render_blueprint_markdown(blueprint)
    json_body = json.dumps(blueprint, indent=2, ensure_ascii=False) + "\n"
    secret_scan = _scan_for_secrets(json_body, markdown)
    blueprint["secret_scan"] = secret_scan
    write_json(out_dir / "data_platform_blueprint.json", blueprint)
    write_text(out_dir / "DATA_PLATFORM_BLUEPRINT.md", render_blueprint_markdown(blueprint))
    write_scope_matrix_csv(out_dir / "DATA_PLATFORM_SCOPE_MATRIX.csv", blueprint)
    blueprint["paths"] = {
        "data_platform_blueprint": str(out_dir / "data_platform_blueprint.json"),
        "data_platform_blueprint_markdown": str(out_dir / "DATA_PLATFORM_BLUEPRINT.md"),
        "data_platform_scope_matrix": str(out_dir / "DATA_PLATFORM_SCOPE_MATRIX.csv"),
    }
    write_json(out_dir / "data_platform_blueprint.json", blueprint)
    return blueprint


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot data platform blueprint")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--due-diligence-report", type=Path)
    parser.add_argument("--readiness-report", type=Path)
    parser.add_argument("--production-proof", type=Path)
    parser.add_argument("--release-label", default="local")
    args = parser.parse_args()

    blueprint = build_data_platform_blueprint_pack(
        args.out_dir,
        due_diligence=load_json(args.due_diligence_report),
        readiness=load_json(args.readiness_report),
        production_proof=load_json(args.production_proof),
        release_label=args.release_label,
    )
    print(json.dumps({
        "status": blueprint["status"],
        "blueprint": blueprint["paths"]["data_platform_blueprint"],
        "markdown": blueprint["paths"]["data_platform_blueprint_markdown"],
        "scope_matrix": blueprint["paths"]["data_platform_scope_matrix"],
        "production_verified": blueprint["summary"]["production_verified"],
        "secret_scan": blueprint["secret_scan"]["status"],
    }, indent=2))


if __name__ == "__main__":
    main()
