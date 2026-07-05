#!/usr/bin/env python3
"""
Run a safe HomePilot autoresearch loop for campaign segmentation.

This benchmarks deterministic segmentation recipes against a tenant-scoped
dashboard snapshot. It writes review artifacts only: no raw addresses, no live
data writes, no Supabase changes, no outreach state changes, and no homeowner
intent claims from opportunity scores or public context.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONTACTED_STATUSES = {"sent", "scanned", "clicked", "responded", "appointment", "customer", "no_response"}
ENGAGED_STATUSES = {"responded", "appointment", "customer"}
CONVERSION_STATUSES = {"appointment", "customer"}
ACTIONABLE_STATUSES = {"queued", "sent", "scanned", "clicked", "responded", "appointment", "no_response"}

OUTCOME_PROXY = {
    "customer": 1.0,
    "appointment": 0.95,
    "responded": 0.78,
    "clicked": 0.52,
    "scanned": 0.42,
    "sent": 0.26,
    "queued": 0.18,
    "no_response": 0.04,
}

MESSAGE_ANGLES = (
    "energy savings",
    "facade refresh",
    "premium finish",
    "subsidy check",
    "maintenance free",
)

DEFAULT_SEGMENT_CONFIG: dict[str, Any] = {
    "strategy_name": "territory_score_baseline",
    "dimensions": ["territory", "score_band"],
    "top_segments": 8,
    "min_segment_size": 12,
    "value_cap_eur": 60000,
    "facade_m2_cap": 320,
    "coverage_target_pct": 35.0,
    "max_segment_share": 0.40,
    "weights": {
        "response_proxy": 0.22,
        "avg_score": 0.18,
        "pipeline_density": 0.14,
        "facade_density": 0.08,
        "public_context": 0.07,
        "actionability": 0.11,
        "coverage": 0.10,
        "denominator_clarity": 0.10,
    },
}

VARIANT_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "strategy_name": "territory_status_score",
        "dimensions": ["territory", "status_cluster", "score_band"],
        "min_segment_size": 8,
        "weights": {
            "response_proxy": 0.26,
            "avg_score": 0.18,
            "pipeline_density": 0.12,
            "facade_density": 0.06,
            "public_context": 0.06,
            "actionability": 0.15,
            "coverage": 0.07,
            "denominator_clarity": 0.10,
        },
    },
    {
        "strategy_name": "message_score_band",
        "dimensions": ["message_angle", "score_band", "status_cluster"],
        "min_segment_size": 8,
        "weights": {
            "response_proxy": 0.24,
            "avg_score": 0.16,
            "pipeline_density": 0.13,
            "facade_density": 0.06,
            "public_context": 0.09,
            "actionability": 0.14,
            "coverage": 0.08,
            "denominator_clarity": 0.10,
        },
    },
    {
        "strategy_name": "public_context_policy_segment",
        "dimensions": ["public_policy", "pre_1990_band", "score_band"],
        "min_segment_size": 10,
        "weights": {
            "response_proxy": 0.20,
            "avg_score": 0.18,
            "pipeline_density": 0.12,
            "facade_density": 0.07,
            "public_context": 0.16,
            "actionability": 0.10,
            "coverage": 0.07,
            "denominator_clarity": 0.10,
        },
    },
    {
        "strategy_name": "property_type_value_segment",
        "dimensions": ["property_type", "value_band", "score_band"],
        "min_segment_size": 8,
        "weights": {
            "response_proxy": 0.18,
            "avg_score": 0.17,
            "pipeline_density": 0.20,
            "facade_density": 0.10,
            "public_context": 0.06,
            "actionability": 0.11,
            "coverage": 0.08,
            "denominator_clarity": 0.10,
        },
    },
    {
        "strategy_name": "partner_tier_message_segment",
        "dimensions": ["partner_tier", "message_angle", "status_cluster"],
        "min_segment_size": 8,
        "weights": {
            "response_proxy": 0.26,
            "avg_score": 0.13,
            "pipeline_density": 0.12,
            "facade_density": 0.06,
            "public_context": 0.06,
            "actionability": 0.16,
            "coverage": 0.11,
            "denominator_clarity": 0.10,
        },
    },
    {
        "strategy_name": "city_facade_opportunity_segment",
        "dimensions": ["city", "facade_band", "score_band"],
        "min_segment_size": 6,
        "weights": {
            "response_proxy": 0.18,
            "avg_score": 0.18,
            "pipeline_density": 0.16,
            "facade_density": 0.14,
            "public_context": 0.06,
            "actionability": 0.10,
            "coverage": 0.08,
            "denominator_clarity": 0.10,
        },
    },
)

RAW_ADDRESS_MARKERS = (
    "daw gevelstraat",
    "daw demolaan",
    "daw crepiweg",
    "daw isolatiepad",
    "daw pleisterlaan",
    "daw renovatiehof",
    "daw steenweg",
    "daw energieplein",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _number(value: Any, fallback: float = 0.0) -> float:
    if value in (None, ""):
        return fallback
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) else fallback


def _pct(numerator: float, denominator: float) -> float:
    return round((numerator / denominator) * 100, 1) if denominator else 0.0


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _merged_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    config = deepcopy(DEFAULT_SEGMENT_CONFIG)
    if not overrides:
        return config
    for key, value in overrides.items():
        if key == "weights" and isinstance(value, dict):
            config["weights"].update(value)
        elif key in config:
            config[key] = value
    return config


def _properties(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return snapshot.get("properties") if isinstance(snapshot.get("properties"), list) else []


def _network(snapshot: dict[str, Any]) -> dict[str, Any]:
    return snapshot.get("network") if isinstance(snapshot.get("network"), dict) else {}


def _partner_stats(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    partners = _network(snapshot).get("partners") if isinstance(_network(snapshot).get("partners"), list) else []
    return {str(row.get("id") or ""): row for row in partners if isinstance(row, dict) and row.get("id")}


def _best_assessment(prop: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    assessments = prop.get("assessments") if isinstance(prop.get("assessments"), dict) else {}
    if not assessments:
        return "", {}
    return sorted(
        assessments.items(),
        key=lambda item: (_number(item[1].get("score")), _number(prop.get("estimatedValue"))),
        reverse=True,
    )[0]


def _partner_id(prop: dict[str, Any]) -> str:
    partner = prop.get("partner") if isinstance(prop.get("partner"), dict) else {}
    return str(partner.get("id") or prop.get("partner_id") or "")


def _partner_name(prop: dict[str, Any]) -> str:
    partner = prop.get("partner") if isinstance(prop.get("partner"), dict) else {}
    return str(partner.get("name") or prop.get("partner_name") or "")


def _lead_queue_index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lead = snapshot.get("leadPrioritization") if isinstance(snapshot.get("leadPrioritization"), dict) else {}
    queue = lead.get("best_queue") if isinstance(lead.get("best_queue"), list) else []
    return {str(row.get("property_id")): row for row in queue if isinstance(row, dict) and row.get("property_id")}


def _assignment_property_ids(snapshot: dict[str, Any]) -> set[str]:
    assignment = snapshot.get("partnerAssignment") if isinstance(snapshot.get("partnerAssignment"), dict) else {}
    batches = assignment.get("best_assignment") if isinstance(assignment.get("best_assignment"), list) else []
    ids: set[str] = set()
    for batch in batches:
        if isinstance(batch, dict) and isinstance(batch.get("selected_property_ids"), list):
            ids.update(str(item) for item in batch["selected_property_ids"] if item)
    return ids


def _metric(prop: dict[str, Any], key: str) -> Any:
    _module, assessment = _best_assessment(prop)
    metrics = assessment.get("metrics") if isinstance(assessment.get("metrics"), dict) else {}
    return metrics.get(key)


def _public_feature(prop: dict[str, Any], key: str, fallback: Any = None) -> Any:
    context = prop.get("publicContext") if isinstance(prop.get("publicContext"), dict) else {}
    features = context.get("features") if isinstance(context.get("features"), list) else []
    for feature in features:
        if isinstance(feature, dict) and feature.get("key") == key:
            return feature.get("value", fallback)
    return fallback


def _score_band(score: float) -> str:
    if score >= 90:
        return "A_plus_90_100"
    if score >= 78:
        return "A_78_89"
    if score >= 62:
        return "B_62_77"
    return "C_under_62"


def _value_band(value: float) -> str:
    if value >= 48000:
        return "premium_value"
    if value >= 32000:
        return "high_value"
    if value >= 20000:
        return "mid_value"
    return "entry_value"


def _facade_band(facade_m2: float) -> str:
    if facade_m2 >= 240:
        return "large_facade"
    if facade_m2 >= 150:
        return "medium_facade"
    return "compact_facade"


def _status_cluster(status: str) -> str:
    if status in {"appointment", "customer"}:
        return "appointment_or_customer"
    if status == "responded":
        return "responded"
    if status in {"clicked", "scanned"}:
        return "warm_click_or_scan"
    if status == "no_response":
        return "no_response_backlog"
    if status == "queued":
        return "queued_not_contacted"
    return "sent_contacted"


def _pre_1990_band(prop: dict[str, Any]) -> str:
    value = _number(_metric(prop, "pre_1990_neighborhood_pct"), _number(_public_feature(prop, "stat_sector_pre_1990_share"), 0.0))
    if value >= 70:
        return "pre_1990_high"
    if value >= 55:
        return "pre_1990_medium"
    return "pre_1990_lower"


def _public_policy(prop: dict[str, Any]) -> str:
    policy = str(_public_feature(prop, "renovation_policy_context", "unknown_policy")).strip().lower().replace(" ", "_")
    heritage = str(_public_feature(prop, "planning_or_heritage_flag", "")).strip().lower()
    if "review" in heritage:
        return "review_zone"
    return policy or "unknown_policy"


def _message_angle(prop: dict[str, Any]) -> str:
    tags = [str(tag).strip().lower() for tag in prop.get("tags", []) if str(tag).strip()]
    for angle in MESSAGE_ANGLES:
        if angle in tags:
            return angle.replace(" ", "_")
    return "general_crepi"


def _public_context_score(prop: dict[str, Any]) -> float:
    context = prop.get("publicContext") if isinstance(prop.get("publicContext"), dict) else {}
    features = context.get("features") if isinstance(context.get("features"), list) else []
    confidence = _number(context.get("confidence"), 0.0)
    return _clamp(confidence * 0.60 + min(1.0, len(features) / 6) * 0.40)


def _dimension_value(prop: dict[str, Any], dimension: str, partner_stats: dict[str, dict[str, Any]]) -> str:
    module_key, assessment = _best_assessment(prop)
    score = _number(assessment.get("score"), 0.0)
    partner = partner_stats.get(_partner_id(prop), {})
    if dimension == "territory":
        return str(prop.get("territory") or partner.get("region") or "unknown_territory")
    if dimension == "city":
        return str(prop.get("city") or "unknown_city")
    if dimension == "partner_tier":
        return str(partner.get("tier") or "unknown_tier")
    if dimension == "module_key":
        return module_key or "unknown_module"
    if dimension == "score_band":
        return _score_band(score)
    if dimension == "value_band":
        return _value_band(_number(prop.get("estimatedValue"), 0.0))
    if dimension == "facade_band":
        return _facade_band(_number(prop.get("estimatedFacadeM2"), 0.0))
    if dimension == "status_cluster":
        return _status_cluster(str(prop.get("status") or "queued"))
    if dimension == "property_type":
        return str(_metric(prop, "property_type") or "unknown_property_type").replace(" ", "_")
    if dimension == "pre_1990_band":
        return _pre_1990_band(prop)
    if dimension == "public_policy":
        return _public_policy(prop)
    if dimension == "message_angle":
        return _message_angle(prop)
    return "unknown"


def _safe_dimension_label(dimensions: dict[str, str]) -> str:
    return " | ".join(f"{key}: {value}" for key, value in dimensions.items())


def _segment_key(dimensions: dict[str, str]) -> str:
    return "__".join(f"{key}={value}" for key, value in dimensions.items())


def _property_row(
    prop: dict[str, Any],
    partner_stats: dict[str, dict[str, Any]],
    queue_index: dict[str, dict[str, Any]],
    assignment_ids: set[str],
) -> dict[str, Any]:
    module_key, assessment = _best_assessment(prop)
    partner_id = _partner_id(prop)
    partner = partner_stats.get(partner_id, {})
    status = str(prop.get("status") or "queued")
    property_id = str(prop.get("id") or "")
    priority = queue_index.get(property_id, {})
    return {
        "property_id": property_id,
        "module_key": module_key,
        "city": str(prop.get("city") or ""),
        "territory": str(prop.get("territory") or partner.get("region") or ""),
        "partner_id": partner_id,
        "partner_name": _partner_name(prop) or str(partner.get("name") or partner_id),
        "partner_tier": str(partner.get("tier") or ""),
        "status": status,
        "score": _number(assessment.get("score"), 0.0),
        "grade": str(assessment.get("grade") or ""),
        "confidence": _number(assessment.get("confidence"), 0.0),
        "priority_score": _number(priority.get("priority_score"), _number(assessment.get("score"), 0.0)),
        "estimated_value": _number(prop.get("estimatedValue"), 0.0),
        "estimated_facade_m2": _number(prop.get("estimatedFacadeM2"), 0.0),
        "public_context_score": _public_context_score(prop),
        "in_partner_assignment_wave": property_id in assignment_ids,
        "property_type": str(_metric(prop, "property_type") or ""),
        "message_angle": _message_angle(prop),
    }


def build_segment_rows(snapshot: dict[str, Any], segment_config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    config = _merged_config(segment_config)
    dimensions = [str(item) for item in config.get("dimensions", [])]
    partner_stats = _partner_stats(snapshot)
    queue_index = _lead_queue_index(snapshot)
    assignment_ids = _assignment_property_ids(snapshot)
    grouped: dict[str, dict[str, Any]] = {}
    total_properties = len(_properties(snapshot))
    for prop in _properties(snapshot):
        module_key, _assessment = _best_assessment(prop)
        if not module_key:
            continue
        dim_values = {dimension: _dimension_value(prop, dimension, partner_stats) for dimension in dimensions}
        key = _segment_key(dim_values)
        row = grouped.setdefault(key, {"segment_key": key, "dimensions": dim_values, "properties": []})
        row["properties"].append(_property_row(prop, partner_stats, queue_index, assignment_ids))

    min_size = int(_number(config.get("min_segment_size"), 1))
    rows = []
    for key, group in grouped.items():
        props = group["properties"]
        count = len(props)
        if count < min_size:
            continue
        contacted = sum(1 for prop in props if prop["status"] in CONTACTED_STATUSES)
        engaged = sum(1 for prop in props if prop["status"] in ENGAGED_STATUSES)
        appointments = sum(1 for prop in props if prop["status"] in CONVERSION_STATUSES)
        no_response = sum(1 for prop in props if prop["status"] == "no_response")
        actionable = sum(1 for prop in props if prop["status"] in ACTIONABLE_STATUSES)
        assignment_wave = sum(1 for prop in props if prop["in_partner_assignment_wave"])
        avg_score = sum(prop["score"] for prop in props) / count
        avg_priority = sum(prop["priority_score"] for prop in props) / count
        avg_public = sum(prop["public_context_score"] for prop in props) / count
        pipeline_value = int(round(sum(prop["estimated_value"] for prop in props)))
        facade_m2 = int(round(sum(prop["estimated_facade_m2"] for prop in props)))
        response_proxy = _pct(sum(OUTCOME_PROXY.get(str(prop["status"]), 0.12) for prop in props), count)
        partner_mix = _count_by(props, "partner_id")
        city_mix = _count_by(props, "city")
        top_property_ids = [prop["property_id"] for prop in sorted(
            props,
            key=lambda item: (item["priority_score"], item["score"], item["estimated_value"], item["property_id"]),
            reverse=True,
        )[:10]]
        features = {
            "response_proxy": response_proxy,
            "avg_score": avg_score,
            "pipeline_density": min(100.0, _pct(pipeline_value / count, max(1.0, _number(config.get("value_cap_eur"), 60000)))),
            "facade_density": min(100.0, _pct(facade_m2 / count, max(1.0, _number(config.get("facade_m2_cap"), 320)))),
            "public_context": avg_public * 100,
            "actionability": max(0.0, _pct(actionable, count) - _pct(no_response, contacted or count) * 0.35),
            "coverage": min(100.0, _pct(count, max(1.0, total_properties * (_number(config.get("coverage_target_pct"), 35.0) / 100.0)))),
            "denominator_clarity": 100.0,
        }
        segment_score = _weighted_segment_score(features, config)
        rows.append({
            "segment_key": key,
            "segment_label": _safe_dimension_label(group["dimensions"]),
            "dimensions": group["dimensions"],
            "property_count": count,
            "contacted_count": contacted,
            "engaged_count": engaged,
            "appointment_count": appointments,
            "no_response_count": no_response,
            "response_rate_pct": _pct(engaged, contacted),
            "appointment_rate_pct": _pct(appointments, contacted),
            "target_response_rate_pct": _pct(engaged, count),
            "response_denominator": "contacted_count",
            "avg_score": round(avg_score, 2),
            "avg_priority_score": round(avg_priority, 2),
            "pipeline_value": pipeline_value,
            "facade_m2": facade_m2,
            "public_context_score": round(avg_public * 100, 2),
            "assignment_wave_count": assignment_wave,
            "partner_count": len(partner_mix),
            "partner_mix": partner_mix,
            "city_mix": city_mix,
            "top_property_ids": top_property_ids,
            "segment_score": segment_score,
            "segment_reasons": _segment_reasons(features, config),
            "synthetic_demo_metric": True,
            "opportunity_not_intent_without_response": engaged < count,
        })
    rows.sort(
        key=lambda row: (
            _number(row.get("segment_score")),
            _number(row.get("property_count")),
            _number(row.get("pipeline_value")),
            str(row.get("segment_key") or ""),
        ),
        reverse=True,
    )
    top_segments = int(_number(config.get("top_segments"), 8))
    return [{"rank": index + 1, **row} for index, row in enumerate(rows[:top_segments])]


def _count_by(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get(field) or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _weighted_segment_score(features: dict[str, float], config: dict[str, Any]) -> float:
    weights = config.get("weights") if isinstance(config.get("weights"), dict) else {}
    total = sum(max(0.0, _number(weight)) for weight in weights.values())
    if total <= 0:
        return 0.0
    score = sum(_number(weight) * _number(features.get(key)) for key, weight in weights.items()) / total
    return round(_clamp(score / 100.0) * 100, 3)


def _segment_reasons(features: dict[str, float], config: dict[str, Any]) -> list[str]:
    labels = {
        "response_proxy": "strong response proxy",
        "avg_score": "high opportunity score",
        "pipeline_density": "high value density",
        "facade_density": "large facade density",
        "public_context": "public-context coverage",
        "actionability": "actionable campaign status mix",
        "coverage": "meaningful segment size",
        "denominator_clarity": "contacted denominator is explicit",
    }
    weights = config.get("weights") if isinstance(config.get("weights"), dict) else {}
    ranked = sorted(
        [(key, _number(weight) * _number(features.get(key))) for key, weight in weights.items() if _number(weight) > 0],
        key=lambda item: item[1],
        reverse=True,
    )
    return [labels.get(key, key) for key, contribution in ranked[:3] if contribution > 0]


def evaluate_segmentation_quality(
    snapshot: dict[str, Any],
    segment_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = _merged_config(segment_config)
    started = time.perf_counter()
    segments = build_segment_rows(snapshot, config)
    runtime_ms = (time.perf_counter() - started) * 1000
    if not segments:
        return {
            "final_score": 0.0,
            "segment_count": 0,
            "covered_properties": 0,
            "coverage_pct": 0.0,
            "avg_segment_score": 0.0,
            "avg_response_rate_pct": 0.0,
            "avg_appointment_rate_pct": 0.0,
            "pipeline_value": 0,
            "facade_m2": 0,
            "denominator_clarity_score": 0.0,
            "max_segment_share_pct": 0.0,
            "runtime_ms": round(runtime_ms, 2),
            "synthetic_demo_metric": True,
            "outcome_proxy_only": True,
        }
    total_properties = len(_properties(snapshot))
    covered_ids: set[str] = set()
    for segment in segments:
        covered_ids.update(str(item) for item in segment.get("top_property_ids", []))
    covered_properties = sum(_number(segment.get("property_count")) for segment in segments)
    avg_segment_score = sum(_number(segment.get("segment_score")) for segment in segments) / len(segments)
    avg_response = sum(_number(segment.get("response_rate_pct")) for segment in segments) / len(segments)
    avg_appointment = sum(_number(segment.get("appointment_rate_pct")) for segment in segments) / len(segments)
    pipeline_value = int(round(sum(_number(segment.get("pipeline_value")) for segment in segments)))
    facade_m2 = int(round(sum(_number(segment.get("facade_m2")) for segment in segments)))
    clarity = 100.0 if all(segment.get("response_denominator") == "contacted_count" for segment in segments) else 0.0
    max_share = max(_number(segment.get("property_count")) for segment in segments) / max(1.0, covered_properties)
    concentration_score = max(0.0, 100.0 - max(0.0, max_share - _number(config.get("max_segment_share"), 0.40)) * 240.0)
    coverage_pct = _pct(covered_properties, total_properties)
    coverage_score = min(100.0, _pct(coverage_pct, _number(config.get("coverage_target_pct"), 35.0)))
    final_score = (
        avg_segment_score * 0.42
        + avg_response * 0.13
        + avg_appointment * 0.08
        + coverage_score * 0.13
        + concentration_score * 0.09
        + clarity * 0.15
    )
    return {
        "final_score": round(final_score, 3),
        "segment_count": len(segments),
        "covered_properties": int(round(covered_properties)),
        "coverage_pct": coverage_pct,
        "avg_segment_score": round(avg_segment_score, 2),
        "avg_response_rate_pct": round(avg_response, 2),
        "avg_appointment_rate_pct": round(avg_appointment, 2),
        "pipeline_value": pipeline_value,
        "facade_m2": facade_m2,
        "denominator_clarity_score": clarity,
        "max_segment_share_pct": round(max_share * 100, 1),
        "runtime_ms": round(runtime_ms, 2),
        "synthetic_demo_metric": True,
        "outcome_proxy_only": True,
        "response_denominator": "contacted_count",
    }


def _variant_config(index: int) -> dict[str, Any]:
    template = deepcopy(VARIANT_TEMPLATES[index % len(VARIANT_TEMPLATES)])
    phase = index // len(VARIANT_TEMPLATES)
    config = _merged_config(template)
    config["strategy_name"] = f"{template['strategy_name']}_v{phase + 1}"
    config["top_segments"] = [6, 8, 10][phase % 3]
    config["min_segment_size"] = max(4, int(_number(template.get("min_segment_size"), 8)) + [-2, 0, 2][(phase // 3) % 3])
    config["coverage_target_pct"] = [25.0, 35.0, 45.0][(phase // 5) % 3]
    config["max_segment_share"] = [0.32, 0.40, 0.48][(phase // 7) % 3]
    return config


def run_segmentation_experiments(
    snapshot: dict[str, Any],
    run_count: int = 24,
    baseline_only: bool = False,
    target_score: float | None = None,
    max_runs: int | None = None,
) -> list[dict[str, Any]]:
    experiments = [{
        "tag": "baseline",
        "segment_config": _merged_config(),
        "description": "current territory and score-band segmentation",
    }]
    best_score = -1.0
    if not baseline_only:
        total_variants = max(0, max_runs if target_score is not None and max_runs is not None else run_count)
        for index in range(total_variants):
            config = _variant_config(index)
            row = {
                "tag": f"variant_{index + 1:02d}",
                "segment_config": config,
                "description": "deterministic campaign segmentation recipe",
            }
            experiments.append(row)
            quality = evaluate_segmentation_quality(snapshot, config)
            best_score = max(best_score, quality["final_score"])
            row["quality"] = quality
            row["segments"] = build_segment_rows(snapshot, config)
            if target_score is not None and best_score >= target_score:
                break

    results = []
    for experiment in experiments:
        if "quality" not in experiment:
            experiment["quality"] = evaluate_segmentation_quality(snapshot, experiment["segment_config"])
            experiment["segments"] = build_segment_rows(snapshot, experiment["segment_config"])
        results.append({**experiment, "status": "keep"})

    def sort_key(row: dict[str, Any]) -> tuple[float, float, float, int]:
        tag = str(row.get("tag") or "")
        tag_number = 0
        if tag.startswith("variant_"):
            try:
                tag_number = int(tag.split("_", 1)[1])
            except ValueError:
                tag_number = 9999
        quality = row["quality"]
        return (
            _number(quality.get("final_score")),
            _number(quality.get("coverage_pct")),
            _number(quality.get("pipeline_value")),
            -tag_number,
        )

    ordered = sorted(results, key=sort_key, reverse=True)
    for index, row in enumerate(ordered):
        row["status"] = "keep" if index == 0 else "discard"
    return ordered


def build_campaign_segmentation_recommendation(
    snapshot: dict[str, Any],
    run_count: int = 24,
    target_score: float | None = None,
    max_runs: int | None = None,
) -> dict[str, Any]:
    results = run_segmentation_experiments(
        snapshot,
        run_count=run_count,
        target_score=target_score,
        max_runs=max_runs,
    )
    best = results[0]
    baseline = next((row for row in results if row["tag"] == "baseline"), best)
    return {
        "segment_config": best["segment_config"],
        "segment_quality": best["quality"],
        "segment_research": {
            "source": "homepilot_campaign_segmentation_autoresearch",
            "experiment_family": "campaign_segmentation",
            "experiment_count": len(results),
            "best_tag": best["tag"],
            "baseline_score": baseline["quality"]["final_score"],
            "best_score": best["quality"]["final_score"],
            "outcome_proxy_only": True,
            "synthetic_demo_evidence": True,
            "non_mutating": True,
            "response_denominator": "contacted_count",
        },
        "best_segments": best["segments"],
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_results_tsv(path: Path, results: list[dict[str, Any]]) -> None:
    fields = [
        "rank",
        "tag",
        "strategy_name",
        "dimensions",
        "final_score",
        "segment_count",
        "coverage_pct",
        "avg_response_rate_pct",
        "avg_appointment_rate_pct",
        "denominator_clarity_score",
        "pipeline_value",
        "status",
        "description",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for rank, row in enumerate(results, start=1):
            quality = row["quality"]
            writer.writerow({
                "rank": rank,
                "tag": row["tag"],
                "strategy_name": row["segment_config"].get("strategy_name"),
                "dimensions": ",".join(row["segment_config"].get("dimensions", [])),
                "final_score": quality["final_score"],
                "segment_count": quality["segment_count"],
                "coverage_pct": quality["coverage_pct"],
                "avg_response_rate_pct": quality["avg_response_rate_pct"],
                "avg_appointment_rate_pct": quality["avg_appointment_rate_pct"],
                "denominator_clarity_score": quality["denominator_clarity_score"],
                "pipeline_value": quality["pipeline_value"],
                "status": row["status"],
                "description": row["description"],
            })


def render_report(pack: dict[str, Any]) -> str:
    best = pack["best"]
    quality = best["quality"]
    summary = pack["summary"]
    lines = [
        "# HomePilot Campaign Segmentation Autoresearch Report",
        "",
        f"Created: {pack['created_at']}",
        f"Status: {pack['status']}",
        f"Release: {pack['release_label']}",
        f"Experiment family: {pack['experiment_family']}",
        f"Best tag: {summary['best_tag']}",
        f"Best strategy: {summary['best_strategy']}",
        f"Final score: {summary['best_score']}",
        "",
        "## Best Quality",
        "",
        f"- Segment count: {quality['segment_count']}",
        f"- Coverage: {quality['coverage_pct']}%",
        f"- Avg response rate: {quality['avg_response_rate_pct']}% using contacted_count denominator",
        f"- Avg appointment rate: {quality['avg_appointment_rate_pct']}% using contacted_count denominator",
        f"- Denominator clarity score: {quality['denominator_clarity_score']}",
        f"- Pipeline value in selected segments: EUR {quality['pipeline_value']:,}".replace(",", " "),
        "",
        "## Guardrails",
        "",
        "- Tenant-scoped dashboard snapshot only.",
        "- Segment rates use contacted_count denominator and keep target_response_rate_pct separate.",
        "- Segment outputs omit raw addresses and contact values; property ids are review anchors only.",
        "- Public-context fields are campaign context, not homeowner intent.",
        "- No live database writes, Supabase writes, outreach state changes, or partner portal changes.",
        "- A winning segmentation is a reviewable plan, not automatic live campaign action.",
        "",
    ]
    return "\n".join(lines)


def _secret_scan(paths: list[Path]) -> list[str]:
    markers = (
        "service-role",
        "secret-token",
        "authorization: bearer",
        "supabase_service_role",
        "@example.",
        *RAW_ADDRESS_MARKERS,
    )
    findings = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        body = path.read_text(encoding="utf-8", errors="ignore").lower()
        for marker in markers:
            if marker in body:
                findings.append(f"{path.name}: contains {marker}")
    return findings


def build_campaign_segmentation_autoresearch_pack(
    out_dir: Path,
    snapshot: dict[str, Any] | None = None,
    release_label: str = "local",
    run_count: int = 24,
    baseline_only: bool = False,
    target_score: float | None = None,
    max_runs: int | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if snapshot is None:
        from homepilot_demo_room import build_demo_payload
        from homepilot_lead_autoresearch import build_lead_priority_recommendation
        from homepilot_partner_assignment_autoresearch import build_partner_assignment_recommendation
        from homepilot_snapshot import build_dashboard_snapshot

        payload = build_demo_payload(tenant_slug="daw-belgium-crepi-network", property_count=160, scenario="daw")
        snapshot = build_dashboard_snapshot(
            payload,
            tenant_name="DAW Belgium",
            tenant_slug="daw-belgium-crepi-network",
            enabled_modules=["facadepilot"],
        )
        snapshot["leadPrioritization"] = build_lead_priority_recommendation(snapshot, run_count=8, limit=30)
        snapshot["partnerAssignment"] = build_partner_assignment_recommendation(snapshot, run_count=8, limit=30)

    results = run_segmentation_experiments(
        snapshot,
        run_count=run_count,
        baseline_only=baseline_only,
        target_score=target_score,
        max_runs=max_runs,
    )
    best = results[0]
    baseline_score = next((row["quality"]["final_score"] for row in results if row["tag"] == "baseline"), None)
    paths = {
        "results": str(out_dir / "results.tsv"),
        "best_campaign_segments": str(out_dir / "best_campaign_segments.json"),
        "report": str(out_dir / "CAMPAIGN_SEGMENTATION_AUTORESEARCH_REPORT.md"),
        "pack": str(out_dir / "campaign_segmentation_autoresearch_pack.json"),
    }
    pack = {
        "pack_type": "homepilot_campaign_segmentation_autoresearch",
        "created_at": utc_now(),
        "status": "pass",
        "release_label": release_label,
        "experiment_family": "campaign_segmentation",
        "baseline_only": baseline_only,
        "experiment_count": len(results),
        "best": best,
        "summary": {
            "best_tag": best["tag"],
            "best_strategy": best["segment_config"].get("strategy_name"),
            "best_score": best["quality"]["final_score"],
            "baseline_score": baseline_score,
            "segment_count": best["quality"]["segment_count"],
            "coverage_pct": best["quality"]["coverage_pct"],
            "avg_response_rate_pct": best["quality"]["avg_response_rate_pct"],
            "denominator_clarity_score": best["quality"]["denominator_clarity_score"],
            "pipeline_value": best["quality"]["pipeline_value"],
        },
        "guardrails": {
            "tenant_scoped_snapshot_only": True,
            "module_scoped": True,
            "partner_scoped_for_producer_networks": True,
            "synthetic_demo_only": True,
            "outcome_proxy_only": True,
            "response_denominator_is_contacted_count": True,
            "target_response_rate_is_separate": True,
            "public_context_not_homeowner_intent": True,
            "opportunity_not_intent_without_response": True,
            "non_mutating_pack": True,
            "writes_live_data": False,
            "writes_supabase": False,
            "changes_outreach_state": False,
            "raw_addresses_in_best_segments": False,
            "raw_contact_values_written": False,
            "secret_values_written": False,
            "winning_segmentation_requires_review": True,
        },
        "paths": paths,
    }
    write_results_tsv(Path(paths["results"]), results)
    write_json(Path(paths["best_campaign_segments"]), {
        "segment_config": best["segment_config"],
        "segment_quality": best["quality"],
        "segment_research": {
            "source": "homepilot_campaign_segmentation_autoresearch",
            "best_tag": best["tag"],
            "experiment_family": "campaign_segmentation",
            "experiment_count": len(results),
            "baseline_score": baseline_score,
            "best_score": best["quality"]["final_score"],
            "outcome_proxy_only": True,
            "synthetic_demo_evidence": True,
            "non_mutating": True,
            "response_denominator": "contacted_count",
        },
        "best_segments": best["segments"],
    })
    Path(paths["report"]).write_text(render_report(pack), encoding="utf-8")
    write_json(Path(paths["pack"]), pack)
    findings = _secret_scan([Path(value) for value in paths.values()])
    pack["secret_scan"] = {"status": "pass" if not findings else "fail", "findings": findings}
    if findings:
        pack["status"] = "fail"
    write_json(Path(paths["pack"]), pack)
    return pack


def main() -> None:
    parser = argparse.ArgumentParser(description="Run HomePilot campaign-segmentation autoresearch")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--release-label", default="local")
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--run", type=int, default=24)
    parser.add_argument("--target-score", type=float)
    parser.add_argument("--max-runs", type=int)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8")) if args.snapshot else None
    pack = build_campaign_segmentation_autoresearch_pack(
        out_dir=args.out_dir,
        snapshot=snapshot,
        release_label=args.release_label,
        run_count=args.run,
        baseline_only=args.baseline,
        target_score=args.target_score,
        max_runs=args.max_runs,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": pack["status"],
        "best_tag": pack["summary"]["best_tag"],
        "best_strategy": pack["summary"]["best_strategy"],
        "best_score": pack["summary"]["best_score"],
        "baseline_score": pack["summary"]["baseline_score"],
        "results": pack["paths"]["results"],
        "best_campaign_segments": pack["paths"]["best_campaign_segments"],
        "report": pack["paths"]["report"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
