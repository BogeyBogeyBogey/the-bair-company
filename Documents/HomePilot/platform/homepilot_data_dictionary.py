#!/usr/bin/env python3
"""
Build the HomePilot enterprise data dictionary.

The dictionary is the customer/buyer-facing explanation layer for the shared
HomePilot data platform: modules, metrics, tables, read models, exports,
surfaces, and the privacy rules that decide what a tenant may see.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_metric_access import ROLE_PERMISSIONS, SURFACE_VISIBILITY, metric_visibility_map
from homepilot_platform import PILOT_MODULES


TABLE_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "table": "homepilot_tenants",
        "grain": "one row per customer tenant",
        "purpose": "Customer account boundary for all properties, campaigns, exports, and access policies.",
        "customer_exposure": "never exported as raw platform administration data",
    },
    {
        "table": "homepilot_memberships",
        "grain": "one tenant membership per Supabase Auth user, optionally scoped to one partner_id",
        "purpose": "Role and access-scope source of truth: unscoped memberships see the tenant; partner-scoped memberships see assigned partner records only.",
        "customer_exposure": "review evidence in account access plans; never exported as lead data",
    },
    {
        "table": "homepilot_tenant_modules",
        "grain": "one enabled pilot module per tenant",
        "purpose": "Product entitlement source of truth, such as WindowPilot-only or multi-module access.",
        "customer_exposure": "summarized in access matrices and handoff manifests",
    },
    {
        "table": "homepilot_properties",
        "grain": "one property per tenant/address identity",
        "purpose": "Shared property spine across all pilots so one house can collect multiple renovation assessments.",
        "customer_exposure": "tenant/module/partner-scoped dashboard, property profile, and export rows",
    },
    {
        "table": "homepilot_assessments",
        "grain": "one module assessment per property",
        "purpose": "Pilot-specific scores, grades, metric JSON, confidence, and evidence references.",
        "customer_exposure": "filtered by tenant, module entitlement, partner scope, and metric visibility",
    },
    {
        "table": "homepilot_campaigns",
        "grain": "one outreach campaign per tenant/module",
        "purpose": "Campaign lifecycle, channel, territory, message variant, partner assignment, metadata, and timing context.",
        "customer_exposure": "tenant/module/partner-scoped campaign dashboard metrics",
    },
    {
        "table": "homepilot_campaign_targets",
        "grain": "one property targeted by one campaign/module",
        "purpose": "Priority score, campaign status, compliance metadata, next action, and sales follow-up state.",
        "customer_exposure": "tenant/module/partner-scoped campaign intelligence and exports",
    },
    {
        "table": "homepilot_interactions",
        "grain": "one touchpoint or response event",
        "purpose": "Contact history, response/no-response status, sentiment, objections, and detail fields.",
        "customer_exposure": "tenant/module/partner-scoped response intelligence and property timelines",
    },
    {
        "table": "homepilot_exports",
        "grain": "one generated customer export",
        "purpose": "Audit log for customer package and spreadsheet export generation.",
        "customer_exposure": "included as export_log.json in customer handoff packages",
    },
    {
        "table": "homepilot_audit_events",
        "grain": "one platform audit event",
        "purpose": "Review trail for package generation, exports, access audits, RLS probes, and operator handoffs.",
        "customer_exposure": "tenant/partner-scoped audit trail reports, not cross-tenant platform logs",
    },
    {
        "table": "homepilot_source_runs",
        "grain": "one public/source enrichment retrieval run",
        "purpose": "Source provenance register with publisher, URL, licence, allowed use, attribution, retrieval time, transform version, and import status.",
        "customer_exposure": "shown as provenance for approved public-data enrichments; never a contact-basis source by itself",
    },
    {
        "table": "homepilot_geographies",
        "grain": "one tenant-scoped geography key such as address, statistical sector, municipality, parcel, building, or custom zone",
        "purpose": "Reusable geographic join spine for official addresses, parcels, buildings, statistical areas, and licensed map/context layers.",
        "customer_exposure": "visible only through tenant/partner-scoped enrichment views and source-attributed dashboard badges",
    },
    {
        "table": "homepilot_public_features",
        "grain": "one public feature per geography/source",
        "purpose": "Reusable licensed area-level features such as building-age mix, income band, land-use class, or flood-risk flag.",
        "customer_exposure": "customer-safe aggregate or geography-context metrics with licence and allowed-use metadata",
    },
    {
        "table": "homepilot_property_enrichments",
        "grain": "one approved public enrichment per property/source/enrichment type",
        "purpose": "Property-linked public fields kept separate from campaign contact basis, with confidence and provenance.",
        "customer_exposure": "tenant/module/partner-scoped enrichment panels and exports only when source licence and allowed use are approved",
    },
    {
        "table": "homepilot_platform_benchmarks",
        "grain": "one aggregate benchmark cohort",
        "purpose": "Privacy-safe cross-customer learning after minimum cohort thresholds and identifier validation.",
        "customer_exposure": "aggregate-only benchmark surfaces",
    },
)


VIEW_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "view": "homepilot_property_intelligence",
        "grain": "one property assessment row",
        "purpose": "Primary dashboard read model combining property, module score, campaign target, latest interaction, and customer-safe metrics.",
        "access_boundary": "security_invoker view plus table RLS, tenant access, module entitlement, partner scope, and metric filtering",
        "columns": (
            "tenant_id", "property_id", "address", "city", "lat", "lon", "property_type",
            "partner_id", "partner_name", "module_key", "module_label", "score", "grade", "confidence", "metrics",
            "evidence_count", "campaign_status", "priority_score", "latest_response_status",
            "latest_objection_code", "interaction_count",
        ),
    },
    {
        "view": "homepilot_property_export",
        "grain": "one Excel-friendly property assessment row",
        "purpose": "Flat export view for sales operations, territory work, and customer spreadsheet review.",
        "access_boundary": "inherits tenant/module/partner/metric filtering from homepilot_property_intelligence",
        "columns": (
            "tenant_id", "property_id", "address", "postcode", "city", "partner_id", "partner_name", "module_key", "score",
            "grade", "campaign_status", "latest_response_status", "interaction_count", "metrics",
        ),
    },
    {
        "view": "homepilot_property_public_enrichment",
        "grain": "one property enrichment row with source provenance",
        "purpose": "Customer-safe public enrichment/provenance read model for licensed official/open data linked to tenant-scoped properties.",
        "access_boundary": "security_invoker view plus tenant access, partner scope, and source-run licence/allowed-use metadata",
        "columns": (
            "tenant_id", "property_id", "address", "postcode", "city", "partner_id", "partner_name",
            "enrichment_type", "public_fields", "confidence", "provenance", "geography_type", "geography_key",
            "country_code", "region", "municipality", "geometry_ref", "source_run_id", "source_name",
            "publisher", "source_url", "licence", "allowed_use", "attribution", "retrieval_finished_at",
            "transform_version",
        ),
    },
    {
        "view": "homepilot_campaign_metrics",
        "grain": "one campaign per tenant/module",
        "purpose": "Campaign funnel, contacted counts, responses, appointments, no-response counts, contacted response rate, and legacy target response rate.",
        "access_boundary": "tenant, module, and partner RLS checks",
        "columns": (
            "tenant_id", "campaign_id", "module_key", "campaign_name", "partner_id", "partner_name", "target_count",
            "contacted_count", "response_count", "appointment_count", "no_response_count", "response_rate_pct",
            "target_response_rate_pct",
        ),
    },
    {
        "view": "homepilot_module_metrics",
        "grain": "one tenant/module aggregate",
        "purpose": "Module-level performance summary for comparing enabled pilots inside one tenant.",
        "access_boundary": "tenant, module, and partner RLS checks",
        "columns": (
            "tenant_id", "module_key", "module_label", "property_count", "average_score",
            "top_opportunity_count", "contacted_count", "response_count", "appointment_count", "response_rate_pct",
            "target_response_rate_pct",
        ),
    },
    {
        "view": "homepilot_second_brain_edges",
        "grain": "one graph edge between module, campaign, property, and reaction nodes",
        "purpose": "Graph-shaped visual layer for the second-brain dashboard experience.",
        "access_boundary": "built from the tenant/module/partner-safe property intelligence view",
        "columns": (
            "tenant_id", "module_key", "source_type", "source_id", "target_type", "target_id", "edge_type", "weight",
        ),
    },
)


EXPORT_SHEET_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "sheet": "properties",
        "purpose": "Prioritized property list for sales teams and territory review.",
        "columns": (
            ("property_id", "Stable property identifier inside the tenant handoff."),
            ("address", "Customer-visible property address."),
            ("city", "Property city."),
            ("lat", "Latitude when available for maps and territory QA."),
            ("lon", "Longitude when available for maps and territory QA."),
            ("status", "Current campaign or follow-up status."),
            ("next_action", "Suggested or scheduled next sales action."),
            ("estimated_value", "Tenant-private commercial value estimate when provided."),
            ("best_module", "Highest-scoring enabled pilot module for this property."),
            ("best_score", "Best visible opportunity score."),
            ("best_grade", "Best visible opportunity grade."),
            ("tags", "Customer-safe property tags."),
        ),
    },
    {
        "sheet": "assessments",
        "purpose": "Per-module scoring and evidence review for each visible property.",
        "columns": (
            ("property_id", "Stable property identifier inside the tenant handoff."),
            ("address", "Customer-visible property address."),
            ("module_key", "Enabled pilot module that produced the assessment."),
            ("score", "Opportunity score for the module."),
            ("grade", "Opportunity grade for the module."),
            ("confidence", "Model/operator confidence when available."),
            ("label", "Customer-facing assessment label when available."),
            ("metrics_json", "Customer-safe metric JSON after visibility filtering."),
            ("evidence_count", "Number of evidence references attached to the assessment."),
        ),
    },
    {
        "sheet": "interactions",
        "purpose": "Campaign memory: touches, responses, objections, and follow-up context.",
        "columns": (
            ("property_id", "Stable property identifier inside the tenant handoff."),
            ("address", "Customer-visible property address."),
            ("date", "Interaction date."),
            ("type", "Interaction or outreach type."),
            ("detail", "Customer-visible interaction detail."),
        ),
    },
    {
        "sheet": "recommendations",
        "purpose": "Ranked learnings and recommended next actions generated from the tenant snapshot.",
        "columns": (
            ("rank", "Recommendation order."),
            ("recommendation", "Customer-facing recommendation text."),
        ),
    },
)


CUSTOMER_ARTIFACT_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "artifact": "dashboard_snapshot.json",
        "purpose": "Tenant/module-scoped dashboard read model used by the static customer dashboard.",
        "customer_exposure": "included in customer packages under data/",
    },
    {
        "artifact": "CUSTOMER_BRIEF.md",
        "purpose": "Boardroom-ready customer intelligence summary covering scorecard, top opportunities, campaign learnings, action plan, data confidence, and guardrails.",
        "customer_exposure": "included in customer packages under data/customer_brief/",
    },
    {
        "artifact": "BOARDROOM_REPORT.md / boardroom-report.html",
        "purpose": "Executive control-surface report translating the scoped dashboard into KPIs, partner or module steering matrix, work queues, recommended next steps, caveats, and export-ready producer partner summary.",
        "customer_exposure": "included in customer packages under data/boardroom_report/ and dashboard/; producer networks also receive data/boardroom_report/partner_summary.csv",
    },
    {
        "artifact": "partner_cutdown_manifest.json",
        "purpose": "Producer-network handoff manifest proving each partner package contains only assigned records, exports, dashboard, boardroom report, and scope leakage evidence.",
        "customer_exposure": "included in DAW-style demo rooms under partner_cutdowns/; each partner package is scoped to one partner_id",
    },
    {
        "artifact": "PARTNER_ACCESS_RECONCILIATION.md",
        "purpose": "Buyer-review explanation of whether partner Auth mapping, account-access memberships, and customer-access verification agree before partner portal access is enabled.",
        "customer_exposure": "included in market-readiness data rooms as non-mutating production-gate evidence; it does not grant access or prove production access by itself",
    },
    {
        "artifact": "PARTNER_ACCESS_RECONCILIATION_MATRIX.csv",
        "purpose": "Partner-by-partner reconciliation matrix for mapped Auth users, planned membership rows, customer-access probe identities, and overall access readiness.",
        "customer_exposure": "included in market-readiness data rooms; contains partner IDs/names and status fields, not raw contact values or secret credentials",
    },
    {
        "artifact": "PARTNER_ACCESS_RECONCILIATION_ISSUES.csv",
        "purpose": "Blocking issues and next actions when partner Auth mapping, account-access planning, or customer-access verification are missing or misaligned.",
        "customer_exposure": "included in market-readiness data rooms so customer IT and launch owners can resolve partner-access blockers before production access",
    },
    {
        "artifact": "CAMPAIGN_LEARNING.md",
        "purpose": "Tenant-scoped campaign learning report covering funnel health, module learnings, segment signals, objections, and next experiment backlog.",
        "customer_exposure": "included in customer packages under data/campaign_learning/",
    },
    {
        "artifact": "TERRITORY_PLAN.md",
        "purpose": "Tenant-scoped territory planning report prioritizing the next campaign batch by city, segment, module, score density, and pipeline value.",
        "customer_exposure": "included in customer packages under data/territory_plan/",
    },
    {
        "artifact": "ROI_FORECAST.md",
        "purpose": "Transparent business-case forecast translating visible opportunities into scenario revenue, gross profit, contact cost, and capacity needs using explicit assumptions.",
        "customer_exposure": "included in customer packages under data/roi_forecast/",
    },
    {
        "artifact": "OPPORTUNITY_DOSSIER.md",
        "purpose": "Explainability dossier for prioritized properties, including customer-safe metric drivers, evidence references, review gaps, and next actions.",
        "customer_exposure": "included in customer packages under data/opportunity_dossier/",
    },
    {
        "artifact": "SOURCE_LEDGER.md",
        "purpose": "Customer-safe source and provenance ledger covering evidence types, source runs, confidence, timestamps, provenance gaps, and guardrails.",
        "customer_exposure": "included in customer packages under data/source_ledger/",
    },
    {
        "artifact": "OPEN_INTELLIGENCE.md",
        "purpose": "HomePilot Open Intelligence model card, model lab, data collaboration room, marketing-impact planner, channel mix, measurement loop, activation plan, outcome loop, and guardrails for enterprise buyer review.",
        "customer_exposure": "included in customer packages under data/open_intelligence/",
    },
    {
        "artifact": "OPEN_INTELLIGENCE_BOARDROOM_BRIEF.md",
        "purpose": "Executive decision brief that translates Open Intelligence evidence into DAW-style boardroom questions, proof stack, owners, blockers, meeting sequence, and activation guardrails.",
        "customer_exposure": "included in customer packages under data/open_intelligence/",
    },
    {
        "artifact": "OPEN_INTELLIGENCE_DECISION_MATRIX.csv",
        "purpose": "Excel-ready boardroom decision matrix for first-wave focus, partner routing, segment-message tests, marketing measurement, and safe data use.",
        "customer_exposure": "included in customer packages under data/open_intelligence/",
    },
    {
        "artifact": "MARKETING_IMPACT_PLANNER.csv",
        "purpose": "Reviewable activation lanes that translate property, partner, segment, message, and source evidence into channel-safe next actions without starting outreach.",
        "customer_exposure": "included in customer packages under data/open_intelligence/",
    },
    {
        "artifact": "MEASUREMENT_LOOP.csv",
        "purpose": "Buyer-review measurement plan for contacted denominators, partner effectiveness, message learning, and customer-approved commercial outcome sync.",
        "customer_exposure": "included in customer packages under data/open_intelligence/",
    },
    {
        "artifact": "PUBLIC_DATA_RECONCILIATION.md",
        "purpose": "Buyer-review and launch-room explanation of whether public-data source register, dataset approvals, first-wave public-data need, and live proof align before production public-data import.",
        "customer_exposure": "included in market-readiness data rooms as non-mutating public-data import gate evidence; it does not fetch, approve, or import data by itself",
    },
    {
        "artifact": "PUBLIC_DATA_RECONCILIATION_MATRIX.csv",
        "purpose": "Source-by-source reconciliation matrix for register status, licence/terms, dataset approval, production import decision, first-wave dependency, and live-proof readiness.",
        "customer_exposure": "included in market-readiness data rooms; contains source governance status, not homeowner contact data or secret credentials",
    },
    {
        "artifact": "PUBLIC_DATA_RECONCILIATION_ISSUES.csv",
        "purpose": "Blocking issues and next actions when public-data approvals, import decisions, legal review, or live proof are missing.",
        "customer_exposure": "included in market-readiness data rooms so legal, IT, data engineering, and customer success can resolve source-governance blockers",
    },
    {
        "artifact": "CUSTOMER_SIGNOFF_RECONCILIATION.md",
        "purpose": "Buyer-review and launch-room explanation of which customer decisions are only review-ready, which are signed, and which block first-wave launch or production.",
        "customer_exposure": "included in market-readiness data rooms as non-mutating decision-gate evidence; it does not approve outreach, partner access, public-data import, or commercial terms by itself",
    },
    {
        "artifact": "CUSTOMER_SIGNOFF_RECONCILIATION_MATRIX.csv",
        "purpose": "Decision-by-decision matrix for buyer-review acceptance, customer inputs, staging review, first-wave go/no-go, live proof, partner access, public data, commercial terms, support acknowledgement, and value metrics.",
        "customer_exposure": "included in market-readiness data rooms; contains signoff status, evidence references, owners, blockers, and next actions, not raw contact values or secret credentials",
    },
    {
        "artifact": "CUSTOMER_SIGNOFF_RECONCILIATION_ISSUES.csv",
        "purpose": "Blocking issues and next actions when customer approvals, live proof, commercial agreement, support acknowledgement, or production signoff are missing.",
        "customer_exposure": "included in market-readiness data rooms so executive sponsors, legal/procurement, IT, and customer success can resolve decision blockers",
    },
    {
        "artifact": "CUSTOMER_SIGNOFF_INTAKE.md",
        "purpose": "Instructions for recording safe customer approval references without storing raw signatures, personal contact details, emails, or secrets in the portable data room.",
        "customer_exposure": "included in market-readiness data rooms as the customer/operator guide for completing signoff evidence",
    },
    {
        "artifact": "CUSTOMER_SIGNOFF_EVIDENCE_TEMPLATE.csv",
        "purpose": "Fillable decision-key template for safe signoff references across buyer-review acceptance, first-wave go/no-go, commercial terms, support acknowledgement, and value metric baseline.",
        "customer_exposure": "included in market-readiness data rooms; filled values should contain approval references only, while raw signatures and personal data stay in approved customer systems",
    },
    {
        "artifact": "homepilot_export.xlsx",
        "purpose": "Excel-friendly operational export for sales and territory workflows.",
        "customer_exposure": "included in customer packages under exports/ when XLSX generation is enabled",
    },
    {
        "artifact": "access_audit.json",
        "purpose": "Evidence that the package was checked for tenant/module leakage and hidden metric exposure.",
        "customer_exposure": "included in customer packages under data/",
    },
)


GLOBAL_METRICS: tuple[dict[str, str], ...] = (
    {
        "key": "estimated_value",
        "label": "Estimated opportunity value",
        "value_type": "number",
        "unit": "EUR",
        "visibility": "tenant_private",
        "description": "Tenant-private commercial estimate used for prioritization and export review.",
    },
    {
        "key": "pipeline_value",
        "label": "Pipeline value",
        "value_type": "number",
        "unit": "EUR",
        "visibility": "tenant_private",
        "description": "Tenant-private pipeline estimate for sales reporting.",
    },
    {
        "key": "project_value",
        "label": "Project value",
        "value_type": "number",
        "unit": "EUR",
        "visibility": "tenant_private",
        "description": "Tenant-private expected project value when a response or qualification supports it.",
    },
    {
        "key": "deal_value",
        "label": "Deal value",
        "value_type": "number",
        "unit": "EUR",
        "visibility": "tenant_private",
        "description": "Tenant-private deal value for won or advanced opportunities.",
    },
)


PRIVACY_RULES: tuple[str, ...] = (
    "Every customer-facing row is scoped by tenant_id.",
    "Module-specific rows are additionally scoped by tenant module entitlements.",
    "Producer-network partner rows are additionally scoped by membership partner_id when present.",
    "Unknown metric keys are hidden from customer dashboard, export, and benchmark surfaces by default.",
    "Dashboard and export surfaces may show benchmarkable and tenant_private metrics only.",
    "Benchmark surfaces may show benchmarkable metrics only and must remain aggregate-only.",
    "Cross-customer learnings never include tenant IDs, property IDs, addresses, campaign IDs, or free-form response detail.",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _normalize_modules(modules: list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    if not modules:
        return list(PILOT_MODULES)
    requested = [str(module) for module in modules]
    unknown = sorted(set(requested) - set(PILOT_MODULES))
    if unknown:
        raise ValueError(f"Unknown module(s): {unknown}")
    requested_set = set(requested)
    return [module for module in PILOT_MODULES if module in requested_set]


def _visible_surfaces(visibility: str) -> list[str]:
    return sorted(
        surface
        for surface, allowed in SURFACE_VISIBILITY.items()
        if visibility in allowed
    )


def _module_rows(modules: list[str]) -> list[dict[str, Any]]:
    rows = []
    for module_key in modules:
        definition = PILOT_MODULES[module_key]
        rows.append({
            "key": definition.key,
            "label": definition.label,
            "category": definition.category,
            "primary_score_key": definition.primary_score_key,
            "metric_count": len(definition.metrics),
        })
    return rows


def _metric_rows(modules: list[str]) -> list[dict[str, Any]]:
    rows = []
    for module_key in modules:
        visibility_map = metric_visibility_map(module_key)
        for metric in PILOT_MODULES[module_key].metrics:
            row = asdict(metric)
            visibility = visibility_map[metric.key]
            row.update({
                "module_key": module_key,
                "metric_key": metric.key,
                "visibility": visibility,
                "visible_on": _visible_surfaces(visibility),
                "customer_visible": visibility in SURFACE_VISIBILITY["dashboard"],
                "export_visible": visibility in SURFACE_VISIBILITY["export"],
                "benchmarkable": visibility in SURFACE_VISIBILITY["benchmark"],
                "primary_score": metric.key == PILOT_MODULES[module_key].primary_score_key,
            })
            rows.append(row)
    return rows


def _global_metric_rows() -> list[dict[str, Any]]:
    rows = []
    for metric in GLOBAL_METRICS:
        visibility = metric["visibility"]
        rows.append({
            **metric,
            "visible_on": _visible_surfaces(visibility),
            "customer_visible": visibility in SURFACE_VISIBILITY["dashboard"],
            "export_visible": visibility in SURFACE_VISIBILITY["export"],
            "benchmarkable": visibility in SURFACE_VISIBILITY["benchmark"],
        })
    return rows


def _surface_description(surface: str) -> str:
    descriptions = {
        "dashboard": "Interactive customer dashboard and property profile experience.",
        "export": "CSV/XLSX data handoff for customer operations teams.",
        "customer_package": "Packaged customer dashboard, data, exports, and audit evidence.",
        "benchmark": "Aggregate-only cross-customer insight surface.",
        "internal": "Operator-only diagnostics, raw evidence, and admin review surfaces.",
    }
    return descriptions.get(surface, "HomePilot product surface.")


def _surface_rows() -> dict[str, Any]:
    return {
        surface: {
            "visibility_classes": sorted(classes),
            "description": _surface_description(surface),
        }
        for surface, classes in sorted(SURFACE_VISIBILITY.items())
    }


def _export_column_rows() -> list[dict[str, Any]]:
    rows = []
    for sheet in EXPORT_SHEET_CATALOG:
        for column, description in sheet["columns"]:
            rows.append({
                "sheet": sheet["sheet"],
                "column": column,
                "description": description,
                "customer_visible": True,
            })
    return rows


def _issues(modules: list[str], metrics: list[dict[str, Any]], export_columns: list[dict[str, Any]]) -> list[str]:
    issues = []
    if not modules:
        issues.append("No pilot modules selected.")
    for module_key in modules:
        definition = PILOT_MODULES[module_key]
        metric_keys = {metric.key for metric in definition.metrics}
        if definition.primary_score_key not in metric_keys:
            issues.append(f"{module_key} primary score key is missing from metric catalog.")
    known_visibility = set().union(*SURFACE_VISIBILITY.values())
    unknown_visibility = sorted({metric["visibility"] for metric in metrics if metric["visibility"] not in known_visibility})
    if unknown_visibility:
        issues.append(f"Unknown metric visibility classes: {unknown_visibility}")
    export_column_names = {column["column"] for column in export_columns}
    for required in ("address", "best_score", "metrics_json", "recommendation"):
        if required not in export_column_names:
            issues.append(f"Export dictionary is missing required column: {required}")
    return issues


def build_data_dictionary(modules: list[str] | None = None) -> dict[str, Any]:
    selected_modules = _normalize_modules(modules)
    metrics = _metric_rows(selected_modules)
    export_columns = _export_column_rows()
    issues = _issues(selected_modules, metrics, export_columns)
    return {
        "report_type": "homepilot_data_dictionary",
        "created_at": utc_now(),
        "status": "pass" if not issues else "fail",
        "modules_selected": selected_modules,
        "modules": _module_rows(selected_modules),
        "metrics": metrics,
        "global_metrics": _global_metric_rows(),
        "surfaces": _surface_rows(),
        "roles": {
            role: {"permissions": list(permissions)}
            for role, permissions in sorted(ROLE_PERMISSIONS.items())
        },
        "tables": list(TABLE_CATALOG),
        "views": list(VIEW_CATALOG),
        "export_sheets": [
            {
                "sheet": sheet["sheet"],
                "purpose": sheet["purpose"],
                "column_count": len(sheet["columns"]),
            }
            for sheet in EXPORT_SHEET_CATALOG
        ],
        "customer_artifacts": list(CUSTOMER_ARTIFACT_CATALOG),
        "export_columns": export_columns,
        "privacy_rules": list(PRIVACY_RULES),
        "counts": {
            "modules": len(selected_modules),
            "metrics": len(metrics),
            "global_metrics": len(GLOBAL_METRICS),
            "tables": len(TABLE_CATALOG),
            "views": len(VIEW_CATALOG),
            "export_columns": len(export_columns),
            "customer_artifacts": len(CUSTOMER_ARTIFACT_CATALOG),
        },
        "issues": issues,
    }


def render_markdown(dictionary: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Data Dictionary",
        "",
        f"Created: {dictionary['created_at']}",
        f"Status: {dictionary['status']}",
        "",
        "## Modules",
        "",
    ]
    for module in dictionary["modules"]:
        lines.append(
            f"- {module['label']} (`{module['key']}`): {module['metric_count']} metrics, primary score `{module['primary_score_key']}`."
        )
    lines += ["", "## Metrics", ""]
    for metric in dictionary["metrics"]:
        unit = f" {metric['unit']}" if metric.get("unit") else ""
        surfaces = ", ".join(metric["visible_on"])
        lines.append(
            f"- `{metric['module_key']}.{metric['metric_key']}`: {metric['label']} ({metric['value_type']}{unit}); visibility `{metric['visibility']}`; surfaces: {surfaces}."
        )
    lines += ["", "## Export Sheets", ""]
    for sheet in dictionary["export_sheets"]:
        lines.append(f"- `{sheet['sheet']}`: {sheet['purpose']} ({sheet['column_count']} columns).")
    lines += ["", "## Customer Artifacts", ""]
    for artifact in dictionary["customer_artifacts"]:
        lines.append(f"- `{artifact['artifact']}`: {artifact['purpose']}")
    lines += ["", "## Dashboard Views", ""]
    for view in dictionary["views"]:
        lines.append(f"- `{view['view']}`: {view['purpose']}")
    lines += ["", "## Tables", ""]
    for table in dictionary["tables"]:
        lines.append(f"- `{table['table']}`: {table['purpose']}")
    lines += ["", "## Privacy Rules", ""]
    for rule in dictionary["privacy_rules"]:
        lines.append(f"- {rule}")
    if dictionary["issues"]:
        lines += ["", "## Issues", ""]
        for issue in dictionary["issues"]:
            lines.append(f"- {issue}")
    lines.append("")
    return "\n".join(lines)


def build_data_dictionary_pack(out_dir: Path, modules: list[str] | None = None) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    dictionary = build_data_dictionary(modules=modules)
    json_path = out_dir / "data_dictionary.json"
    markdown_path = out_dir / "DATA_DICTIONARY.md"
    write_json(json_path, dictionary)
    markdown_path.write_text(render_markdown(dictionary), encoding="utf-8")
    return {
        "status": dictionary["status"],
        "paths": {
            "data_dictionary": str(json_path),
            "markdown": str(markdown_path),
        },
        "dictionary": dictionary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the HomePilot enterprise data dictionary")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--module", dest="modules", action="append", default=None)
    args = parser.parse_args()
    pack = build_data_dictionary_pack(args.out_dir, modules=args.modules)
    print(json.dumps({
        "status": pack["status"],
        "paths": pack["paths"],
        "modules": pack["dictionary"]["modules_selected"],
        "counts": pack["dictionary"]["counts"],
        "issues": pack["dictionary"]["issues"],
    }, indent=2, ensure_ascii=False))
    if pack["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
