#!/usr/bin/env python3
"""
Run a safe HomePilot autoresearch loop for partner wave assignment.

This benchmarks deterministic partner-batch recipes against a tenant-scoped
producer-network dashboard snapshot. It does not reassign properties across
partners: each selected property remains with its existing assigned partner.
Outputs are review artifacts only, with no raw addresses, no contact data, no
Supabase writes, and no live outreach state changes.
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

DEFAULT_ASSIGNMENT_CONFIG: dict[str, Any] = {
    "strategy_name": "current_partner_priority_baseline",
    "quota_mode": "global_priority",
    "batch_size": 50,
    "max_partner_share": 1.0,
    "capacity_fraction": 0.35,
    "value_cap_eur": 60000,
    "facade_m2_cap": 320,
    "no_response_penalty": 0.08,
    "review_gap_penalty": 0.04,
    "seed_partner_coverage": False,
    "weights": {
        "lead_priority": 0.55,
        "module_score": 0.18,
        "estimated_value": 0.08,
        "facade_m2": 0.05,
        "status_signal": 0.08,
        "partner_capacity": 0.03,
        "partner_response": 0.03,
    },
}

VARIANT_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "strategy_name": "balanced_network_wave",
        "quota_mode": "even",
        "max_partner_share": 0.16,
        "seed_partner_coverage": True,
        "weights": {
            "lead_priority": 0.45,
            "module_score": 0.18,
            "estimated_value": 0.08,
            "facade_m2": 0.05,
            "status_signal": 0.08,
            "partner_capacity": 0.10,
            "partner_response": 0.06,
        },
    },
    {
        "strategy_name": "capacity_weighted_wave",
        "quota_mode": "capacity",
        "max_partner_share": 0.18,
        "seed_partner_coverage": True,
        "weights": {
            "lead_priority": 0.42,
            "module_score": 0.16,
            "estimated_value": 0.08,
            "facade_m2": 0.04,
            "status_signal": 0.08,
            "partner_capacity": 0.16,
            "partner_response": 0.06,
        },
    },
    {
        "strategy_name": "response_lift_partner_wave",
        "quota_mode": "response_weighted",
        "max_partner_share": 0.18,
        "seed_partner_coverage": True,
        "weights": {
            "lead_priority": 0.36,
            "module_score": 0.14,
            "estimated_value": 0.07,
            "facade_m2": 0.04,
            "status_signal": 0.18,
            "partner_capacity": 0.08,
            "partner_response": 0.13,
        },
    },
    {
        "strategy_name": "pipeline_value_partner_wave",
        "quota_mode": "pipeline_weighted",
        "max_partner_share": 0.20,
        "seed_partner_coverage": True,
        "weights": {
            "lead_priority": 0.36,
            "module_score": 0.14,
            "estimated_value": 0.22,
            "facade_m2": 0.10,
            "status_signal": 0.06,
            "partner_capacity": 0.08,
            "partner_response": 0.04,
        },
    },
    {
        "strategy_name": "first_wave_actionable_partner_wave",
        "quota_mode": "capacity",
        "max_partner_share": 0.15,
        "seed_partner_coverage": True,
        "weights": {
            "lead_priority": 0.40,
            "module_score": 0.16,
            "estimated_value": 0.10,
            "facade_m2": 0.05,
            "status_signal": 0.16,
            "partner_capacity": 0.09,
            "partner_response": 0.04,
        },
    },
    {
        "strategy_name": "premium_partner_headroom_wave",
        "quota_mode": "tier_capacity",
        "max_partner_share": 0.19,
        "seed_partner_coverage": True,
        "weights": {
            "lead_priority": 0.38,
            "module_score": 0.17,
            "estimated_value": 0.12,
            "facade_m2": 0.06,
            "status_signal": 0.07,
            "partner_capacity": 0.14,
            "partner_response": 0.06,
        },
    },
)

REASON_LABELS = {
    "lead_priority": "top autoresearched priority queue",
    "module_score": "high module opportunity score",
    "estimated_value": "large estimated opportunity value",
    "facade_m2": "large facade surface",
    "status_signal": "campaign response proxy",
    "partner_capacity": "partner capacity headroom",
    "partner_response": "partner response history",
}

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
    config = deepcopy(DEFAULT_ASSIGNMENT_CONFIG)
    if not overrides:
        return config
    for key, value in overrides.items():
        if key == "weights" and isinstance(value, dict):
            config["weights"].update(value)
        elif key in config:
            config[key] = value
    return config


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


def _partner_territory(prop: dict[str, Any]) -> str:
    partner = prop.get("partner") if isinstance(prop.get("partner"), dict) else {}
    return str(partner.get("territory") or partner.get("region") or prop.get("territory") or "")


def _network(snapshot: dict[str, Any]) -> dict[str, Any]:
    return snapshot.get("network") if isinstance(snapshot.get("network"), dict) else {}


def _partner_stats(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    partners = _network(snapshot).get("partners") if isinstance(_network(snapshot).get("partners"), list) else []
    stats: dict[str, dict[str, Any]] = {}
    for partner in partners:
        if isinstance(partner, dict) and partner.get("id"):
            stats[str(partner["id"])] = partner
    return stats


def _lead_queue_index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lead = snapshot.get("leadPrioritization") if isinstance(snapshot.get("leadPrioritization"), dict) else {}
    queue = lead.get("best_queue") if isinstance(lead.get("best_queue"), list) else []
    index: dict[str, dict[str, Any]] = {}
    for row in queue:
        if isinstance(row, dict) and row.get("property_id"):
            index[str(row["property_id"])] = row
    return index


def _status_feature(status: str) -> float:
    return _number(OUTCOME_PROXY.get(status), 0.12)


def _tier_multiplier(partner: dict[str, Any]) -> float:
    tier = str(partner.get("tier") or "").lower()
    if tier == "platinum":
        return 1.16
    if tier == "gold":
        return 1.08
    if tier == "silver":
        return 1.0
    return 0.95


def _partner_capacity_feature(partner: dict[str, Any]) -> float:
    capacity = _number(partner.get("capacity"), 0.0)
    assigned = max(1.0, _number(partner.get("properties"), 1.0))
    return _clamp((capacity / assigned) / 1.15)


def _partner_response_feature(partner: dict[str, Any]) -> float:
    return _clamp(_number(partner.get("response_rate_pct"), 0.0) / 45.0)


def _candidate_features(
    prop: dict[str, Any],
    config: dict[str, Any],
    partner_stats: dict[str, dict[str, Any]],
    queue_index: dict[str, dict[str, Any]],
) -> dict[str, float | str | int | bool]:
    property_id = str(prop.get("id") or "")
    module_key, assessment = _best_assessment(prop)
    partner_id = _partner_id(prop)
    partner = partner_stats.get(partner_id, {})
    queue_row = queue_index.get(property_id, {})
    lead_priority = _number(queue_row.get("priority_score"), _number(assessment.get("score")))
    status = str(prop.get("status") or "queued")
    confidence = _number(assessment.get("confidence"), 0.0)
    evidence = assessment.get("evidence") if isinstance(assessment.get("evidence"), list) else []
    return {
        "property_id": property_id,
        "module_key": module_key,
        "lead_priority": _clamp(lead_priority / 100),
        "module_score": _clamp(_number(assessment.get("score")) / 100),
        "estimated_value": _clamp(_number(prop.get("estimatedValue")) / max(1.0, _number(config.get("value_cap_eur"), 60000))),
        "facade_m2": _clamp(_number(prop.get("estimatedFacadeM2")) / max(1.0, _number(config.get("facade_m2_cap"), 320))),
        "status_signal": _status_feature(status),
        "partner_capacity": _partner_capacity_feature(partner),
        "partner_response": _partner_response_feature(partner),
        "confidence": _clamp(confidence),
        "has_evidence": bool(evidence),
    }


def _assignment_score(features: dict[str, float | str | int | bool], config: dict[str, Any], status: str) -> float:
    weights = config.get("weights") if isinstance(config.get("weights"), dict) else {}
    total_weight = sum(max(0.0, _number(weight)) for weight in weights.values())
    if total_weight <= 0:
        return 0.0
    weighted = 0.0
    for key, weight in weights.items():
        weighted += _number(weight) * _number(features.get(key))
    score = weighted / total_weight
    if status == "no_response":
        score -= _number(config.get("no_response_penalty"), 0.08)
    if _number(features.get("confidence")) < 0.70 or not features.get("has_evidence"):
        score -= _number(config.get("review_gap_penalty"), 0.04)
    return round(_clamp(score) * 100, 3)


def _reason_codes(features: dict[str, float | str | int | bool], config: dict[str, Any]) -> list[str]:
    weights = config.get("weights") if isinstance(config.get("weights"), dict) else {}
    ranked = sorted(
        [
            (key, _number(weight) * _number(features.get(key)))
            for key, weight in weights.items()
            if _number(weight) > 0
        ],
        key=lambda item: item[1],
        reverse=True,
    )
    return [REASON_LABELS.get(key, key) for key, contribution in ranked[:3] if contribution > 0]


def build_assignment_candidates(snapshot: dict[str, Any], assignment_config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    config = _merged_config(assignment_config)
    partner_stats = _partner_stats(snapshot)
    queue_index = _lead_queue_index(snapshot)
    properties = snapshot.get("properties") if isinstance(snapshot.get("properties"), list) else []
    rows: list[dict[str, Any]] = []
    for prop in properties:
        module_key, assessment = _best_assessment(prop)
        if not module_key:
            continue
        partner_id = _partner_id(prop)
        if not partner_id:
            continue
        partner = partner_stats.get(partner_id, {})
        status = str(prop.get("status") or "queued")
        features = _candidate_features(prop, config, partner_stats, queue_index)
        assignment_score = _assignment_score(features, config, status)
        territory = str(prop.get("territory") or "")
        partner_territory = str(partner.get("region") or partner.get("territory") or _partner_territory(prop))
        rows.append({
            "property_id": str(prop.get("id") or ""),
            "city": str(prop.get("city") or ""),
            "territory": territory,
            "partner_id": partner_id,
            "partner_name": _partner_name(prop) or str(partner.get("name") or partner_id),
            "partner_region": partner_territory,
            "module_key": module_key,
            "module_score": int(round(_number(assessment.get("score")))),
            "grade": str(assessment.get("grade") or ""),
            "confidence": round(_number(assessment.get("confidence")), 3),
            "status": status,
            "estimated_value": int(round(_number(prop.get("estimatedValue")))),
            "estimated_facade_m2": int(round(_number(prop.get("estimatedFacadeM2")))),
            "assignment_score": assignment_score,
            "priority_score": round(_number(features.get("lead_priority")) * 100, 3),
            "assignment_reasons": _reason_codes(features, config),
            "territory_fit": not territory or not partner_territory or territory == partner_territory,
            "selected_partner_id": partner_id,
            "scope_safe_existing_assignment": True,
            "opportunity_not_intent_without_response": status not in ENGAGED_STATUSES,
            "synthetic_response_proxy": True,
        })
    rows.sort(
        key=lambda row: (
            _number(row.get("assignment_score")),
            _number(row.get("priority_score")),
            _number(row.get("module_score")),
            _number(row.get("estimated_value")),
            str(row.get("property_id") or ""),
        ),
        reverse=True,
    )
    return rows


def _quota_weights(partners: dict[str, dict[str, Any]], config: dict[str, Any]) -> dict[str, float]:
    mode = str(config.get("quota_mode") or "global_priority")
    weights: dict[str, float] = {}
    for partner_id, partner in partners.items():
        capacity = max(1.0, _number(partner.get("capacity"), 1.0))
        response = max(1.0, _number(partner.get("response_rate_pct"), 1.0))
        pipeline = max(1.0, _number(partner.get("pipeline_value"), 1.0))
        if mode == "even":
            weight = 1.0
        elif mode == "capacity":
            weight = capacity
        elif mode == "response_weighted":
            weight = capacity * (0.65 + response / 100)
        elif mode == "pipeline_weighted":
            weight = math.sqrt(pipeline) * (0.75 + response / 150)
        elif mode == "tier_capacity":
            weight = capacity * _tier_multiplier(partner)
        else:
            weight = capacity
        weights[partner_id] = max(0.001, weight)
    return weights


def _target_counts(partners: dict[str, dict[str, Any]], config: dict[str, Any], batch_size: int) -> dict[str, int]:
    if not partners or batch_size <= 0:
        return {}
    weights = _quota_weights(partners, config)
    total = sum(weights.values()) or 1.0
    raw = {partner_id: batch_size * weight / total for partner_id, weight in weights.items()}
    counts = {partner_id: int(math.floor(value)) for partner_id, value in raw.items()}
    remainder = batch_size - sum(counts.values())
    ordered = sorted(raw.items(), key=lambda item: (item[1] - math.floor(item[1]), item[0]), reverse=True)
    for partner_id, _value in ordered[:max(0, remainder)]:
        counts[partner_id] += 1
    return counts


def _partner_capacity_cap(partner: dict[str, Any], config: dict[str, Any], fallback: int) -> int:
    capacity = max(1.0, _number(partner.get("capacity"), fallback))
    fraction = max(0.01, _number(config.get("capacity_fraction"), 0.35))
    return max(1, int(math.ceil(capacity * fraction)))


def select_partner_wave(snapshot: dict[str, Any], assignment_config: dict[str, Any] | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    config = _merged_config(assignment_config)
    batch_size = int(limit or _number(config.get("batch_size"), 50))
    batch_size = max(1, batch_size)
    candidates = build_assignment_candidates(snapshot, config)
    partners = _partner_stats(snapshot)
    if not candidates:
        return []
    by_partner: dict[str, list[dict[str, Any]]] = {}
    for row in candidates:
        by_partner.setdefault(str(row.get("partner_id") or ""), []).append(row)

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    counts: dict[str, int] = {}
    max_share = _number(config.get("max_partner_share"), 1.0)
    max_per_partner = max(1, int(math.ceil(batch_size * max_share)))
    capacity_caps = {
        partner_id: _partner_capacity_cap(partner, config, fallback=max_per_partner)
        for partner_id, partner in partners.items()
    }

    def can_take(row: dict[str, Any]) -> bool:
        property_id = str(row.get("property_id") or "")
        partner_id = str(row.get("partner_id") or "")
        if not property_id or property_id in selected_ids:
            return False
        partner_limit = min(max_per_partner, capacity_caps.get(partner_id, max_per_partner))
        return counts.get(partner_id, 0) < partner_limit

    def take(row: dict[str, Any]) -> bool:
        if len(selected) >= batch_size or not can_take(row):
            return False
        selected_ids.add(str(row["property_id"]))
        partner_id = str(row.get("partner_id") or "")
        counts[partner_id] = counts.get(partner_id, 0) + 1
        selected.append(row)
        return True

    quota_mode = str(config.get("quota_mode") or "global_priority")
    if config.get("seed_partner_coverage") and len(selected) < batch_size:
        for partner_id in sorted(by_partner):
            rows = by_partner[partner_id]
            if rows:
                take(rows[0])

    if quota_mode != "global_priority" and len(selected) < batch_size:
        targets = _target_counts(partners, config, batch_size)
        for partner_id, target in sorted(targets.items(), key=lambda item: (item[1], item[0]), reverse=True):
            for row in by_partner.get(partner_id, []):
                if counts.get(partner_id, 0) >= target or len(selected) >= batch_size:
                    break
                take(row)

    for row in candidates:
        if len(selected) >= batch_size:
            break
        take(row)

    for rank, row in enumerate(selected, start=1):
        row["assignment_rank"] = rank
    return selected


def _count_by(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get(field) or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _partner_balance_score(rows: list[dict[str, Any]], partner_count: int, max_partner_share: float) -> tuple[float, float, float]:
    if not rows:
        return 100.0, 0.0, 0.0
    counts = _count_by(rows, "partner_id")
    n = len(rows)
    expected_partners = max(1, min(partner_count or len(counts), n))
    coverage = _pct(len(counts), expected_partners)
    max_share = max(counts.values()) / n
    even_target = n / expected_partners
    deviation = sum(abs(count - even_target) / even_target for count in counts.values()) / expected_partners
    distribution = max(0.0, 100.0 - deviation * 70.0)
    concentration = max(0.0, 100.0 - max(0.0, max_share - max_partner_share) * 260.0)
    return round(coverage * 0.35 + distribution * 0.35 + concentration * 0.30, 2), round(coverage, 1), round(max_share * 100, 1)


def _capacity_fit_score(
    rows: list[dict[str, Any]],
    partners: dict[str, dict[str, Any]],
    config: dict[str, Any],
    batch_size: int,
) -> tuple[float, int]:
    if not rows or not partners:
        return 100.0, 0
    counts = _count_by(rows, "partner_id")
    targets = _target_counts(partners, config, batch_size)
    ratios = []
    over_capacity_count = 0
    for partner_id, partner in partners.items():
        count = counts.get(partner_id, 0)
        target = max(1, targets.get(partner_id, 1))
        cap = _partner_capacity_cap(partner, config, fallback=target)
        if count > cap:
            over_capacity_count += 1
        ratios.append(abs(count - target) / target)
    avg_deviation = sum(ratios) / len(ratios) if ratios else 0.0
    return round(max(0.0, 100.0 - avg_deviation * 52.0 - over_capacity_count * 7.0), 2), over_capacity_count


def summarize_partner_assignment(rows: list[dict[str, Any]], snapshot: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    partners = _partner_stats(snapshot)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("partner_id") or ""), []).append(row)
    summary = []
    for partner_id, partner_rows in sorted(grouped.items()):
        partner = partners.get(partner_id, {})
        n = len(partner_rows)
        status_mix = _count_by(partner_rows, "status")
        reason_counts: dict[str, int] = {}
        for row in partner_rows:
            for reason in row.get("assignment_reasons", []):
                reason_counts[str(reason)] = reason_counts.get(str(reason), 0) + 1
        top_reasons = [reason for reason, _count in sorted(reason_counts.items(), key=lambda item: (item[1], item[0]), reverse=True)[:3]]
        capacity = int(round(_number(partner.get("capacity"), n)))
        summary.append({
            "partner_id": partner_id,
            "partner_name": str(partner.get("name") or partner_rows[0].get("partner_name") or partner_id),
            "territory": str(partner.get("region") or partner_rows[0].get("partner_region") or ""),
            "recommended_wave": "first_review_wave",
            "selected_count": n,
            "selected_property_ids": [str(row.get("property_id") or "") for row in partner_rows],
            "avg_assignment_score": round(sum(_number(row.get("assignment_score")) for row in partner_rows) / n, 2) if n else 0.0,
            "avg_priority_score": round(sum(_number(row.get("priority_score")) for row in partner_rows) / n, 2) if n else 0.0,
            "avg_module_score": round(sum(_number(row.get("module_score")) for row in partner_rows) / n, 2) if n else 0.0,
            "pipeline_value": int(round(sum(_number(row.get("estimated_value")) for row in partner_rows))),
            "facade_m2": int(round(sum(_number(row.get("estimated_facade_m2")) for row in partner_rows))),
            "response_proxy_score": round(_pct(sum(OUTCOME_PROXY.get(str(row.get("status") or ""), 0.12) for row in partner_rows), n), 2) if n else 0.0,
            "capacity": capacity,
            "capacity_used_pct": _pct(n, capacity),
            "status_mix": status_mix,
            "top_assignment_reasons": top_reasons,
            "scope": "assigned_records_only",
        })
    return summary


def evaluate_assignment_quality(
    snapshot: dict[str, Any],
    assignment_config: dict[str, Any] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    config = _merged_config(assignment_config)
    config["batch_size"] = limit
    started = time.perf_counter()
    selected = select_partner_wave(snapshot, config, limit=limit)
    runtime_ms = (time.perf_counter() - started) * 1000
    n = len(selected)
    partners = _partner_stats(snapshot)
    partner_count = len(partners)
    partner_balance, partner_coverage, max_partner_share = _partner_balance_score(
        selected,
        partner_count=partner_count,
        max_partner_share=_number(config.get("max_partner_share"), 1.0),
    )
    capacity_fit, over_capacity_count = _capacity_fit_score(selected, partners, config, max(1, limit))
    avg_assignment = sum(_number(row.get("assignment_score")) for row in selected) / n if n else 0.0
    avg_priority = sum(_number(row.get("priority_score")) for row in selected) / n if n else 0.0
    avg_module = sum(_number(row.get("module_score")) for row in selected) / n if n else 0.0
    avg_value = sum(_number(row.get("estimated_value")) for row in selected) / n if n else 0.0
    pipeline_value = int(round(sum(_number(row.get("estimated_value")) for row in selected)))
    facade_m2 = int(round(sum(_number(row.get("estimated_facade_m2")) for row in selected)))
    response_proxy = _pct(sum(OUTCOME_PROXY.get(str(row.get("status") or ""), 0.12) for row in selected), n) if n else 0.0
    engaged = sum(1 for row in selected if row.get("status") in ENGAGED_STATUSES)
    appointments = sum(1 for row in selected if row.get("status") in CONVERSION_STATUSES)
    actionable = sum(1 for row in selected if row.get("status") in ACTIONABLE_STATUSES)
    no_response = sum(1 for row in selected if row.get("status") == "no_response")
    territory_fit_count = sum(1 for row in selected if row.get("territory_fit"))
    territory_fit = _pct(territory_fit_count, n)
    leakage_count = sum(1 for row in selected if row.get("partner_id") != row.get("selected_partner_id"))
    scope_safety = 100.0 if leakage_count == 0 else 0.0
    value_score = min(100.0, _pct(avg_value, max(1.0, _number(config.get("value_cap_eur"), 60000))))
    actionability_score = max(0.0, _pct(actionable, n) - _pct(no_response, n) * 0.35)
    final_score = (
        avg_assignment * 0.26
        + partner_balance * 0.21
        + capacity_fit * 0.15
        + response_proxy * 0.13
        + territory_fit * 0.10
        + value_score * 0.06
        + actionability_score * 0.04
        + scope_safety * 0.05
    )
    return {
        "final_score": round(final_score, 3),
        "batch_size": n,
        "avg_assignment_score": round(avg_assignment, 2),
        "avg_priority_score": round(avg_priority, 2),
        "avg_module_score": round(avg_module, 2),
        "pipeline_value": pipeline_value,
        "facade_m2": facade_m2,
        "engaged_rate_pct": _pct(engaged, n),
        "appointment_rate_pct": _pct(appointments, n),
        "response_proxy_score": round(response_proxy, 2),
        "partner_balance_score": partner_balance,
        "partner_coverage_pct": partner_coverage,
        "max_partner_share_pct": max_partner_share,
        "capacity_fit_score": capacity_fit,
        "over_capacity_count": over_capacity_count,
        "territory_fit_score": territory_fit,
        "scope_leakage_count": leakage_count,
        "actionability_score": round(actionability_score, 2),
        "no_response_share_pct": _pct(no_response, n),
        "runtime_ms": round(runtime_ms, 2),
        "synthetic_demo_metric": True,
        "outcome_proxy_only": True,
        "existing_partner_assignments_only": True,
    }


def _variant_config(index: int) -> dict[str, Any]:
    template = deepcopy(VARIANT_TEMPLATES[index % len(VARIANT_TEMPLATES)])
    phase = index // len(VARIANT_TEMPLATES)
    config = _merged_config(template)
    config["strategy_name"] = f"{template['strategy_name']}_v{phase + 1}"
    config["value_cap_eur"] = [50000, 60000, 72000][phase % 3]
    config["facade_m2_cap"] = [260, 320, 380][(phase // 3) % 3]
    base_share = _number(template.get("max_partner_share"), 0.18)
    config["max_partner_share"] = round(max(0.12, min(0.24, base_share + [-0.02, 0.0, 0.02][(phase // 4) % 3])), 3)
    config["capacity_fraction"] = [0.18, 0.25, 0.35][(phase // 5) % 3]
    config["no_response_penalty"] = [0.04, 0.08, 0.12][(phase // 7) % 3]
    return config


def run_partner_assignment_experiments(
    snapshot: dict[str, Any],
    run_count: int = 24,
    baseline_only: bool = False,
    limit: int = 50,
    target_score: float | None = None,
    max_runs: int | None = None,
) -> list[dict[str, Any]]:
    baseline = _merged_config({"batch_size": limit})
    experiments = [{
        "tag": "baseline",
        "assignment_config": baseline,
        "description": "current assigned-partner priority ordering",
    }]
    best_score = -1.0
    if not baseline_only:
        total_variants = max(0, max_runs if target_score is not None and max_runs is not None else run_count)
        for index in range(total_variants):
            config = _variant_config(index)
            config["batch_size"] = limit
            row = {
                "tag": f"variant_{index + 1:02d}",
                "assignment_config": config,
                "description": "deterministic partner wave assignment recipe",
            }
            experiments.append(row)
            quality = evaluate_assignment_quality(snapshot, config, limit=limit)
            best_score = max(best_score, quality["final_score"])
            row["quality"] = quality
            row["assignment"] = summarize_partner_assignment(
                select_partner_wave(snapshot, config, limit=limit),
                snapshot,
                config,
            )
            if target_score is not None and best_score >= target_score:
                break

    results = []
    for experiment in experiments:
        if "quality" not in experiment:
            experiment["quality"] = evaluate_assignment_quality(
                snapshot,
                experiment["assignment_config"],
                limit=limit,
            )
            experiment["assignment"] = summarize_partner_assignment(
                select_partner_wave(snapshot, experiment["assignment_config"], limit=limit),
                snapshot,
                experiment["assignment_config"],
            )
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
            _number(quality.get("partner_balance_score")),
            -_number(quality.get("runtime_ms")),
            -tag_number,
        )

    ordered = sorted(results, key=sort_key, reverse=True)
    for index, row in enumerate(ordered):
        row["status"] = "keep" if index == 0 else "discard"
    return ordered


def build_partner_assignment_recommendation(
    snapshot: dict[str, Any],
    run_count: int = 24,
    limit: int = 50,
    target_score: float | None = None,
    max_runs: int | None = None,
) -> dict[str, Any]:
    results = run_partner_assignment_experiments(
        snapshot,
        run_count=run_count,
        limit=limit,
        target_score=target_score,
        max_runs=max_runs,
    )
    best = results[0]
    baseline = next((row for row in results if row["tag"] == "baseline"), best)
    return {
        "assignment_config": best["assignment_config"],
        "assignment_quality": best["quality"],
        "assignment_research": {
            "source": "homepilot_partner_assignment_autoresearch",
            "experiment_family": "partner_assignment",
            "experiment_count": len(results),
            "best_tag": best["tag"],
            "baseline_score": baseline["quality"]["final_score"],
            "best_score": best["quality"]["final_score"],
            "outcome_proxy_only": True,
            "synthetic_demo_evidence": True,
            "non_mutating": True,
            "existing_partner_assignments_only": True,
        },
        "best_assignment": best["assignment"],
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_results_tsv(path: Path, results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "rank",
        "tag",
        "strategy_name",
        "final_score",
        "partner_balance_score",
        "partner_coverage_pct",
        "capacity_fit_score",
        "territory_fit_score",
        "scope_leakage_count",
        "pipeline_value",
        "batch_size",
        "status",
        "description",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for rank, row in enumerate(results, start=1):
            quality = row["quality"]
            writer.writerow({
                "rank": rank,
                "tag": row["tag"],
                "strategy_name": row["assignment_config"].get("strategy_name"),
                "final_score": quality["final_score"],
                "partner_balance_score": quality["partner_balance_score"],
                "partner_coverage_pct": quality["partner_coverage_pct"],
                "capacity_fit_score": quality["capacity_fit_score"],
                "territory_fit_score": quality["territory_fit_score"],
                "scope_leakage_count": quality["scope_leakage_count"],
                "pipeline_value": quality["pipeline_value"],
                "batch_size": quality["batch_size"],
                "status": row["status"],
                "description": row["description"],
            })


def render_report(pack: dict[str, Any]) -> str:
    best = pack["best"]
    quality = best["quality"]
    summary = pack["summary"]
    lines = [
        "# HomePilot Partner Assignment Autoresearch Report",
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
        f"- Partner balance score: {quality['partner_balance_score']}",
        f"- Partner coverage: {quality['partner_coverage_pct']}%",
        f"- Capacity fit score: {quality['capacity_fit_score']}",
        f"- Territory fit score: {quality['territory_fit_score']}",
        f"- Scope leakage count: {quality['scope_leakage_count']}",
        f"- Pipeline value in first wave: EUR {quality['pipeline_value']:,}".replace(",", " "),
        f"- Batch size: {quality['batch_size']}",
        "",
        "## Guardrails",
        "",
        "- Tenant-scoped dashboard snapshot only.",
        "- Existing partner assignments only; no cross-partner reassignment in V1.",
        "- Best assignment omits raw addresses and contact values; use source snapshot under tenant scope for operational review.",
        "- No live database writes, Supabase writes, outreach state changes, or partner portal changes.",
        "- Synthetic/demo response status is an outcome proxy, not proof of homeowner intent.",
        "- A winning assignment is a reviewable wave plan, not automatic live campaign action.",
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


def build_partner_assignment_autoresearch_pack(
    out_dir: Path,
    snapshot: dict[str, Any] | None = None,
    release_label: str = "local",
    run_count: int = 24,
    baseline_only: bool = False,
    limit: int = 50,
    target_score: float | None = None,
    max_runs: int | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if snapshot is None:
        from homepilot_demo_room import build_demo_payload
        from homepilot_lead_autoresearch import build_lead_priority_recommendation
        from homepilot_snapshot import build_dashboard_snapshot

        payload = build_demo_payload(tenant_slug="daw-belgium-crepi-network", property_count=160, scenario="daw")
        snapshot = build_dashboard_snapshot(
            payload,
            tenant_name="DAW Belgium",
            tenant_slug="daw-belgium-crepi-network",
            enabled_modules=["facadepilot"],
        )
        snapshot["leadPrioritization"] = build_lead_priority_recommendation(snapshot, run_count=8, limit=limit)

    results = run_partner_assignment_experiments(
        snapshot,
        run_count=run_count,
        baseline_only=baseline_only,
        limit=limit,
        target_score=target_score,
        max_runs=max_runs,
    )
    best = results[0]
    paths = {
        "results": str(out_dir / "results.tsv"),
        "best_partner_assignment": str(out_dir / "best_partner_assignment.json"),
        "report": str(out_dir / "PARTNER_ASSIGNMENT_AUTORESEARCH_REPORT.md"),
        "pack": str(out_dir / "partner_assignment_autoresearch_pack.json"),
    }
    baseline_score = next((row["quality"]["final_score"] for row in results if row["tag"] == "baseline"), None)
    pack = {
        "pack_type": "homepilot_partner_assignment_autoresearch",
        "created_at": utc_now(),
        "status": "pass",
        "release_label": release_label,
        "experiment_family": "partner_assignment",
        "baseline_only": baseline_only,
        "experiment_count": len(results),
        "best": best,
        "summary": {
            "best_tag": best["tag"],
            "best_strategy": best["assignment_config"].get("strategy_name"),
            "best_score": best["quality"]["final_score"],
            "baseline_score": baseline_score,
            "partner_balance_score": best["quality"]["partner_balance_score"],
            "partner_coverage_pct": best["quality"]["partner_coverage_pct"],
            "capacity_fit_score": best["quality"]["capacity_fit_score"],
            "territory_fit_score": best["quality"]["territory_fit_score"],
            "scope_leakage_count": best["quality"]["scope_leakage_count"],
            "pipeline_value": best["quality"]["pipeline_value"],
            "batch_size": best["quality"]["batch_size"],
            "partner_batches": len(best["assignment"]),
        },
        "guardrails": {
            "tenant_scoped_snapshot_only": True,
            "module_scoped": True,
            "partner_scoped": True,
            "existing_partner_assignments_only": True,
            "no_cross_partner_raw_records": True,
            "synthetic_demo_only": True,
            "outcome_proxy_only": True,
            "opportunity_not_intent_without_response": True,
            "non_mutating_pack": True,
            "writes_live_data": False,
            "writes_supabase": False,
            "changes_outreach_state": False,
            "raw_addresses_in_best_assignment": False,
            "raw_contact_values_written": False,
            "secret_values_written": False,
            "winning_assignment_requires_review": True,
        },
        "paths": paths,
    }
    write_results_tsv(Path(paths["results"]), results)
    write_json(Path(paths["best_partner_assignment"]), {
        "assignment_config": best["assignment_config"],
        "assignment_quality": best["quality"],
        "assignment_research": {
            "source": "homepilot_partner_assignment_autoresearch",
            "best_tag": best["tag"],
            "experiment_family": "partner_assignment",
            "experiment_count": len(results),
            "baseline_score": baseline_score,
            "best_score": best["quality"]["final_score"],
            "outcome_proxy_only": True,
            "synthetic_demo_evidence": True,
            "non_mutating": True,
            "existing_partner_assignments_only": True,
        },
        "best_assignment": best["assignment"],
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
    parser = argparse.ArgumentParser(description="Run HomePilot partner-assignment autoresearch")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--release-label", default="local")
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--run", type=int, default=24)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--target-score", type=float)
    parser.add_argument("--max-runs", type=int)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8")) if args.snapshot else None
    pack = build_partner_assignment_autoresearch_pack(
        out_dir=args.out_dir,
        snapshot=snapshot,
        release_label=args.release_label,
        run_count=args.run,
        baseline_only=args.baseline,
        limit=args.limit,
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
        "best_partner_assignment": pack["paths"]["best_partner_assignment"],
        "report": pack["paths"]["report"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
