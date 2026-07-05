#!/usr/bin/env python3
"""
Audit HomePilot tenant/module access before sharing customer data.

This is a local preflight for the rule that matters most commercially:

  A customer sees only its own tenant and enabled modules.

The audit can inspect onboarding JSON, canonical payload JSON, dashboard
snapshot JSON, and an export directory. It returns a machine-readable report
with an access matrix and explicit issues.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from homepilot_onboarding import load_onboarding_payload
from homepilot_metric_access import hidden_metric_keys
from homepilot_platform import PILOT_MODULES
from homepilot_store import load_payload


MODULE_KEYS = set(PILOT_MODULES)
MODULE_LABELS = {key: definition.label for key, definition in PILOT_MODULES.items()}


def _add_count(matrix: dict[str, dict[str, Any]], module_key: str, field: str, count: int = 1) -> None:
    if module_key not in matrix:
        matrix[module_key] = {"enabled": False, "payload": 0, "snapshot": 0, "export": 0}
    matrix[module_key][field] = matrix[module_key].get(field, 0) + count


def _tenant_ids_from_onboarding(onboarding: dict[str, Any]) -> set[str]:
    return {row["id"] for row in onboarding.get("tenants", [])}


def _enabled_modules_from_onboarding(onboarding: dict[str, Any]) -> set[str]:
    return {
        row["module_key"]
        for row in onboarding.get("tenant_modules", [])
        if row.get("enabled", True)
    }


def _module_mentions(value: Any) -> set[str]:
    mentions: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in MODULE_KEYS:
                mentions.add(key)
            mentions |= _module_mentions(item)
    elif isinstance(value, list):
        for item in value:
            mentions |= _module_mentions(item)
    elif isinstance(value, str):
        lower = value.lower()
        for module_key, label in MODULE_LABELS.items():
            if value == module_key or lower == label.lower():
                mentions.add(module_key)
    return mentions


def audit_payload(
    payload_path: Path,
    tenant_ids: set[str],
    enabled_modules: set[str],
    matrix: dict[str, dict[str, Any]],
) -> list[str]:
    issues: list[str] = []
    payload = load_payload(payload_path)

    for collection in ("properties", "campaigns", "campaign_targets", "assessments", "interactions", "response_insights"):
        for row in payload.get(collection, []):
            tenant_id = row.get("tenant_id")
            if tenant_id and tenant_id not in tenant_ids:
                issues.append(f"{collection}: tenant {tenant_id} is not in onboarding tenant ids")
            module_key = row.get("module_key")
            if module_key:
                _add_count(matrix, module_key, "payload")
                if module_key not in enabled_modules:
                    issues.append(f"{collection}: module {module_key} is not enabled for tenant")
                if collection == "assessments":
                    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
                    for metric_key in hidden_metric_keys(module_key, metrics, surface="customer_package"):
                        issues.append(f"{collection}: hidden metric {module_key}.{metric_key} is visible")
    return issues


def audit_snapshot(
    snapshot_path: Path,
    tenant_ids: set[str],
    enabled_modules: set[str],
    matrix: dict[str, dict[str, Any]],
) -> list[str]:
    issues: list[str] = []
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    tenant = snapshot.get("tenant", {})
    tenant_id = tenant.get("id", "")
    if tenant_id in tenant_ids:
        pass
    elif tenant_id and tenant_id not in tenant_ids:
        # Snapshots often use a display slug, so warn only when it looks like a UUID-ish id.
        if len(str(tenant_id)) >= 32:
            issues.append(f"snapshot: tenant id {tenant_id} is not in onboarding tenant ids")

    snapshot_modules = set(tenant.get("modules", []))
    for module_key in snapshot_modules:
        _add_count(matrix, module_key, "snapshot", 0)
        if module_key not in enabled_modules:
            issues.append(f"snapshot: module {module_key} is not enabled for tenant")

    for prop in snapshot.get("properties", []):
        for module_key, assessment in prop.get("assessments", {}).items():
            _add_count(matrix, module_key, "snapshot")
            if module_key not in enabled_modules:
                issues.append(f"snapshot property {prop.get('id')}: module {module_key} is not enabled")
            metrics = assessment.get("metrics") if isinstance(assessment.get("metrics"), dict) else {}
            for metric_key in hidden_metric_keys(module_key, metrics, surface="dashboard"):
                issues.append(f"snapshot property {prop.get('id')}: hidden metric {module_key}.{metric_key} is visible")

    forbidden_mentions = _module_mentions(snapshot) - enabled_modules
    for module_key in sorted(forbidden_mentions):
        issues.append(f"snapshot: forbidden module mention found: {module_key}")
    return issues


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def audit_export_dir(
    export_dir: Path,
    enabled_modules: set[str],
    matrix: dict[str, dict[str, Any]],
) -> list[str]:
    issues: list[str] = []
    manifest_path = export_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for module_key in manifest.get("summary", {}).get("modules", {}):
            if module_key not in enabled_modules:
                issues.append(f"export manifest: module {module_key} is not enabled")

    for csv_name in ("properties.csv", "assessments.csv", "interactions.csv"):
        rows = _read_csv_rows(export_dir / csv_name)
        for row in rows:
            for field in ("module_key", "best_module"):
                module_key = row.get(field, "")
                if module_key:
                    _add_count(matrix, module_key, "export")
                    if module_key not in enabled_modules:
                        issues.append(f"{csv_name}: module {module_key} is not enabled")
            if csv_name == "assessments.csv" and row.get("module_key"):
                metrics = {}
                if row.get("metrics_json"):
                    try:
                        metrics = json.loads(row["metrics_json"])
                    except json.JSONDecodeError:
                        issues.append(f"{csv_name}: metrics_json is not valid JSON")
                for metric_key in hidden_metric_keys(row["module_key"], metrics, surface="export"):
                    issues.append(f"{csv_name}: hidden metric {row['module_key']}.{metric_key} is visible")
            forbidden_mentions = _module_mentions(row) - enabled_modules
            for module_key in sorted(forbidden_mentions):
                issues.append(f"{csv_name}: forbidden module mention found: {module_key}")
    return issues


def build_access_audit(
    onboarding_path: Path,
    payload_path: Path | None = None,
    snapshot_path: Path | None = None,
    export_dir: Path | None = None,
) -> dict[str, Any]:
    onboarding = load_onboarding_payload(onboarding_path)
    tenant_ids = _tenant_ids_from_onboarding(onboarding)
    enabled_modules = _enabled_modules_from_onboarding(onboarding)
    matrix = {
        key: {"enabled": key in enabled_modules, "payload": 0, "snapshot": 0, "export": 0}
        for key in PILOT_MODULES
    }
    issues: list[str] = []

    if payload_path:
        issues += audit_payload(payload_path, tenant_ids, enabled_modules, matrix)
    if snapshot_path:
        issues += audit_snapshot(snapshot_path, tenant_ids, enabled_modules, matrix)
    if export_dir:
        issues += audit_export_dir(export_dir, enabled_modules, matrix)

    return {
        "status": "pass" if not issues else "fail",
        "tenant_ids": sorted(tenant_ids),
        "enabled_modules": sorted(enabled_modules),
        "matrix": matrix,
        "issues": issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit HomePilot tenant/module access")
    parser.add_argument("--onboarding", required=True, type=Path)
    parser.add_argument("--payload", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--export-dir", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    report = build_access_audit(
        onboarding_path=args.onboarding,
        payload_path=args.payload,
        snapshot_path=args.snapshot,
        export_dir=args.export_dir,
    )
    body = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(body + "\n", encoding="utf-8")
    print(body)
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
