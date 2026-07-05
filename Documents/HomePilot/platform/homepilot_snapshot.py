#!/usr/bin/env python3
"""
Build customer-facing HomePilot dashboard snapshots.

The store layer keeps normalized tenant/module/property records. The client
needs a compact read model: one tenant, enabled modules, property cards,
assessments, interactions, objections, and recommendations. This module turns a
canonical HomePilot payload into that read model and can emit JSON or a static
JavaScript file for the dependency-free dashboard.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from homepilot_entitlements import filter_payload_for_entitlements
from homepilot_platform import PILOT_MODULES
from homepilot_metric_access import filter_metrics_for_surface
from homepilot_source_ledger import build_source_ledger
from homepilot_store import load_payload, summarize_payload, validate_payload
from homepilot_visual_intelligence import build_visual_intelligence


HERE = Path(__file__).parent.resolve()
HOME_ROOT = HERE.parent
DEFAULT_CLIENT_DATA = HOME_ROOT / "client" / "dashboard-data.js"

MODULE_LABELS = {key: definition.label for key, definition in PILOT_MODULES.items()}

LABEL_METRIC_KEYS = {
    "facadepilot": ("facade_preset", "property_type", "render_quality"),
    "windowpilot": ("replacement_urgency", "glazing_age_signal", "frame_material_signal"),
    "roofpilot": ("roof_age_signal", "roof_material_signal", "storm_or_moss_signal"),
    "gardenpilot": ("maintenance_signal", "outdoor_living_fit", "privacy_fit"),
    "poolpilot": ("pool_fit", "sun_exposure_signal", "terrain_complexity"),
    "porchpilot": ("porch_style_fit", "entry_visibility", "front_house_upgrade_fit"),
    "drivewaypilot": ("surface_condition_signal", "drainage_risk", "ev_charger_fit"),
}

VALUE_METRIC_KEYS = (
    "estimated_value",
    "pipeline_value",
    "project_value",
    "deal_value",
    "median_income",
)

STATUS_ACTIONS = {
    "generated": "Queue for campaign",
    "queued": "Send campaign asset",
    "sent": "Check for response",
    "scanned": "Follow up on scan",
    "clicked": "Call while interest is warm",
    "responded": "Qualify renovation intent",
    "appointment": "Prepare estimate",
    "customer": "Move to customer handoff",
    "rejected": "Archive or retarget later",
    "no_response": "Retarget with softer message",
}

CONTACTED_STATUSES = {"sent", "scanned", "clicked", "responded", "appointment", "customer", "no_response"}
ENGAGED_STATUSES = {"responded", "appointment", "customer"}
CONVERSION_STATUSES = {"appointment", "customer"}


def _first_text(*values: Any, fallback: str = "") -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return fallback


def _number(value: Any, fallback: float = 0.0) -> float:
    if value in (None, ""):
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _best_target(targets: list[dict[str, Any]]) -> dict[str, Any]:
    if not targets:
        return {}
    status_rank = {
        "customer": 9,
        "appointment": 8,
        "responded": 7,
        "clicked": 6,
        "scanned": 5,
        "sent": 4,
        "queued": 3,
        "generated": 2,
        "no_response": 1,
        "rejected": 0,
    }
    return sorted(
        targets,
        key=lambda row: (
            status_rank.get(str(row.get("status") or ""), 0),
            _number(row.get("priority_score")),
        ),
        reverse=True,
    )[0]


def _assessment_label(module_key: str, metrics: dict[str, Any], grade: str) -> str:
    for key in LABEL_METRIC_KEYS.get(module_key, ()):
        value = metrics.get(key)
        if value not in (None, ""):
            return str(value)
    return f"{MODULE_LABELS.get(module_key, module_key)} {grade or 'opportunity'}"


def _assessment_value(metrics: dict[str, Any], score: float) -> int:
    for key in VALUE_METRIC_KEYS:
        value = metrics.get(key)
        if value not in (None, ""):
            return int(round(_number(value)))
    return int(round(max(15000, min(95000, score * 850))))


def _interaction_date(value: str) -> str:
    if not value:
        return "Queued"
    return value[:10]


def _status_from_targets(targets: list[dict[str, Any]]) -> str:
    target = _best_target(targets)
    return str(target.get("status") or "generated")


def _next_action(targets: list[dict[str, Any]], best_module: str) -> str:
    target = _best_target(targets)
    metadata = target.get("metadata") if isinstance(target.get("metadata"), dict) else {}
    explicit = _first_text(metadata.get("next_action"), metadata.get("nextAction"))
    if explicit:
        return explicit
    status = str(target.get("status") or "generated")
    module = MODULE_LABELS.get(best_module, best_module)
    action = STATUS_ACTIONS.get(status, "Review property")
    return f"{action} ({module})" if module else action


def _property_tags(prop: dict[str, Any], assessments: list[dict[str, Any]]) -> list[str]:
    tags = [str(tag) for tag in prop.get("tags", []) if str(tag).strip()]
    property_type = _first_text(prop.get("property_type"), prop.get("core", {}).get("property_type"))
    if property_type:
        tags.append(property_type)
    for assessment in assessments:
        grade = _first_text(assessment.get("grade"))
        if grade in ("A+", "A"):
            tags.append(f"{MODULE_LABELS.get(assessment['module_key'], assessment['module_key'])} {grade}")
    seen: set[str] = set()
    clean: list[str] = []
    for tag in tags:
        key = tag.lower()
        if key not in seen:
            clean.append(tag)
            seen.add(key)
    return clean[:8]


def _collect_objections(
    interactions: list[dict[str, Any]],
    targets: list[dict[str, Any]],
) -> list[str]:
    objections: list[str] = []
    for interaction in interactions:
        code = _first_text(interaction.get("objection_code"))
        if code:
            objections.append(code.replace("_", " "))
        status = _first_text(interaction.get("response_status"))
        if status in {"not_interested", "later", "wrong_address", "do_not_contact"}:
            objections.append(status.replace("_", " "))
    for target in targets:
        metadata = target.get("metadata") if isinstance(target.get("metadata"), dict) else {}
        for value in metadata.get("objections", []) if isinstance(metadata.get("objections"), list) else []:
            if value:
                objections.append(str(value))
    return sorted(set(objections))


def _snapshot_summary(tenant_id: str, properties: list[dict[str, Any]]) -> dict[str, Any]:
    module_counts: dict[str, int] = {}
    assessment_count = 0
    for prop in properties:
        for module_key in prop.get("assessments", {}):
            module_counts[module_key] = module_counts.get(module_key, 0) + 1
            assessment_count += 1
    return {
        "tenants": 1 if tenant_id else 0,
        "properties": len(properties),
        "assessments": assessment_count,
        "campaign_targets": sum(1 for prop in properties if prop.get("status")),
        "modules": module_counts,
    }


def _recommendations(properties: list[dict[str, Any]], modules: list[str]) -> list[str]:
    if not properties:
        return ["Import a first campaign to unlock territory recommendations."]
    top_modules: dict[str, int] = {}
    no_response = 0
    responded = 0
    for prop in properties:
        assessments = prop.get("assessments", {})
        if assessments:
            best_key = sorted(assessments, key=lambda key: assessments[key].get("score", 0), reverse=True)[0]
            top_modules[best_key] = top_modules.get(best_key, 0) + 1
        if prop.get("status") == "no_response":
            no_response += 1
        if prop.get("status") in ENGAGED_STATUSES:
            responded += 1

    best_module = max(top_modules, key=top_modules.get) if top_modules else (modules[0] if modules else "")
    best_label = MODULE_LABELS.get(best_module, best_module)
    recommendations = [
        f"{best_label} is currently the strongest entry point in this tenant dataset.",
        "Keep high-score properties in a separate call queue; they carry the highest weighted renovation value.",
    ]
    if no_response:
        recommendations.append("Retarget no-response properties with a lower-friction message before changing territory.")
    if responded:
        recommendations.append("Use response history as training data for the next message variant and sales script.")
    return recommendations[:4]


def _property_network(prop: dict[str, Any]) -> dict[str, Any]:
    core = prop.get("core") if isinstance(prop.get("core"), dict) else {}
    network = core.get("network") if isinstance(core.get("network"), dict) else {}
    partner_id = _first_text(network.get("partner_id"), core.get("partner_id"))
    if not partner_id:
        return {}
    return {
        "id": partner_id,
        "name": _first_text(network.get("partner_name"), core.get("partner_name"), fallback=partner_id),
        "region": _first_text(network.get("partner_region"), core.get("partner_region"), prop.get("city")),
        "territory": _first_text(network.get("territory"), core.get("territory"), prop.get("city")),
        "producer": _first_text(network.get("producer"), core.get("producer")),
        "scope": _first_text(network.get("scope"), fallback="partner"),
    }


def _public_context(prop: dict[str, Any]) -> dict[str, Any]:
    core = prop.get("core") if isinstance(prop.get("core"), dict) else {}
    source = core.get("public_enrichment") or core.get("publicContext") or core.get("public_context")
    if not isinstance(source, dict):
        return {}

    features: list[dict[str, Any]] = []
    raw_features = source.get("features") if isinstance(source.get("features"), list) else []
    for feature in raw_features[:6]:
        if not isinstance(feature, dict):
            continue
        features.append({
            "key": _first_text(feature.get("key"), fallback="public_context"),
            "label": _first_text(feature.get("label"), feature.get("key"), fallback="Public context"),
            "value": feature.get("value"),
            "unit": _first_text(feature.get("unit")),
            "source": _first_text(feature.get("source"), fallback="Public data source"),
            "geographyLevel": _first_text(feature.get("geography_level"), feature.get("geographyLevel")),
            "licence": _first_text(feature.get("licence"), source.get("licence")),
        })

    guardrails = [
        str(item).strip()
        for item in source.get("guardrails", [])
        if str(item).strip()
    ] if isinstance(source.get("guardrails"), list) else []

    geography = source.get("geography") if isinstance(source.get("geography"), dict) else {}
    return {
        "status": _first_text(source.get("status"), fallback="available"),
        "sourceRunId": _first_text(source.get("source_run_id"), source.get("sourceRunId")),
        "readModel": _first_text(source.get("read_model"), source.get("readModel")),
        "licence": _first_text(source.get("licence")),
        "allowedUse": _first_text(source.get("allowed_use"), source.get("allowedUse")),
        "attribution": _first_text(source.get("attribution")),
        "retrievedAt": _first_text(source.get("retrieval_finished_at"), source.get("retrievedAt")),
        "transformVersion": _first_text(source.get("transform_version"), source.get("transformVersion")),
        "confidence": _number(source.get("confidence")),
        "geography": {
            "level": _first_text(geography.get("level"), geography.get("type")),
            "key": _first_text(geography.get("key"), geography.get("id")),
            "city": _first_text(geography.get("city"), prop.get("city")),
            "region": _first_text(geography.get("region")),
        },
        "features": features,
        "guardrails": guardrails[:5],
    }


def _public_context_summary(properties: list[dict[str, Any]]) -> dict[str, Any]:
    contexts = [
        prop.get("publicContext")
        for prop in properties
        if isinstance(prop.get("publicContext"), dict) and prop.get("publicContext", {}).get("features")
    ]
    source_runs = sorted({
        str(context.get("sourceRunId"))
        for context in contexts
        if context.get("sourceRunId")
    })
    feature_keys = sorted({
        str(feature.get("key"))
        for context in contexts
        for feature in context.get("features", [])
        if isinstance(feature, dict) and feature.get("key")
    })
    return {
        "status": "available" if contexts else "not_configured",
        "propertiesWithContext": len(contexts),
        "featureCount": sum(len(context.get("features", [])) for context in contexts),
        "featureTypes": feature_keys[:12],
        "sourceRuns": source_runs[:8],
        "privateLanesExcluded": True,
        "guardrails": [
            "No owner data",
            "No scraped personal contact data",
            "No individual EPC label",
            "Public context is not homeowner intent",
        ],
    }


def _network_from_payload(payload: dict[str, Any], properties: list[dict[str, Any]]) -> dict[str, Any] | None:
    source = payload.get("network") if isinstance(payload.get("network"), dict) else {}
    partners_by_id: dict[str, dict[str, Any]] = {}
    source_partners = source.get("partners", [])
    if not isinstance(source_partners, list):
        source_partners = []
    for partner in source_partners:
        if not isinstance(partner, dict) or not partner.get("id"):
            continue
        partners_by_id[str(partner["id"])] = dict(partner)
    for prop in properties:
        partner = prop.get("partner") if isinstance(prop.get("partner"), dict) else {}
        partner_id = _first_text(partner.get("id"))
        if not partner_id:
            continue
        partners_by_id.setdefault(partner_id, {
            "id": partner_id,
            "name": _first_text(partner.get("name"), fallback=partner_id),
            "region": _first_text(partner.get("region"), fallback="Unknown"),
            "territory": _first_text(partner.get("territory"), fallback="Unknown"),
        })

    if not partners_by_id and not source:
        return None

    partner_metrics: dict[str, dict[str, Any]] = {
        partner_id: {
            **partner,
            "properties": 0,
            "top_opportunities": 0,
            "contacted": 0,
            "responded": 0,
            "appointments": 0,
            "no_response": 0,
            "pipeline_value": 0,
            "facade_m2": 0,
        }
        for partner_id, partner in partners_by_id.items()
    }
    for prop in properties:
        partner = prop.get("partner") if isinstance(prop.get("partner"), dict) else {}
        partner_id = _first_text(partner.get("id"))
        if not partner_id:
            continue
        row = partner_metrics.setdefault(partner_id, {"id": partner_id, "name": partner_id})
        best = max((item.get("score", 0) for item in prop.get("assessments", {}).values()), default=0)
        row["properties"] = int(row.get("properties", 0)) + 1
        row["top_opportunities"] = int(row.get("top_opportunities", 0)) + (1 if best >= 78 else 0)
        row["contacted"] = int(row.get("contacted", 0)) + (1 if prop.get("status") in CONTACTED_STATUSES else 0)
        row["responded"] = int(row.get("responded", 0)) + (1 if prop.get("status") in ENGAGED_STATUSES else 0)
        row["appointments"] = int(row.get("appointments", 0)) + (1 if prop.get("status") in CONVERSION_STATUSES else 0)
        row["no_response"] = int(row.get("no_response", 0)) + (1 if prop.get("status") == "no_response" else 0)
        row["pipeline_value"] = int(row.get("pipeline_value", 0)) + int(round(_number(prop.get("estimatedValue"))))
        row["facade_m2"] = int(row.get("facade_m2", 0)) + int(round(_number(prop.get("estimatedFacadeM2"))))

    partners = sorted(partner_metrics.values(), key=lambda row: (-int(row.get("pipeline_value", 0)), str(row.get("name") or "")))
    for partner in partners:
        total = max(1, int(partner.get("properties", 0)))
        contacted = int(partner.get("contacted", 0))
        partner["target_response_rate_pct"] = round((int(partner.get("responded", 0)) / total) * 100, 1)
        partner["response_rate_pct"] = round((int(partner.get("responded", 0)) / contacted) * 100, 1) if contacted else 0
        partner["appointment_rate_pct"] = round((int(partner.get("appointments", 0)) / contacted) * 100, 1) if contacted else 0

    return {
        "type": source.get("type") or "producer_partner_network",
        "producer": source.get("producer", {"name": "Producer network"}),
        "product_focus": source.get("product_focus") or "facade renovation",
        "visibility": source.get("visibility", {
            "producer": "aggregate network plus partner drilldown",
            "partner": "own assigned campaign records only",
        }),
        "partners": partners,
        "metrics": {
            "partners": len(partners),
            "properties": len(properties),
            "pipeline_value": sum(int(row.get("pipeline_value", 0)) for row in partners),
            "facade_m2": sum(int(row.get("facade_m2", 0)) for row in partners),
            "appointments": sum(int(row.get("appointments", 0)) for row in partners),
            "responded": sum(int(row.get("responded", 0)) for row in partners),
            "contacted": sum(int(row.get("contacted", 0)) for row in partners),
        },
    }


def _access_lenses(modules: list[str], network: dict[str, Any] | None) -> list[dict[str, Any]]:
    module_keys = list(modules)
    first_module = module_keys[:1]
    partners = network.get("partners", []) if isinstance(network, dict) else []
    if not isinstance(partners, list):
        partners = []
    first_partner_id = _first_text((partners[0] or {}).get("id")) if partners else ""
    producer_name = _first_text((network or {}).get("producer", {}).get("name") if isinstance((network or {}).get("producer"), dict) else "", fallback="Producer network")

    lenses = [
        {
            "key": "producer_network",
            "label": f"{producer_name} executive",
            "role": "owner",
            "scope": "aggregate network plus partner drilldown" if partners else "tenant-wide module workspace",
            "partner_mode": "all",
            "module_mode": "all",
            "module_keys": module_keys,
            "summary": "Producer sees aggregate performance and can drill into partners inside the same tenant.",
            "blocked_visibility": [
                "other tenant raw addresses",
                "raw personal contact data outside approved sources",
            ],
            "live_gate": "blocked_until_live_rls_customer_access_proof",
            "buyer_review_only": True,
        },
        {
            "key": "partner_renovator",
            "label": "Partner renovator",
            "role": "manager",
            "scope": "assigned records only",
            "partner_mode": "first_partner",
            "partner_id": first_partner_id,
            "module_mode": "all",
            "module_keys": module_keys,
            "summary": "Partner view demonstrates the cutdown a renovator should receive for its own assigned campaign records.",
            "blocked_visibility": [
                "other partner raw addresses",
                "producer-wide raw comparison exports",
                "cross-tenant campaign learnings",
            ],
            "live_gate": "blocked_until_live_rls_customer_access_and_partner_reconciliation",
            "buyer_review_only": True,
        },
        {
            "key": "module_only_customer",
            "label": "Module-only customer",
            "role": "viewer",
            "scope": "tenant plus entitled module rows only",
            "partner_mode": "all",
            "module_mode": "first_module",
            "module_keys": first_module,
            "summary": "Shows what a customer sees when they bought only one pilot module.",
            "blocked_visibility": [
                "disabled module metrics",
                "disabled module exports",
                "cross-module private scores",
            ],
            "live_gate": "blocked_until_live_schema_rls_customer_access_proof",
            "buyer_review_only": True,
        },
        {
            "key": "it_security",
            "label": "IT and security review",
            "role": "admin",
            "scope": "proof, audit, provenance, and guardrails",
            "partner_mode": "all",
            "module_mode": "all",
            "module_keys": module_keys,
            "summary": "Focuses the demo on audit evidence and access boundaries instead of sales operation.",
            "blocked_visibility": [
                "secrets",
                "raw cross-tenant data",
                "unapproved public-data fields",
            ],
            "live_gate": "blocked_until_production_proof_and_customer_access_verification_pass",
            "buyer_review_only": True,
        },
        {
            "key": "customer_success",
            "label": "Customer success operator",
            "role": "manager",
            "scope": "adoption, handoff readiness, follow-up queues",
            "partner_mode": "all",
            "module_mode": "all",
            "module_keys": module_keys,
            "summary": "Shows the operating view for training, onboarding, follow-up queues, and value realization.",
            "blocked_visibility": [
                "unapproved outreach actions",
                "live contact activation before go/no-go",
            ],
            "live_gate": "blocked_until_customer_training_signoff_and_launch_go_no_go",
            "buyer_review_only": True,
        },
    ]
    if not partners:
        lenses = [lens for lens in lenses if lens["key"] != "partner_renovator"]
    if not first_module:
        lenses = [lens for lens in lenses if lens["key"] != "module_only_customer"]
    return lenses


def _node_id(kind: str, value: Any) -> str:
    clean = str(value or "").strip().lower()
    clean = "".join(char if char.isalnum() else "_" for char in clean)
    clean = "_".join(part for part in clean.split("_") if part)
    return f"{kind}:{clean[:80] or 'unknown'}"


def _add_brain_node(
    nodes: dict[str, dict[str, Any]],
    node_id: str,
    label: str,
    node_type: str,
    **attrs: Any,
) -> None:
    existing = nodes.get(node_id, {})
    weight = int(existing.get("weight", 0)) + int(attrs.pop("weight", 1))
    nodes[node_id] = {
        **existing,
        "id": node_id,
        "label": label,
        "type": node_type,
        "weight": weight,
        **{key: value for key, value in attrs.items() if value not in (None, "", [])},
    }


def _add_brain_edge(
    edges: dict[tuple[str, str, str], dict[str, Any]],
    source: str,
    target: str,
    edge_type: str,
    label: str,
    **attrs: Any,
) -> None:
    key = (source, target, edge_type)
    existing = edges.get(key, {})
    weight = int(existing.get("weight", 0)) + int(attrs.pop("weight", 1))
    edges[key] = {
        **existing,
        "source": source,
        "target": target,
        "type": edge_type,
        "label": label,
        "weight": weight,
        **{field: value for field, value in attrs.items() if value not in (None, "", [])},
    }


def _build_second_brain(
    tenant_id: str,
    properties: list[dict[str, Any]],
    campaigns: list[dict[str, str]],
    modules: list[str],
    network: dict[str, Any] | None = None,
) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}

    tenant_node = _node_id("tenant", tenant_id)
    _add_brain_node(nodes, tenant_node, "Tenant workspace", "tenant", weight=max(1, len(properties)))

    for module_key in modules:
        module_node = _node_id("module", module_key)
        _add_brain_node(
            nodes,
            module_node,
            MODULE_LABELS.get(module_key, module_key),
            "module",
            module_key=module_key,
        )
        _add_brain_edge(edges, tenant_node, module_node, "enabled_module", "enabled")

    for campaign in campaigns:
        campaign_id = str(campaign.get("id") or "")
        module_key = str(campaign.get("module") or "")
        campaign_node = _node_id("campaign", campaign_id)
        _add_brain_node(
            nodes,
            campaign_node,
            _first_text(campaign.get("name"), campaign_id, fallback="Campaign"),
            "campaign",
            module_key=module_key,
            partner_id=campaign.get("partner_id"),
            territory=campaign.get("territory"),
        )
        if module_key:
            _add_brain_edge(edges, _node_id("module", module_key), campaign_node, "campaign", "campaign")
        if campaign.get("partner_id"):
            _add_brain_edge(
                edges,
                _node_id("partner", campaign.get("partner_id")),
                campaign_node,
                "partner_campaign",
                "campaign",
                partner_id=campaign.get("partner_id"),
            )

    network_partners = (network or {}).get("partners", [])
    if not isinstance(network_partners, list):
        network_partners = []
    for partner in network_partners:
        partner_node = _node_id("partner", partner.get("id"))
        _add_brain_node(
            nodes,
            partner_node,
            _first_text(partner.get("name"), partner.get("id"), fallback="Partner"),
            "partner",
            partner_id=partner.get("id"),
            region=partner.get("region"),
            weight=max(1, int(partner.get("properties", 1) or 1)),
        )
        _add_brain_edge(edges, tenant_node, partner_node, "partner_scope", "allocates", partner_id=partner.get("id"))

    for prop in properties:
        prop_node = _node_id("property", prop.get("id"))
        best = sorted(
            prop.get("assessments", {}).items(),
            key=lambda item: item[1].get("score", 0),
            reverse=True,
        )[0]
        best_module, best_assessment = best
        _add_brain_node(
            nodes,
            prop_node,
            _first_text(prop.get("address"), prop.get("id"), fallback="Property"),
            "property",
            property_id=prop.get("id"),
            city=prop.get("city"),
            score=best_assessment.get("score"),
            grade=best_assessment.get("grade"),
            module_key=best_module,
            status=prop.get("status"),
            weight=max(1, round(_number(best_assessment.get("score")) / 20)),
        )

        status = _first_text(prop.get("status"), fallback="generated")
        partner = prop.get("partner") if isinstance(prop.get("partner"), dict) else {}
        if partner.get("id"):
            partner_node = _node_id("partner", partner.get("id"))
            _add_brain_node(nodes, partner_node, _first_text(partner.get("name"), partner.get("id")), "partner", partner_id=partner.get("id"))
            _add_brain_edge(edges, partner_node, prop_node, "assigned_property", "assigned", property_id=prop.get("id"), partner_id=partner.get("id"))

        status_node = _node_id("status", status)
        _add_brain_node(nodes, status_node, status.replace("_", " ").title(), "reaction", status=status)
        _add_brain_edge(edges, prop_node, status_node, "campaign_status", "status", property_id=prop.get("id"))

        action = _first_text(prop.get("nextAction"), fallback="Review property")
        action_node = _node_id("action", action)
        _add_brain_node(nodes, action_node, action, "action")
        _add_brain_edge(edges, status_node, action_node, "next_action", "next", property_id=prop.get("id"))

        for tag in prop.get("tags", [])[:4]:
            tag_node = _node_id("tag", tag)
            _add_brain_node(nodes, tag_node, str(tag), "signal")
            _add_brain_edge(edges, tag_node, prop_node, "tag_signal", "signal", property_id=prop.get("id"))

        for objection in prop.get("objections", [])[:4]:
            objection_node = _node_id("objection", objection)
            _add_brain_node(nodes, objection_node, str(objection), "objection")
            _add_brain_edge(edges, prop_node, objection_node, "objection", "objection", property_id=prop.get("id"))

        public_context = prop.get("publicContext") if isinstance(prop.get("publicContext"), dict) else {}
        source_run_id = _first_text(public_context.get("sourceRunId"))
        for feature in public_context.get("features", [])[:3]:
            if not isinstance(feature, dict):
                continue
            feature_key = _first_text(feature.get("key"), fallback="public_context")
            feature_label = _first_text(feature.get("label"), feature_key, fallback="Public context")
            context_node = _node_id("public_context", feature_key)
            _add_brain_node(
                nodes,
                context_node,
                feature_label,
                "signal",
                source="public_context",
                source_run_id=source_run_id,
                geography_level=feature.get("geographyLevel"),
            )
            _add_brain_edge(
                edges,
                context_node,
                prop_node,
                "public_context",
                "public context",
                property_id=prop.get("id"),
                source_run_id=source_run_id,
                feature_key=feature_key,
            )

        for module_key, assessment in prop.get("assessments", {}).items():
            module_node = _node_id("module", module_key)
            _add_brain_edge(
                edges,
                module_node,
                prop_node,
                "scores_property",
                "scores",
                module_key=module_key,
                property_id=prop.get("id"),
                score=assessment.get("score"),
            )
            signal_label = _first_text(assessment.get("label"), fallback=MODULE_LABELS.get(module_key, module_key))
            signal_node = _node_id("signal", f"{module_key}:{signal_label}")
            _add_brain_node(
                nodes,
                signal_node,
                signal_label,
                "signal",
                module_key=module_key,
                score=assessment.get("score"),
            )
            _add_brain_edge(
                edges,
                signal_node,
                prop_node,
                "assessment_signal",
                "evidence",
                module_key=module_key,
                property_id=prop.get("id"),
                score=assessment.get("score"),
            )

    ordered_nodes = sorted(
        nodes.values(),
        key=lambda row: (
            {"tenant": 0, "module": 1, "partner": 2, "campaign": 3, "signal": 4, "property": 5, "reaction": 6, "objection": 7, "action": 8}.get(row["type"], 9),
            -int(row.get("weight", 0)),
            row["label"],
        ),
    )
    ordered_edges = sorted(edges.values(), key=lambda row: (row["type"], row["source"], row["target"]))
    return {
        "nodes": ordered_nodes,
        "edges": ordered_edges,
        "stats": {
            "nodes": len(ordered_nodes),
            "edges": len(ordered_edges),
            "properties": len(properties),
            "modules": len(modules),
            "signals": sum(1 for node in ordered_nodes if node["type"] == "signal"),
            "reactions": sum(1 for node in ordered_nodes if node["type"] in {"reaction", "objection"}),
        },
    }


def build_dashboard_snapshot(
    payload: dict[str, Any],
    tenant_name: str | None = None,
    tenant_slug: str | None = None,
    enabled_modules: list[str] | None = None,
    tenant_ids: list[str] | set[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    if enabled_modules is not None or tenant_ids is not None:
        payload = filter_payload_for_entitlements(
            payload,
            tenant_ids=tenant_ids,
            enabled_modules=enabled_modules,
        )
    else:
        validate_payload(payload)

    properties_by_id = {row["id"]: row for row in payload.get("properties", [])}
    assessments_by_property: dict[str, list[dict[str, Any]]] = {}
    targets_by_property: dict[str, list[dict[str, Any]]] = {}
    interactions_by_property: dict[str, list[dict[str, Any]]] = {}

    tenant_ids = set()
    allowed_modules = set(enabled_modules) if enabled_modules is not None else None
    module_keys = set(enabled_modules or [])
    for prop in properties_by_id.values():
        tenant_ids.add(str(prop.get("tenant_id") or ""))
    for assessment in payload.get("assessments", []):
        if allowed_modules is not None and assessment["module_key"] not in allowed_modules:
            continue
        assessments_by_property.setdefault(assessment["property_id"], []).append(assessment)
        tenant_ids.add(str(assessment.get("tenant_id") or ""))
        module_keys.add(assessment["module_key"])
    for target in payload.get("campaign_targets", []):
        if allowed_modules is not None and target["module_key"] not in allowed_modules:
            continue
        targets_by_property.setdefault(target["property_id"], []).append(target)
        module_keys.add(target["module_key"])
    for interaction in payload.get("interactions", []):
        if allowed_modules is not None and interaction.get("module_key") not in allowed_modules:
            continue
        if interaction.get("property_id"):
            interactions_by_property.setdefault(interaction["property_id"], []).append(interaction)
            if interaction.get("module_key"):
                module_keys.add(interaction["module_key"])

    ordered_modules = [key for key in PILOT_MODULES if key in module_keys]
    tenant_id_list = sorted(item for item in tenant_ids if item)
    if len(tenant_id_list) > 1:
        raise ValueError(f"Dashboard snapshots must contain exactly one tenant, got: {tenant_id_list}")
    tenant_id = tenant_id_list[0] if tenant_id_list else "tenant_demo"
    dashboard_properties: list[dict[str, Any]] = []

    for prop in properties_by_id.values():
        prop_assessments = assessments_by_property.get(prop["id"], [])
        prop_targets = targets_by_property.get(prop["id"], [])
        core = prop.get("core") if isinstance(prop.get("core"), dict) else {}
        partner = _property_network(prop)
        assessment_map: dict[str, dict[str, Any]] = {}
        best_module = ""
        best_score = -1.0
        estimated_value = 0
        estimated_facade_m2 = _number(core.get("estimated_facade_m2"))

        for assessment in prop_assessments:
            module_key = assessment["module_key"]
            raw_metrics = assessment.get("metrics") if isinstance(assessment.get("metrics"), dict) else {}
            metrics = filter_metrics_for_surface(module_key, raw_metrics, surface="dashboard")
            score = _number(assessment.get("score"))
            grade = _first_text(assessment.get("grade"), fallback="B")
            if score > best_score:
                best_score = score
                best_module = module_key
            estimated_value = max(estimated_value, _assessment_value(metrics, score))
            if module_key == "facadepilot":
                estimated_facade_m2 = max(estimated_facade_m2, _number(metrics.get("visible_facade_area_m2")))
            assessment_map[module_key] = {
                "score": int(round(score)),
                "grade": grade,
                "label": _assessment_label(module_key, metrics, grade),
                "confidence": _number(assessment.get("confidence"), 0.65),
                "metrics": metrics,
                "evidence": assessment.get("evidence", []),
            }

        status = _status_from_targets(prop_targets)
        interactions = sorted(
            interactions_by_property.get(prop["id"], []),
            key=lambda row: str(row.get("occurred_at") or row.get("created_at") or ""),
        )
        dashboard_interactions = [{
            "date": _interaction_date(_first_text(row.get("occurred_at"), row.get("created_at"))),
            "type": _first_text(row.get("interaction_type"), fallback="note"),
            "detail": _first_text(row.get("detail"), row.get("response_status"), fallback="Interaction logged"),
        } for row in interactions]

        dashboard_properties.append({
            "id": prop["id"],
            "address": prop["address"],
            "city": _first_text(prop.get("city"), prop.get("postcode"), fallback="Unknown"),
            "lat": _number(prop.get("lat")),
            "lon": _number(prop.get("lon")),
            "status": status,
            "nextAction": _next_action(prop_targets, best_module),
            "estimatedValue": estimated_value or int(round(max(15000, best_score * 850))),
            "estimatedFacadeM2": int(round(estimated_facade_m2)) if estimated_facade_m2 else 0,
            "partner": partner,
            "producer": _first_text(core.get("producer"), partner.get("producer")),
            "territory": _first_text(core.get("territory"), partner.get("territory"), prop.get("city")),
            "renovationSystem": _first_text(core.get("renovation_system"), core.get("system"), fallback=""),
            "tags": _property_tags(prop, prop_assessments),
            "publicContext": _public_context(prop),
            "assessments": assessment_map,
            "interactions": dashboard_interactions,
            "objections": _collect_objections(interactions, prop_targets),
        })

    dashboard_properties = [row for row in dashboard_properties if row["assessments"]]
    dashboard_properties.sort(
        key=lambda prop: max((item.get("score", 0) for item in prop["assessments"].values()), default=0),
        reverse=True,
    )

    campaigns = _campaigns_from_payload(payload, allowed_modules)
    source_ledger = build_source_ledger(payload)
    network = _network_from_payload(payload, dashboard_properties)
    brain = _build_second_brain(tenant_id, dashboard_properties, campaigns, ordered_modules, network=network)
    snapshot = {
        "tenant": {
            "id": tenant_slug or tenant_id,
            "name": tenant_name or tenant_slug or tenant_id,
            "modules": ordered_modules,
        },
        "campaigns": campaigns,
        "properties": dashboard_properties,
        "recommendations": _recommendations(dashboard_properties, ordered_modules),
        "summary": _snapshot_summary(tenant_id, dashboard_properties),
        "network": network,
        "accessLenses": _access_lenses(ordered_modules, network),
        "trust": {
            "sourceLedger": source_ledger,
            "publicContext": _public_context_summary(dashboard_properties),
        },
        "brain": brain,
    }
    snapshot["visualIntelligence"] = build_visual_intelligence(snapshot)
    return snapshot


def _campaigns_from_payload(payload: dict[str, Any], allowed_modules: set[str] | None = None) -> list[dict[str, str]]:
    campaigns = payload.get("campaigns", [])
    if campaigns:
        rows = []
        for row in campaigns:
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            module_key = _first_text(row.get("module_key"), row.get("module"))
            if not row.get("id") or (allowed_modules is not None and module_key not in allowed_modules):
                continue
            rows.append({
                "id": str(row.get("id")),
                "name": _first_text(row.get("name"), row.get("id")),
                "module": module_key,
                "partner_id": _first_text(row.get("partner_id"), metadata.get("partner_id")),
                "partner_name": _first_text(row.get("partner_name"), metadata.get("partner_name")),
                "territory": _first_text(row.get("territory"), metadata.get("territory")),
            })
        return rows

    by_id: dict[str, str] = {}
    for target in payload.get("campaign_targets", []):
        if allowed_modules is not None and target.get("module_key") not in allowed_modules:
            continue
        campaign_id = _first_text(target.get("campaign_id"))
        if campaign_id:
            by_id[campaign_id] = _first_text(target.get("module_key"))
    return [{
        "id": campaign_id,
        "name": campaign_id,
        "module": module_key,
    } for campaign_id, module_key in sorted(by_id.items())]


def write_dashboard_json(snapshot: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")


def write_dashboard_js(snapshot: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(snapshot, indent=2, ensure_ascii=False)
    output_path.write_text(
        "// Generated by platform/homepilot_snapshot.py.\n"
        "// Keep tenant-specific dashboard snapshots out of public repos.\n"
        f"window.HOMEPILOT_DASHBOARD = {body};\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HomePilot dashboard snapshots")
    parser.add_argument("--json", required=True, type=Path, help="Canonical HomePilot payload")
    parser.add_argument("--tenant-name", default="")
    parser.add_argument("--tenant-slug", default="")
    parser.add_argument("--module", dest="enabled_modules", action="append", default=None, help="Restrict snapshot to an enabled module key; repeat for multiple modules")
    sub = parser.add_subparsers(dest="cmd", required=True)

    json_cmd = sub.add_parser("dashboard-json", help="Write dashboard snapshot JSON")
    json_cmd.add_argument("--out", required=True, type=Path)

    js_cmd = sub.add_parser("dashboard-js", help="Write dashboard-data.js for the static client")
    js_cmd.add_argument("--out", type=Path, default=DEFAULT_CLIENT_DATA)

    args = parser.parse_args()
    payload = load_payload(args.json)
    snapshot = build_dashboard_snapshot(
        payload,
        tenant_name=args.tenant_name or None,
        tenant_slug=args.tenant_slug or None,
        enabled_modules=args.enabled_modules,
    )

    if args.cmd == "dashboard-json":
        write_dashboard_json(snapshot, args.out)
        print(json.dumps({"output": str(args.out), "properties": len(snapshot["properties"])}, indent=2))
    elif args.cmd == "dashboard-js":
        write_dashboard_js(snapshot, args.out)
        print(json.dumps({"output": str(args.out), "properties": len(snapshot["properties"])}, indent=2))


if __name__ == "__main__":
    main()
