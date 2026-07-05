#!/usr/bin/env python3
"""
Build customer-safe source and provenance ledgers for HomePilot payloads.

Large renovation customers need more than a ranked opportunity list. They need
to know which records have evidence, timestamps, confidence, source lineage,
and campaign provenance. This module turns a tenant/module-scoped payload into
an auditable, exportable ledger without exposing raw internal features or
cross-tenant data.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_platform import PILOT_MODULES
from homepilot_store import load_payload


CONTACTED_STATUSES = {"sent", "scanned", "clicked", "responded", "appointment", "customer", "no_response"}
RESPONDED_STATUSES = {"responded", "appointment", "customer"}
PROVENANCE_METADATA_KEYS = ("source_provenance", "contact_basis", "contact_channel", "opt_out_method", "lead_claim")
TIMESTAMP_KEYS = ("created_at", "updated_at", "occurred_at", "captured_at", "source_captured_at", "assessed_at")
RAW_FIELD_NAMES = {
    "email",
    "phone",
    "owner_name",
    "raw_features",
    "debug",
    "prompt",
    "secret",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _rows(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    values = payload.get(key, [])
    if not isinstance(values, list):
        return []
    return [row for row in values if isinstance(row, dict)]


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


def _timestamp_values(row: dict[str, Any]) -> list[str]:
    values = []
    for key in TIMESTAMP_KEYS:
        value = row.get(key)
        if value not in (None, ""):
            values.append(str(value))
    return values


def _latest_timestamp(payload: dict[str, Any]) -> str | None:
    values: list[str] = []
    for key in ("campaigns", "properties", "assessments", "campaign_targets", "interactions"):
        for row in _rows(payload, key):
            values.extend(_timestamp_values(row))
    return sorted(values)[-1] if values else None


def _tenant_ids(payload: dict[str, Any]) -> list[str]:
    ids = set()
    for key in ("campaigns", "properties", "assessments", "campaign_targets", "interactions"):
        for row in _rows(payload, key):
            tenant_id = str(row.get("tenant_id") or "").strip()
            if tenant_id:
                ids.add(tenant_id)
    return sorted(ids)


def _module_keys(payload: dict[str, Any]) -> list[str]:
    modules = set()
    for key in ("campaigns", "assessments", "campaign_targets", "interactions"):
        for row in _rows(payload, key):
            module_key = str(row.get("module_key") or "").strip()
            if module_key:
                modules.add(module_key)
    return [module for module in PILOT_MODULES if module in modules] + sorted(modules - set(PILOT_MODULES))


def _evidence_counter(assessments: list[dict[str, Any]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for assessment in assessments:
        evidence = assessment.get("evidence")
        if not isinstance(evidence, list):
            continue
        for item in evidence:
            if isinstance(item, dict):
                counter[str(item.get("type") or "unknown")] += 1
            else:
                counter["reference"] += 1
    return counter


def _source_runs(assessments: list[dict[str, Any]]) -> Counter[str]:
    runs: Counter[str] = Counter()
    for assessment in assessments:
        source_run_id = str(assessment.get("source_run_id") or "").strip()
        if source_run_id:
            runs[source_run_id] += 1
    return runs


def _module_coverage(payload: dict[str, Any]) -> list[dict[str, Any]]:
    assessments = _rows(payload, "assessments")
    targets = _rows(payload, "campaign_targets")
    interactions = _rows(payload, "interactions")
    by_module: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "assessments": 0,
        "scores": 0,
        "evidence_references": 0,
        "confidence_values": [],
        "targets": 0,
        "contacted": 0,
        "responses": 0,
        "interactions": 0,
    })

    for assessment in assessments:
        module_key = str(assessment.get("module_key") or "unknown")
        bucket = by_module[module_key]
        bucket["assessments"] += 1
        if _number(assessment.get("score")) is not None:
            bucket["scores"] += 1
        confidence = _number(assessment.get("confidence"))
        if confidence is not None:
            bucket["confidence_values"].append(confidence)
        evidence = assessment.get("evidence")
        if isinstance(evidence, list):
            bucket["evidence_references"] += len(evidence)

    for target in targets:
        module_key = str(target.get("module_key") or "unknown")
        status = str(target.get("status") or "generated")
        bucket = by_module[module_key]
        bucket["targets"] += 1
        if status in CONTACTED_STATUSES:
            bucket["contacted"] += 1
        if status in RESPONDED_STATUSES:
            bucket["responses"] += 1

    for interaction in interactions:
        module_key = str(interaction.get("module_key") or "unknown")
        by_module[module_key]["interactions"] += 1

    rows = []
    for module_key in sorted(by_module):
        bucket = by_module[module_key]
        confidences = bucket.pop("confidence_values")
        avg_confidence = round(sum(confidences) / len(confidences), 3) if confidences else None
        assessments_count = int(bucket["assessments"])
        evidence_assessments = sum(
            1 for assessment in assessments
            if str(assessment.get("module_key") or "unknown") == module_key and assessment.get("evidence")
        )
        rows.append({
            "module_key": module_key,
            "module_label": PILOT_MODULES[module_key].label if module_key in PILOT_MODULES else module_key,
            **bucket,
            "score_coverage_pct": _pct(bucket["scores"], assessments_count),
            "evidence_coverage_pct": _pct(evidence_assessments, assessments_count),
            "average_confidence": avg_confidence,
            "response_rate_pct": _pct(bucket["responses"], bucket["contacted"]),
        })
    return rows


def _gap_summary(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    properties = _rows(payload, "properties")
    assessments = _rows(payload, "assessments")
    targets = _rows(payload, "campaign_targets")
    issues: list[dict[str, Any]] = []
    failures: list[str] = []

    tenant_ids = _tenant_ids(payload)
    if len(tenant_ids) != 1:
        failures.append(f"Source ledger expects exactly one tenant after scoping, got {len(tenant_ids)}.")
    if not assessments:
        failures.append("No assessments available for source ledger.")

    missing_geocode = sum(1 for row in properties if row.get("lat") in (None, "") or row.get("lon") in (None, ""))
    if missing_geocode:
        issues.append({"severity": "review", "key": "missing_geocode", "count": missing_geocode})

    missing_property_source = sum(1 for row in properties if not str(row.get("source_external_id") or "").strip())
    if missing_property_source:
        issues.append({"severity": "review", "key": "missing_property_source_external_id", "count": missing_property_source})

    missing_assessment_evidence = sum(1 for row in assessments if not row.get("evidence"))
    if missing_assessment_evidence:
        issues.append({"severity": "review", "key": "missing_assessment_evidence", "count": missing_assessment_evidence})

    missing_confidence = sum(1 for row in assessments if _number(row.get("confidence")) is None)
    if missing_confidence:
        issues.append({"severity": "review", "key": "missing_confidence", "count": missing_confidence})

    missing_source_run = sum(1 for row in assessments if not str(row.get("source_run_id") or "").strip())
    if missing_source_run:
        issues.append({"severity": "review", "key": "missing_source_run_id", "count": missing_source_run})

    missing_score = sum(1 for row in assessments if _number(row.get("score")) is None)
    if missing_score:
        failures.append(f"Assessments missing score: {missing_score}")

    contacted_targets = [row for row in targets if str(row.get("status") or "generated") in CONTACTED_STATUSES]
    for metadata_key in PROVENANCE_METADATA_KEYS:
        missing = 0
        for target in contacted_targets:
            metadata = target.get("metadata") if isinstance(target.get("metadata"), dict) else {}
            if not str(metadata.get(metadata_key) or "").strip():
                missing += 1
        if missing:
            issues.append({"severity": "review", "key": f"missing_{metadata_key}", "count": missing})

    rows_with_timestamp = 0
    total_rows = 0
    for key in ("campaigns", "properties", "assessments", "campaign_targets", "interactions"):
        for row in _rows(payload, key):
            total_rows += 1
            if _timestamp_values(row):
                rows_with_timestamp += 1
    if total_rows and rows_with_timestamp == 0:
        issues.append({
            "severity": "review",
            "key": "missing_all_record_timestamps",
            "count": total_rows,
        })

    return issues, failures


def _raw_field_scan(payload: dict[str, Any]) -> list[str]:
    leaked = set()
    for key in ("properties", "assessments", "campaign_targets", "interactions"):
        for row in _rows(payload, key):
            for field in row:
                if field in RAW_FIELD_NAMES:
                    leaked.add(field)
            metadata = row.get("metadata")
            if isinstance(metadata, dict):
                for field in metadata:
                    if field in RAW_FIELD_NAMES:
                        leaked.add(f"metadata.{field}")
    return sorted(leaked)


def build_source_ledger(payload: dict[str, Any]) -> dict[str, Any]:
    properties = _rows(payload, "properties")
    assessments = _rows(payload, "assessments")
    campaigns = _rows(payload, "campaigns")
    targets = _rows(payload, "campaign_targets")
    interactions = _rows(payload, "interactions")
    tenant_ids = _tenant_ids(payload)
    module_keys = _module_keys(payload)
    evidence_by_type = _evidence_counter(assessments)
    source_runs = _source_runs(assessments)
    issues, failures = _gap_summary(payload)
    raw_fields = _raw_field_scan(payload)
    if raw_fields:
        failures.append(f"Payload contains raw/internal fields not allowed in source ledger inputs: {raw_fields}")

    confidence_values = [_number(row.get("confidence")) for row in assessments]
    confidence_values = [value for value in confidence_values if value is not None]
    evidence_reference_count = sum(evidence_by_type.values())
    contacted = sum(1 for row in targets if str(row.get("status") or "generated") in CONTACTED_STATUSES)
    responses = sum(1 for row in targets if str(row.get("status") or "generated") in RESPONDED_STATUSES)
    timestamped_rows = 0
    total_rows = 0
    for key in ("campaigns", "properties", "assessments", "campaign_targets", "interactions"):
        for row in _rows(payload, key):
            total_rows += 1
            if _timestamp_values(row):
                timestamped_rows += 1

    return {
        "report_type": "homepilot_source_ledger",
        "created_at": utc_now(),
        "status": "fail" if failures else "pass",
        "review_status": "review_required" if issues else "ready",
        "scope": {
            "tenant_ids": tenant_ids,
            "tenant_scoped": len(tenant_ids) == 1,
            "module_keys": module_keys,
            "module_scoped": all(module in PILOT_MODULES for module in module_keys),
        },
        "summary": {
            "properties": len(properties),
            "assessments": len(assessments),
            "campaigns": len(campaigns),
            "campaign_targets": len(targets),
            "interactions": len(interactions),
            "evidence_references": evidence_reference_count,
            "source_runs": len(source_runs),
            "average_confidence": round(sum(confidence_values) / len(confidence_values), 3) if confidence_values else None,
            "contacted": contacted,
            "responses": responses,
            "response_rate_pct": _pct(responses, contacted),
            "latest_timestamp": _latest_timestamp(payload),
            "timestamp_coverage_pct": _pct(timestamped_rows, total_rows),
            "review_gap_count": sum(issue["count"] for issue in issues),
        },
        "source_runs": [
            {"source_run_id": source_run_id, "assessments": count}
            for source_run_id, count in sorted(source_runs.items())
        ],
        "evidence_by_type": [
            {"type": evidence_type, "count": count}
            for evidence_type, count in sorted(evidence_by_type.items())
        ],
        "module_coverage": _module_coverage(payload),
        "review_gaps": issues,
        "failures": failures,
        "guardrails": {
            "source": "tenant/module-scoped HomePilot payload",
            "tenant_scoped": len(tenant_ids) == 1,
            "raw_internal_fields_excluded": not raw_fields,
            "lead_claim_language_required": True,
            "opportunity_not_intent_without_response": True,
            "cross_customer_learning": "aggregate-only outside this customer package",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    scope = report["scope"]
    summary = report["summary"]
    lines = [
        "# HomePilot Source Ledger",
        "",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        f"Review status: {report['review_status']}",
        f"Tenant scoped: {'yes' if scope['tenant_scoped'] else 'no'}",
        f"Modules: {', '.join(scope['module_keys']) or 'none'}",
        "",
        "## Coverage Summary",
        "",
        f"- Properties: {summary['properties']}",
        f"- Assessments: {summary['assessments']}",
        f"- Evidence references: {summary['evidence_references']}",
        f"- Source runs: {summary['source_runs']}",
        f"- Average confidence: {summary['average_confidence'] if summary['average_confidence'] is not None else 'n/a'}",
        f"- Campaign targets: {summary['campaign_targets']}",
        f"- Contacted: {summary['contacted']}",
        f"- Responses: {summary['responses']} ({summary['response_rate_pct']}%)",
        f"- Latest timestamp: {summary['latest_timestamp'] or 'n/a'}",
        f"- Timestamp coverage: {summary['timestamp_coverage_pct']}%",
        f"- Review gaps: {summary['review_gap_count']}",
        "",
        "## Module Coverage",
        "",
    ]
    if report["module_coverage"]:
        for module in report["module_coverage"]:
            lines.append(
                f"- {module['module_label']} (`{module['module_key']}`): "
                f"{module['assessments']} assessments, {module['evidence_references']} evidence refs, "
                f"score coverage {module['score_coverage_pct']}%, evidence coverage {module['evidence_coverage_pct']}%, "
                f"response rate {module['response_rate_pct']}%."
            )
    else:
        lines.append("- No module coverage available.")

    lines += ["", "## Evidence Types", ""]
    if report["evidence_by_type"]:
        for item in report["evidence_by_type"]:
            lines.append(f"- `{item['type']}`: {item['count']}")
    else:
        lines.append("- No evidence references available.")

    lines += ["", "## Source Runs", ""]
    if report["source_runs"]:
        for item in report["source_runs"]:
            lines.append(f"- `{item['source_run_id']}`: {item['assessments']} assessments")
    else:
        lines.append("- No source run IDs available yet.")

    lines += ["", "## Review Gaps", ""]
    if report["review_gaps"]:
        for gap in report["review_gaps"]:
            lines.append(f"- {gap['key']}: {gap['count']} ({gap['severity']})")
    else:
        lines.append("- No review gaps detected.")

    if report["failures"]:
        lines += ["", "## Failures", ""]
        for failure in report["failures"]:
            lines.append(f"- {failure}")

    lines += ["", "## Guardrails", ""]
    for key, value in report["guardrails"].items():
        if isinstance(value, bool):
            value = "yes" if value else "no"
        lines.append(f"- {key}: {value}")
    lines.append("")
    return "\n".join(lines)


def build_source_ledger_pack(out_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = build_source_ledger(payload)
    json_path = out_dir / "source_ledger.json"
    markdown_path = out_dir / "SOURCE_LEDGER.md"
    write_json(json_path, report)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return {
        "status": report["status"],
        "paths": {
            "source_ledger": str(json_path),
            "markdown": str(markdown_path),
        },
        "report": report,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot source/provenance ledger")
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    pack = build_source_ledger_pack(args.out_dir, payload=load_payload(args.payload))
    print(json.dumps({
        "status": pack["status"],
        "review_status": pack["report"]["review_status"],
        "summary": pack["report"]["summary"],
        "paths": pack["paths"],
    }, indent=2, ensure_ascii=False))
    if pack["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
