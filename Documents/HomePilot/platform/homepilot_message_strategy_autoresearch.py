#!/usr/bin/env python3
"""
Run a safe HomePilot autoresearch loop for campaign message strategy.

This benchmarks deterministic message recipes against tenant-scoped campaign
segments. Outputs are review artifacts only: no raw addresses, no contact data,
no live writes, no Supabase changes, no outreach state changes, and no homeowner
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


MESSAGE_ANGLES = (
    "energy_savings",
    "facade_refresh",
    "premium_finish",
    "subsidy_check",
    "maintenance_free",
    "local_partner_review",
)

DEFAULT_MESSAGE_CONFIG: dict[str, Any] = {
    "strategy_name": "segment_angle_baseline",
    "max_message_tests": 8,
    "angle_order": ["facade_refresh", "energy_savings", "maintenance_free"],
    "cta_mode": "review_call",
    "tone": "consultative",
    "proof_mode": "visual_and_public_context",
    "compliance_strictness": "high",
    "weights": {
        "segment_score": 0.22,
        "response_proxy": 0.18,
        "appointment_proxy": 0.08,
        "angle_fit": 0.17,
        "compliance": 0.20,
        "clarity": 0.08,
        "proof_strength": 0.07,
    },
}

VARIANT_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "strategy_name": "proof_first_facade_refresh",
        "angle_order": ["facade_refresh", "energy_savings", "maintenance_free", "local_partner_review"],
        "cta_mode": "visual_review",
        "tone": "consultative",
        "proof_mode": "visual_first",
        "weights": {
            "segment_score": 0.21,
            "response_proxy": 0.16,
            "appointment_proxy": 0.07,
            "angle_fit": 0.20,
            "compliance": 0.22,
            "clarity": 0.08,
            "proof_strength": 0.06,
        },
    },
    {
        "strategy_name": "subsidy_review_without_claims",
        "angle_order": ["subsidy_check", "energy_savings", "facade_refresh", "local_partner_review"],
        "cta_mode": "eligibility_review",
        "tone": "careful",
        "proof_mode": "public_context_review",
        "weights": {
            "segment_score": 0.18,
            "response_proxy": 0.16,
            "appointment_proxy": 0.07,
            "angle_fit": 0.16,
            "compliance": 0.28,
            "clarity": 0.08,
            "proof_strength": 0.07,
        },
    },
    {
        "strategy_name": "premium_finish_reference",
        "angle_order": ["premium_finish", "facade_refresh", "local_partner_review", "maintenance_free"],
        "cta_mode": "reference_review",
        "tone": "premium",
        "proof_mode": "finish_and_partner",
        "weights": {
            "segment_score": 0.20,
            "response_proxy": 0.15,
            "appointment_proxy": 0.10,
            "angle_fit": 0.18,
            "compliance": 0.22,
            "clarity": 0.08,
            "proof_strength": 0.07,
        },
    },
    {
        "strategy_name": "low_friction_maintenance",
        "angle_order": ["maintenance_free", "facade_refresh", "energy_savings", "local_partner_review"],
        "cta_mode": "quick_scan",
        "tone": "low_friction",
        "proof_mode": "maintenance_and_visual",
        "weights": {
            "segment_score": 0.18,
            "response_proxy": 0.18,
            "appointment_proxy": 0.06,
            "angle_fit": 0.20,
            "compliance": 0.23,
            "clarity": 0.10,
            "proof_strength": 0.05,
        },
    },
    {
        "strategy_name": "local_partner_trust",
        "angle_order": ["local_partner_review", "facade_refresh", "maintenance_free", "energy_savings"],
        "cta_mode": "partner_review",
        "tone": "local_trust",
        "proof_mode": "partner_and_territory",
        "weights": {
            "segment_score": 0.17,
            "response_proxy": 0.16,
            "appointment_proxy": 0.08,
            "angle_fit": 0.19,
            "compliance": 0.24,
            "clarity": 0.08,
            "proof_strength": 0.08,
        },
    },
    {
        "strategy_name": "reactivation_soft_followup",
        "angle_order": ["maintenance_free", "local_partner_review", "facade_refresh", "energy_savings"],
        "cta_mode": "soft_followup",
        "tone": "soft",
        "proof_mode": "low_commitment_review",
        "weights": {
            "segment_score": 0.15,
            "response_proxy": 0.19,
            "appointment_proxy": 0.05,
            "angle_fit": 0.22,
            "compliance": 0.25,
            "clarity": 0.10,
            "proof_strength": 0.04,
        },
    },
)

FORBIDDEN_CLAIM_MARKERS = (
    "guaranteed",
    "we know",
    "you must",
    "subsidy guaranteed",
    "will save",
    "owner data",
    "epc label",
    "buying intent",
    "urgent problem",
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
    config = deepcopy(DEFAULT_MESSAGE_CONFIG)
    if not overrides:
        return config
    for key, value in overrides.items():
        if key == "weights" and isinstance(value, dict):
            config["weights"].update(value)
        elif key in config:
            config[key] = value
    return config


def _campaign_segments(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    segmentation = snapshot.get("campaignSegmentation") if isinstance(snapshot.get("campaignSegmentation"), dict) else {}
    segments = segmentation.get("best_segments") if isinstance(segmentation.get("best_segments"), list) else []
    return [segment for segment in segments if isinstance(segment, dict)]


def _segment_dimensions(segment: dict[str, Any]) -> dict[str, str]:
    dimensions = segment.get("dimensions") if isinstance(segment.get("dimensions"), dict) else {}
    return {str(key): str(value) for key, value in dimensions.items()}


def _preferred_angle(segment: dict[str, Any], config: dict[str, Any]) -> str:
    dimensions = _segment_dimensions(segment)
    explicit = str(dimensions.get("message_angle") or "").strip()
    angle_order = [str(angle) for angle in config.get("angle_order", []) if str(angle) in MESSAGE_ANGLES]
    if explicit in MESSAGE_ANGLES and explicit in angle_order:
        return explicit
    status_cluster = str(dimensions.get("status_cluster") or "")
    value_band = str(dimensions.get("value_band") or "")
    public_policy = str(dimensions.get("public_policy") or "")
    partner_tier = str(dimensions.get("partner_tier") or "")
    if "no_response" in status_cluster and "maintenance_free" in angle_order:
        return "maintenance_free"
    if public_policy in {"high_renovation_activity", "review_zone"} and "subsidy_check" in angle_order:
        return "subsidy_check"
    if value_band == "premium_value" or partner_tier == "platinum":
        if "premium_finish" in angle_order:
            return "premium_finish"
    if "local_partner_review" in angle_order and dimensions.get("territory"):
        return "local_partner_review"
    return angle_order[0] if angle_order else "facade_refresh"


def _angle_fit(segment: dict[str, Any], angle: str) -> float:
    dimensions = _segment_dimensions(segment)
    explicit = str(dimensions.get("message_angle") or "")
    status_cluster = str(dimensions.get("status_cluster") or "")
    score = 58.0
    if explicit == angle:
        score += 28.0
    if angle == "maintenance_free" and "no_response" in status_cluster:
        score += 22.0
    if angle == "premium_finish" and dimensions.get("partner_tier") == "platinum":
        score += 18.0
    if angle == "subsidy_check" and dimensions.get("public_policy") in {"high_renovation_activity", "review_zone"}:
        score += 18.0
    if angle == "local_partner_review" and (dimensions.get("territory") or dimensions.get("partner_tier")):
        score += 14.0
    if angle == "energy_savings" and dimensions.get("pre_1990_band") in {"pre_1990_high", "pre_1990_medium"}:
        score += 14.0
    return min(100.0, score)


def _proof_points(segment: dict[str, Any], angle: str, proof_mode: str) -> list[str]:
    points = [
        "HomePilot opportunity score and evidence coverage",
        "DAW facade insulation and crepi review path",
    ]
    if angle == "energy_savings":
        points.append("energy and comfort context to be approved by DAW before launch")
    elif angle == "subsidy_check":
        points.append("subsidy or policy context as a review prompt, not an eligibility promise")
    elif angle == "premium_finish":
        points.append("finish-quality and reference-story angle for high-value segments")
    elif angle == "maintenance_free":
        points.append("maintenance and facade-refresh convenience angle")
    elif angle == "local_partner_review":
        points.append("assigned local renovation partner review")
    if proof_mode in {"public_context_review", "visual_and_public_context"}:
        points.append("approved public-context fields only, with source and allowed-use review")
    return points[:4]


def _subject_theme(angle: str, tone: str) -> str:
    table = {
        "energy_savings": "Facade insulation review",
        "facade_refresh": "Crepi facade refresh review",
        "premium_finish": "Premium exterior finish review",
        "subsidy_check": "Facade renovation options review",
        "maintenance_free": "Low-maintenance facade refresh",
        "local_partner_review": "Local facade partner review",
    }
    theme = table.get(angle, "Facade renovation review")
    if tone == "soft":
        return f"Optional {theme.lower()}"
    if tone == "premium":
        return f"{theme}: reference-led option"
    return theme


def _opening_line(angle: str, tone: str) -> str:
    if angle == "subsidy_check":
        return "We are reviewing which facade renovation options may be relevant in this area, subject to customer and legal approval."
    if angle == "energy_savings":
        return "DAW and its renovation partners can review facade insulation options where the HomePilot opportunity signal is strong."
    if angle == "premium_finish":
        return "This segment can be approached with a reference-led exterior finish story after DAW approval."
    if angle == "maintenance_free":
        return "This segment fits a low-friction facade refresh review with no assumption of homeowner intent."
    if angle == "local_partner_review":
        return "The assigned local renovation partner can review the facade opportunity under DAW's approved campaign rules."
    if tone == "soft":
        return "This is a low-commitment review invitation based on campaign context, not an intent claim."
    return "This segment can be approached with a safe crepi/facade refresh review message."


def _cta(config: dict[str, Any]) -> str:
    cta_mode = str(config.get("cta_mode") or "review_call")
    return {
        "visual_review": "Invite to review a visual facade option.",
        "eligibility_review": "Invite to check whether any approved renovation context applies.",
        "reference_review": "Invite to compare a reference finish and request partner follow-up.",
        "quick_scan": "Invite to request a quick facade scan.",
        "partner_review": "Invite to speak with the assigned local partner.",
        "soft_followup": "Offer an easy opt-out and optional review link.",
        "review_call": "Invite to book or request a review call.",
    }.get(cta_mode, "Invite to request a review call.")


def _message_text_blob(candidate: dict[str, Any]) -> str:
    return " ".join(
        str(value)
        for value in (
            candidate.get("subject_theme"),
            candidate.get("opening_line"),
            candidate.get("call_to_action"),
            " ".join(candidate.get("proof_points", [])),
        )
    ).lower()


def _forbidden_claim_count(candidate: dict[str, Any]) -> int:
    body = _message_text_blob(candidate)
    return sum(1 for marker in FORBIDDEN_CLAIM_MARKERS if marker in body)


def _compliance_score(candidate: dict[str, Any], config: dict[str, Any]) -> float:
    forbidden = _forbidden_claim_count(candidate)
    score = 100.0 - forbidden * 35.0
    if candidate.get("response_denominator") != "contacted_count":
        score -= 20.0
    if candidate.get("angle") == "subsidy_check":
        score -= 4.0
    if config.get("compliance_strictness") == "high":
        score -= 0.0
    return max(0.0, score)


def _clarity_score(candidate: dict[str, Any]) -> float:
    required = ["subject_theme", "opening_line", "proof_points", "call_to_action", "claim_guardrails"]
    present = sum(1 for key in required if candidate.get(key))
    return _pct(present, len(required))


def _proof_strength(segment: dict[str, Any], angle: str) -> float:
    public_context = _number(segment.get("public_context_score"), 0.0)
    score = public_context * 0.45 + _number(segment.get("avg_score"), 0.0) * 0.35
    if angle in {"local_partner_review", "premium_finish"}:
        score += min(20.0, _number(segment.get("partner_count"), 0.0) * 8.0)
    return min(100.0, score)


def _weighted_message_score(features: dict[str, float], config: dict[str, Any]) -> float:
    weights = config.get("weights") if isinstance(config.get("weights"), dict) else {}
    total = sum(max(0.0, _number(weight)) for weight in weights.values())
    if total <= 0:
        return 0.0
    score = sum(_number(weight) * _number(features.get(key)) for key, weight in weights.items()) / total
    return round(_clamp(score / 100.0) * 100, 3)


def build_message_tests(snapshot: dict[str, Any], message_config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    config = _merged_config(message_config)
    segments = _campaign_segments(snapshot)
    tests: list[dict[str, Any]] = []
    for segment in segments:
        angle = _preferred_angle(segment, config)
        candidate: dict[str, Any] = {
            "segment_key": str(segment.get("segment_key") or ""),
            "segment_label": str(segment.get("segment_label") or ""),
            "dimensions": _segment_dimensions(segment),
            "angle": angle,
            "tone": config.get("tone"),
            "subject_theme": _subject_theme(angle, str(config.get("tone") or "consultative")),
            "opening_line": _opening_line(angle, str(config.get("tone") or "consultative")),
            "proof_points": _proof_points(segment, angle, str(config.get("proof_mode") or "")),
            "call_to_action": _cta(config),
            "claim_guardrails": [
                "No homeowner intent claim unless explicit response/customer evidence exists.",
                "No promised savings, subsidy eligibility, or technical outcome claims.",
                "Use approved DAW copy, suppression, opt-out, and legal review before launch.",
            ],
            "segment_score": _number(segment.get("segment_score"), 0.0),
            "property_count": int(round(_number(segment.get("property_count"), 0.0))),
            "response_rate_pct": _number(segment.get("response_rate_pct"), 0.0),
            "appointment_rate_pct": _number(segment.get("appointment_rate_pct"), 0.0),
            "response_denominator": segment.get("response_denominator") or "contacted_count",
            "pipeline_value": int(round(_number(segment.get("pipeline_value"), 0.0))),
            "facade_m2": int(round(_number(segment.get("facade_m2"), 0.0))),
            "top_property_ids": list(segment.get("top_property_ids", []))[:5] if isinstance(segment.get("top_property_ids"), list) else [],
            "synthetic_demo_metric": True,
            "outcome_proxy_only": True,
            "draft_requires_customer_approval": True,
        }
        features = {
            "segment_score": _number(candidate.get("segment_score")),
            "response_proxy": _number(candidate.get("response_rate_pct")),
            "appointment_proxy": _number(candidate.get("appointment_rate_pct")),
            "angle_fit": _angle_fit(segment, angle),
            "compliance": _compliance_score(candidate, config),
            "clarity": _clarity_score(candidate),
            "proof_strength": _proof_strength(segment, angle),
        }
        candidate["message_score"] = _weighted_message_score(features, config)
        candidate["angle_fit_score"] = round(features["angle_fit"], 2)
        candidate["compliance_score"] = round(features["compliance"], 2)
        candidate["clarity_score"] = round(features["clarity"], 2)
        candidate["proof_strength_score"] = round(features["proof_strength"], 2)
        candidate["forbidden_claim_count"] = _forbidden_claim_count(candidate)
        candidate["compliance_status"] = "pass" if candidate["forbidden_claim_count"] == 0 and features["compliance"] >= 90 else "review"
        tests.append(candidate)

    tests.sort(
        key=lambda row: (
            _number(row.get("message_score")),
            _number(row.get("property_count")),
            _number(row.get("pipeline_value")),
            str(row.get("segment_key") or ""),
        ),
        reverse=True,
    )
    limit = int(_number(config.get("max_message_tests"), 8))
    return [{"rank": index + 1, **row} for index, row in enumerate(tests[:limit])]


def evaluate_message_quality(snapshot: dict[str, Any], message_config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = _merged_config(message_config)
    started = time.perf_counter()
    tests = build_message_tests(snapshot, config)
    runtime_ms = (time.perf_counter() - started) * 1000
    if not tests:
        return {
            "final_score": 0.0,
            "message_test_count": 0,
            "covered_properties": 0,
            "avg_message_score": 0.0,
            "compliance_pass_rate_pct": 0.0,
            "forbidden_claim_count": 0,
            "angle_diversity_count": 0,
            "response_denominator": "contacted_count",
            "runtime_ms": round(runtime_ms, 2),
            "synthetic_demo_metric": True,
            "outcome_proxy_only": True,
        }
    n = len(tests)
    avg_message = sum(_number(row.get("message_score")) for row in tests) / n
    compliance_pass = sum(1 for row in tests if row.get("compliance_status") == "pass")
    forbidden = sum(int(_number(row.get("forbidden_claim_count"), 0.0)) for row in tests)
    covered = int(round(sum(_number(row.get("property_count")) for row in tests)))
    pipeline = int(round(sum(_number(row.get("pipeline_value")) for row in tests)))
    angle_diversity = len({str(row.get("angle") or "") for row in tests})
    clarity = sum(_number(row.get("clarity_score")) for row in tests) / n
    proof = sum(_number(row.get("proof_strength_score")) for row in tests) / n
    denominator_ok = all(row.get("response_denominator") == "contacted_count" for row in tests)
    compliance_rate = _pct(compliance_pass, n)
    diversity_score = min(100.0, _pct(angle_diversity, min(4, n)))
    final_score = (
        avg_message * 0.36
        + compliance_rate * 0.24
        + clarity * 0.11
        + proof * 0.09
        + diversity_score * 0.08
        + (100.0 if denominator_ok else 0.0) * 0.12
    )
    return {
        "final_score": round(final_score, 3),
        "message_test_count": n,
        "covered_properties": covered,
        "avg_message_score": round(avg_message, 2),
        "compliance_pass_rate_pct": compliance_rate,
        "forbidden_claim_count": forbidden,
        "angle_diversity_count": angle_diversity,
        "angle_diversity_score": round(diversity_score, 2),
        "avg_clarity_score": round(clarity, 2),
        "avg_proof_strength_score": round(proof, 2),
        "pipeline_value": pipeline,
        "response_denominator": "contacted_count",
        "runtime_ms": round(runtime_ms, 2),
        "synthetic_demo_metric": True,
        "outcome_proxy_only": True,
    }


def _variant_config(index: int) -> dict[str, Any]:
    template = deepcopy(VARIANT_TEMPLATES[index % len(VARIANT_TEMPLATES)])
    phase = index // len(VARIANT_TEMPLATES)
    config = _merged_config(template)
    config["strategy_name"] = f"{template['strategy_name']}_v{phase + 1}"
    config["max_message_tests"] = [6, 8, 10][phase % 3]
    config["compliance_strictness"] = ["high", "high", "strict"][(phase // 3) % 3]
    return config


def run_message_experiments(
    snapshot: dict[str, Any],
    run_count: int = 24,
    baseline_only: bool = False,
    target_score: float | None = None,
    max_runs: int | None = None,
) -> list[dict[str, Any]]:
    experiments = [{
        "tag": "baseline",
        "message_config": _merged_config(),
        "description": "current segment-message angle ordering",
    }]
    best_score = -1.0
    if not baseline_only:
        total_variants = max(0, max_runs if target_score is not None and max_runs is not None else run_count)
        for index in range(total_variants):
            config = _variant_config(index)
            row = {
                "tag": f"variant_{index + 1:02d}",
                "message_config": config,
                "description": "deterministic message strategy recipe",
            }
            experiments.append(row)
            quality = evaluate_message_quality(snapshot, config)
            best_score = max(best_score, quality["final_score"])
            row["quality"] = quality
            row["message_tests"] = build_message_tests(snapshot, config)
            if target_score is not None and best_score >= target_score:
                break

    results = []
    for experiment in experiments:
        if "quality" not in experiment:
            experiment["quality"] = evaluate_message_quality(snapshot, experiment["message_config"])
            experiment["message_tests"] = build_message_tests(snapshot, experiment["message_config"])
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
            _number(quality.get("compliance_pass_rate_pct")),
            _number(quality.get("pipeline_value")),
            -tag_number,
        )

    ordered = sorted(results, key=sort_key, reverse=True)
    for index, row in enumerate(ordered):
        row["status"] = "keep" if index == 0 else "discard"
    return ordered


def build_message_strategy_recommendation(
    snapshot: dict[str, Any],
    run_count: int = 24,
    target_score: float | None = None,
    max_runs: int | None = None,
) -> dict[str, Any]:
    results = run_message_experiments(
        snapshot,
        run_count=run_count,
        target_score=target_score,
        max_runs=max_runs,
    )
    best = results[0]
    baseline = next((row for row in results if row["tag"] == "baseline"), best)
    return {
        "message_config": best["message_config"],
        "message_quality": best["quality"],
        "message_research": {
            "source": "homepilot_message_strategy_autoresearch",
            "experiment_family": "message_strategy",
            "experiment_count": len(results),
            "best_tag": best["tag"],
            "baseline_score": baseline["quality"]["final_score"],
            "best_score": best["quality"]["final_score"],
            "outcome_proxy_only": True,
            "synthetic_demo_evidence": True,
            "non_mutating": True,
            "response_denominator": "contacted_count",
            "drafts_require_customer_approval": True,
        },
        "best_message_tests": best["message_tests"],
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_results_tsv(path: Path, results: list[dict[str, Any]]) -> None:
    fields = [
        "rank",
        "tag",
        "strategy_name",
        "final_score",
        "message_test_count",
        "compliance_pass_rate_pct",
        "forbidden_claim_count",
        "angle_diversity_count",
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
                "strategy_name": row["message_config"].get("strategy_name"),
                "final_score": quality["final_score"],
                "message_test_count": quality["message_test_count"],
                "compliance_pass_rate_pct": quality["compliance_pass_rate_pct"],
                "forbidden_claim_count": quality["forbidden_claim_count"],
                "angle_diversity_count": quality["angle_diversity_count"],
                "pipeline_value": quality.get("pipeline_value", 0),
                "status": row["status"],
                "description": row["description"],
            })


def render_report(pack: dict[str, Any]) -> str:
    best = pack["best"]
    quality = best["quality"]
    summary = pack["summary"]
    lines = [
        "# HomePilot Message Strategy Autoresearch Report",
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
        f"- Message tests: {quality['message_test_count']}",
        f"- Compliance pass rate: {quality['compliance_pass_rate_pct']}%",
        f"- Forbidden claim count: {quality['forbidden_claim_count']}",
        f"- Angle diversity: {quality['angle_diversity_count']}",
        f"- Pipeline value in selected message tests: EUR {quality.get('pipeline_value', 0):,}".replace(",", " "),
        f"- Response denominator: {quality['response_denominator']}",
        "",
        "## Guardrails",
        "",
        "- Tenant-scoped dashboard snapshot only.",
        "- Drafts are review artifacts and require customer/legal approval before use.",
        "- No homeowner intent, promised savings, subsidy eligibility, or technical outcome claims.",
        "- Message tests omit raw addresses and contact values; property ids are review anchors only.",
        "- No live database writes, Supabase writes, outreach state changes, or partner portal changes.",
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


def build_message_strategy_autoresearch_pack(
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
        from homepilot_campaign_segmentation_autoresearch import build_campaign_segmentation_recommendation
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
        snapshot["campaignSegmentation"] = build_campaign_segmentation_recommendation(snapshot, run_count=8)

    if not _campaign_segments(snapshot):
        from homepilot_campaign_segmentation_autoresearch import build_campaign_segmentation_recommendation

        snapshot = deepcopy(snapshot)
        snapshot["campaignSegmentation"] = build_campaign_segmentation_recommendation(snapshot, run_count=8)

    results = run_message_experiments(
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
        "best_message_strategy": str(out_dir / "best_message_strategy.json"),
        "report": str(out_dir / "MESSAGE_STRATEGY_AUTORESEARCH_REPORT.md"),
        "pack": str(out_dir / "message_strategy_autoresearch_pack.json"),
    }
    pack = {
        "pack_type": "homepilot_message_strategy_autoresearch",
        "created_at": utc_now(),
        "status": "pass",
        "release_label": release_label,
        "experiment_family": "message_strategy",
        "baseline_only": baseline_only,
        "experiment_count": len(results),
        "best": best,
        "summary": {
            "best_tag": best["tag"],
            "best_strategy": best["message_config"].get("strategy_name"),
            "best_score": best["quality"]["final_score"],
            "baseline_score": baseline_score,
            "message_test_count": best["quality"]["message_test_count"],
            "compliance_pass_rate_pct": best["quality"]["compliance_pass_rate_pct"],
            "forbidden_claim_count": best["quality"]["forbidden_claim_count"],
            "angle_diversity_count": best["quality"]["angle_diversity_count"],
            "pipeline_value": best["quality"].get("pipeline_value", 0),
        },
        "guardrails": {
            "tenant_scoped_snapshot_only": True,
            "module_scoped": True,
            "partner_scoped_for_producer_networks": True,
            "synthetic_demo_only": True,
            "outcome_proxy_only": True,
            "response_denominator_is_contacted_count": True,
            "drafts_require_customer_approval": True,
            "public_context_not_homeowner_intent": True,
            "no_homeowner_intent_claims": True,
            "no_promised_savings_or_subsidy_claims": True,
            "non_mutating_pack": True,
            "writes_live_data": False,
            "writes_supabase": False,
            "changes_outreach_state": False,
            "raw_addresses_in_best_message_tests": False,
            "raw_contact_values_written": False,
            "secret_values_written": False,
            "winning_message_strategy_requires_review": True,
        },
        "paths": paths,
    }
    write_results_tsv(Path(paths["results"]), results)
    write_json(Path(paths["best_message_strategy"]), {
        "message_config": best["message_config"],
        "message_quality": best["quality"],
        "message_research": {
            "source": "homepilot_message_strategy_autoresearch",
            "best_tag": best["tag"],
            "experiment_family": "message_strategy",
            "experiment_count": len(results),
            "baseline_score": baseline_score,
            "best_score": best["quality"]["final_score"],
            "outcome_proxy_only": True,
            "synthetic_demo_evidence": True,
            "non_mutating": True,
            "response_denominator": "contacted_count",
            "drafts_require_customer_approval": True,
        },
        "best_message_tests": best["message_tests"],
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
    parser = argparse.ArgumentParser(description="Run HomePilot message-strategy autoresearch")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--release-label", default="local")
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--run", type=int, default=24)
    parser.add_argument("--target-score", type=float)
    parser.add_argument("--max-runs", type=int)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8")) if args.snapshot else None
    pack = build_message_strategy_autoresearch_pack(
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
        "best_message_strategy": pack["paths"]["best_message_strategy"],
        "report": pack["paths"]["report"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
