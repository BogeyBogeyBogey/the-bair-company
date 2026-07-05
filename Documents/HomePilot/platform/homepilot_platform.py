#!/usr/bin/env python3
"""
HomePilot Platform core contracts.

This module is independent from any single Pilot. It defines:

- available Pilot modules
- metric catalogs per module
- deterministic property IDs
- a FacadePilot CSV adapter for migration
- a small CLI for schema/catalog/export work
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


HERE = Path(__file__).parent.resolve()
SCHEMA_PATH = HERE / "supabase_schema.sql"
UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "homepilot.property-intelligence")


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    label: str
    value_type: str
    unit: str
    visibility: str
    description: str = ""


@dataclass(frozen=True)
class ModuleDefinition:
    key: str
    label: str
    category: str
    primary_score_key: str
    metrics: tuple[MetricDefinition, ...]


def metric(
    key: str,
    label: str,
    value_type: str,
    unit: str = "",
    visibility: str = "tenant_private",
    description: str = "",
) -> MetricDefinition:
    return MetricDefinition(key, label, value_type, unit, visibility, description)


PILOT_MODULES: dict[str, ModuleDefinition] = {
    "facadepilot": ModuleDefinition(
        key="facadepilot",
        label="FacadePilot",
        category="exterior",
        primary_score_key="facade_opportunity_score",
        metrics=(
            metric("facade_opportunity_score", "Facade opportunity score", "number", "0-100", "benchmarkable"),
            metric("facade_grade", "Facade lead grade", "string", "", "benchmarkable"),
            metric("visible_facade_area_m2", "Visible facade area proxy", "number", "m2"),
            metric("facade_preset", "Recommended renovation type", "string", "", "benchmarkable"),
            metric("property_type", "Property type", "string", "", "benchmarkable"),
            metric("pre_1990_neighborhood_pct", "Pre-1990 neighborhood share", "number", "%", "benchmarkable"),
            metric("median_income", "Neighborhood median income", "number", "EUR"),
            metric("render_quality", "Render/source image quality", "string"),
        ),
    ),
    "windowpilot": ModuleDefinition(
        key="windowpilot",
        label="WindowPilot",
        category="exterior",
        primary_score_key="window_opportunity_score",
        metrics=(
            metric("window_opportunity_score", "Window opportunity score", "number", "0-100", "benchmarkable"),
            metric("glazing_age_signal", "Glazing age signal", "string"),
            metric("frame_material_signal", "Frame material signal", "string"),
            metric("energy_savings_story_fit", "Energy savings story fit", "number", "0-100", "benchmarkable"),
            metric("visible_window_count", "Visible window count", "number", "count"),
            metric("replacement_urgency", "Replacement urgency", "string", "", "benchmarkable"),
        ),
    ),
    "roofpilot": ModuleDefinition(
        key="roofpilot",
        label="RoofPilot",
        category="exterior",
        primary_score_key="roof_opportunity_score",
        metrics=(
            metric("roof_opportunity_score", "Roof opportunity score", "number", "0-100", "benchmarkable"),
            metric("roof_area_m2", "Roof area", "number", "m2"),
            metric("roof_age_signal", "Roof age signal", "string"),
            metric("roof_material_signal", "Roof material signal", "string"),
            metric("solar_cross_sell_fit", "Solar cross-sell fit", "number", "0-100", "benchmarkable"),
            metric("storm_or_moss_signal", "Storm or moss signal", "string"),
        ),
    ),
    "gardenpilot": ModuleDefinition(
        key="gardenpilot",
        label="GardenPilot",
        category="outdoor",
        primary_score_key="garden_opportunity_score",
        metrics=(
            metric("garden_opportunity_score", "Garden opportunity score", "number", "0-100", "benchmarkable"),
            metric("garden_area_m2", "Garden area", "number", "m2"),
            metric("outdoor_living_fit", "Outdoor living fit", "number", "0-100", "benchmarkable"),
            metric("maintenance_signal", "Maintenance signal", "string"),
            metric("privacy_fit", "Privacy fit", "number", "0-100", "benchmarkable"),
        ),
    ),
    "poolpilot": ModuleDefinition(
        key="poolpilot",
        label="PoolPilot",
        category="outdoor",
        primary_score_key="pool_opportunity_score",
        metrics=(
            metric("pool_opportunity_score", "Pool opportunity score", "number", "0-100", "benchmarkable"),
            metric("pool_fit", "Pool fit", "number", "0-100", "benchmarkable"),
            metric("sun_exposure_signal", "Sun exposure signal", "string"),
            metric("garden_access_quality", "Garden access quality", "string"),
            metric("terrain_complexity", "Terrain complexity", "string"),
        ),
    ),
    "porchpilot": ModuleDefinition(
        key="porchpilot",
        label="PorchPilot",
        category="exterior",
        primary_score_key="porch_opportunity_score",
        metrics=(
            metric("porch_opportunity_score", "Porch opportunity score", "number", "0-100", "benchmarkable"),
            metric("entry_visibility", "Entry visibility", "string"),
            metric("front_house_upgrade_fit", "Front house upgrade fit", "number", "0-100", "benchmarkable"),
            metric("porch_style_fit", "Porch style fit", "string"),
        ),
    ),
    "drivewaypilot": ModuleDefinition(
        key="drivewaypilot",
        label="DrivewayPilot",
        category="outdoor",
        primary_score_key="driveway_opportunity_score",
        metrics=(
            metric("driveway_opportunity_score", "Driveway opportunity score", "number", "0-100", "benchmarkable"),
            metric("driveway_area_m2", "Driveway area", "number", "m2"),
            metric("surface_condition_signal", "Surface condition signal", "string"),
            metric("drainage_risk", "Drainage risk", "string"),
            metric("ev_charger_fit", "EV charger fit", "number", "0-100", "benchmarkable"),
        ),
    ),
}


def module_catalog() -> dict[str, dict[str, Any]]:
    return {key: asdict(definition) for key, definition in PILOT_MODULES.items()}


def metric_catalog(module_key: str | None = None) -> dict[str, list[dict[str, Any]]]:
    modules = {module_key: PILOT_MODULES[module_key]} if module_key else PILOT_MODULES
    return {key: [asdict(item) for item in definition.metrics] for key, definition in modules.items()}


def normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def stable_hash(*parts: Any, length: int = 20) -> str:
    raw = "|".join(normalize_text(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def canonical_uuid(*parts: Any) -> str:
    raw = "|".join(normalize_text(part) for part in parts)
    return str(uuid.uuid5(UUID_NAMESPACE, raw))


def normalize_uuid(value: Any, *fallback_parts: Any) -> str:
    text = str(value or "").strip()
    try:
        return str(uuid.UUID(text))
    except (TypeError, ValueError, AttributeError):
        parts = fallback_parts or (text,)
        return canonical_uuid(*parts)


def canonical_campaign_id(tenant_id: str, module_key: str, campaign_key: Any) -> str:
    return normalize_uuid(campaign_key, tenant_id, module_key, campaign_key)


def canonical_tenant_id(tenant_key: Any) -> str:
    return normalize_uuid(tenant_key, "tenant", tenant_key)


def canonical_property_id(tenant_id: str, address: str, lat: Any = None, lon: Any = None) -> str:
    lat_key = "" if lat in (None, "") else f"{float(lat):.5f}"
    lon_key = "" if lon in (None, "") else f"{float(lon):.5f}"
    return f"prop_{stable_hash(tenant_id, address, lat_key, lon_key)}"


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def facade_row_to_homepilot_records(
    row: dict[str, Any],
    tenant_id: str,
    campaign_id: str | None = None,
    source_run_id: str | None = None,
) -> dict[str, Any]:
    """Convert one FacadePilot scored CSV row to HomePilot record payloads."""
    tenant_uuid = canonical_tenant_id(tenant_id)
    address = _string(row.get("adres")) or "Onbekend adres"
    lat = _num(row.get("lat"))
    lon = _num(row.get("lon"))
    property_id = canonical_property_id(tenant_uuid, address, lat, lon)
    capakey = _string(row.get("CAPAKEY") or row.get("capakey"))
    score = _num(row.get("lead_score"))
    grade = _string(row.get("lead_klasse"))
    assessment_id = f"asmt_{stable_hash(tenant_uuid, property_id, 'facadepilot', source_run_id or capakey or '')}"

    property_record = {
        "id": property_id,
        "tenant_id": tenant_uuid,
        "address": address,
        "lat": lat,
        "lon": lon,
        "source_external_id": capakey,
        "property_type": _string(row.get("huistype")),
        "core": {
            "perceel_m2": _num(row.get("perceel_m2")),
            "bebouwd_m2": _num(row.get("bebouwd_m2")),
            "bebouwd_ratio": _num(row.get("bebouwd_ratio")),
            "sector_id": _string(row.get("sector_id")),
            "google_maps": _string(row.get("google_maps")),
        },
    }

    metrics = {
        "facade_opportunity_score": score,
        "facade_grade": grade,
        "visible_facade_area_m2": _num(row.get("bebouwd_m2")),
        "facade_preset": _string(row.get("preset_auto") or row.get("facade_preset")),
        "property_type": _string(row.get("huistype")),
        "pre_1990_neighborhood_pct": _num(row.get("pct_pre_1990")),
        "median_income": _num(row.get("mediaan_inkomen")),
        "render_quality": _string(row.get("render_quality_type")),
    }
    metrics = {key: value for key, value in metrics.items() if value is not None}

    evidence = []
    for evidence_type, col in (
        ("streetview", "streetview_path"),
        ("render", "render_path"),
        ("flyer", "flyer_path"),
        ("landing", "landing_url"),
    ):
        value = _string(row.get(col))
        if value:
            evidence.append({"type": evidence_type, "value": value})

    assessment_record = {
        "id": assessment_id,
        "tenant_id": tenant_uuid,
        "property_id": property_id,
        "module_key": "facadepilot",
        "score": score,
        "grade": grade,
        "confidence": 0.85 if evidence else 0.65,
        "metrics": metrics,
        "evidence": evidence,
        "source_run_id": source_run_id,
    }

    target_record = None
    if campaign_id:
        campaign_uuid = canonical_campaign_id(tenant_uuid, "facadepilot", campaign_id)
        target_record = {
            "tenant_id": tenant_uuid,
            "campaign_id": campaign_uuid,
            "property_id": property_id,
            "module_key": "facadepilot",
            "status": "generated",
            "priority_score": score,
            "priority_grade": grade,
        }

    return {
        "property": property_record,
        "assessment": assessment_record,
        "campaign_target": target_record,
    }


def convert_facade_csv(
    csv_path: Path,
    tenant_id: str,
    campaign_id: str | None = None,
    source_run_id: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    tenant_uuid = canonical_tenant_id(tenant_id)
    properties_by_id: dict[str, dict[str, Any]] = {}
    assessments: list[dict[str, Any]] = []
    campaign_targets: list[dict[str, Any]] = []
    campaigns: list[dict[str, Any]] = []
    campaign_uuid = canonical_campaign_id(tenant_uuid, "facadepilot", campaign_id) if campaign_id else None
    if campaign_uuid:
        campaigns.append({
            "id": campaign_uuid,
            "tenant_id": tenant_uuid,
            "module_key": "facadepilot",
            "name": str(campaign_id),
            "channel": "direct_mail",
            "status": "running",
        })

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            records = facade_row_to_homepilot_records(row, tenant_uuid, campaign_uuid, source_run_id)
            prop = records["property"]
            properties_by_id[prop["id"]] = prop
            assessments.append(records["assessment"])
            if records["campaign_target"]:
                campaign_targets.append(records["campaign_target"])

    return {
        "campaigns": campaigns,
        "properties": list(properties_by_id.values()),
        "assessments": assessments,
        "campaign_targets": campaign_targets,
        "interactions": [],
        "response_insights": [],
    }


def load_schema() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="HomePilot platform utilities")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("catalog", help="Print module and metrics catalog as JSON")
    sub.add_parser("schema", help="Print Supabase schema SQL")

    convert = sub.add_parser("convert-facade-csv", help="Convert FacadePilot scored CSV to HomePilot JSON")
    convert.add_argument("--csv", required=True, type=Path)
    convert.add_argument("--tenant-id", required=True)
    convert.add_argument("--campaign-id", default="")
    convert.add_argument("--source-run-id", default="")
    convert.add_argument("--out", required=True, type=Path)

    args = parser.parse_args()

    if args.cmd == "catalog":
        print(json.dumps({"modules": module_catalog(), "metrics": metric_catalog()}, indent=2, ensure_ascii=False))
    elif args.cmd == "schema":
        print(load_schema())
    elif args.cmd == "convert-facade-csv":
        if not args.csv.exists():
            raise SystemExit(f"CSV not found: {args.csv}")
        payload = convert_facade_csv(
            args.csv,
            tenant_id=args.tenant_id,
            campaign_id=args.campaign_id or None,
            source_run_id=args.source_run_id or None,
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            f"Wrote {args.out}: "
            f"{len(payload['properties'])} properties, "
            f"{len(payload['assessments'])} assessments, "
            f"{len(payload['campaign_targets'])} campaign targets"
        )


if __name__ == "__main__":
    main()
