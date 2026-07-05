#!/usr/bin/env python3
"""
Build the HomePilot customer API/read-model contract.

Supabase exposes the customer read models through PostgREST. This module
documents the allowed GET endpoints, filters, auth model, RLS guarantees, and
integration examples without requiring live credentials.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_data_dictionary import VIEW_CATALOG
from homepilot_metric_access import ROLE_PERMISSIONS
from homepilot_platform import PILOT_MODULES


READ_ENDPOINTS: tuple[dict[str, Any], ...] = (
    {
        "id": "property_intelligence",
        "view": "homepilot_property_intelligence",
        "path": "/rest/v1/homepilot_property_intelligence",
        "purpose": "Primary customer dashboard table with property, assessment, campaign status, latest interaction, and filtered metrics.",
        "surface": "dashboard",
        "permission": "dashboard_read",
        "recommended_filters": ("module_key=eq.windowpilot", "campaign_status=in.(responded,appointment)", "score=gte.75"),
        "default_select": "property_id,address,city,module_key,score,grade,campaign_status,latest_response_status,metrics",
        "sort_examples": ("score.desc", "latest_interaction_at.desc"),
    },
    {
        "id": "property_export",
        "view": "homepilot_property_export",
        "path": "/rest/v1/homepilot_property_export",
        "purpose": "Flat customer export view for spreadsheet-like integrations and BI tools.",
        "surface": "export",
        "permission": "export_download",
        "recommended_filters": ("module_key=eq.facadepilot", "campaign_status=neq.rejected"),
        "default_select": "property_id,address,postcode,city,module_key,score,grade,campaign_status,metrics",
        "sort_examples": ("priority_score.desc", "updated_at.desc"),
    },
    {
        "id": "property_public_enrichment",
        "view": "homepilot_property_public_enrichment",
        "path": "/rest/v1/homepilot_property_public_enrichment",
        "purpose": "Customer-safe public enrichment read model with source, licence, allowed use, attribution, confidence, and provenance.",
        "surface": "dashboard",
        "permission": "dashboard_read",
        "recommended_filters": ("enrichment_type=eq.official_address", "source_name=eq.BeSt Addresses"),
        "default_select": "property_id,address,enrichment_type,public_fields,confidence,source_name,licence,allowed_use,attribution,retrieval_finished_at",
        "sort_examples": ("retrieval_finished_at.desc",),
    },
    {
        "id": "campaign_metrics",
        "view": "homepilot_campaign_metrics",
        "path": "/rest/v1/homepilot_campaign_metrics",
        "purpose": "Campaign funnel and response metrics by tenant, campaign, and module.",
        "surface": "dashboard",
        "permission": "dashboard_read",
        "recommended_filters": ("module_key=eq.windowpilot", "response_rate_pct=gte.0"),
        "default_select": "campaign_id,module_key,campaign_name,target_count,contacted_count,response_count,appointment_count,no_response_count,response_rate_pct,target_response_rate_pct",
        "sort_examples": ("response_rate_pct.desc", "last_target_update_at.desc"),
    },
    {
        "id": "module_metrics",
        "view": "homepilot_module_metrics",
        "path": "/rest/v1/homepilot_module_metrics",
        "purpose": "Module-level performance summary for comparing enabled pilots inside one tenant.",
        "surface": "dashboard",
        "permission": "dashboard_read",
        "recommended_filters": ("module_key=in.(windowpilot,facadepilot)",),
        "default_select": "module_key,module_label,property_count,average_score,top_opportunity_count,contacted_count,response_count,appointment_count,response_rate_pct,target_response_rate_pct",
        "sort_examples": ("average_score.desc",),
    },
    {
        "id": "second_brain_edges",
        "view": "homepilot_second_brain_edges",
        "path": "/rest/v1/homepilot_second_brain_edges",
        "purpose": "Graph edge feed for second-brain visuals connecting modules, campaigns, properties, and reactions.",
        "surface": "dashboard",
        "permission": "dashboard_read",
        "recommended_filters": ("module_key=eq.windowpilot", "weight=gte.1"),
        "default_select": "module_key,source_type,source_id,target_type,target_id,edge_type,weight",
        "sort_examples": ("weight.desc",),
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


def _endpoint_contract(endpoint: dict[str, Any], base_url: str) -> dict[str, Any]:
    view_catalog = {view["view"]: view for view in VIEW_CATALOG}
    view = view_catalog.get(endpoint["view"], {})
    return {
        **endpoint,
        "method": "GET",
        "url": f"{base_url.rstrip('/')}{endpoint['path']}",
        "required_headers": {
            "apikey": "HOMEPILOT_SUPABASE_ANON_KEY",
            "Authorization": "Bearer <customer-jwt>",
        },
        "query_parameters": {
            "select": endpoint["default_select"],
            "order": list(endpoint["sort_examples"]),
            "limit": "1..1000, depending on customer UI/export use",
            "filters": list(endpoint["recommended_filters"]),
        },
        "view_grain": view.get("grain", "customer-scoped read model"),
        "documented_columns": list(view.get("columns", [])),
        "access_boundary": view.get("access_boundary", "security_invoker view plus underlying table RLS"),
        "example_curl": (
            "curl -H 'apikey: $HOMEPILOT_SUPABASE_ANON_KEY' "
            "-H 'Authorization: Bearer $CUSTOMER_JWT' "
            f"'{base_url.rstrip('/')}{endpoint['path']}?select={endpoint['default_select']}&limit=50'"
        ),
    }


def _issues(endpoints: list[dict[str, Any]]) -> list[str]:
    issues = []
    catalog_views = {view["view"] for view in VIEW_CATALOG}
    endpoint_views = {endpoint["view"] for endpoint in endpoints}
    missing_catalog = sorted(endpoint_views - catalog_views)
    if missing_catalog:
        issues.append(f"Endpoints reference undocumented views: {missing_catalog}")
    required_views = {
        "homepilot_property_intelligence",
        "homepilot_property_export",
        "homepilot_property_public_enrichment",
        "homepilot_campaign_metrics",
        "homepilot_module_metrics",
        "homepilot_second_brain_edges",
    }
    missing_endpoints = sorted(required_views - endpoint_views)
    if missing_endpoints:
        issues.append(f"Missing API endpoints for views: {missing_endpoints}")
    body = json.dumps(endpoints, ensure_ascii=False).lower()
    if "service-role" in body or "service_role" in body:
        issues.append("Customer API contract must not mention privileged database credentials.")
    for endpoint in endpoints:
        permission = endpoint.get("permission")
        if not any(permission in permissions for permissions in ROLE_PERMISSIONS.values()):
            issues.append(f"Unknown permission in endpoint {endpoint.get('id')}: {permission}")
    return issues


def build_api_contract(
    modules: list[str] | None = None,
    base_url: str = "https://PROJECT.supabase.co",
) -> dict[str, Any]:
    selected_modules = _normalize_modules(modules)
    endpoints = [_endpoint_contract(endpoint, base_url=base_url) for endpoint in READ_ENDPOINTS]
    issues = _issues(endpoints)
    return {
        "report_type": "homepilot_customer_api_contract",
        "created_at": utc_now(),
        "status": "pass" if not issues else "fail",
        "base_url": base_url,
        "modules_selected": selected_modules,
        "auth_model": {
            "runtime_key": "HOMEPILOT_SUPABASE_ANON_KEY",
            "bearer": "customer Supabase Auth JWT",
            "forbidden": ["privileged database keys in browsers", "cross-tenant admin reads", "unfiltered raw table access"],
        },
        "access_guarantees": [
            "All endpoints are GET-only customer read models.",
            "Views are security_invoker views so underlying table RLS remains active.",
            "Tenant access is enforced by homepilot_has_tenant_access.",
            "Module access is enforced by homepilot_has_module_access.",
            "Customer-facing metrics are filtered through homepilot_metrics_for_customer.",
            "Unknown or internal metric keys are hidden from customer surfaces by default.",
        ],
        "endpoints": endpoints,
        "counts": {
            "modules": len(selected_modules),
            "endpoints": len(endpoints),
            "views": len({endpoint["view"] for endpoint in endpoints}),
        },
        "issues": issues,
    }


def render_markdown(contract: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Customer API Contract",
        "",
        f"Created: {contract['created_at']}",
        f"Status: {contract['status']}",
        f"Base URL: `{contract['base_url']}`",
        "",
        "## Auth Model",
        "",
        "Use the Supabase anon key plus a customer JWT. Never expose privileged database keys in customer apps.",
        "",
        "## Access Guarantees",
        "",
    ]
    for guarantee in contract["access_guarantees"]:
        lines.append(f"- {guarantee}")
    lines += ["", "## Endpoints", ""]
    for endpoint in contract["endpoints"]:
        lines += [
            f"### `{endpoint['method']} {endpoint['path']}`",
            "",
            endpoint["purpose"],
            "",
            f"- View: `{endpoint['view']}`",
            f"- Surface: `{endpoint['surface']}`",
            f"- Permission: `{endpoint['permission']}`",
            f"- Access boundary: {endpoint['access_boundary']}",
            f"- Default select: `{endpoint['default_select']}`",
            "",
            "Example:",
            "",
            "```bash",
            endpoint["example_curl"],
            "```",
            "",
        ]
    if contract["issues"]:
        lines += ["## Issues", ""]
        lines.extend(f"- {issue}" for issue in contract["issues"])
        lines.append("")
    return "\n".join(lines)


def build_api_contract_pack(
    out_dir: Path,
    modules: list[str] | None = None,
    base_url: str = "https://PROJECT.supabase.co",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    contract = build_api_contract(modules=modules, base_url=base_url)
    json_path = out_dir / "api_contract.json"
    markdown_path = out_dir / "API_CONTRACT.md"
    write_json(json_path, contract)
    markdown_path.write_text(render_markdown(contract), encoding="utf-8")
    return {
        "status": contract["status"],
        "paths": {
            "api_contract": str(json_path),
            "markdown": str(markdown_path),
        },
        "contract": contract,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the HomePilot customer API/read-model contract")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--module", dest="modules", action="append", default=None)
    parser.add_argument("--base-url", default="https://PROJECT.supabase.co")
    args = parser.parse_args()
    pack = build_api_contract_pack(args.out_dir, modules=args.modules, base_url=args.base_url)
    print(json.dumps({
        "status": pack["status"],
        "paths": pack["paths"],
        "modules": pack["contract"]["modules_selected"],
        "counts": pack["contract"]["counts"],
        "issues": pack["contract"]["issues"],
    }, indent=2, ensure_ascii=False))
    if pack["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
