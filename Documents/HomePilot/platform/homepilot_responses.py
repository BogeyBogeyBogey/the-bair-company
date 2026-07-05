#!/usr/bin/env python3
"""
Merge campaign response CSV rows into a HomePilot payload.

This is the operator bridge between "we contacted these properties" and
"what happened afterwards". It supports simple spreadsheet columns and emits a
validated HomePilot payload with updated campaign target statuses plus
interaction records.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_platform import PILOT_MODULES, canonical_campaign_id, canonical_uuid, normalize_text
from homepilot_store import load_payload, validate_payload


STATUS_VALUES = {
    "generated",
    "queued",
    "sent",
    "scanned",
    "clicked",
    "responded",
    "appointment",
    "customer",
    "rejected",
    "no_response",
}

INTERACTION_VALUES = {
    "flyer_sent",
    "email_sent",
    "scan",
    "click",
    "form_submit",
    "call",
    "meeting",
    "note",
    "status_change",
    "exported",
}


def _text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _timestamp(value: str) -> str:
    if not value:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return value


def _property_index(payload: dict[str, Any]) -> dict[str, str]:
    index = {}
    for prop in payload.get("properties", []):
        index[prop["id"]] = prop["id"]
        index[normalize_text(prop.get("address", ""))] = prop["id"]
    return index


def _tenant_for_property(payload: dict[str, Any], property_id: str) -> str:
    for prop in payload.get("properties", []):
        if prop["id"] == property_id:
            return prop["tenant_id"]
    raise ValueError(f"Unknown property_id: {property_id}")


def _module_for_property(payload: dict[str, Any], property_id: str, explicit_module: str) -> str:
    if explicit_module:
        if explicit_module not in PILOT_MODULES:
            raise ValueError(f"Unknown module_key: {explicit_module}")
        return explicit_module
    modules = sorted({
        row["module_key"]
        for row in payload.get("assessments", [])
        if row["property_id"] == property_id
    })
    if len(modules) == 1:
        return modules[0]
    raise ValueError(f"Response row for {property_id} needs module_key; available modules: {modules}")


def _campaign_for_response(
    payload: dict[str, Any],
    tenant_id: str,
    property_id: str,
    module_key: str,
    campaign_key: str,
) -> str:
    if campaign_key:
        return canonical_campaign_id(tenant_id, module_key, campaign_key)
    candidates = [
        target["campaign_id"]
        for target in payload.get("campaign_targets", [])
        if target["property_id"] == property_id and target["module_key"] == module_key
    ]
    if candidates:
        return candidates[0]
    raise ValueError(f"Response row for {property_id}/{module_key} needs campaign_id")


def _upsert_target(
    payload: dict[str, Any],
    tenant_id: str,
    campaign_id: str,
    property_id: str,
    module_key: str,
    status: str,
    occurred_at: str,
    next_action: str,
) -> None:
    for target in payload.setdefault("campaign_targets", []):
        if (
            target["campaign_id"] == campaign_id
            and target["property_id"] == property_id
            and target["module_key"] == module_key
        ):
            target["status"] = status
            target["last_interaction_at"] = occurred_at
            if next_action:
                metadata = target.setdefault("metadata", {})
                metadata["next_action"] = next_action
            return
    payload["campaign_targets"].append({
        "tenant_id": tenant_id,
        "campaign_id": campaign_id,
        "property_id": property_id,
        "module_key": module_key,
        "status": status,
        "last_interaction_at": occurred_at,
        "metadata": {"next_action": next_action} if next_action else {},
    })


def merge_response_rows(payload: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    index = _property_index(payload)
    interactions = payload.setdefault("interactions", [])

    for row in rows:
        property_key = _text(row, "property_id", "property", "address", "adres")
        property_id = index.get(property_key) or index.get(normalize_text(property_key))
        if not property_id:
            raise ValueError(f"Response row references unknown property: {property_key}")

        tenant_id = _tenant_for_property(payload, property_id)
        module_key = _module_for_property(payload, property_id, _text(row, "module_key", "module", "pilot"))
        campaign_key = _text(row, "campaign_id", "campaign", "campaign_key")
        campaign_id = _campaign_for_response(payload, tenant_id, property_id, module_key, campaign_key)
        status = _text(row, "status", "campaign_status") or "responded"
        if status not in STATUS_VALUES:
            raise ValueError(f"Unsupported campaign status: {status}")

        interaction_type = _text(row, "interaction_type", "type") or "status_change"
        if interaction_type not in INTERACTION_VALUES:
            raise ValueError(f"Unsupported interaction_type: {interaction_type}")

        occurred_at = _timestamp(_text(row, "occurred_at", "date", "datum"))
        next_action = _text(row, "next_action", "nextAction")
        _upsert_target(payload, tenant_id, campaign_id, property_id, module_key, status, occurred_at, next_action)

        detail = _text(row, "detail", "note", "comment", "reactie")
        response_status = _text(row, "response_status")
        interaction = {
            "id": canonical_uuid("interaction", tenant_id, campaign_id, property_id, module_key, occurred_at, interaction_type, detail, status),
            "tenant_id": tenant_id,
            "property_id": property_id,
            "campaign_id": campaign_id,
            "module_key": module_key,
            "interaction_type": interaction_type,
            "response_status": response_status or ("interested" if status in {"responded", "appointment", "customer"} else "none"),
            "sentiment": _text(row, "sentiment") or "unknown",
            "objection_code": _text(row, "objection_code", "objection"),
            "detail": detail or status.replace("_", " "),
            "occurred_at": occurred_at,
        }
        interactions.append({key: value for key, value in interaction.items() if value not in ("", None)})

    validate_payload(payload)
    return payload


def read_response_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge response CSV rows into a HomePilot payload")
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    payload = load_payload(args.payload)
    rows = read_response_csv(args.csv)
    merged = merge_response_rows(payload, rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "output": str(args.out),
        "response_rows": len(rows),
        "interactions": len(merged.get("interactions", [])),
        "campaign_targets": len(merged.get("campaign_targets", [])),
    }, indent=2))


if __name__ == "__main__":
    main()
