#!/usr/bin/env python3
"""
Build HomePilot data vendor and enrichment readiness packs.

Property intelligence gets better when every score can point to a source layer:
parcel/cadastre, geocode, imagery, building age or energy signals, permit
history, pricing estimates, and contact provenance. This module audits a
tenant-scoped customer package, explains which enrichment categories are present,
and writes a concrete backlog for missing source layers.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


SECRET_PATTERNS = {
    "api_key_assignment": re.compile(r"api[_-]?key\s*[:=]\s*['\"][^'\"]+", re.IGNORECASE),
    "bearer_token": re.compile(r"bearer\s+[A-Za-z0-9._-]{20,}", re.IGNORECASE),
    "jwt_like_token": re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _path_from_manifest(manifest: dict[str, Any], key: str) -> Path | None:
    paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
    value = paths.get(key)
    return Path(value) if value else None


def _rows(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(count: int, total: int) -> float:
    if not total:
        return 0.0
    return round((count / total) * 100, 2)


def _assessments_for_property(payload: dict[str, Any], property_id: str) -> list[dict[str, Any]]:
    return [row for row in _rows(payload, "assessments") if row.get("property_id") == property_id]


def _targets_for_property(payload: dict[str, Any], property_id: str) -> list[dict[str, Any]]:
    return [row for row in _rows(payload, "campaign_targets") if row.get("property_id") == property_id]


def _metrics(assessments: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for assessment in assessments:
        values = assessment.get("metrics") if isinstance(assessment.get("metrics"), dict) else {}
        merged.update(values)
    return merged


def _core(prop: dict[str, Any]) -> dict[str, Any]:
    value = prop.get("core")
    return value if isinstance(value, dict) else {}


def _evidence_types(assessments: list[dict[str, Any]]) -> set[str]:
    types: set[str] = set()
    for assessment in assessments:
        for item in assessment.get("evidence", []) if isinstance(assessment.get("evidence"), list) else []:
            if isinstance(item, dict):
                types.add(str(item.get("type") or "").lower())
    return types


def _has_contact_provenance(targets: list[dict[str, Any]]) -> bool:
    if not targets:
        return False
    required = ("source_provenance", "contact_basis", "contact_channel", "opt_out_method", "lead_claim")
    for target in targets:
        metadata = target.get("metadata") if isinstance(target.get("metadata"), dict) else {}
        if all(str(metadata.get(key) or "").strip() for key in required):
            return True
    return False


def _has_any(metrics: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(metrics.get(key) not in (None, "") for key in keys)


def source_requirements() -> list[dict[str, Any]]:
    return [
        {
            "key": "parcel_boundary",
            "label": "Parcel and address identity",
            "purpose": "Deduplicate properties, connect cadastre/parcel records, and keep territory exports stable.",
            "vendor_options": ["regional cadastre/parcel data", "customer GIS files", "parcel API provider"],
            "freshness_sla": "quarterly or before territory expansion",
            "license_review": "confirm customer use, export rights, and derived-score rights",
        },
        {
            "key": "geocode",
            "label": "Geocode and map placement",
            "purpose": "Map/cluster views, routing, sales territories, and local density analysis.",
            "vendor_options": ["geocoder", "customer address master", "GIS batch geocoding"],
            "freshness_sla": "before every campaign import",
            "license_review": "confirm display and export rights for coordinates",
        },
        {
            "key": "imagery",
            "label": "Street/aerial/visual evidence",
            "purpose": "Explain visual renovation signals and defend opportunity scores.",
            "vendor_options": ["street imagery", "aerial imagery", "customer photos", "measurement/inspection provider"],
            "freshness_sla": "12 months for sales use; faster for storm/roof campaigns",
            "license_review": "confirm screenshot, derivative, and customer portal display rights",
        },
        {
            "key": "building_age_energy",
            "label": "Building age and energy signals",
            "purpose": "Prioritize insulation, windows, roof, and energy-saving narratives.",
            "vendor_options": ["EPC/energy registry", "building age dataset", "customer survey", "derived neighborhood age model"],
            "freshness_sla": "annual or campaign-specific refresh",
            "license_review": "confirm public-record use and lead-claim wording",
        },
        {
            "key": "permit_history",
            "label": "Permit and renovation history",
            "purpose": "Avoid recently renovated properties and identify expansion/renovation context.",
            "vendor_options": ["municipal permit data", "customer CRM history", "public renovation notices"],
            "freshness_sla": "monthly for active territories",
            "license_review": "confirm lawful basis and local availability before claims",
        },
        {
            "key": "pricing_estimate",
            "label": "Project value and pricing estimates",
            "purpose": "Pipeline value, capacity planning, and sales prioritization.",
            "vendor_options": ["customer price book", "module estimate model", "regional cost benchmarks"],
            "freshness_sla": "quarterly or after price book changes",
            "license_review": "mark estimates as indicative unless customer-approved",
        },
        {
            "key": "contact_provenance",
            "label": "Contact basis and outreach provenance",
            "purpose": "Compliance review before activation and CRM handoff.",
            "vendor_options": ["customer campaign records", "suppression list", "consent/contact-basis review"],
            "freshness_sla": "before each outreach batch",
            "license_review": "required for every contactable record",
        },
    ]


def _category_checks(payload: dict[str, Any]) -> dict[str, Callable[[dict[str, Any]], bool]]:
    def assessments(prop: dict[str, Any]) -> list[dict[str, Any]]:
        return _assessments_for_property(payload, str(prop.get("id") or ""))

    return {
        "parcel_boundary": lambda prop: bool(str(prop.get("source_external_id") or "").strip() or str(prop.get("core", {}).get("parcel_id") if isinstance(prop.get("core"), dict) else "").strip()),
        "geocode": lambda prop: _num(prop.get("lat")) is not None and _num(prop.get("lon")) is not None,
        "imagery": lambda prop: bool(_evidence_types(assessments(prop)).intersection({"streetview", "aerial", "satellite", "orthophoto", "render", "image", "photo"})),
        "building_age_energy": lambda prop: _has_any({**_core(prop), **_metrics(assessments(prop))}, ("glazing_age_signal", "energy_savings_story_fit", "pre_1990_neighborhood_pct", "building_age_signal", "epc_score", "energy_label")),
        "permit_history": lambda prop: _has_any({**_core(prop), **_metrics(assessments(prop))}, ("permit_signal", "recent_permit", "renovation_history", "last_renovation_year")),
        "pricing_estimate": lambda prop: _has_any(_core(prop), ("estimated_value", "pipeline_value", "project_value", "deal_value")) or any(_has_any(assessment.get("metrics", {}) if isinstance(assessment.get("metrics"), dict) else {}, ("estimated_value", "pipeline_value", "project_value", "deal_value", "median_income")) for assessment in assessments(prop)),
        "contact_provenance": lambda prop: _has_contact_provenance(_targets_for_property(payload, str(prop.get("id") or ""))),
    }


def build_enrichment_plan(payload: dict[str, Any], tenant: dict[str, Any] | None = None) -> dict[str, Any]:
    properties = _rows(payload, "properties")
    tenant_ids = sorted({str(row.get("tenant_id") or "") for row in properties if row.get("tenant_id")})
    categories = source_requirements()
    checks = _category_checks(payload)
    coverage = []
    backlog = []

    for category in categories:
        key = category["key"]
        covered = [prop for prop in properties if checks[key](prop)]
        missing = [prop for prop in properties if not checks[key](prop)]
        coverage.append({
            "key": key,
            "label": category["label"],
            "covered": len(covered),
            "missing": len(missing),
            "coverage_pct": _pct(len(covered), len(properties)),
            "freshness_sla": category["freshness_sla"],
            "license_review": category["license_review"],
        })
        for prop in missing:
            backlog.append({
                "property_id": prop.get("id", ""),
                "address": prop.get("address", ""),
                "city": prop.get("city", ""),
                "tenant_id": prop.get("tenant_id", ""),
                "category": key,
                "label": category["label"],
                "recommended_sources": "; ".join(category["vendor_options"]),
                "priority": "high" if key in {"parcel_boundary", "geocode", "contact_provenance"} else "medium",
            })

    failures: list[str] = []
    warnings: list[str] = []
    if len(tenant_ids) != 1:
        failures.append(f"Enrichment plan expects exactly one scoped tenant, got {tenant_ids}.")
    if not properties:
        failures.append("Enrichment plan needs at least one property.")
    if backlog:
        warnings.append(f"{len(backlog)} enrichment backlog item(s) remain before broad territory scale-up.")

    return {
        "report_type": "homepilot_data_vendor_enrichment_plan",
        "created_at": utc_now(),
        "status": "fail" if failures else "pass",
        "review_status": "ready_with_backlog" if backlog and not failures else ("ready" if not failures else "action_required"),
        "tenant": tenant or {"id": tenant_ids[0] if tenant_ids else None},
        "summary": {
            "properties": len(properties),
            "categories": len(categories),
            "backlog_items": len(backlog),
            "average_coverage_pct": round(sum(row["coverage_pct"] for row in coverage) / len(coverage), 2) if coverage else 0,
        },
        "source_requirements": categories,
        "coverage": coverage,
        "backlog": backlog,
        "guardrails": {
            "vendor_credentials_included": False,
            "raw_owner_contact_data_required": False,
            "license_review_required_before_production": True,
            "customer_claim_language": "opportunity intelligence unless response or customer-approved source proves intent",
            "tenant_scoped": len(tenant_ids) == 1,
        },
        "failures": failures,
        "warnings": warnings,
    }


def _scan_files(paths: list[Path]) -> list[dict[str, str]]:
    findings = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        body = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(body):
                findings.append({"file": str(path), "pattern": label})
    return findings


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def render_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Data Vendor And Enrichment Plan",
        "",
        f"Created: {plan['created_at']}",
        f"Status: {plan['status']}",
        f"Review status: {plan['review_status']}",
        f"Properties: {plan['summary']['properties']}",
        f"Backlog items: {plan['summary']['backlog_items']}",
        "",
        "## Coverage",
        "",
    ]
    for row in plan["coverage"]:
        lines.append(f"- {row['label']}: {row['coverage_pct']}% ({row['covered']} covered, {row['missing']} missing)")
    lines += ["", "## Vendor Guardrails", ""]
    for key, value in plan["guardrails"].items():
        if isinstance(value, bool):
            value = "yes" if value else "no"
        lines.append(f"- {key}: {value}")
    if plan["backlog"]:
        lines += ["", "## First Backlog Items", ""]
        for item in plan["backlog"][:10]:
            lines.append(f"- {item['address']} / {item['category']}: {item['recommended_sources']}")
    if plan["warnings"]:
        lines += ["", "## Warnings", ""]
        lines.extend(f"- {warning}" for warning in plan["warnings"])
    if plan["failures"]:
        lines += ["", "## Failures", ""]
        lines.extend(f"- {failure}" for failure in plan["failures"])
    lines.append("")
    return "\n".join(lines)


def build_enrichment_pack(package_manifest_path: Path, out_dir: Path) -> dict[str, Any]:
    manifest = load_json(package_manifest_path)
    payload_path = _path_from_manifest(manifest, "scoped_payload")
    if not payload_path or not payload_path.exists():
        raise ValueError("Customer package manifest is missing an existing scoped_payload path")
    payload = load_json(payload_path)
    plan = build_enrichment_plan(payload, tenant=manifest.get("tenant", {}))
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / "data_vendor_plan.json"
    markdown_path = out_dir / "DATA_VENDOR_PLAN.md"
    requirements_path = out_dir / "source_requirements.json"
    backlog_path = out_dir / "enrichment_backlog.csv"
    write_json(plan_path, plan)
    write_json(requirements_path, plan["source_requirements"])
    write_csv(backlog_path, plan["backlog"])
    write_text(markdown_path, render_markdown(plan))
    secret_findings = _scan_files([plan_path, markdown_path, requirements_path, backlog_path])
    if secret_findings:
        plan["status"] = "fail"
        plan["failures"] = [*plan["failures"], f"Secret-like values found in enrichment artifacts: {secret_findings}"]
        write_json(plan_path, plan)
        write_text(markdown_path, render_markdown(plan))
    return {
        "status": plan["status"],
        "review_status": plan["review_status"],
        "plan": plan,
        "paths": {
            "data_vendor_plan": str(plan_path),
            "markdown": str(markdown_path),
            "source_requirements": str(requirements_path),
            "enrichment_backlog": str(backlog_path),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HomePilot data vendor and enrichment readiness pack")
    parser.add_argument("--package-manifest", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    pack = build_enrichment_pack(args.package_manifest, args.out_dir)
    print(json.dumps({
        "output": str(args.out_dir),
        "status": pack["status"],
        "review_status": pack["review_status"],
        "summary": pack["plan"]["summary"],
        "data_vendor_plan": pack["paths"]["data_vendor_plan"],
        "backlog": pack["paths"]["enrichment_backlog"],
        "failures": pack["plan"]["failures"],
        "warnings": pack["plan"]["warnings"],
    }, indent=2, ensure_ascii=False))
    if pack["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
