#!/usr/bin/env python3
"""
HomePilot product access and metric visibility policy.

Tenant/module entitlements decide which records a customer may see. This module
adds the field-level product contract: which metrics are safe for customer
dashboards, exports, aggregate benchmarks, and internal operator surfaces.
"""

from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone
from typing import Any

from homepilot_platform import PILOT_MODULES


ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "viewer": ("dashboard_read", "export_download", "benchmark_read"),
    "manager": ("dashboard_read", "export_download", "benchmark_read", "campaign_update", "response_update"),
    "admin": (
        "dashboard_read",
        "export_download",
        "benchmark_read",
        "campaign_update",
        "response_update",
        "member_manage",
        "module_manage",
    ),
    "owner": (
        "dashboard_read",
        "export_download",
        "benchmark_read",
        "campaign_update",
        "response_update",
        "member_manage",
        "module_manage",
        "billing_manage",
        "tenant_delete_request",
    ),
}

SURFACE_VISIBILITY: dict[str, set[str]] = {
    "dashboard": {"benchmarkable", "tenant_private"},
    "export": {"benchmarkable", "tenant_private"},
    "customer_package": {"benchmarkable", "tenant_private"},
    "benchmark": {"benchmarkable"},
    "internal": {"benchmarkable", "tenant_private", "internal", "raw_evidence", "admin_only"},
}

GLOBAL_METRIC_VISIBILITY = {
    "estimated_value": "tenant_private",
    "pipeline_value": "tenant_private",
    "project_value": "tenant_private",
    "deal_value": "tenant_private",
}

INTERNAL_PREFIXES = (
    "internal_",
    "raw_",
    "debug_",
    "model_",
    "prompt_",
    "token_",
    "embedding_",
    "llm_",
)

INTERNAL_SUFFIXES = (
    "_prompt",
    "_raw",
    "_debug",
    "_token",
    "_embedding",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _validate_surface(surface: str) -> str:
    if surface not in SURFACE_VISIBILITY:
        raise ValueError(f"Unknown metric surface: {surface}")
    return surface


def _validate_role(role: str) -> str:
    if role not in ROLE_PERMISSIONS:
        raise ValueError(f"Unknown product role: {role}")
    return role


def _catalog_visibility(module_key: str, metric_key: str) -> str | None:
    definition = PILOT_MODULES.get(module_key)
    if not definition:
        return None
    for metric in definition.metrics:
        if metric.key == metric_key:
            return metric.visibility
    return None


def metric_visibility(module_key: str, metric_key: str) -> str:
    if metric_key in GLOBAL_METRIC_VISIBILITY:
        return GLOBAL_METRIC_VISIBILITY[metric_key]
    catalog_value = _catalog_visibility(module_key, metric_key)
    if catalog_value:
        return catalog_value
    lowered = metric_key.lower()
    if lowered.startswith(INTERNAL_PREFIXES) or lowered.endswith(INTERNAL_SUFFIXES):
        return "internal"
    return "internal"


def metric_visibility_map(module_key: str) -> dict[str, str]:
    if module_key not in PILOT_MODULES:
        raise ValueError(f"Unknown module: {module_key}")
    mapping = {metric.key: metric.visibility for metric in PILOT_MODULES[module_key].metrics}
    mapping.update(GLOBAL_METRIC_VISIBILITY)
    return dict(sorted(mapping.items()))


def filter_metrics_for_surface(
    module_key: str,
    metrics: dict[str, Any],
    surface: str = "dashboard",
) -> dict[str, Any]:
    surface = _validate_surface(surface)
    if surface == "internal":
        return dict(metrics)
    allowed = SURFACE_VISIBILITY[surface]
    return {
        key: value
        for key, value in metrics.items()
        if metric_visibility(module_key, key) in allowed
    }


def hidden_metric_keys(
    module_key: str,
    metrics: dict[str, Any],
    surface: str = "dashboard",
) -> list[str]:
    surface = _validate_surface(surface)
    if surface == "internal":
        return []
    allowed = SURFACE_VISIBILITY[surface]
    return sorted(
        key
        for key in metrics
        if metric_visibility(module_key, key) not in allowed
    )


def filter_payload_metrics_for_surface(
    payload: dict[str, Any],
    surface: str = "customer_package",
) -> dict[str, Any]:
    filtered = copy.deepcopy(payload)
    for assessment in filtered.get("assessments", []):
        metrics = assessment.get("metrics") if isinstance(assessment.get("metrics"), dict) else {}
        assessment["metrics"] = filter_metrics_for_surface(
            str(assessment.get("module_key") or ""),
            metrics,
            surface=surface,
        )
    return filtered


def _normalize_modules(enabled_modules: list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    if enabled_modules is None:
        return list(PILOT_MODULES)
    modules = [str(module) for module in enabled_modules]
    unknown = sorted(set(modules) - set(PILOT_MODULES))
    if unknown:
        raise ValueError(f"Unknown module(s): {unknown}")
    return [module for module in PILOT_MODULES if module in set(modules)]


def build_product_access_matrix(
    enabled_modules: list[str] | tuple[str, ...] | set[str] | None = None,
    role: str = "viewer",
    surface: str = "dashboard",
) -> dict[str, Any]:
    role = _validate_role(role)
    surface = _validate_surface(surface)
    modules = []
    for module_key in _normalize_modules(enabled_modules):
        definition = PILOT_MODULES[module_key]
        visible = []
        hidden = []
        for metric in definition.metrics:
            row = {
                "key": metric.key,
                "label": metric.label,
                "value_type": metric.value_type,
                "unit": metric.unit,
                "visibility": metric.visibility,
            }
            if metric.visibility in SURFACE_VISIBILITY[surface]:
                visible.append(row)
            else:
                hidden.append(row)
        modules.append({
            "key": module_key,
            "label": definition.label,
            "category": definition.category,
            "primary_score_key": definition.primary_score_key,
            "visible_metrics": visible,
            "hidden_metrics": hidden,
        })
    return {
        "report_type": "homepilot_product_access_matrix",
        "created_at": utc_now(),
        "role": role,
        "permissions": list(ROLE_PERMISSIONS[role]),
        "surface": surface,
        "surface_visibility": sorted(SURFACE_VISIBILITY[surface]),
        "modules": modules,
        "guardrails": [
            "tenant_id is enforced by RLS and local handoff filters",
            "module_key is enforced by tenant module entitlements",
            "unknown metric keys are hidden from customer surfaces by default",
            "benchmark surfaces expose benchmarkable metrics only and must remain aggregate-only",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Print the HomePilot product access matrix")
    parser.add_argument("--module", dest="modules", action="append", default=None)
    parser.add_argument("--role", default="viewer", choices=sorted(ROLE_PERMISSIONS))
    parser.add_argument("--surface", default="dashboard", choices=sorted(SURFACE_VISIBILITY))
    args = parser.parse_args()
    print(json.dumps(
        build_product_access_matrix(args.modules, role=args.role, surface=args.surface),
        indent=2,
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
