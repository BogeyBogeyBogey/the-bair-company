#!/usr/bin/env python3
"""
Generic Pilot CSV adapter.

Use this for WindowPilot, RoofPilot, GardenPilot, PoolPilot, PorchPilot,
DrivewayPilot, and future modules when their CSV already contains canonical
metric columns. FacadePilot keeps its legacy adapter because its source columns
are older and more specific.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from homepilot_platform import (
    PILOT_MODULES,
    canonical_campaign_id,
    canonical_property_id,
    canonical_tenant_id,
    stable_hash,
)
from homepilot_store import summarize_payload, validate_payload


ADDRESS_COLUMNS = ("address", "adres", "straat", "property_address")
CITY_COLUMNS = ("city", "gemeente", "plaats")
POSTCODE_COLUMNS = ("postcode", "postal_code", "zip")
LAT_COLUMNS = ("lat", "latitude")
LON_COLUMNS = ("lon", "lng", "longitude")
SOURCE_COLUMNS = ("source_external_id", "external_id", "capakey", "CAPAKEY")
PROPERTY_TYPE_COLUMNS = ("property_type", "huistype", "building_type")
GRADE_COLUMNS = ("grade", "lead_klasse", "priority_grade")
CONFIDENCE_COLUMNS = ("confidence", "model_confidence")
STATUS_COLUMNS = ("status", "campaign_status")
NEXT_ACTION_COLUMNS = ("next_action", "nextAction")

EVIDENCE_COLUMNS = {
    "streetview": ("streetview_path", "streetview_url"),
    "satellite": ("satellite_path", "satellite_url"),
    "render": ("render_path", "render_url"),
    "photo": ("photo_path", "photo_url"),
    "landing": ("landing_url", "landing_page"),
}


def _text(row: dict[str, Any], *columns: str) -> str:
    for column in columns:
        value = row.get(column)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _metric_value(value: Any, value_type: str) -> Any | None:
    if value in (None, ""):
        return None
    if value_type == "number":
        return _num(value)
    return str(value).strip()


def _score_value(row: dict[str, Any], module_key: str) -> float | None:
    definition = PILOT_MODULES[module_key]
    candidates = (
        definition.primary_score_key,
        "score",
        "lead_score",
        "priority_score",
        f"{module_key}_score",
    )
    return _num(_text(row, *candidates))


def _grade_value(row: dict[str, Any], module_key: str) -> str | None:
    definition = PILOT_MODULES[module_key]
    return _text(row, f"{definition.primary_score_key}_grade", f"{module_key}_grade", *GRADE_COLUMNS) or None


def _evidence(row: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for evidence_type, columns in EVIDENCE_COLUMNS.items():
        value = _text(row, *columns)
        if value:
            items.append({"type": evidence_type, "value": value})
    return items


def _metrics(row: dict[str, Any], module_key: str) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for metric in PILOT_MODULES[module_key].metrics:
        value = _metric_value(row.get(metric.key), metric.value_type)
        if value is not None:
            metrics[metric.key] = value
    return metrics


def _target_status(row: dict[str, Any]) -> str:
    return _text(row, *STATUS_COLUMNS) or "generated"


def pilot_row_to_records(
    row: dict[str, Any],
    module_key: str,
    tenant_id: str,
    campaign_id: str | None = None,
    source_run_id: str | None = None,
) -> dict[str, Any]:
    if module_key not in PILOT_MODULES:
        raise ValueError(f"Unknown module_key: {module_key}")
    tenant_uuid = canonical_tenant_id(tenant_id)
    address = _text(row, *ADDRESS_COLUMNS)
    if not address:
        raise ValueError(f"CSV row missing address column: {row}")
    lat = _num(_text(row, *LAT_COLUMNS))
    lon = _num(_text(row, *LON_COLUMNS))
    property_id = canonical_property_id(tenant_uuid, address, lat, lon)
    source_external_id = _text(row, *SOURCE_COLUMNS) or None
    score = _score_value(row, module_key)
    grade = _grade_value(row, module_key)
    metrics = _metrics(row, module_key)
    primary_score_key = PILOT_MODULES[module_key].primary_score_key
    if score is not None and primary_score_key not in metrics:
        metrics[primary_score_key] = score

    assessment_id = "asmt_" + stable_hash(
        tenant_uuid,
        property_id,
        module_key,
        source_run_id or source_external_id or "",
    )
    evidence = _evidence(row)
    confidence = _num(_text(row, *CONFIDENCE_COLUMNS))

    property_record = {
        "id": property_id,
        "tenant_id": tenant_uuid,
        "source_external_id": source_external_id,
        "address": address,
        "postcode": _text(row, *POSTCODE_COLUMNS) or None,
        "city": _text(row, *CITY_COLUMNS) or None,
        "lat": lat,
        "lon": lon,
        "property_type": _text(row, *PROPERTY_TYPE_COLUMNS) or None,
        "core": {},
    }

    assessment_record = {
        "id": assessment_id,
        "tenant_id": tenant_uuid,
        "property_id": property_id,
        "module_key": module_key,
        "score": score,
        "grade": grade,
        "confidence": confidence if confidence is not None else (0.85 if evidence else 0.65),
        "metrics": metrics,
        "evidence": evidence,
        "source_run_id": source_run_id,
    }

    target_record = None
    if campaign_id:
        campaign_uuid = canonical_campaign_id(tenant_uuid, module_key, campaign_id)
        metadata = {}
        next_action = _text(row, *NEXT_ACTION_COLUMNS)
        if next_action:
            metadata["next_action"] = next_action
        target_record = {
            "tenant_id": tenant_uuid,
            "campaign_id": campaign_uuid,
            "property_id": property_id,
            "module_key": module_key,
            "status": _target_status(row),
            "priority_score": score,
            "priority_grade": grade,
            "metadata": metadata,
        }

    return {
        "property": property_record,
        "assessment": assessment_record,
        "campaign_target": target_record,
    }


def convert_pilot_csv(
    csv_path: Path,
    module_key: str,
    tenant_id: str,
    campaign_id: str | None = None,
    source_run_id: str | None = None,
    campaign_name: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if module_key not in PILOT_MODULES:
        raise ValueError(f"Unknown module_key: {module_key}")

    tenant_uuid = canonical_tenant_id(tenant_id)
    campaign_uuid = canonical_campaign_id(tenant_uuid, module_key, campaign_id) if campaign_id else None
    campaigns = []
    if campaign_uuid:
        campaigns.append({
            "id": campaign_uuid,
            "tenant_id": tenant_uuid,
            "module_key": module_key,
            "name": campaign_name or str(campaign_id),
            "channel": "direct_mail",
            "status": "running",
        })

    properties_by_id: dict[str, dict[str, Any]] = {}
    assessments: list[dict[str, Any]] = []
    campaign_targets: list[dict[str, Any]] = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            records = pilot_row_to_records(row, module_key, tenant_uuid, campaign_uuid, source_run_id)
            prop = {key: value for key, value in records["property"].items() if value is not None}
            properties_by_id[prop["id"]] = prop
            assessments.append(records["assessment"])
            if records["campaign_target"]:
                campaign_targets.append(records["campaign_target"])

    payload = {
        "campaigns": campaigns,
        "properties": list(properties_by_id.values()),
        "assessments": assessments,
        "campaign_targets": campaign_targets,
        "interactions": [],
        "response_insights": [],
    }
    validate_payload(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a module CSV into HomePilot JSON")
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--module", required=True, choices=sorted(PILOT_MODULES))
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--campaign-id", default="")
    parser.add_argument("--campaign-name", default="")
    parser.add_argument("--source-run-id", default="")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    payload = convert_pilot_csv(
        csv_path=args.csv,
        module_key=args.module,
        tenant_id=args.tenant_id,
        campaign_id=args.campaign_id or None,
        source_run_id=args.source_run_id or None,
        campaign_name=args.campaign_name or None,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(args.out), "summary": summarize_payload(payload)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
