#!/usr/bin/env python3
"""
HomePilot schema deployment manifest.

This creates a non-destructive release artifact for database changes: exact SQL
files, checksums, required contract markers, apply order, and post-apply checks.
It is meant for operator review before applying Supabase SQL in production.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_sql_apply_plan import build_sql_apply_plan_pack


HERE = Path(__file__).parent.resolve()
HOME_ROOT = HERE.parent

SQL_STEPS = (
    {
        "name": "base_schema",
        "path": "platform/supabase_schema.sql",
        "purpose": "Create HomePilot tables, indexes, RLS helpers, and RLS policies.",
        "required_markers": (
            "create table if not exists public.homepilot_tenants",
            "create table if not exists public.homepilot_properties",
            "create table if not exists public.homepilot_audit_events",
            "alter table public.homepilot_properties enable row level security",
            "homepilot_has_tenant_access",
            "homepilot_has_module_access",
            "sample_size >= 10",
        ),
    },
    {
        "name": "dashboard_views",
        "path": "platform/dashboard_views.sql",
        "purpose": "Create tenant/module-safe customer views and metric filtering functions.",
        "required_markers": (
            "with (security_invoker = true)",
            "homepilot_metrics_for_customer",
            "homepilot_property_intelligence",
            "homepilot_property_export",
            "homepilot_campaign_metrics",
            "homepilot_module_metrics",
            "homepilot_second_brain_edges",
        ),
    },
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _statement_count(sql: str) -> int:
    return sum(1 for part in sql.split(";") if part.strip())


def build_sql_step(step: dict[str, Any], root: Path = HOME_ROOT) -> dict[str, Any]:
    path = root / step["path"]
    if not path.exists():
        return {
            "name": step["name"],
            "path": str(path),
            "relative_path": step["path"],
            "purpose": step["purpose"],
            "status": "fail",
            "missing": True,
            "missing_markers": list(step["required_markers"]),
        }
    body = _read(path)
    lower = body.lower()
    missing_markers = [marker for marker in step["required_markers"] if marker.lower() not in lower]
    return {
        "name": step["name"],
        "path": str(path),
        "relative_path": step["path"],
        "purpose": step["purpose"],
        "status": "pass" if not missing_markers else "fail",
        "missing": False,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "statement_count": _statement_count(body),
        "required_markers": list(step["required_markers"]),
        "missing_markers": missing_markers,
    }


def build_deployment_manifest(
    root: Path = HOME_ROOT,
    release_label: str = "local",
    environment: str = "supabase",
) -> dict[str, Any]:
    steps = [build_sql_step(step, root=root) for step in SQL_STEPS]
    failures = [step for step in steps if step["status"] != "pass"]
    hashes = [step.get("sha256") for step in steps if step.get("sha256")]
    duplicate_hashes = sorted({value for value in hashes if hashes.count(value) > 1})
    issues = []
    for step in failures:
        if step.get("missing"):
            issues.append(f"{step['relative_path']} is missing.")
        for marker in step.get("missing_markers", []):
            issues.append(f"{step['relative_path']} missing marker: {marker}")
    for digest in duplicate_hashes:
        issues.append(f"Duplicate SQL file hash detected: {digest}")

    status = "pass" if not issues else "fail"
    manifest = {
        "manifest_type": "homepilot_schema_deployment_manifest",
        "created_at": utc_now(),
        "release_label": release_label,
        "environment": environment,
        "status": status,
        "root": str(root),
        "apply_order": [step["relative_path"] for step in steps],
        "steps": steps,
        "issues": issues,
        "post_apply_checks": [
        "Run platform/homepilot_healthcheck.py --live --require-live.",
        "Review the generated SQL_APPLY_PLAN.md and apply.sql before applying SQL.",
        "Run platform/homepilot_live_readiness.py to confirm redacted Supabase, fixture, and customer access credentials are ready.",
            "Run platform/homepilot_live_schema_verification.py --live and require production_verified=true.",
            "Run platform/homepilot_store.py seed-modules with service-role access.",
            "Run platform/homepilot_launch.py rls-fixture with real customer JWTs.",
            "Archive launch_report.json, rls_probe_report.json, cleanup_plan.json, and cleanup_plan.sql.",
            "Optionally run platform/homepilot_production_cutover.py --live to orchestrate schema verification, module seed, launch, customer access verification, and release audit in one evidence chain.",
            "Run platform/homepilot_release_audit.py with --require-production.",
        ],
        "rollback_note": "SQL files are idempotent forward schema setup. Use homepilot_recovery.py for data rollback and Supabase migration backups for schema rollback.",
    }
    return manifest


def render_deployment_runbook(manifest: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Schema Deployment Runbook",
        "",
        f"Release: {manifest['release_label']}",
        f"Created: {manifest['created_at']}",
        f"Status: {manifest['status']}",
        "",
        "## Apply Order",
        "",
    ]
    for index, step in enumerate(manifest["steps"], start=1):
        lines.append(f"{index}. {step['relative_path']} - {step['purpose']}")
        lines.append(f"   - sha256: {step.get('sha256', 'missing')}")
        lines.append(f"   - status: {step['status']}")
    lines += [
        "",
        "## Post-Apply Checks",
        "",
    ]
    for check in manifest["post_apply_checks"]:
        lines.append(f"- {check}")
    if manifest["issues"]:
        lines += ["", "## Issues", ""]
        for issue in manifest["issues"]:
            lines.append(f"- {issue}")
    lines += ["", "## Rollback Note", "", manifest["rollback_note"], ""]
    return "\n".join(lines)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def build_deployment_pack(
    out_dir: Path,
    root: Path = HOME_ROOT,
    release_label: str = "local",
    environment: str = "supabase",
) -> dict[str, Any]:
    manifest = build_deployment_manifest(root=root, release_label=release_label, environment=environment)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "deployment_manifest.json"
    runbook_path = out_dir / "DEPLOYMENT_RUNBOOK.md"
    sql_apply_pack = build_sql_apply_plan_pack(out_dir, root=root, release_label=release_label)
    write_json(manifest_path, manifest)
    write_text(runbook_path, render_deployment_runbook(manifest))
    return {
        "pack_type": "homepilot_schema_deployment_pack",
        "created_at": utc_now(),
        "status": "pass" if manifest["status"] == "pass" and sql_apply_pack["status"] == "pass" else "fail",
        "paths": {
            "deployment_manifest": str(manifest_path),
            "deployment_runbook": str(runbook_path),
            "sql_apply_plan": sql_apply_pack["paths"]["sql_apply_plan"],
            "sql_apply_runbook": sql_apply_pack["paths"]["sql_apply_runbook"],
            "apply_sql": sql_apply_pack["paths"]["apply_sql"],
            "post_apply_verification_sql": sql_apply_pack["paths"]["post_apply_verification_sql"],
        },
        "manifest": manifest,
        "sql_apply_plan": sql_apply_pack["plan"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HomePilot schema deployment evidence")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--release-label", default="local")
    parser.add_argument("--environment", default="supabase")
    args = parser.parse_args()

    pack = build_deployment_pack(
        out_dir=args.out_dir,
        release_label=args.release_label,
        environment=args.environment,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": pack["status"],
        "deployment_manifest": pack["paths"]["deployment_manifest"],
        "deployment_runbook": pack["paths"]["deployment_runbook"],
        "sql_apply_plan": pack["paths"]["sql_apply_plan"],
        "apply_sql": pack["paths"]["apply_sql"],
        "steps": len(pack["manifest"]["steps"]),
        "issues": len(pack["manifest"]["issues"]),
    }, indent=2))
    if pack["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
