#!/usr/bin/env python3
"""
HomePilot tenant/module entitlement filters.

RLS is the production enforcement layer. These helpers are the local handoff
guardrails used before generating customer dashboards, exports, and packages:
scope a canonical platform payload to exactly the tenant(s) and module(s) a
customer is allowed to see.
"""

from __future__ import annotations

from typing import Any

from homepilot_platform import PILOT_MODULES
from homepilot_store import validate_payload


MODULE_KEYS = set(PILOT_MODULES)


def tenant_ids_from_onboarding(onboarding: dict[str, Any]) -> set[str]:
    return {
        str(row["id"])
        for row in onboarding.get("tenants", [])
        if row.get("id")
    }


def enabled_modules_from_onboarding(onboarding: dict[str, Any]) -> list[str]:
    enabled = {
        str(row["module_key"])
        for row in onboarding.get("tenant_modules", [])
        if row.get("module_key") and row.get("enabled", True)
    }
    return [key for key in PILOT_MODULES if key in enabled]


def _normalize_modules(enabled_modules: list[str] | set[str] | tuple[str, ...] | None) -> set[str]:
    if enabled_modules is None:
        return set(MODULE_KEYS)
    modules = {str(key) for key in enabled_modules}
    unknown = modules - MODULE_KEYS
    if unknown:
        raise ValueError(f"Unknown enabled module(s): {sorted(unknown)}")
    return modules


def _tenant_ok(row: dict[str, Any], tenant_ids: set[str]) -> bool:
    tenant_id = str(row.get("tenant_id") or "")
    return not tenant_ids or tenant_id in tenant_ids


def _module_ok(row: dict[str, Any], enabled_modules: set[str]) -> bool:
    module_key = str(row.get("module_key") or "")
    return not module_key or module_key in enabled_modules


def filter_payload_for_entitlements(
    payload: dict[str, Any],
    tenant_ids: set[str] | list[str] | tuple[str, ...] | None = None,
    enabled_modules: list[str] | set[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Return a canonical payload scoped to the given tenant/module access.

    Properties do not carry a module key, so a property is exposed only when an
    allowed assessment, target, or interaction references it. This prevents a
    module-filtered handoff from leaking addresses for properties that belong
    only to another module.
    """
    validate_payload(payload)

    allowed_tenants = {str(item) for item in (tenant_ids or []) if str(item)}
    allowed_modules = _normalize_modules(enabled_modules)

    source_properties = {
        str(row["id"]): row
        for row in payload.get("properties", [])
        if _tenant_ok(row, allowed_tenants)
    }

    campaigns = [
        row for row in payload.get("campaigns", [])
        if _tenant_ok(row, allowed_tenants) and _module_ok(row, allowed_modules)
    ]
    source_had_campaigns = bool(payload.get("campaigns"))
    campaign_ids = {str(row["id"]) for row in campaigns}

    def campaign_ok(row: dict[str, Any]) -> bool:
        campaign_id = str(row.get("campaign_id") or "")
        return not campaign_id or not source_had_campaigns or campaign_id in campaign_ids

    assessments = [
        row for row in payload.get("assessments", [])
        if _tenant_ok(row, allowed_tenants)
        and _module_ok(row, allowed_modules)
        and str(row.get("property_id") or "") in source_properties
    ]
    targets = [
        row for row in payload.get("campaign_targets", [])
        if _tenant_ok(row, allowed_tenants)
        and _module_ok(row, allowed_modules)
        and str(row.get("property_id") or "") in source_properties
        and campaign_ok(row)
    ]
    interactions = [
        row for row in payload.get("interactions", [])
        if _tenant_ok(row, allowed_tenants)
        and _module_ok(row, allowed_modules)
        and str(row.get("property_id") or "") in source_properties
        and campaign_ok(row)
    ]
    response_insights = [
        row for row in payload.get("response_insights", [])
        if _tenant_ok(row, allowed_tenants)
        and _module_ok(row, allowed_modules)
        and campaign_ok(row)
    ]
    exports = [
        row for row in payload.get("exports", [])
        if _tenant_ok(row, allowed_tenants)
        and _module_ok(row, allowed_modules)
    ]

    visible_property_ids = {
        str(row.get("property_id") or "")
        for collection in (assessments, targets, interactions)
        for row in collection
        if row.get("property_id")
    }
    properties = [
        row for property_id, row in source_properties.items()
        if property_id in visible_property_ids
    ]

    scoped = {
        "campaigns": campaigns,
        "properties": properties,
        "assessments": assessments,
        "campaign_targets": targets,
        "interactions": interactions,
        "response_insights": response_insights,
        "exports": exports,
    }
    if properties and isinstance(payload.get("network"), dict):
        scoped["network"] = payload["network"]
    validate_payload(scoped)
    return scoped
