#!/usr/bin/env python3
"""
HomePilot data quality audit.

Validation proves a payload is structurally importable. This audit answers the
next enterprise question: will the data be useful enough for customer-facing
maps, scoring, exports, sales follow-up, and learning loops?
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_platform import PILOT_MODULES
from homepilot_store import load_payload, validate_payload


RESPONDED_STATUSES = {"responded", "appointment", "customer"}
CONTACTED_STATUSES = {"sent", "scanned", "clicked", "responded", "appointment", "customer", "no_response"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _pct(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100, 2)


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_geo(prop: dict[str, Any]) -> bool:
    return _num(prop.get("lat")) is not None and _num(prop.get("lon")) is not None


def _nonempty_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value)


def _duplicate_count(values: list[str]) -> int:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return len(duplicates)


def _address_key(prop: dict[str, Any]) -> str:
    tenant = str(prop.get("tenant_id") or "").strip().lower()
    address = str(prop.get("address") or "").strip().lower()
    city = str(prop.get("city") or "").strip().lower()
    return "|".join((tenant, address, city))


def build_data_quality_report(
    payload: dict[str, Any],
    min_score_coverage_pct: float = 95.0,
    min_geocode_coverage_pct: float = 80.0,
    min_target_coverage_pct: float = 75.0,
    min_evidence_coverage_pct: float = 50.0,
) -> dict[str, Any]:
    validate_payload(payload)

    properties = payload.get("properties", [])
    assessments = payload.get("assessments", [])
    targets = payload.get("campaign_targets", [])
    interactions = payload.get("interactions", [])
    campaigns = payload.get("campaigns", [])

    failures: list[str] = []
    warnings: list[str] = []

    property_ids = [str(row.get("id") or "") for row in properties]
    assessment_ids = [str(row.get("id") or "") for row in assessments]
    campaign_ids = [str(row.get("id") or "") for row in campaigns]
    property_duplicate_count = _duplicate_count(property_ids)
    assessment_duplicate_count = _duplicate_count(assessment_ids)
    campaign_duplicate_count = _duplicate_count(campaign_ids)
    duplicate_address_count = _duplicate_count([_address_key(row) for row in properties if row.get("address")])

    if not properties:
        failures.append("Payload contains no properties.")
    if not assessments:
        failures.append("Payload contains no assessments.")
    if property_duplicate_count:
        failures.append(f"Payload contains {property_duplicate_count} duplicate property id(s).")
    if assessment_duplicate_count:
        failures.append(f"Payload contains {assessment_duplicate_count} duplicate assessment id(s).")
    if campaign_duplicate_count:
        failures.append(f"Payload contains {campaign_duplicate_count} duplicate campaign id(s).")
    if duplicate_address_count:
        warnings.append(f"Payload contains {duplicate_address_count} duplicate tenant/address/city combination(s).")

    geocoded_count = sum(1 for prop in properties if _is_geo(prop))
    city_count = sum(1 for prop in properties if str(prop.get("city") or "").strip())
    scored_count = sum(1 for assessment in assessments if _num(assessment.get("score")) is not None)
    evidence_count = sum(1 for assessment in assessments if _nonempty_list(assessment.get("evidence")))
    assessment_pairs = {
        (str(row.get("property_id") or ""), str(row.get("module_key") or ""))
        for row in assessments
    }
    target_pairs = {
        (str(row.get("property_id") or ""), str(row.get("module_key") or ""))
        for row in targets
    }
    targeted_assessment_count = len(assessment_pairs.intersection(target_pairs))
    contacted_count = sum(1 for target in targets if target.get("status") in CONTACTED_STATUSES)
    response_count = sum(1 for target in targets if target.get("status") in RESPONDED_STATUSES)

    primary_score_metric_count = 0
    for assessment in assessments:
        module_key = assessment.get("module_key")
        definition = PILOT_MODULES.get(str(module_key))
        metrics = assessment.get("metrics") if isinstance(assessment.get("metrics"), dict) else {}
        if definition and definition.primary_score_key in metrics:
            primary_score_metric_count += 1

    metrics = {
        "property_count": len(properties),
        "assessment_count": len(assessments),
        "campaign_count": len(campaigns),
        "target_count": len(targets),
        "interaction_count": len(interactions),
        "geocode_coverage_pct": _pct(geocoded_count, len(properties)),
        "city_coverage_pct": _pct(city_count, len(properties)),
        "score_coverage_pct": _pct(scored_count, len(assessments)),
        "primary_score_metric_coverage_pct": _pct(primary_score_metric_count, len(assessments)),
        "evidence_coverage_pct": _pct(evidence_count, len(assessments)),
        "target_coverage_pct": _pct(targeted_assessment_count, len(assessment_pairs)),
        "contacted_count": contacted_count,
        "response_count": response_count,
        "response_rate_pct": _pct(response_count, contacted_count),
        "duplicate_property_id_count": property_duplicate_count,
        "duplicate_assessment_id_count": assessment_duplicate_count,
        "duplicate_campaign_id_count": campaign_duplicate_count,
        "duplicate_address_count": duplicate_address_count,
    }

    if metrics["score_coverage_pct"] < min_score_coverage_pct:
        failures.append(
            f"Score coverage {metrics['score_coverage_pct']}% is below {min_score_coverage_pct}%."
        )
    if metrics["primary_score_metric_coverage_pct"] < min_score_coverage_pct:
        warnings.append(
            f"Primary score metric coverage {metrics['primary_score_metric_coverage_pct']}% is below {min_score_coverage_pct}%."
        )
    if metrics["geocode_coverage_pct"] < min_geocode_coverage_pct:
        warnings.append(
            f"Geocode coverage {metrics['geocode_coverage_pct']}% is below {min_geocode_coverage_pct}%."
        )
    if metrics["target_coverage_pct"] < min_target_coverage_pct:
        warnings.append(
            f"Campaign target coverage {metrics['target_coverage_pct']}% is below {min_target_coverage_pct}%."
        )
    if metrics["evidence_coverage_pct"] < min_evidence_coverage_pct:
        warnings.append(
            f"Evidence coverage {metrics['evidence_coverage_pct']}% is below {min_evidence_coverage_pct}%."
        )

    module_counts: dict[str, int] = {}
    for assessment in assessments:
        module_key = str(assessment.get("module_key") or "")
        module_counts[module_key] = module_counts.get(module_key, 0) + 1

    status = "fail" if failures else ("warn" if warnings else "pass")
    return {
        "report_type": "homepilot_data_quality",
        "created_at": utc_now(),
        "status": status,
        "thresholds": {
            "min_score_coverage_pct": min_score_coverage_pct,
            "min_geocode_coverage_pct": min_geocode_coverage_pct,
            "min_target_coverage_pct": min_target_coverage_pct,
            "min_evidence_coverage_pct": min_evidence_coverage_pct,
        },
        "metrics": metrics,
        "modules": module_counts,
        "failures": failures,
        "warnings": warnings,
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit HomePilot payload data quality")
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--fail-on-warn", action="store_true")
    parser.add_argument("--min-score-coverage-pct", type=float, default=95.0)
    parser.add_argument("--min-geocode-coverage-pct", type=float, default=80.0)
    parser.add_argument("--min-target-coverage-pct", type=float, default=75.0)
    parser.add_argument("--min-evidence-coverage-pct", type=float, default=50.0)
    args = parser.parse_args()

    report = build_data_quality_report(
        load_payload(args.json),
        min_score_coverage_pct=args.min_score_coverage_pct,
        min_geocode_coverage_pct=args.min_geocode_coverage_pct,
        min_target_coverage_pct=args.min_target_coverage_pct,
        min_evidence_coverage_pct=args.min_evidence_coverage_pct,
    )
    write_json(args.out, report)
    print(json.dumps({
        "output": str(args.out),
        "status": report["status"],
        "properties": report["metrics"]["property_count"],
        "assessments": report["metrics"]["assessment_count"],
        "warnings": len(report["warnings"]),
        "failures": len(report["failures"]),
    }, indent=2))
    if report["status"] == "fail" or (args.fail_on_warn and report["status"] == "warn"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
