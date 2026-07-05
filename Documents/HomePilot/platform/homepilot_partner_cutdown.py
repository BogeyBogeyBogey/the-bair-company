#!/usr/bin/env python3
"""
Build partner-specific HomePilot cutdown packages.

Producer networks such as DAW need two views of the same tenant-scoped data:
the producer sees aggregate network performance, while each renovation partner
receives only assigned records. This module creates those partner handoff
packages from a canonical payload and writes explicit leakage evidence.
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from homepilot_customer_package import build_customer_package
from homepilot_onboarding import build_onboarding_payload
from homepilot_store import load_payload, summarize_payload, validate_payload


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _first_text(*values: Any, fallback: str = "") -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return fallback


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("metadata")
    return value if isinstance(value, dict) else {}


def _core(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("core")
    return value if isinstance(value, dict) else {}


def _network(row: dict[str, Any]) -> dict[str, Any]:
    core = _core(row)
    value = core.get("network")
    return value if isinstance(value, dict) else {}


def row_partner_id(row: dict[str, Any]) -> str:
    metadata = _metadata(row)
    core = _core(row)
    network = _network(row)
    return _first_text(
        row.get("partner_id"),
        metadata.get("partner_id"),
        core.get("partner_id"),
        network.get("partner_id"),
    )


def network_partners(payload: dict[str, Any]) -> list[dict[str, Any]]:
    network = payload.get("network") if isinstance(payload.get("network"), dict) else {}
    partners = network.get("partners") if isinstance(network.get("partners"), list) else []
    return [partner for partner in partners if isinstance(partner, dict) and partner.get("id")]


def partner_ids(payload: dict[str, Any]) -> list[str]:
    ids = [str(partner["id"]) for partner in network_partners(payload)]
    if ids:
        return ids
    discovered = {row_partner_id(row) for row in payload.get("properties", []) if row_partner_id(row)}
    discovered |= {row_partner_id(row) for row in payload.get("campaigns", []) if row_partner_id(row)}
    discovered |= {row_partner_id(row) for row in payload.get("campaign_targets", []) if row_partner_id(row)}
    return sorted(discovered)


def _partner_record(payload: dict[str, Any], partner_id: str) -> dict[str, Any]:
    for partner in network_partners(payload):
        if str(partner.get("id")) == str(partner_id):
            return deepcopy(partner)
    return {"id": partner_id, "name": partner_id, "region": "Unknown"}


def _filtered_network(payload: dict[str, Any], partner_id: str) -> dict[str, Any] | None:
    source = payload.get("network") if isinstance(payload.get("network"), dict) else None
    if not source:
        return None
    network = deepcopy(source)
    network["source_type"] = source.get("type")
    network["type"] = "partner_cutdown"
    network["partners"] = [_partner_record(payload, partner_id)]
    visibility = network.get("visibility") if isinstance(network.get("visibility"), dict) else {}
    network["visibility"] = {
        "partner": visibility.get("partner") or "Partner sees only assigned campaign records and own follow-up history.",
        "producer_context": visibility.get("producer") or "Producer retains aggregate network view outside this partner cutdown.",
    }
    network["scope"] = {"partner_id": partner_id, "scope_type": "assigned_records_only"}
    return network


def filter_payload_for_partner(payload: dict[str, Any], partner_id: str) -> dict[str, Any]:
    validate_payload(payload)
    partner_id = str(partner_id)

    campaigns = [row for row in payload.get("campaigns", []) if row_partner_id(row) == partner_id]
    campaign_ids = {str(row.get("id")) for row in campaigns if row.get("id")}

    properties = [row for row in payload.get("properties", []) if row_partner_id(row) == partner_id]
    property_ids = {str(row.get("id")) for row in properties if row.get("id")}

    targets = [
        row for row in payload.get("campaign_targets", [])
        if str(row.get("property_id") or "") in property_ids
        and (not campaign_ids or str(row.get("campaign_id") or "") in campaign_ids)
    ]
    if not campaign_ids:
        campaign_ids = {str(row.get("campaign_id")) for row in targets if row.get("campaign_id")}
        campaigns = [row for row in payload.get("campaigns", []) if str(row.get("id") or "") in campaign_ids]

    assessments = [
        row for row in payload.get("assessments", [])
        if str(row.get("property_id") or "") in property_ids
    ]
    interactions = [
        row for row in payload.get("interactions", [])
        if str(row.get("property_id") or "") in property_ids
        and (not row.get("campaign_id") or str(row.get("campaign_id")) in campaign_ids)
    ]
    response_insights = [
        row for row in payload.get("response_insights", [])
        if not row.get("campaign_id") or str(row.get("campaign_id")) in campaign_ids
    ]

    scoped: dict[str, Any] = {
        "campaigns": deepcopy(campaigns),
        "properties": deepcopy(properties),
        "assessments": deepcopy(assessments),
        "campaign_targets": deepcopy(targets),
        "interactions": deepcopy(interactions),
        "response_insights": deepcopy(response_insights),
        "exports": [],
        "audit_events": [],
    }
    network = _filtered_network(payload, partner_id)
    if network and properties:
        scoped["network"] = network
    validate_payload(scoped)
    return scoped


def _all_strings(value: Any) -> list[str]:
    if isinstance(value, dict):
        strings: list[str] = []
        for key, item in value.items():
            strings.append(str(key))
            strings.extend(_all_strings(item))
        return strings
    if isinstance(value, list):
        strings = []
        for item in value:
            strings.extend(_all_strings(item))
        return strings
    if isinstance(value, str):
        return [value]
    return []


def audit_partner_scope(value: Any, partner_id: str, partners: list[dict[str, Any]]) -> dict[str, Any]:
    strings = _all_strings(value)
    allowed_id = str(partner_id)
    partner_names = {str(partner.get("id")): str(partner.get("name") or partner.get("id")) for partner in partners}
    partner_ids = set(partner_names)
    visible_partner_ids = sorted(item for item in partner_ids if item in strings)
    other_partner_ids = sorted(item for item in visible_partner_ids if item != allowed_id)
    other_partner_names = sorted(
        name for pid, name in partner_names.items()
        if pid != allowed_id and name and name in strings
    )
    return {
        "status": "pass" if not other_partner_ids and not other_partner_names else "fail",
        "allowed_partner_id": allowed_id,
        "visible_partner_ids": visible_partner_ids,
        "other_partner_ids": other_partner_ids,
        "other_partner_names": other_partner_names,
    }


def build_partner_cutdown_pack(
    payload: dict[str, Any],
    out_dir: Path,
    tenant_name: str,
    tenant_slug: str,
    modules: list[str],
    include_xlsx: bool = False,
    include_zip: bool = False,
) -> dict[str, Any]:
    validate_payload(payload)
    out_dir.mkdir(parents=True, exist_ok=True)
    partners = network_partners(payload)
    ids = partner_ids(payload)
    partner_rows = []

    for partner_id in ids:
        partner = _partner_record(payload, partner_id)
        partner_name = str(partner.get("name") or partner_id)
        partner_dir = out_dir / partner_id
        data_dir = partner_dir / "data"
        package_dir = partner_dir / "customer_package"
        scoped_payload = filter_payload_for_partner(payload, partner_id)
        onboarding = build_onboarding_payload(
            name=tenant_name,
            slug=tenant_slug,
            modules=modules,
            subscription_tier="producer-network-partner-cutdown",
            settings={
                "partner_cutdown": True,
                "partner_id": partner_id,
                "partner_name": partner_name,
                "producer_network": True,
            },
        )
        payload_path = data_dir / "scoped_payload.json"
        onboarding_path = data_dir / "onboarding.json"
        write_json(payload_path, scoped_payload)
        write_json(onboarding_path, onboarding)
        package_manifest = build_customer_package(
            onboarding_path=onboarding_path,
            payload_path=payload_path,
            output_dir=package_dir,
            tenant_name=f"{partner_name} - DAW partner cutdown",
            tenant_slug=tenant_slug,
            modules=modules,
            include_xlsx=include_xlsx,
            include_zip=include_zip,
            audit_payload=True,
        )
        snapshot_path = Path(package_manifest["paths"]["dashboard_snapshot"])
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        payload_audit = audit_partner_scope(scoped_payload, partner_id, partners)
        snapshot_audit = audit_partner_scope(snapshot, partner_id, partners)
        counts = summarize_payload(scoped_payload)
        status = "pass" if (
            package_manifest["access_audit"]["status"] == "pass"
            and package_manifest["boardroom_report"]["status"] == "pass"
            and payload_audit["status"] == "pass"
            and snapshot_audit["status"] == "pass"
            and counts["properties"] > 0
        ) else "fail"
        partner_rows.append({
            "partner_id": partner_id,
            "partner_name": partner_name,
            "region": partner.get("region") or partner.get("territory"),
            "status": status,
            "counts": counts,
            "access_audit": package_manifest["access_audit"]["status"],
            "boardroom_report": package_manifest["boardroom_report"]["status"],
            "payload_scope_audit": payload_audit,
            "snapshot_scope_audit": snapshot_audit,
            "paths": {
                "payload": str(payload_path),
                "onboarding": str(onboarding_path),
                "manifest": package_manifest["paths"]["manifest"],
                "dashboard": package_manifest["paths"]["dashboard_index"],
                "boardroom_report": package_manifest["paths"]["boardroom_report_html"],
                "exports": package_manifest["paths"]["exports"],
                "zip": package_manifest["paths"].get("zip"),
            },
        })

    failures = [row for row in partner_rows if row["status"] != "pass"]
    manifest = {
        "pack_type": "homepilot_partner_cutdown_pack",
        "status": "pass" if partner_rows and not failures else "fail",
        "tenant_slug": tenant_slug,
        "tenant_name": tenant_name,
        "modules": modules,
        "partners": partner_rows,
        "summary": {
            "partners": len(partner_rows),
            "failed_partners": len(failures),
            "properties": sum(row["counts"]["properties"] for row in partner_rows),
            "campaign_targets": sum(row["counts"]["campaign_targets"] for row in partner_rows),
            "interactions": sum(row["counts"].get("interactions", 0) for row in partner_rows),
        },
        "paths": {"manifest": str(out_dir / "partner_cutdown_manifest.json")},
    }
    write_json(out_dir / "partner_cutdown_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build partner-specific HomePilot cutdown packages")
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--tenant-name", required=True)
    parser.add_argument("--tenant-slug", required=True)
    parser.add_argument("--module", action="append", dest="modules", default=[])
    parser.add_argument("--include-xlsx", action="store_true")
    parser.add_argument("--include-zip", action="store_true")
    args = parser.parse_args()
    payload = load_payload(args.payload)
    pack = build_partner_cutdown_pack(
        payload=payload,
        out_dir=args.out_dir,
        tenant_name=args.tenant_name,
        tenant_slug=args.tenant_slug,
        modules=args.modules or ["facadepilot"],
        include_xlsx=args.include_xlsx,
        include_zip=args.include_zip,
    )
    print(json.dumps({"output": str(args.out_dir), "status": pack["status"], "summary": pack["summary"]}, indent=2))


if __name__ == "__main__":
    main()
