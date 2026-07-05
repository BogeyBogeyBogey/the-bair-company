#!/usr/bin/env python3
"""
Privacy-safe HomePilot platform benchmarks.

Raw customer data, addresses, tenant IDs, responses, and property IDs stay
tenant-scoped. This module produces only aggregate benchmark rows for
public.homepilot_platform_benchmarks when a cohort reaches the minimum sample
size. Small cohorts are skipped, not rounded up.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from homepilot_platform import PILOT_MODULES, canonical_uuid
from homepilot_store import HomePilotStore, load_payload, validate_payload


DEFAULT_MIN_SAMPLE_SIZE = 10
BENCHMARK_KEY = "module_performance"
RESPONDED_STATUSES = {"responded", "appointment", "customer"}
APPOINTMENT_STATUSES = {"appointment", "customer"}
RAW_FIELD_NAMES = {
    "tenant_id",
    "tenant_ids",
    "property_id",
    "property_ids",
    "address",
    "addresses",
    "source_external_id",
    "campaign_id",
    "campaign_ids",
    "interaction_detail",
    "detail",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100, 2)


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _cohort(min_sample_size: int) -> dict[str, Any]:
    return {
        "scope": "platform",
        "privacy": "aggregate_only",
        "min_sample_size": min_sample_size,
    }


def _status_by_property_module(payloads: list[dict[str, Any]]) -> dict[tuple[str, str, str], str]:
    ranks = {
        "customer": 7,
        "appointment": 6,
        "responded": 5,
        "clicked": 4,
        "scanned": 3,
        "sent": 2,
        "no_response": 1,
        "rejected": 0,
        "generated": 0,
        "queued": 0,
    }
    statuses: dict[tuple[str, str, str], str] = {}
    for payload in payloads:
        for target in payload.get("campaign_targets", []):
            key = (
                str(target.get("tenant_id") or ""),
                str(target.get("property_id") or ""),
                str(target.get("module_key") or ""),
            )
            status = str(target.get("status") or "generated")
            current = statuses.get(key)
            if current is None or ranks.get(status, 0) > ranks.get(current, 0):
                statuses[key] = status
    return statuses


def _samples(payloads: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    statuses = _status_by_property_module(payloads)
    seen: set[tuple[str, str, str]] = set()
    by_module: dict[str, list[dict[str, Any]]] = {}

    for payload in payloads:
        for assessment in payload.get("assessments", []):
            module_key = str(assessment.get("module_key") or "")
            if module_key not in PILOT_MODULES:
                continue
            key = (
                str(assessment.get("tenant_id") or ""),
                str(assessment.get("property_id") or ""),
                module_key,
            )
            if key in seen:
                continue
            seen.add(key)
            score = _number(assessment.get("score"))
            by_module.setdefault(module_key, []).append({
                "score": score,
                "grade": str(assessment.get("grade") or ""),
                "status": statuses.get(key, "generated"),
            })
    return by_module


def _metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [sample["score"] for sample in samples if sample.get("score") is not None]
    top_grade_count = sum(1 for sample in samples if sample.get("grade") in {"A+", "A"})
    contacted_count = sum(
        1 for sample in samples
        if sample.get("status") in {"sent", "scanned", "clicked", "responded", "appointment", "customer", "no_response"}
    )
    response_count = sum(1 for sample in samples if sample.get("status") in RESPONDED_STATUSES)
    appointment_count = sum(1 for sample in samples if sample.get("status") in APPOINTMENT_STATUSES)
    customer_count = sum(1 for sample in samples if sample.get("status") == "customer")
    sample_size = len(samples)

    return {
        "score_avg": _round(sum(scores) / len(scores)) if scores else None,
        "score_median": _round(median(scores)) if scores else None,
        "top_grade_rate_pct": _pct(top_grade_count, sample_size),
        "contacted_count": contacted_count,
        "response_count": response_count,
        "response_rate_pct": _pct(response_count, contacted_count),
        "appointment_count": appointment_count,
        "appointment_rate_pct": _pct(appointment_count, contacted_count),
        "customer_count": customer_count,
        "customer_rate_pct": _pct(customer_count, contacted_count),
    }


def validate_benchmark_rows(rows: list[dict[str, Any]], min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE) -> None:
    for row in rows:
        for field in ("id", "module_key", "benchmark_key", "cohort", "sample_size", "metrics"):
            if field not in row:
                raise ValueError(f"Benchmark row missing {field}: {row}")
        if row["module_key"] not in PILOT_MODULES:
            raise ValueError(f"Unknown module_key: {row['module_key']}")
        if int(row["sample_size"]) < min_sample_size:
            raise ValueError(f"Benchmark sample_size below threshold: {row}")
        for container_name in ("cohort", "metrics"):
            container = row.get(container_name)
            if not isinstance(container, dict):
                raise ValueError(f"Benchmark {container_name} must be an object: {row}")
            forbidden = sorted(RAW_FIELD_NAMES.intersection(container))
            if forbidden:
                raise ValueError(f"Benchmark {container_name} contains raw fields {forbidden}: {row}")


def build_benchmark_rows(
    payloads: list[dict[str, Any]],
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
    computed_at: str | None = None,
) -> list[dict[str, Any]]:
    if min_sample_size < 10:
        raise ValueError("min_sample_size must be >= 10")
    for payload in payloads:
        validate_payload(payload)

    rows: list[dict[str, Any]] = []
    cohort = _cohort(min_sample_size)
    cohort_key = json.dumps(cohort, sort_keys=True, ensure_ascii=False)
    timestamp = computed_at or utc_now()
    for module_key, samples in sorted(_samples(payloads).items()):
        sample_size = len(samples)
        if sample_size < min_sample_size:
            continue
        rows.append({
            "id": canonical_uuid("benchmark", module_key, BENCHMARK_KEY, cohort_key),
            "module_key": module_key,
            "benchmark_key": BENCHMARK_KEY,
            "cohort": cohort,
            "sample_size": sample_size,
            "metrics": _metrics(samples),
            "computed_at": timestamp,
        })
    validate_benchmark_rows(rows, min_sample_size=min_sample_size)
    return rows


def load_payloads(paths: list[Path]) -> list[dict[str, Any]]:
    if not paths:
        raise ValueError("At least one payload JSON is required")
    return [load_payload(path) for path in paths]


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build privacy-safe HomePilot benchmark rows")
    parser.add_argument("--json", dest="json_paths", action="append", required=True, type=Path)
    parser.add_argument("--min-sample-size", type=int, default=DEFAULT_MIN_SAMPLE_SIZE)
    sub = parser.add_subparsers(dest="cmd", required=True)

    build = sub.add_parser("build", help="Write benchmark rows to JSON")
    build.add_argument("--out", required=True, type=Path)

    import_rows = sub.add_parser("import-json", help="Build and import benchmark rows")
    import_rows.add_argument("--dry-run", action="store_true")
    import_rows.add_argument("--out", type=Path)

    args = parser.parse_args()
    rows = build_benchmark_rows(load_payloads(args.json_paths), min_sample_size=args.min_sample_size)

    if args.cmd == "build":
        write_json(args.out, {"benchmarks": rows, "count": len(rows)})
        print(json.dumps({"output": str(args.out), "count": len(rows)}, indent=2))
    elif args.cmd == "import-json":
        if args.out:
            write_json(args.out, {"benchmarks": rows, "count": len(rows)})
        store = HomePilotStore(dry_run=args.dry_run)
        count = store.upsert(
            "homepilot_platform_benchmarks",
            rows,
            on_conflict="module_key,benchmark_key,cohort",
        )
        print(json.dumps({"imported": count, "dry_run": store.dry_run}, indent=2))


if __name__ == "__main__":
    main()
