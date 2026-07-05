#!/usr/bin/env python3
"""
Run a safe HomePilot autoresearch loop for opportunity prioritization.

This benchmarks deterministic scoring recipes against a tenant-scoped dashboard
snapshot. It writes review artifacts only: no live data writes, no Supabase
changes, no outreach state changes, and no homeowner intent claims.
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

STATUS_FEATURES = {
    "response_proxy": OUTCOME_PROXY,
    "next_wave": {
        "clicked": 1.0,
        "responded": 0.86,
        "sent": 0.72,
        "scanned": 0.66,
        "queued": 0.58,
        "appointment": 0.48,
        "customer": 0.18,
        "no_response": 0.28,
    },
    "reactivation": {
        "clicked": 0.9,
        "responded": 0.72,
        "no_response": 0.62,
        "sent": 0.55,
        "scanned": 0.52,
        "queued": 0.42,
        "appointment": 0.38,
        "customer": 0.12,
    },
}

DEFAULT_PRIORITY_CONFIG: dict[str, Any] = {
    "model_name": "dashboard_score_only",
    "status_mode": "response_proxy",
    "top_n": 50,
    "value_cap_eur": 60000,
    "facade_m2_cap": 320,
    "max_partner_share": 0.30,
    "no_response_penalty": 0.08,
    "review_gap_penalty": 0.05,
    "weights": {
        "module_score": 1.0,
        "estimated_value": 0.0,
        "facade_m2": 0.0,
        "confidence": 0.0,
        "public_context": 0.0,
        "evidence": 0.0,
        "status_signal": 0.0,
        "partner_capacity": 0.0,
        "partner_response": 0.0,
    },
}

VARIANT_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "model_name": "balanced_opportunity_value",
        "status_mode": "response_proxy",
        "weights": {
            "module_score": 0.42,
            "estimated_value": 0.20,
            "facade_m2": 0.10,
            "confidence": 0.08,
            "public_context": 0.05,
            "evidence": 0.04,
            "status_signal": 0.08,
            "partner_capacity": 0.02,
            "partner_response": 0.01,
        },
    },
    {
        "model_name": "response_lift",
        "status_mode": "response_proxy",
        "weights": {
            "module_score": 0.32,
            "estimated_value": 0.12,
            "facade_m2": 0.06,
            "confidence": 0.08,
            "public_context": 0.04,
            "evidence": 0.04,
            "status_signal": 0.28,
            "partner_capacity": 0.02,
            "partner_response": 0.04,
        },
    },
    {
        "model_name": "pipeline_value",
        "status_mode": "response_proxy",
        "weights": {
            "module_score": 0.30,
            "estimated_value": 0.34,
            "facade_m2": 0.13,
            "confidence": 0.06,
            "public_context": 0.04,
            "evidence": 0.03,
            "status_signal": 0.06,
            "partner_capacity": 0.03,
            "partner_response": 0.01,
        },
    },
    {
        "model_name": "first_wave_action",
        "status_mode": "next_wave",
        "weights": {
            "module_score": 0.36,
            "estimated_value": 0.18,
            "facade_m2": 0.08,
            "confidence": 0.07,
            "public_context": 0.05,
            "evidence": 0.04,
            "status_signal": 0.16,
            "partner_capacity": 0.04,
            "partner_response": 0.02,
        },
    },
    {
        "model_name": "partner_capacity_balanced",
        "status_mode": "next_wave",
        "weights": {
            "module_score": 0.34,
            "estimated_value": 0.16,
            "facade_m2": 0.07,
            "confidence": 0.07,
            "public_context": 0.04,
            "evidence": 0.03,
            "status_signal": 0.12,
            "partner_capacity": 0.10,
            "partner_response": 0.07,
        },
    },
    {
        "model_name": "public_context_confident",
        "status_mode": "response_proxy",
        "weights": {
            "module_score": 0.34,
            "estimated_value": 0.15,
            "facade_m2": 0.07,
            "confidence": 0.12,
            "public_context": 0.15,
            "evidence": 0.07,
            "status_signal": 0.06,
            "partner_capacity": 0.03,
            "partner_response": 0.01,
        },
    },
    {
        "model_name": "retargeting_backlog",
        "status_mode": "reactivation",
        "weights": {
            "module_score": 0.38,
            "estimated_value": 0.18,
            "facade_m2": 0.08,
            "confidence": 0.08,
            "public_context": 0.05,
            "evidence": 0.04,
            "status_signal": 0.15,
            "partner_capacity": 0.03,
            "partner_response": 0.01,
        },
    },
)

REASON_LABELS = {
    "module_score": "high opportunity score",
    "estimated_value": "large estimated opportunity value",
    "facade_m2": "large facade surface",
    "confidence": "strong model confidence",
    "public_context": "public-context coverage",
    "evidence": "customer-visible evidence coverage",
    "status_signal": "campaign response proxy",
    "partner_capacity": "partner capacity fit",
    "partner_response": "partner response history",
}


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
    config = deepcopy(DEFAULT_PRIORITY_CONFIG)
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


def _partner_stats(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    network = snapshot.get("network") if isinstance(snapshot.get("network"), dict) else {}
    partners = network.get("partners") if isinstance(network.get("partners"), list) else []
    return {str(row.get("id") or ""): row for row in partners if isinstance(row, dict)}


def _status_feature(status: str, mode: str) -> float:
    table = STATUS_FEATURES.get(mode) or STATUS_FEATURES["response_proxy"]
    return _number(table.get(status), 0.12)


def _public_context_feature(prop: dict[str, Any]) -> float:
    context = prop.get("publicContext") if isinstance(prop.get("publicContext"), dict) else {}
    features = context.get("features") if isinstance(context.get("features"), list) else []
    confidence = _number(context.get("confidence"), 0.0)
    coverage = min(1.0, len(features) / 6)
    return _clamp(confidence * 0.55 + coverage * 0.45)


def _property_features(
    prop: dict[str, Any],
    config: dict[str, Any],
    partner_stats: dict[str, dict[str, Any]],
) -> dict[str, float | str | int]:
    module_key, assessment = _best_assessment(prop)
    evidence = assessment.get("evidence") if isinstance(assessment.get("evidence"), list) else []
    partner_id = _partner_id(prop)
    partner = partner_stats.get(partner_id, {})
    properties = max(1.0, _number(partner.get("properties"), 1))
    capacity = _number(partner.get("capacity"), properties)
    capacity_fit = _clamp((capacity / properties) / 1.25)
    response_fit = _clamp(_number(partner.get("response_rate_pct"), 0.0) / 45.0)
    status = str(prop.get("status") or "queued")
    return {
        "property_id": str(prop.get("id") or ""),
        "module_key": module_key,
        "module_score": _clamp(_number(assessment.get("score")) / 100),
        "estimated_value": _clamp(_number(prop.get("estimatedValue")) / max(1.0, _number(config.get("value_cap_eur"), 60000))),
        "facade_m2": _clamp(_number(prop.get("estimatedFacadeM2")) / max(1.0, _number(config.get("facade_m2_cap"), 320))),
        "confidence": _clamp(_number(assessment.get("confidence"), 0.0)),
        "public_context": _public_context_feature(prop),
        "evidence": _clamp(len(evidence) / 4),
        "status_signal": _status_feature(status, str(config.get("status_mode") or "response_proxy")),
        "partner_capacity": capacity_fit,
        "partner_response": response_fit,
    }


def _weighted_priority_score(features: dict[str, float | str | int], config: dict[str, Any], status: str) -> float:
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
    if _number(features.get("confidence")) < 0.70 or _number(features.get("evidence")) <= 0:
        score -= _number(config.get("review_gap_penalty"), 0.05)
    return round(_clamp(score) * 100, 3)


def _reason_codes(features: dict[str, float | str | int], config: dict[str, Any]) -> list[str]:
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


def score_property_priorities(
    snapshot: dict[str, Any],
    priority_config: dict[str, Any] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    config = _merged_config(priority_config)
    top_n = int(limit or _number(config.get("top_n"), 50))
    partner_stats = _partner_stats(snapshot)
    properties = snapshot.get("properties") if isinstance(snapshot.get("properties"), list) else []
    rows: list[dict[str, Any]] = []
    for prop in properties:
        module_key, assessment = _best_assessment(prop)
        if not module_key:
            continue
        status = str(prop.get("status") or "queued")
        features = _property_features(prop, config, partner_stats)
        priority_score = _weighted_priority_score(features, config, status)
        rows.append({
            "property_id": str(prop.get("id") or ""),
            "city": str(prop.get("city") or ""),
            "territory": str(prop.get("territory") or ""),
            "partner_id": _partner_id(prop),
            "partner_name": _partner_name(prop),
            "module_key": module_key,
            "module_score": int(round(_number(assessment.get("score")))),
            "grade": str(assessment.get("grade") or ""),
            "confidence": round(_number(assessment.get("confidence")), 3),
            "status": status,
            "estimated_value": int(round(_number(prop.get("estimatedValue")))),
            "estimated_facade_m2": int(round(_number(prop.get("estimatedFacadeM2")))),
            "priority_score": priority_score,
            "priority_reasons": _reason_codes(features, config),
            "opportunity_not_intent_without_response": status not in ENGAGED_STATUSES,
            "synthetic_response_proxy": True,
        })
    rows.sort(
        key=lambda row: (
            _number(row.get("priority_score")),
            _number(row.get("module_score")),
            _number(row.get("estimated_value")),
            str(row.get("property_id") or ""),
        ),
        reverse=True,
    )
    return [{"rank": index + 1, **row} for index, row in enumerate(rows[:top_n])]


def _partner_balance_score(queue: list[dict[str, Any]], total_partner_count: int, max_partner_share: float) -> tuple[float, float, float]:
    if not queue:
        return 100.0, 0.0, 0.0
    counts: dict[str, int] = {}
    for row in queue:
        partner_id = str(row.get("partner_id") or "tenant")
        counts[partner_id] = counts.get(partner_id, 0) + 1
    unique = len(counts)
    coverage = _pct(unique, max(1, min(total_partner_count or unique, len(queue))))
    max_share = max(counts.values()) / len(queue)
    concentration = max(0.0, 100.0 - max(0.0, max_share - max_partner_share) * 260.0)
    return round(coverage * 0.45 + concentration * 0.55, 2), round(coverage, 1), round(max_share * 100, 1)


def evaluate_priority_quality(
    snapshot: dict[str, Any],
    priority_config: dict[str, Any] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    config = _merged_config(priority_config)
    started = time.perf_counter()
    queue = score_property_priorities(snapshot, config, limit=limit)
    runtime_ms = (time.perf_counter() - started) * 1000
    n = len(queue)
    network = snapshot.get("network") if isinstance(snapshot.get("network"), dict) else {}
    partners = network.get("partners") if isinstance(network.get("partners"), list) else []

    engaged = sum(1 for row in queue if row.get("status") in ENGAGED_STATUSES)
    conversions = sum(1 for row in queue if row.get("status") in CONVERSION_STATUSES)
    actionable = sum(1 for row in queue if row.get("status") in ACTIONABLE_STATUSES)
    no_response = sum(1 for row in queue if row.get("status") == "no_response")
    public_covered = sum(1 for row in queue if row.get("priority_reasons") and "public-context coverage" in row["priority_reasons"])
    evidence_covered = sum(1 for row in queue if row.get("priority_reasons") and "customer-visible evidence coverage" in row["priority_reasons"])
    avg_score = sum(_number(row.get("module_score")) for row in queue) / n if n else 0.0
    avg_priority = sum(_number(row.get("priority_score")) for row in queue) / n if n else 0.0
    avg_value = sum(_number(row.get("estimated_value")) for row in queue) / n if n else 0.0
    avg_facade = sum(_number(row.get("estimated_facade_m2")) for row in queue) / n if n else 0.0
    avg_confidence = sum(_number(row.get("confidence")) for row in queue) / n if n else 0.0
    pipeline_value = int(round(sum(_number(row.get("estimated_value")) for row in queue)))
    partner_balance, partner_coverage, max_partner_share = _partner_balance_score(
        queue,
        total_partner_count=len(partners),
        max_partner_share=_number(config.get("max_partner_share"), 0.30),
    )

    response_proxy_score = sum(OUTCOME_PROXY.get(str(row.get("status") or ""), 0.12) for row in queue)
    response_proxy_score = _pct(response_proxy_score, n) if n else 0.0
    value_score = min(100.0, _pct(avg_value, max(1.0, _number(config.get("value_cap_eur"), 60000))))
    facade_score = min(100.0, _pct(avg_facade, max(1.0, _number(config.get("facade_m2_cap"), 320))))
    confidence_score = _clamp(avg_confidence) * 100
    evidence_score = confidence_score * 0.55 + _pct(public_covered, n) * 0.25 + _pct(evidence_covered, n) * 0.20
    actionability_score = max(0.0, _pct(actionable, n) - _pct(no_response, n) * 0.35)
    final_score = (
        response_proxy_score * 0.25
        + avg_score * 0.20
        + value_score * 0.16
        + facade_score * 0.08
        + partner_balance * 0.14
        + evidence_score * 0.10
        + actionability_score * 0.07
    )
    return {
        "final_score": round(final_score, 3),
        "top_n": n,
        "avg_priority_score": round(avg_priority, 2),
        "avg_module_score": round(avg_score, 2),
        "avg_estimated_value": int(round(avg_value)),
        "pipeline_value": pipeline_value,
        "avg_facade_m2": round(avg_facade, 1),
        "engaged_rate_pct": _pct(engaged, n),
        "appointment_rate_pct": _pct(conversions, n),
        "response_proxy_score": round(response_proxy_score, 2),
        "partner_balance_score": partner_balance,
        "partner_coverage_pct": partner_coverage,
        "max_partner_share_pct": max_partner_share,
        "public_context_reason_pct": _pct(public_covered, n),
        "evidence_reason_pct": _pct(evidence_covered, n),
        "actionability_score": round(actionability_score, 2),
        "no_response_share_pct": _pct(no_response, n),
        "runtime_ms": round(runtime_ms, 2),
        "synthetic_demo_metric": True,
        "outcome_proxy_only": True,
    }


def _variant_config(index: int) -> dict[str, Any]:
    template = deepcopy(VARIANT_TEMPLATES[index % len(VARIANT_TEMPLATES)])
    phase = index // len(VARIANT_TEMPLATES)
    config = _merged_config(template)
    config["model_name"] = f"{template['model_name']}_v{phase + 1}"
    config["value_cap_eur"] = [50000, 60000, 72000][phase % 3]
    config["facade_m2_cap"] = [260, 320, 380][(phase // 3) % 3]
    config["max_partner_share"] = [0.24, 0.30, 0.36][(phase // 5) % 3]
    config["no_response_penalty"] = [0.04, 0.08, 0.13][(phase // 7) % 3]
    return config


def run_lead_experiments(
    snapshot: dict[str, Any],
    run_count: int = 24,
    baseline_only: bool = False,
    limit: int = 50,
    target_score: float | None = None,
    max_runs: int | None = None,
) -> list[dict[str, Any]]:
    baseline = _merged_config({"top_n": limit})
    experiments = [{
        "tag": "baseline",
        "priority_config": baseline,
        "description": "current dashboard score-only ordering",
    }]
    best_score = -1.0
    if not baseline_only:
        total_variants = max(0, max_runs if target_score is not None and max_runs is not None else run_count)
        for index in range(total_variants):
            config = _variant_config(index)
            config["top_n"] = limit
            row = {
                "tag": f"variant_{index + 1:02d}",
                "priority_config": config,
                "description": "deterministic opportunity-prioritization recipe",
            }
            experiments.append(row)
            quality = evaluate_priority_quality(snapshot, config, limit=limit)
            best_score = max(best_score, quality["final_score"])
            row["quality"] = quality
            row["queue"] = score_property_priorities(snapshot, config, limit=limit)
            if target_score is not None and best_score >= target_score:
                break

    results = []
    for experiment in experiments:
        if "quality" not in experiment:
            experiment["quality"] = evaluate_priority_quality(
                snapshot,
                experiment["priority_config"],
                limit=limit,
            )
            experiment["queue"] = score_property_priorities(
                snapshot,
                experiment["priority_config"],
                limit=limit,
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
            _number(quality.get("pipeline_value")),
            -_number(quality.get("runtime_ms")),
            -tag_number,
        )

    ordered = sorted(results, key=sort_key, reverse=True)
    for index, row in enumerate(ordered):
        row["status"] = "keep" if index == 0 else "discard"
    return ordered


def build_lead_priority_recommendation(
    snapshot: dict[str, Any],
    run_count: int = 24,
    limit: int = 50,
    target_score: float | None = None,
    max_runs: int | None = None,
) -> dict[str, Any]:
    results = run_lead_experiments(
        snapshot,
        run_count=run_count,
        limit=limit,
        target_score=target_score,
        max_runs=max_runs,
    )
    best = results[0]
    baseline = next((row for row in results if row["tag"] == "baseline"), best)
    return {
        "priority_config": best["priority_config"],
        "priority_quality": best["quality"],
        "priority_research": {
            "source": "homepilot_lead_autoresearch",
            "experiment_family": "lead_prioritization",
            "experiment_count": len(results),
            "best_tag": best["tag"],
            "baseline_score": baseline["quality"]["final_score"],
            "best_score": best["quality"]["final_score"],
            "outcome_proxy_only": True,
            "synthetic_demo_evidence": True,
            "non_mutating": True,
        },
        "best_queue": best["queue"],
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_results_tsv(path: Path, results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "rank",
        "tag",
        "model_name",
        "final_score",
        "avg_module_score",
        "engaged_rate_pct",
        "appointment_rate_pct",
        "pipeline_value",
        "partner_balance_score",
        "max_partner_share_pct",
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
                "model_name": row["priority_config"].get("model_name"),
                "final_score": quality["final_score"],
                "avg_module_score": quality["avg_module_score"],
                "engaged_rate_pct": quality["engaged_rate_pct"],
                "appointment_rate_pct": quality["appointment_rate_pct"],
                "pipeline_value": quality["pipeline_value"],
                "partner_balance_score": quality["partner_balance_score"],
                "max_partner_share_pct": quality["max_partner_share_pct"],
                "status": row["status"],
                "description": row["description"],
            })


def render_report(pack: dict[str, Any]) -> str:
    best = pack["best"]
    quality = best["quality"]
    summary = pack["summary"]
    lines = [
        "# HomePilot Lead Autoresearch Report",
        "",
        f"Created: {pack['created_at']}",
        f"Status: {pack['status']}",
        f"Release: {pack['release_label']}",
        f"Experiment family: {pack['experiment_family']}",
        f"Best tag: {summary['best_tag']}",
        f"Best model: {best['priority_config'].get('model_name')}",
        f"Final score: {summary['best_score']}",
        "",
        "## Best Quality",
        "",
        f"- Avg module score: {quality['avg_module_score']}",
        f"- Engaged-rate proxy: {quality['engaged_rate_pct']}%",
        f"- Appointment-rate proxy: {quality['appointment_rate_pct']}%",
        f"- Pipeline value in top queue: EUR {quality['pipeline_value']:,}".replace(",", " "),
        f"- Partner balance score: {quality['partner_balance_score']}",
        f"- Max partner share: {quality['max_partner_share_pct']}%",
        f"- No-response share: {quality['no_response_share_pct']}%",
        "",
        "## Guardrails",
        "",
        "- Tenant-scoped dashboard snapshot only.",
        "- Synthetic/demo response status is an outcome proxy, not proof of homeowner intent.",
        "- No live database writes, Supabase writes, outreach state changes, or cross-tenant learning.",
        "- Best queue omits raw addresses and contact values; use source snapshot under tenant scope for operational review.",
        "- A winning model is a reviewable recommendation, not automatic live campaign action.",
        "",
    ]
    return "\n".join(lines)


def _secret_scan(paths: list[Path]) -> list[str]:
    markers = ("service-role", "secret-token", "authorization: bearer", "supabase_service_role", "@example.")
    findings = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        body = path.read_text(encoding="utf-8", errors="ignore").lower()
        for marker in markers:
            if marker in body:
                findings.append(f"{path.name}: contains {marker}")
    return findings


def build_lead_autoresearch_pack(
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
        from homepilot_snapshot import build_dashboard_snapshot

        payload = build_demo_payload(tenant_slug="daw-belgium-crepi-network", property_count=160, scenario="daw")
        snapshot = build_dashboard_snapshot(
            payload,
            tenant_name="DAW Belgium",
            tenant_slug="daw-belgium-crepi-network",
            enabled_modules=["facadepilot"],
        )

    results = run_lead_experiments(
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
        "best_lead_priority": str(out_dir / "best_lead_priority.json"),
        "report": str(out_dir / "LEAD_AUTORESEARCH_REPORT.md"),
        "pack": str(out_dir / "lead_autoresearch_pack.json"),
    }
    pack = {
        "pack_type": "homepilot_lead_autoresearch",
        "created_at": utc_now(),
        "status": "pass",
        "release_label": release_label,
        "experiment_family": "lead_prioritization",
        "baseline_only": baseline_only,
        "experiment_count": len(results),
        "best": best,
        "summary": {
            "best_tag": best["tag"],
            "best_model": best["priority_config"].get("model_name"),
            "best_score": best["quality"]["final_score"],
            "baseline_score": next((row["quality"]["final_score"] for row in results if row["tag"] == "baseline"), None),
            "engaged_rate_pct": best["quality"]["engaged_rate_pct"],
            "appointment_rate_pct": best["quality"]["appointment_rate_pct"],
            "pipeline_value": best["quality"]["pipeline_value"],
            "partner_balance_score": best["quality"]["partner_balance_score"],
            "top_n": best["quality"]["top_n"],
        },
        "guardrails": {
            "tenant_scoped_snapshot_only": True,
            "module_scoped": True,
            "synthetic_demo_only": True,
            "outcome_proxy_only": True,
            "opportunity_not_intent_without_response": True,
            "non_mutating_pack": True,
            "writes_live_data": False,
            "writes_supabase": False,
            "changes_outreach_state": False,
            "raw_addresses_in_best_queue": False,
            "raw_contact_values_written": False,
            "secret_values_written": False,
            "winning_model_requires_review": True,
        },
        "paths": paths,
    }
    write_results_tsv(Path(paths["results"]), results)
    write_json(Path(paths["best_lead_priority"]), {
        "priority_config": best["priority_config"],
        "priority_quality": best["quality"],
        "priority_research": {
            "source": "homepilot_lead_autoresearch",
            "best_tag": best["tag"],
            "experiment_count": len(results),
            "baseline_score": pack["summary"]["baseline_score"],
            "best_score": best["quality"]["final_score"],
            "outcome_proxy_only": True,
            "synthetic_demo_evidence": True,
            "non_mutating": True,
        },
        "best_queue": best["queue"],
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
    parser = argparse.ArgumentParser(description="Run HomePilot lead-prioritization autoresearch")
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
    pack = build_lead_autoresearch_pack(
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
        "best_model": pack["summary"]["best_model"],
        "best_score": pack["summary"]["best_score"],
        "baseline_score": pack["summary"]["baseline_score"],
        "results": pack["paths"]["results"],
        "best_lead_priority": pack["paths"]["best_lead_priority"],
        "report": pack["paths"]["report"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
