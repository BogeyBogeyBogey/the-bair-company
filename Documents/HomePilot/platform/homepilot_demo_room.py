#!/usr/bin/env python3
"""
Build a synthetic HomePilot enterprise demo room.

This is the product showroom for buyer demos and customer-success onboarding:
one tenant, all pilot modules, realistic property/campaign/response data, a
customer package, exports, access audit, audit trail, and data dictionary.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_audit_trail import build_audit_event
from homepilot_customer_package import build_customer_package
from homepilot_data_dictionary import build_data_dictionary_pack
from homepilot_enrichment import build_enrichment_pack
from homepilot_integrations import build_integration_pack
from homepilot_onboarding import build_onboarding_payload, validate_onboarding_payload
from homepilot_partner_cutdown import build_partner_cutdown_pack
from homepilot_platform import PILOT_MODULES, canonical_campaign_id, canonical_property_id, canonical_tenant_id, canonical_uuid, stable_hash
from homepilot_portal import build_portal_bundle
from homepilot_privacy import build_export_log_record
from homepilot_store import summarize_payload, validate_payload


DEFAULT_CREATED_AT = "2026-06-19T00:00:00+00:00"
DEMO_MODULES = tuple(PILOT_MODULES.keys())
SCALED_DEMO_DEFAULT_PROPERTIES = 2000

PROPERTY_BLUEPRINTS: tuple[dict[str, Any], ...] = (
    {
        "address": "Tiensesteenweg 56",
        "city": "Bunsbeek",
        "lat": 50.841,
        "lon": 4.947,
        "property_type": "halfopen",
        "tags": ["pre-1990", "energy story", "visible facade"],
        "estimated_value": 68000,
        "status": "responded",
        "next_action": "Call after 18:00 with combined window and facade story",
        "modules": {
            "windowpilot": 92,
            "facadepilot": 87,
            "roofpilot": 64,
            "porchpilot": 58,
        },
        "interactions": [
            ("2026-06-02T10:00:00+00:00", "direct_mail", "none", "Window and facade concept sent"),
            ("2026-06-05T18:22:00+00:00", "landing_page_scan", "interested", "Viewed visual twice after work"),
            ("2026-06-06T19:10:00+00:00", "call", "interested", "Asked about energy savings and phasing"),
        ],
        "objections": ["Timing after summer"],
    },
    {
        "address": "Beekstraat 32",
        "city": "Mechelen",
        "lat": 51.026,
        "lon": 4.477,
        "property_type": "open bebouwing",
        "tags": ["premium fit", "large envelope", "driveway"],
        "estimated_value": 118000,
        "status": "appointment",
        "next_action": "Prepare premium multi-module estimate",
        "modules": {
            "facadepilot": 84,
            "windowpilot": 89,
            "roofpilot": 86,
            "drivewaypilot": 78,
            "gardenpilot": 72,
        },
        "interactions": [
            ("2026-06-01T09:30:00+00:00", "email", "interested", "WindowPilot visual opened"),
            ("2026-06-03T11:20:00+00:00", "call", "appointment", "Interested in financing options"),
            ("2026-06-10T14:00:00+00:00", "meeting", "appointment", "Site visit booked"),
        ],
        "objections": ["Needs financing"],
    },
    {
        "address": "Stationsstraat 9",
        "city": "Aarschot",
        "lat": 50.987,
        "lon": 4.836,
        "property_type": "vrijstaand",
        "tags": ["roof cross-sell", "driveway", "solar story"],
        "estimated_value": 94000,
        "status": "sent",
        "next_action": "Retarget with roof-first copy and driveway upsell",
        "modules": {
            "roofpilot": 88,
            "drivewaypilot": 82,
            "facadepilot": 77,
            "windowpilot": 69,
        },
        "interactions": [
            ("2026-06-07T08:45:00+00:00", "direct_mail", "none", "Roof refresh visual sent"),
        ],
        "objections": [],
    },
    {
        "address": "Dorpstraat 41",
        "city": "Lubbeek",
        "lat": 50.882,
        "lon": 4.840,
        "property_type": "gezinswoning",
        "tags": ["family home", "outdoor living", "garden potential"],
        "estimated_value": 76000,
        "status": "responded",
        "next_action": "Offer garden-first package with pool optionality",
        "modules": {
            "gardenpilot": 90,
            "poolpilot": 83,
            "roofpilot": 70,
            "windowpilot": 66,
        },
        "interactions": [
            ("2026-06-08T15:05:00+00:00", "landing_page_scan", "interested", "Garden concept opened"),
            ("2026-06-09T17:35:00+00:00", "call", "interested", "Asked for phased garden and pool approach"),
        ],
        "objections": ["Budget spread"],
    },
    {
        "address": "Kerkstraat 18",
        "city": "Tienen",
        "lat": 50.809,
        "lon": 4.937,
        "property_type": "rijwoning",
        "tags": ["classic street", "porch visible", "brick restoration"],
        "estimated_value": 42000,
        "status": "no_response",
        "next_action": "Retarget with smaller porch and brick restoration message",
        "modules": {
            "porchpilot": 81,
            "facadepilot": 73,
            "windowpilot": 61,
        },
        "interactions": [
            ("2026-06-04T13:00:00+00:00", "direct_mail", "none", "Porch visual delivered"),
            ("2026-06-14T09:00:00+00:00", "status_change", "no_response", "Marked no response after 10 days"),
        ],
        "objections": ["No response"],
    },
    {
        "address": "Vijverlaan 7",
        "city": "Genk",
        "lat": 50.965,
        "lon": 5.501,
        "property_type": "villa",
        "tags": ["pool fit", "sun exposure", "premium outdoor"],
        "estimated_value": 132000,
        "status": "clicked",
        "next_action": "Call with pool and garden concept before weekend",
        "modules": {
            "poolpilot": 91,
            "gardenpilot": 86,
            "drivewaypilot": 74,
            "facadepilot": 68,
        },
        "interactions": [
            ("2026-06-11T12:00:00+00:00", "email", "clicked", "Pool concept clicked"),
            ("2026-06-12T20:15:00+00:00", "landing_page_scan", "clicked", "Viewed outdoor living gallery"),
        ],
        "objections": [],
    },
    {
        "address": "Naamsesteenweg 144",
        "city": "Leuven",
        "lat": 50.873,
        "lon": 4.701,
        "property_type": "hoekwoning",
        "tags": ["noise reduction", "student area", "window story"],
        "estimated_value": 57000,
        "status": "queued",
        "next_action": "Queue for noise-reduction WindowPilot campaign",
        "modules": {
            "windowpilot": 80,
            "facadepilot": 71,
            "roofpilot": 52,
        },
        "interactions": [],
        "objections": [],
    },
    {
        "address": "Koning Albertlaan 22",
        "city": "Diest",
        "lat": 50.984,
        "lon": 5.052,
        "property_type": "halfopen",
        "tags": ["roof visible", "pre-1990", "facade refresh"],
        "estimated_value": 88000,
        "status": "responded",
        "next_action": "Send roof-first dossier with facade timing option",
        "modules": {
            "roofpilot": 92,
            "facadepilot": 79,
            "windowpilot": 72,
        },
        "interactions": [
            ("2026-06-13T10:15:00+00:00", "email", "interested", "Opened roof concept and clicked estimate range"),
            ("2026-06-13T18:40:00+00:00", "call", "interested", "Asked whether facade work can be phased after roof"),
        ],
        "objections": ["Needs technical proof"],
    },
    {
        "address": "Lindenhof 5",
        "city": "Hasselt",
        "lat": 50.931,
        "lon": 5.338,
        "property_type": "villa",
        "tags": ["premium garden", "pool ready", "quiet street"],
        "estimated_value": 154000,
        "status": "appointment",
        "next_action": "Book outdoor-living consult with pool and garden scope",
        "modules": {
            "gardenpilot": 94,
            "poolpilot": 89,
            "drivewaypilot": 76,
            "facadepilot": 65,
        },
        "interactions": [
            ("2026-06-09T08:10:00+00:00", "email", "clicked", "Clicked garden transformation visual"),
            ("2026-06-10T16:30:00+00:00", "call", "appointment", "Requested appointment for garden and pool concept"),
        ],
        "objections": ["Wants premium references"],
    },
    {
        "address": "Brusselsesteenweg 201",
        "city": "Herent",
        "lat": 50.899,
        "lon": 4.670,
        "property_type": "rijwoning",
        "tags": ["noise corridor", "old glazing", "front upgrade"],
        "estimated_value": 52000,
        "status": "sent",
        "next_action": "Retarget with comfort and noise-reduction WindowPilot angle",
        "modules": {
            "windowpilot": 87,
            "porchpilot": 70,
            "facadepilot": 67,
        },
        "interactions": [
            ("2026-06-12T09:00:00+00:00", "direct_mail", "none", "Comfort-focused window concept sent"),
        ],
        "objections": [],
    },
    {
        "address": "Parklaan 68",
        "city": "Sint-Truiden",
        "lat": 50.817,
        "lon": 5.186,
        "property_type": "open bebouwing",
        "tags": ["large driveway", "ev-ready", "garden cross-sell"],
        "estimated_value": 99000,
        "status": "clicked",
        "next_action": "Call with driveway drainage and EV charger package",
        "modules": {
            "drivewaypilot": 91,
            "gardenpilot": 73,
            "windowpilot": 64,
        },
        "interactions": [
            ("2026-06-15T12:20:00+00:00", "email", "clicked", "Clicked driveway before/after visual"),
            ("2026-06-15T20:05:00+00:00", "landing_page_scan", "clicked", "Viewed EV-ready driveway section"),
        ],
        "objections": ["Needs drainage detail"],
    },
    {
        "address": "Schoolstraat 12",
        "city": "Rotselaar",
        "lat": 50.953,
        "lon": 4.716,
        "property_type": "gezinswoning",
        "tags": ["family comfort", "window upgrade", "roof later"],
        "estimated_value": 64000,
        "status": "no_response",
        "next_action": "Switch from energy-savings copy to comfort and child-room copy",
        "modules": {
            "windowpilot": 82,
            "roofpilot": 71,
            "facadepilot": 63,
        },
        "interactions": [
            ("2026-06-06T10:00:00+00:00", "direct_mail", "none", "Window comfort mailer sent"),
            ("2026-06-16T10:00:00+00:00", "status_change", "no_response", "No response after follow-up window"),
        ],
        "objections": ["No response"],
    },
    {
        "address": "Bergstraat 77",
        "city": "Landen",
        "lat": 50.752,
        "lon": 5.082,
        "property_type": "hoevewoning",
        "tags": ["heritage facade", "porch story", "roof plane"],
        "estimated_value": 112000,
        "status": "queued",
        "next_action": "Queue for heritage-safe facade and porch campaign",
        "modules": {
            "facadepilot": 88,
            "porchpilot": 84,
            "roofpilot": 79,
            "windowpilot": 58,
        },
        "interactions": [],
        "objections": [],
    },
    {
        "address": "Heidestraat 3",
        "city": "Mol",
        "lat": 51.184,
        "lon": 5.116,
        "property_type": "bungalow",
        "tags": ["sun exposure", "pool fit", "outdoor living"],
        "estimated_value": 126000,
        "status": "responded",
        "next_action": "Share low-maintenance pool concept with garden phasing",
        "modules": {
            "poolpilot": 93,
            "gardenpilot": 84,
            "drivewaypilot": 68,
        },
        "interactions": [
            ("2026-06-14T11:00:00+00:00", "email", "interested", "Asked about pool maintenance and timeline"),
            ("2026-06-14T18:25:00+00:00", "call", "interested", "Wants phased concept before holiday period"),
        ],
        "objections": ["Maintenance concern"],
    },
    {
        "address": "Veldkant 29",
        "city": "Bierbeek",
        "lat": 50.830,
        "lon": 4.760,
        "property_type": "open bebouwing",
        "tags": ["multi-module", "energy bundle", "driveway visible"],
        "estimated_value": 141000,
        "status": "appointment",
        "next_action": "Prepare whole-home renovation roadmap for appointment",
        "modules": {
            "facadepilot": 86,
            "windowpilot": 90,
            "roofpilot": 82,
            "drivewaypilot": 80,
            "gardenpilot": 78,
        },
        "interactions": [
            ("2026-06-02T14:10:00+00:00", "email", "clicked", "Clicked whole-home energy bundle"),
            ("2026-06-04T17:55:00+00:00", "call", "appointment", "Appointment booked for staged renovation roadmap"),
        ],
        "objections": ["Wants staged budget"],
    },
    {
        "address": "Molenweg 101",
        "city": "Aalst",
        "lat": 50.939,
        "lon": 4.037,
        "property_type": "halfopen",
        "tags": ["facade priority", "old windows", "urban street"],
        "estimated_value": 73000,
        "status": "sent",
        "next_action": "Send compact facade-first case with window follow-up",
        "modules": {
            "facadepilot": 91,
            "windowpilot": 78,
            "porchpilot": 62,
        },
        "interactions": [
            ("2026-06-17T08:35:00+00:00", "direct_mail", "none", "Facade-first visual sent"),
        ],
        "objections": [],
    },
)

DEMO_CITY_CENTERS: tuple[dict[str, Any], ...] = (
    {"city": "Leuven", "lat": 50.8798, "lon": 4.7005, "segment": "university corridor"},
    {"city": "Mechelen", "lat": 51.0259, "lon": 4.4775, "segment": "commuter belt"},
    {"city": "Hasselt", "lat": 50.9307, "lon": 5.3325, "segment": "family comfort"},
    {"city": "Genk", "lat": 50.9650, "lon": 5.5008, "segment": "outdoor living"},
    {"city": "Aalst", "lat": 50.9360, "lon": 4.0397, "segment": "urban refresh"},
    {"city": "Tienen", "lat": 50.8078, "lon": 4.9378, "segment": "classic street"},
    {"city": "Diest", "lat": 50.9892, "lon": 5.0506, "segment": "roof and facade"},
    {"city": "Aarschot", "lat": 50.9872, "lon": 4.8368, "segment": "energy upgrade"},
    {"city": "Herent", "lat": 50.9082, "lon": 4.6706, "segment": "noise reduction"},
    {"city": "Sint-Truiden", "lat": 50.8168, "lon": 5.1865, "segment": "driveway and garden"},
    {"city": "Mol", "lat": 51.1840, "lon": 5.1160, "segment": "pool fit"},
    {"city": "Rotselaar", "lat": 50.9531, "lon": 4.7166, "segment": "family renovation"},
    {"city": "Lubbeek", "lat": 50.8822, "lon": 4.8405, "segment": "garden potential"},
    {"city": "Landen", "lat": 50.7522, "lon": 5.0822, "segment": "heritage envelope"},
    {"city": "Bierbeek", "lat": 50.8287, "lon": 4.7597, "segment": "multi-module"},
)
DEMO_STREET_NAMES = (
    "Demo Lindestraat",
    "Demo Parklaan",
    "Demo Veldkant",
    "Demo Molenweg",
    "Demo Schoolstraat",
    "Demo Beekstraat",
    "Demo Stationsstraat",
    "Demo Kerkstraat",
    "Demo Vijverlaan",
    "Demo Hofstraat",
    "Demo Bergstraat",
    "Demo Zonneweg",
)
DEMO_PROPERTY_TYPES = (
    "rijwoning",
    "halfopen",
    "open bebouwing",
    "gezinswoning",
    "hoekwoning",
    "bungalow",
    "villa",
    "hoevewoning",
)
DEMO_STATUS_SEQUENCE = (
    "appointment",
    "responded",
    "clicked",
    "sent",
    "sent",
    "no_response",
    "queued",
    "sent",
    "clicked",
    "responded",
    "queued",
    "no_response",
)
MODULE_TAGS = {
    "facadepilot": ("visible facade", "energy story", "front upgrade"),
    "windowpilot": ("old glazing", "comfort story", "noise reduction"),
    "roofpilot": ("roof visible", "solar cross-sell", "moss signal"),
    "gardenpilot": ("garden potential", "outdoor living", "privacy fit"),
    "poolpilot": ("pool fit", "sun exposure", "premium outdoor"),
    "porchpilot": ("porch visible", "entry upgrade", "street appeal"),
    "drivewaypilot": ("driveway visible", "ev-ready", "drainage story"),
}
MODULE_NEXT_ACTIONS = {
    "facadepilot": "Open with facade insulation visual and staged budget range",
    "windowpilot": "Open with comfort, noise reduction, and energy savings story",
    "roofpilot": "Open with roof-first technical proof and solar optionality",
    "gardenpilot": "Open with outdoor-living concept and phased garden plan",
    "poolpilot": "Open with low-maintenance pool concept and access check",
    "porchpilot": "Open with entry upgrade visual and compact budget story",
    "drivewaypilot": "Open with driveway drainage, finish, and EV-ready package",
}
STATUS_OBJECTIONS = {
    "appointment": ["Wants staged budget"],
    "responded": ["Needs timing clarity"],
    "clicked": ["Needs proof before call"],
    "sent": [],
    "queued": [],
    "no_response": ["No response"],
}

DAW_PARTNERS: tuple[dict[str, Any], ...] = (
    {"id": "renotec-antwerp", "name": "Renotec Gevelwerken", "region": "Antwerp", "cities": ("Antwerpen", "Mechelen", "Lier"), "lat": 51.2194, "lon": 4.4025, "capacity": 220, "tier": "platinum"},
    {"id": "crepi-plus-limburg", "name": "Crepi Plus Limburg", "region": "Limburg", "cities": ("Hasselt", "Genk", "Beringen"), "lat": 50.9307, "lon": 5.3325, "capacity": 180, "tier": "gold"},
    {"id": "gevelmeesters-vlaams-brabant", "name": "Gevelmeesters Vlaams-Brabant", "region": "Vlaams-Brabant", "cities": ("Leuven", "Tienen", "Aarschot"), "lat": 50.8798, "lon": 4.7005, "capacity": 210, "tier": "platinum"},
    {"id": "facadecare-brussels", "name": "FacadeCare Brussels", "region": "Brussels", "cities": ("Brussel", "Dilbeek", "Zaventem"), "lat": 50.8503, "lon": 4.3517, "capacity": 150, "tier": "gold"},
    {"id": "oost-crepi-gent", "name": "Oost Crepi Gent", "region": "Oost-Vlaanderen", "cities": ("Gent", "Aalst", "Sint-Niklaas"), "lat": 51.0543, "lon": 3.7174, "capacity": 190, "tier": "gold"},
    {"id": "westkust-gevel", "name": "Westkust Gevel", "region": "West-Vlaanderen", "cities": ("Brugge", "Kortrijk", "Oostende"), "lat": 51.2093, "lon": 3.2247, "capacity": 170, "tier": "silver"},
    {"id": "waals-brabant-facades", "name": "Waals-Brabant Facades", "region": "Waals-Brabant", "cities": ("Wavre", "Nivelles", "Ottignies"), "lat": 50.7167, "lon": 4.6167, "capacity": 130, "tier": "silver"},
    {"id": "liege-crepi-solutions", "name": "Liege Crepi Solutions", "region": "Liege", "cities": ("Luik", "Verviers", "Seraing"), "lat": 50.6326, "lon": 5.5797, "capacity": 160, "tier": "gold"},
    {"id": "hainaut-renovation", "name": "Hainaut Renovation", "region": "Hainaut", "cities": ("Charleroi", "Mons", "Tournai"), "lat": 50.4108, "lon": 4.4446, "capacity": 155, "tier": "silver"},
    {"id": "namur-facade-team", "name": "Namur Facade Team", "region": "Namur", "cities": ("Namen", "Dinant", "Gembloux"), "lat": 50.4674, "lon": 4.8718, "capacity": 125, "tier": "silver"},
)
DAW_STREET_NAMES = (
    "DAW Demolaan",
    "DAW Gevelstraat",
    "DAW Crepiweg",
    "DAW Isolatiepad",
    "DAW Pleisterlaan",
    "DAW Renovatiehof",
    "DAW Steenweg",
    "DAW Energieplein",
)
DAW_MESSAGE_VARIANTS = (
    "energy_savings",
    "facade_refresh",
    "premium_finish",
    "subsidy_check",
    "maintenance_free",
)
PUBLIC_CONTEXT_GUARDRAILS = (
    "No owner data",
    "No scraped personal contact data",
    "No individual EPC label",
    "Opportunity context only; no homeowner intent claim",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _grade(score: int) -> str:
    if score >= 90:
        return "A+"
    if score >= 78:
        return "A"
    if score >= 62:
        return "B"
    return "C"


def _metrics_for_module(module_key: str, score: int, value: int, property_type: str) -> dict[str, Any]:
    shared = {
        "estimated_value": value,
        "building_age_signal": "pre-2000 envelope",
        "energy_label": "D",
        "permit_signal": "no recent renovation permit found",
        "last_renovation_year": 1998 if score >= 80 else 2008,
    }
    if module_key == "facadepilot":
        return {**shared, "facade_opportunity_score": score, "facade_grade": _grade(score), "visible_facade_area_m2": round(score * 1.45, 1), "facade_preset": "Crepi insulation" if score >= 80 else "Brick restoration", "property_type": property_type, "pre_1990_neighborhood_pct": 58, "median_income": 43800, "render_quality": "high"}
    if module_key == "windowpilot":
        return {**shared, "window_opportunity_score": score, "glazing_age_signal": "pre-2000", "frame_material_signal": "mixed aluminium and PVC", "energy_savings_story_fit": min(98, score + 3), "visible_window_count": max(7, int(score / 6)), "replacement_urgency": "Old glazing and comfort story"}
    if module_key == "roofpilot":
        return {**shared, "roof_opportunity_score": score, "roof_area_m2": round(score * 1.8, 1), "roof_age_signal": "older roof plane", "roof_material_signal": "tile", "solar_cross_sell_fit": min(96, score + 5), "storm_or_moss_signal": "moss visible" if score >= 75 else "low urgency"}
    if module_key == "gardenpilot":
        return {**shared, "garden_opportunity_score": score, "garden_area_m2": round(score * 4.2, 1), "outdoor_living_fit": min(99, score + 4), "maintenance_signal": "upgrade potential", "privacy_fit": min(95, score + 2)}
    if module_key == "poolpilot":
        return {**shared, "pool_opportunity_score": score, "pool_fit": min(99, score + 5), "sun_exposure_signal": "strong afternoon sun", "garden_access_quality": "good machinery access", "terrain_complexity": "low" if score >= 80 else "medium"}
    if module_key == "porchpilot":
        return {**shared, "porch_opportunity_score": score, "entry_visibility": "high street visibility", "front_house_upgrade_fit": min(97, score + 6), "porch_style_fit": "modern canopy"}
    if module_key == "drivewaypilot":
        return {**shared, "driveway_opportunity_score": score, "driveway_area_m2": round(score * 1.25, 1), "surface_condition_signal": "aging paving", "drainage_risk": "medium", "ev_charger_fit": min(94, score + 4)}
    raise ValueError(f"Unknown module: {module_key}")


def _score_for(index: int, module_offset: int, primary_offset: int) -> int:
    raw = 54 + ((index * (module_offset + 7) + module_offset * 13) % 42)
    if module_offset == primary_offset:
        raw += 10
    return max(48, min(97, raw))


def _module_mix(index: int) -> dict[str, int]:
    modules = list(DEMO_MODULES)
    primary_offset = (index * 5 + index // 7) % len(modules)
    count = 3 + (index % 3)
    selected_offsets = [(primary_offset + step * 2) % len(modules) for step in range(count)]
    selected: dict[str, int] = {}
    for offset in selected_offsets:
        selected[modules[offset]] = _score_for(index, offset, primary_offset)
    return selected


def _scaled_lat_lon(index: int, city: dict[str, Any]) -> tuple[float, float]:
    lat_offset = (((index * 37) % 180) - 90) / 10000
    lon_offset = (((index * 53) % 220) - 110) / 10000
    return round(float(city["lat"]) + lat_offset, 6), round(float(city["lon"]) + lon_offset, 6)


def _interactions_for_status(
    status: str,
    module_key: str,
    address: str,
    index: int,
) -> list[tuple[str, str, str, str]]:
    day = 1 + (index % 18)
    base = f"2026-06-{day:02d}"
    if status == "queued":
        return []
    if status == "sent":
        return [(f"{base}T09:00:00+00:00", "direct_mail", "none", f"{PILOT_MODULES[module_key].label} concept sent for {address}")]
    if status == "clicked":
        return [
            (f"{base}T10:15:00+00:00", "email", "clicked", f"{PILOT_MODULES[module_key].label} visual clicked"),
            (f"{base}T20:05:00+00:00", "landing_page_scan", "clicked", "Viewed estimate and before/after section"),
        ]
    if status == "responded":
        return [
            (f"{base}T08:45:00+00:00", "email", "clicked", f"{PILOT_MODULES[module_key].label} concept opened"),
            (f"{base}T18:20:00+00:00", "call", "interested", "Asked for budget range and timing"),
        ]
    if status == "appointment":
        return [
            (f"{base}T08:30:00+00:00", "email", "clicked", "Opened tailored property concept"),
            (f"{base}T17:40:00+00:00", "call", "appointment", "Appointment requested for staged renovation roadmap"),
            (f"2026-06-{min(28, day + 3):02d}T14:00:00+00:00", "meeting", "appointment", "Demo site visit booked"),
        ]
    if status == "no_response":
        return [
            (f"{base}T11:00:00+00:00", "direct_mail", "none", f"{PILOT_MODULES[module_key].label} mailer sent"),
            (f"2026-06-{min(28, day + 10):02d}T11:00:00+00:00", "status_change", "no_response", "No response after follow-up window"),
        ]
    return []


def _scaled_blueprint(index: int) -> dict[str, Any]:
    city = DEMO_CITY_CENTERS[(index - 1) % len(DEMO_CITY_CENTERS)]
    street = DEMO_STREET_NAMES[(index * 7) % len(DEMO_STREET_NAMES)]
    house_number = 1000 + index
    address = f"{street} {house_number}"
    lat, lon = _scaled_lat_lon(index, city)
    property_type = DEMO_PROPERTY_TYPES[(index * 3) % len(DEMO_PROPERTY_TYPES)]
    modules = _module_mix(index)
    best_module = max(modules, key=modules.get)
    status = DEMO_STATUS_SEQUENCE[(index - 1) % len(DEMO_STATUS_SEQUENCE)]
    best_score = modules[best_module]
    value_seed = 36000 + best_score * 900 + ((index * 431) % 42000)
    tags = [
        "synthetic demo address",
        city["segment"],
        property_type,
        *MODULE_TAGS[best_module],
    ]
    return {
        "address": address,
        "city": city["city"],
        "lat": lat,
        "lon": lon,
        "property_type": property_type,
        "tags": tags,
        "estimated_value": int(value_seed),
        "status": status,
        "next_action": MODULE_NEXT_ACTIONS[best_module],
        "modules": modules,
        "interactions": _interactions_for_status(status, best_module, address, index),
        "objections": STATUS_OBJECTIONS.get(status, []),
        "synthetic_index": index,
    }


def _demo_blueprints(property_count: int | None = None) -> list[dict[str, Any]]:
    if property_count is None:
        return list(PROPERTY_BLUEPRINTS)
    if property_count < 1:
        raise ValueError("property_count must be at least 1")
    return [_scaled_blueprint(index) for index in range(1, property_count + 1)]


def _daw_status(index: int) -> str:
    return DEMO_STATUS_SEQUENCE[(index + index // 11) % len(DEMO_STATUS_SEQUENCE)]


def _daw_lat_lon(index: int, partner: dict[str, Any]) -> tuple[float, float]:
    lat_offset = (((index * 31) % 170) - 85) / 10000
    lon_offset = (((index * 47) % 210) - 105) / 10000
    return round(float(partner["lat"]) + lat_offset, 6), round(float(partner["lon"]) + lon_offset, 6)


def _daw_interactions(status: str, partner: dict[str, Any], address: str, index: int) -> list[tuple[str, str, str, str]]:
    day = 1 + (index % 20)
    base = f"2026-06-{day:02d}"
    if status == "queued":
        return []
    if status == "sent":
        return [(f"{base}T09:30:00+00:00", "direct_mail", "none", f"DAW crepi concept sent for {partner['name']}")]
    if status == "clicked":
        return [
            (f"{base}T10:40:00+00:00", "email", "clicked", "Clicked DAW finish visual"),
            (f"{base}T19:20:00+00:00", "landing_page_scan", "clicked", "Viewed facade insulation benefits"),
        ]
    if status == "responded":
        return [
            (f"{base}T08:55:00+00:00", "email", "clicked", "Opened DAW crepi concept"),
            (f"{base}T18:35:00+00:00", "call", "interested", f"Asked {partner['name']} for facade budget range"),
        ]
    if status == "appointment":
        return [
            (f"{base}T08:20:00+00:00", "email", "clicked", "Opened DAW system explanation"),
            (f"{base}T17:45:00+00:00", "call", "appointment", f"Appointment requested with {partner['name']}"),
            (f"2026-06-{min(28, day + 4):02d}T15:00:00+00:00", "meeting", "appointment", f"Site visit booked for {address}"),
        ]
    if status == "no_response":
        return [
            (f"{base}T11:10:00+00:00", "direct_mail", "none", "DAW crepi mailer sent"),
            (f"2026-06-{min(28, day + 10):02d}T11:10:00+00:00", "status_change", "no_response", "No response after DAW follow-up window"),
        ]
    return []


def _demo_public_context(
    index: int,
    city: str,
    region: str,
    source_run_id: str,
    facade_m2: int = 0,
) -> dict[str, Any]:
    pre_1990_share = 42 + ((index * 7) % 39)
    parcel_area = 145 + ((index * 29) % 620)
    footprint_area = max(72, int(round(facade_m2 * 0.62))) if facade_m2 else 82 + ((index * 13) % 170)
    sector_key = "demo-sector-" + stable_hash(region, city, str(index % 43))[:10]
    heritage_flag = "review zone" if index % 23 == 0 else "no public restriction signal"
    permit_pressure = "high renovation activity" if index % 5 in {0, 1} else "normal renovation activity"
    return {
        "status": "demo_public_context",
        "source_run_id": f"{source_run_id}-public-context",
        "read_model": "homepilot_property_public_enrichment",
        "licence": "Synthetic demo; production requires dataset-level licence and attribution review",
        "allowed_use": "Buyer demo, product training, and data-model review only",
        "attribution": "Synthetic HomePilot public-context demo, modelled after official/open Belgian data lanes",
        "retrieval_finished_at": DEFAULT_CREATED_AT,
        "transform_version": "demo-public-context-v1",
        "confidence": round(0.76 + ((index % 17) / 100), 2),
        "geography": {
            "level": "statistical_sector",
            "key": sector_key,
            "city": city,
            "region": region,
        },
        "features": [
            {
                "key": "official_address_match",
                "label": "Official address match",
                "value": "matched demo address",
                "source": "Synthetic BeSt address context",
                "geography_level": "address",
                "licence": "Demo only; mirror of CC BY 4.0-style address lane",
            },
            {
                "key": "parcel_area_m2",
                "label": "Parcel area",
                "value": parcel_area,
                "unit": "m2",
                "source": "Synthetic cadastral parcel geometry context",
                "geography_level": "parcel",
                "licence": "Demo only; production terms must be verified",
            },
            {
                "key": "building_footprint_area_m2",
                "label": "Building footprint area",
                "value": footprint_area,
                "unit": "m2",
                "source": "Synthetic building footprint context",
                "geography_level": "building",
                "licence": "Demo only; source layer must be approved before import",
            },
            {
                "key": "stat_sector_pre_1990_share",
                "label": "Pre-1990 neighbourhood share",
                "value": pre_1990_share,
                "unit": "%",
                "source": "Synthetic Statbel statistical-sector context",
                "geography_level": "statistical_sector",
                "licence": "Demo only; mirror of aggregate CC BY 4.0-style lane",
            },
            {
                "key": "renovation_policy_context",
                "label": "Renovation policy context",
                "value": permit_pressure,
                "source": "Synthetic regional public-policy context",
                "geography_level": "municipality",
                "licence": "Demo only; production source must be reviewed",
            },
            {
                "key": "planning_or_heritage_flag",
                "label": "Planning or heritage flag",
                "value": heritage_flag,
                "source": "Synthetic planning-zone context",
                "geography_level": "zone",
                "licence": "Demo only; property-zone source must be licensed",
            },
        ],
        "guardrails": list(PUBLIC_CONTEXT_GUARDRAILS),
    }


def build_daw_demo_payload(
    tenant_slug: str = "daw-belgium-crepi-network",
    property_count: int = SCALED_DEMO_DEFAULT_PROPERTIES,
) -> dict[str, Any]:
    tenant_id = canonical_tenant_id(tenant_slug)
    campaigns = []
    campaign_by_partner: dict[str, str] = {}
    for partner in DAW_PARTNERS:
        campaign_id = canonical_campaign_id(tenant_id, "facadepilot", f"daw-{partner['id']}-q3")
        campaign_by_partner[partner["id"]] = campaign_id
        campaigns.append({
            "id": campaign_id,
            "tenant_id": tenant_id,
            "module_key": "facadepilot",
            "name": f"DAW Crepi x {partner['name']} Q3",
            "channel": "multichannel",
            "status": "running",
            "territory": {"region": partner["region"], "cities": list(partner["cities"]), "producer": "DAW"},
            "message_variant": DAW_MESSAGE_VARIANTS[len(campaigns) % len(DAW_MESSAGE_VARIANTS)],
            "partner_id": partner["id"],
            "partner_name": partner["name"],
            "metadata": {
                "producer": "DAW",
                "partner_id": partner["id"],
                "partner_name": partner["name"],
                "territory": partner["region"],
                "network_role": "renovation_partner",
            },
        })

    payload: dict[str, Any] = {
        "network": {
            "type": "producer_partner_network",
            "producer": {
                "id": "daw",
                "name": "DAW Belgium",
                "role": "crepi producer",
                "product_lines": ["DAW crepi", "facade insulation systems", "exterior finishing"],
            },
            "product_focus": "crepi and facade insulation",
            "visibility": {
                "producer": "DAW sees aggregate network performance, regional coverage, product demand, and partner drilldown.",
                "partner": "Each facade renovator sees only assigned campaign records and own follow-up history.",
            },
            "partners": [dict(partner) for partner in DAW_PARTNERS],
        },
        "campaigns": campaigns,
        "properties": [],
        "assessments": [],
        "campaign_targets": [],
        "interactions": [],
        "response_insights": [],
        "exports": [],
        "audit_events": [],
    }

    for index in range(1, property_count + 1):
        partner = DAW_PARTNERS[(index - 1) % len(DAW_PARTNERS)]
        city = partner["cities"][(index // len(DAW_PARTNERS)) % len(partner["cities"])]
        street = DAW_STREET_NAMES[index % len(DAW_STREET_NAMES)]
        address = f"{street} {2000 + index}"
        lat, lon = _daw_lat_lon(index, partner)
        property_id = canonical_property_id(tenant_id, address, lat, lon)
        score = max(58, min(98, 62 + ((index * 17 + len(partner["id"])) % 37)))
        if partner["tier"] == "platinum":
            score = min(99, score + 5)
        grade = _grade(score)
        facade_m2 = 80 + ((index * 19) % 240)
        estimated_value = int(facade_m2 * (145 + (score % 18)))
        status = _daw_status(index)
        message_variant = DAW_MESSAGE_VARIANTS[index % len(DAW_MESSAGE_VARIANTS)]
        objections = STATUS_OBJECTIONS.get(status, [])
        campaign_id = campaign_by_partner[partner["id"]]
        payload["properties"].append({
            "id": property_id,
            "tenant_id": tenant_id,
            "source_external_id": f"daw-crepi-{index:04d}",
            "address": address,
            "city": city,
            "country_code": "BE",
            "lat": lat,
            "lon": lon,
            "property_type": DEMO_PROPERTY_TYPES[(index * 5) % len(DEMO_PROPERTY_TYPES)],
            "tags": ["DAW synthetic lead", "crepi opportunity", partner["region"], message_variant.replace("_", " ")],
            "core": {
                "demo": True,
                "synthetic_record": True,
                "estimated_value": estimated_value,
                "estimated_facade_m2": facade_m2,
                "producer": "DAW",
                "renovation_system": "DAW crepi + facade insulation",
                "territory": partner["region"],
                "building_age_signal": "pre-2000 facade",
                "energy_label": "D",
                "network": {
                    "producer": "DAW",
                    "scope": "producer_partner_network",
                    "partner_id": partner["id"],
                    "partner_name": partner["name"],
                    "partner_region": partner["region"],
                    "territory": partner["region"],
                    "partner_tier": partner["tier"],
                },
                "public_enrichment": _demo_public_context(
                    index=index,
                    city=city,
                    region=partner["region"],
                    source_run_id="daw-crepi-network-demo",
                    facade_m2=facade_m2,
                ),
            },
        })
        payload["assessments"].append({
            "id": "asmt_" + stable_hash(tenant_id, property_id, "facadepilot", "daw-crepi-network"),
            "tenant_id": tenant_id,
            "property_id": property_id,
            "module_key": "facadepilot",
            "score": score,
            "grade": grade,
            "confidence": round(0.64 + (score / 285), 2),
            "metrics": {
                "facade_opportunity_score": score,
                "facade_grade": grade,
                "visible_facade_area_m2": facade_m2,
                "facade_preset": "DAW crepi insulation",
                "property_type": DEMO_PROPERTY_TYPES[(index * 5) % len(DEMO_PROPERTY_TYPES)],
                "pre_1990_neighborhood_pct": 44 + (index % 38),
                "median_income": 36000 + ((index * 313) % 28000),
                "render_quality": "high",
                "estimated_value": estimated_value,
            },
            "evidence": [{"type": "render", "value": f"DAW crepi facade signal for {address}"}],
            "source_run_id": "daw-crepi-network-demo",
        })
        payload["campaign_targets"].append({
            "tenant_id": tenant_id,
            "campaign_id": campaign_id,
            "property_id": property_id,
            "module_key": "facadepilot",
            "status": status,
            "priority_score": score,
            "priority_grade": grade,
            "metadata": {
                "producer": "DAW",
                "partner_id": partner["id"],
                "partner_name": partner["name"],
                "territory": partner["region"],
                "message_variant": message_variant,
                "next_action": f"{partner['name']}: {MODULE_NEXT_ACTIONS['facadepilot']}",
                "objections": objections,
                "source_provenance": "synthetic DAW producer network demo",
                "contact_basis": "demo scenario; partner/customer campaign approval required before live outreach",
                "contact_channel": "multichannel",
                "opt_out_method": "demo suppression workflow",
                "lead_claim": "opportunity intelligence only; no homeowner buying intent claimed",
                "demo": True,
                "demo_dataset": "daw-crepi-network-demo",
            },
        })
        for interaction_index, (occurred_at, interaction_type, response_status, detail) in enumerate(_daw_interactions(status, partner, address, index), start=1):
            payload["interactions"].append({
                "id": canonical_uuid("daw_interaction", tenant_id, property_id, interaction_index),
                "tenant_id": tenant_id,
                "property_id": property_id,
                "campaign_id": campaign_id,
                "module_key": "facadepilot",
                "interaction_type": interaction_type,
                "response_status": response_status,
                "detail": detail,
                "objection_code": objections[0].lower().replace(" ", "_") if objections and status in {"no_response", "appointment"} else None,
                "metadata": {"demo": True, "producer": "DAW", "partner_id": partner["id"]},
                "occurred_at": occurred_at,
            })

    for partner in DAW_PARTNERS:
        partner_targets = [target for target in payload["campaign_targets"] if target["metadata"]["partner_id"] == partner["id"]]
        payload["response_insights"].append({
            "id": canonical_uuid("daw_insight", tenant_id, partner["id"]),
            "tenant_id": tenant_id,
            "campaign_id": campaign_by_partner[partner["id"]],
            "module_key": "facadepilot",
            "insight_type": "recommendation",
            "title": f"{partner['name']} partner playbook",
            "body": f"{partner['region']} has {len(partner_targets)} assigned DAW crepi opportunities; compare appointments and no-response backlog weekly.",
            "supporting_metrics": {"assigned_properties": len(partner_targets), "producer": "DAW", "demo": True},
        })
    payload["exports"].append(build_export_log_record(
        tenant_id=tenant_id,
        module_key="facadepilot",
        export_type="xlsx",
        storage_path=f"demo/{tenant_slug}/daw_network/homepilot_export.xlsx",
        row_count=property_count,
        filters={"producer": "DAW", "scenario": "producer_partner_network"},
        created_at=DEFAULT_CREATED_AT,
    ))
    payload["audit_events"].append(build_audit_event(
        tenant_id=tenant_id,
        module_key="facadepilot",
        event_type="data_imported",
        subject_type="daw_producer_network_demo",
        subject_id=tenant_slug,
        details={"demo": True, "producer": "DAW", "partners": len(DAW_PARTNERS), "properties": property_count},
        created_at=DEFAULT_CREATED_AT,
    ))
    validate_payload(payload)
    return payload


def build_demo_onboarding(
    name: str = "HomePilot Enterprise Demo",
    slug: str = "homepilot-enterprise-demo",
    modules: list[str] | tuple[str, ...] = DEMO_MODULES,
    settings: dict[str, Any] | None = None,
    subscription_tier: str = "enterprise-demo",
) -> dict[str, Any]:
    payload = build_onboarding_payload(
        name=name,
        slug=slug,
        modules=list(modules),
        subscription_tier=subscription_tier,
        settings=settings or {"demo": True, "dataset": "synthetic_enterprise_showroom"},
    )
    validate_onboarding_payload(payload)
    return payload


def build_demo_payload(
    tenant_slug: str = "homepilot-enterprise-demo",
    property_count: int | None = None,
    scenario: str = "enterprise",
) -> dict[str, Any]:
    if scenario == "daw":
        return build_daw_demo_payload(
            tenant_slug=tenant_slug,
            property_count=property_count or SCALED_DEMO_DEFAULT_PROPERTIES,
        )
    if scenario != "enterprise":
        raise ValueError(f"Unknown demo scenario: {scenario}")
    tenant_id = canonical_tenant_id(tenant_slug)
    blueprints = _demo_blueprints(property_count)
    source_run_id = "homepilot-scaled-demo" if property_count is not None else "homepilot-enterprise-demo"
    campaigns = []
    for module_key in DEMO_MODULES:
        campaigns.append({
            "id": canonical_campaign_id(tenant_id, module_key, f"demo-{module_key}-q3"),
            "tenant_id": tenant_id,
            "module_key": module_key,
            "name": f"{PILOT_MODULES[module_key].label} Enterprise Demo Q3",
            "channel": "multichannel",
            "status": "running",
            "territory": {"region": "Flanders", "demo": True},
            "message_variant": f"demo_{module_key}_value_story",
        })

    payload: dict[str, list[dict[str, Any]]] = {
        "campaigns": campaigns,
        "properties": [],
        "assessments": [],
        "campaign_targets": [],
        "interactions": [],
        "response_insights": [],
        "exports": [],
        "audit_events": [],
    }
    campaign_by_module = {campaign["module_key"]: campaign["id"] for campaign in campaigns}

    for index, blueprint in enumerate(blueprints, start=1):
        property_id = canonical_property_id(tenant_id, blueprint["address"], blueprint["lat"], blueprint["lon"])
        facade_score = blueprint["modules"].get("facadepilot", 0)
        public_context_facade_m2 = int(round(facade_score * 1.45)) if facade_score else 0
        payload["properties"].append({
            "id": property_id,
            "tenant_id": tenant_id,
            "source_external_id": f"demo-property-{index:04d}",
            "address": blueprint["address"],
            "city": blueprint["city"],
            "country_code": "BE",
            "lat": blueprint["lat"],
            "lon": blueprint["lon"],
            "property_type": blueprint["property_type"],
            "tags": blueprint["tags"],
            "core": {
                "demo": True,
                "estimated_value": blueprint["estimated_value"],
                "building_age_signal": "pre-2000 envelope",
                "energy_label": "D",
                "permit_signal": "no recent renovation permit found",
                "last_renovation_year": 1998,
                "demo_dataset": source_run_id,
                "synthetic_record": True,
                "public_enrichment": _demo_public_context(
                    index=index,
                    city=blueprint["city"],
                    region="Flanders",
                    source_run_id=source_run_id,
                    facade_m2=public_context_facade_m2,
                ),
            },
        })

        best_module = max(blueprint["modules"], key=blueprint["modules"].get)
        for module_key, score in blueprint["modules"].items():
            campaign_id = campaign_by_module[module_key]
            grade = _grade(score)
            payload["assessments"].append({
                "id": "asmt_" + stable_hash(tenant_id, property_id, module_key, "enterprise-demo"),
                "tenant_id": tenant_id,
                "property_id": property_id,
                "module_key": module_key,
                "score": score,
                "grade": grade,
                "confidence": round(0.62 + (score / 260), 2),
                "metrics": _metrics_for_module(module_key, score, blueprint["estimated_value"], blueprint["property_type"]),
                "evidence": [{"type": "render", "value": f"{PILOT_MODULES[module_key].label} visual signal for {blueprint['address']}"}],
                "source_run_id": source_run_id,
            })
            payload["campaign_targets"].append({
                "tenant_id": tenant_id,
                "campaign_id": campaign_id,
                "property_id": property_id,
                "module_key": module_key,
                "status": blueprint["status"] if module_key == best_module else "generated",
                "priority_score": score,
                "priority_grade": grade,
                "metadata": {
                    "next_action": blueprint["next_action"] if module_key == best_module else f"Use as {PILOT_MODULES[module_key].label} cross-sell context",
                    "objections": blueprint["objections"],
                    "source_provenance": "synthetic enterprise demo target list",
                    "contact_basis": "demo scenario; customer-owned campaign review required before live outreach",
                    "contact_channel": "multichannel",
                    "opt_out_method": "demo suppression workflow",
                    "lead_claim": "opportunity intelligence only; no homeowner buying intent claimed",
                    "demo": True,
                    "demo_dataset": source_run_id,
                },
            })

        for interaction_index, (occurred_at, interaction_type, response_status, detail) in enumerate(blueprint["interactions"], start=1):
            payload["interactions"].append({
                "id": canonical_uuid("demo_interaction", tenant_id, property_id, best_module, interaction_index),
                "tenant_id": tenant_id,
                "property_id": property_id,
                "campaign_id": campaign_by_module[best_module],
                "module_key": best_module,
                "interaction_type": interaction_type,
                "response_status": response_status,
                "detail": detail,
                "objection_code": blueprint["objections"][0].lower().replace(" ", "_") if blueprint["objections"] and response_status in {"no_response", "appointment"} else None,
                "metadata": {"demo": True},
                "occurred_at": occurred_at,
            })

    for module_key in DEMO_MODULES:
        module_scores = [assessment["score"] for assessment in payload["assessments"] if assessment["module_key"] == module_key]
        if not module_scores:
            continue
        payload["response_insights"].append({
            "id": canonical_uuid("demo_insight", tenant_id, module_key),
            "tenant_id": tenant_id,
            "campaign_id": campaign_by_module[module_key],
            "module_key": module_key,
            "insight_type": "recommendation",
            "title": f"{PILOT_MODULES[module_key].label} sales angle",
            "body": f"Average demo score {round(sum(module_scores) / len(module_scores), 1)}; use this module when the property evidence supports a clear first conversation.",
            "supporting_metrics": {"average_score": round(sum(module_scores) / len(module_scores), 1), "demo": True},
        })
        payload["exports"].append(build_export_log_record(
            tenant_id=tenant_id,
            module_key=module_key,
            export_type="xlsx",
            storage_path=f"demo/{tenant_slug}/{module_key}/homepilot_export.xlsx",
            row_count=len(module_scores),
            filters={"demo": True, "modules": [module_key]},
            created_at=DEFAULT_CREATED_AT,
        ))
        payload["audit_events"].append(build_audit_event(
            tenant_id=tenant_id,
            module_key=module_key,
            event_type="data_imported",
            subject_type="enterprise_demo_room",
            subject_id=tenant_slug,
            details={"demo": True, "module": module_key, "records": len(module_scores)},
            created_at=DEFAULT_CREATED_AT,
        ))

    validate_payload(payload)
    return payload


def render_demo_readme(manifest: dict[str, Any]) -> str:
    dataset = manifest.get("dataset", {})
    network = manifest.get("network") if isinstance(manifest.get("network"), dict) else {}
    lines = [
        "# HomePilot Enterprise Demo Room",
        "",
        "Synthetic, customer-safe showroom for HomePilot property intelligence.",
        "",
        f"Status: {manifest['status']}",
        f"Tenant: {manifest['tenant']['name']}",
        f"Modules: {', '.join(manifest['modules'])}",
        f"Properties: {manifest['summary']['properties']}",
        f"Dataset: {dataset.get('mode', 'synthetic demo')}",
    ]
    if network:
        lines += [
            f"Producer network: {network.get('producer', {}).get('name', 'Producer')}",
            f"Partners: {network.get('metrics', {}).get('partners', 0)}",
            f"Facade m2: {network.get('metrics', {}).get('facade_m2', 0)}",
        ]
    lines += ["", "## Open First", ""]
    lines += [
        f"- Dashboard: {manifest['paths']['dashboard_index']}",
        f"- Boardroom report: {manifest['paths']['boardroom_report']}",
        f"- Partner cutdowns: {manifest['paths'].get('partner_cutdowns_manifest', 'Not generated for this scenario')}",
        f"- Package manifest: {manifest['paths']['customer_package_manifest']}",
        f"- Portal bundle: {manifest['paths']['portal_manifest']}",
        f"- CRM integration pack: {manifest['paths']['integration_manifest']}",
        f"- Data vendor plan: {manifest['paths']['data_vendor_plan_markdown']}",
        f"- Data dictionary: {manifest['paths']['data_dictionary_markdown']}",
        "",
        "## What To Show A Large Customer",
        "",
        "- Executive tab for decision ledger, shortlist, readiness, and campaign memory.",
        "- Database/export tab for Excel-like inspection and CSV/XLSX handoff.",
        "- Second brain graph linking modules, properties, signals, reactions, objections, and next actions.",
        "- Producer/partner lens for DAW-style network views and partner-specific campaign cutdowns.",
        "- Portal, CRM/webhook, and data-vendor artefacts showing the route from demo to real customer rollout.",
        "- Access audit and audit trail proving the demo package is tenant/module scoped.",
        "",
        "## Synthetic Data Notice",
        "",
        "All rows are generated demo records. Do not treat addresses, responses, or values as real customer data.",
        "Scaled demo addresses use the `Demo ...` street prefix so they are recognizable as synthetic during customer conversations.",
        "",
    ]
    return "\n".join(lines)


def build_demo_room(
    out_dir: Path,
    tenant_name: str = "HomePilot Enterprise Demo",
    tenant_slug: str = "homepilot-enterprise-demo",
    include_xlsx: bool = True,
    include_zip: bool = True,
    property_count: int | None = None,
    scenario: str = "enterprise",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    modules = ("facadepilot",) if scenario == "daw" else DEMO_MODULES
    scenario_settings = {
        "demo": True,
        "dataset": "daw_crepi_partner_network" if scenario == "daw" else "synthetic_enterprise_showroom",
        "scenario": scenario,
    }
    onboarding = build_demo_onboarding(
        name=tenant_name,
        slug=tenant_slug,
        modules=modules,
        settings=scenario_settings,
        subscription_tier="producer-network-demo" if scenario == "daw" else "enterprise-demo",
    )
    payload = build_demo_payload(tenant_slug=tenant_slug, property_count=property_count, scenario=scenario)
    onboarding_path = data_dir / "onboarding.json"
    payload_path = data_dir / "payload.json"
    write_json(onboarding_path, onboarding)
    write_json(payload_path, payload)

    package_dir = out_dir / "customer_package"
    package_manifest = build_customer_package(
        onboarding_path=onboarding_path,
        payload_path=payload_path,
        output_dir=package_dir,
        tenant_name=tenant_name,
        tenant_slug=tenant_slug,
        modules=list(modules),
        include_xlsx=include_xlsx,
        include_zip=include_zip,
        audit_payload=True,
        include_intelligence_lab=scenario == "daw",
        intelligence_lab_run_count=12,
    )
    package_snapshot = json.loads(Path(package_manifest["paths"]["dashboard_snapshot"]).read_text(encoding="utf-8"))
    dictionary_pack = build_data_dictionary_pack(out_dir / "data_dictionary", modules=list(modules))
    partner_cutdown_pack = None
    if scenario == "daw":
        partner_cutdown_pack = build_partner_cutdown_pack(
            payload=payload,
            out_dir=out_dir / "partner_cutdowns",
            tenant_name=tenant_name,
            tenant_slug=tenant_slug,
            modules=list(modules),
            include_xlsx=include_xlsx,
            include_zip=include_zip,
        )
    portal_pack = build_portal_bundle(Path(package_manifest["paths"]["manifest"]), out_dir / "portal")
    integration_pack = build_integration_pack(Path(package_manifest["paths"]["manifest"]), out_dir / "sales_integration")
    enrichment_pack = build_enrichment_pack(Path(package_manifest["paths"]["manifest"]), out_dir / "data_vendor_enrichment")

    status_checks = {
        "customer_package": package_manifest["access_audit"]["status"],
        "audit_trail": package_manifest["audit_trail"]["status"],
        "data_dictionary": dictionary_pack["status"],
        "portal": portal_pack["status"],
        "integration": integration_pack["status"],
        "enrichment": enrichment_pack["status"],
        "boardroom_report": package_manifest["boardroom_report"]["status"],
    }
    if partner_cutdown_pack is not None:
        status_checks["partner_cutdowns"] = partner_cutdown_pack["status"]

    manifest = {
        "pack_type": "homepilot_enterprise_demo_room",
        "created_at": utc_now(),
        "status": "pass" if all(status == "pass" for status in status_checks.values()) else "fail",
        "tenant": package_manifest["tenant"],
        "modules": list(modules),
        "dataset": {
            "mode": "daw_producer_network" if scenario == "daw" else ("scaled_synthetic" if property_count is not None else "curated_synthetic"),
            "scenario": scenario,
            "requested_properties": property_count,
            "synthetic": True,
            "safe_for_demo": True,
            "note": "Generated records are fictional and intended for product demos, not homeowner claims.",
        },
        "summary": summarize_payload(payload),
        "network": package_snapshot.get("network"),
        "status_checks": status_checks,
        "customer_package": {
            "summary": package_manifest["summary"],
            "access_audit": package_manifest["access_audit"]["status"],
            "audit_trail": package_manifest["audit_trail"]["status"],
        },
        "portal": {
            "status": portal_pack["status"],
            "checks": portal_pack["checks"],
        },
        "sales_integration": {
            "status": integration_pack["status"],
            "providers": integration_pack["providers"],
            "counts": integration_pack["counts"],
        },
        "data_vendor_enrichment": {
            "status": enrichment_pack["status"],
            "review_status": enrichment_pack["review_status"],
            "summary": enrichment_pack["plan"]["summary"],
        },
        "data_dictionary": {
            "status": dictionary_pack["status"],
            "counts": dictionary_pack["dictionary"]["counts"],
        },
        "boardroom_report": package_manifest["boardroom_report"],
        "partner_cutdowns": {
            "status": partner_cutdown_pack["status"],
            "summary": partner_cutdown_pack["summary"],
        } if partner_cutdown_pack is not None else None,
        "paths": {
            "manifest": str(out_dir / "manifest.json"),
            "readme": str(out_dir / "README.md"),
            "onboarding": str(onboarding_path),
            "payload": str(payload_path),
            "customer_package_manifest": package_manifest["paths"]["manifest"],
            "dashboard_index": package_manifest["paths"]["dashboard_index"],
            "boardroom_report": package_manifest["paths"]["boardroom_report_html"],
            "boardroom_report_markdown": package_manifest["paths"]["boardroom_report_markdown"],
            "partner_cutdowns_manifest": partner_cutdown_pack["paths"]["manifest"] if partner_cutdown_pack is not None else None,
            "exports": package_manifest["paths"]["exports"],
            "zip": package_manifest["paths"].get("zip"),
            "portal_manifest": portal_pack["paths"]["portal_manifest"],
            "portal_readme": portal_pack["paths"]["readme"],
            "integration_manifest": integration_pack["paths"]["integration_manifest"],
            "integration_runbook": integration_pack["paths"]["runbook"],
            "data_vendor_plan": enrichment_pack["paths"]["data_vendor_plan"],
            "data_vendor_plan_markdown": enrichment_pack["paths"]["markdown"],
            "enrichment_backlog": enrichment_pack["paths"]["enrichment_backlog"],
            "data_dictionary": dictionary_pack["paths"]["data_dictionary"],
            "data_dictionary_markdown": dictionary_pack["paths"]["markdown"],
        },
    }
    write_json(out_dir / "manifest.json", manifest)
    write_text(out_dir / "README.md", render_demo_readme(manifest))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot enterprise demo room")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--tenant-name", default="HomePilot Enterprise Demo")
    parser.add_argument("--tenant-slug", default="homepilot-enterprise-demo")
    parser.add_argument("--property-count", type=int, help=f"Build a scaled synthetic demo dataset, for example {SCALED_DEMO_DEFAULT_PROPERTIES}.")
    parser.add_argument("--scenario", choices=("enterprise", "daw"), default="enterprise")
    parser.add_argument("--no-xlsx", action="store_true")
    parser.add_argument("--no-zip", action="store_true")
    args = parser.parse_args()
    manifest = build_demo_room(
        out_dir=args.out_dir,
        tenant_name=args.tenant_name,
        tenant_slug=args.tenant_slug,
        include_xlsx=not args.no_xlsx,
        include_zip=not args.no_zip,
        property_count=args.property_count,
        scenario=args.scenario,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": manifest["status"],
        "dashboard": manifest["paths"]["dashboard_index"],
        "manifest": manifest["paths"]["manifest"],
        "zip": manifest["paths"].get("zip"),
        "summary": manifest["summary"],
    }, indent=2, ensure_ascii=False))
    if manifest["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
