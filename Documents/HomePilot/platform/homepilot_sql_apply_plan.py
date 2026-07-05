#!/usr/bin/env python3
"""
Build a non-destructive SQL apply plan for HomePilot.

The deployment manifest says what should be applied. This pack gives an
operator or customer IT reviewer the exact SQL bundle, checksums, psql command,
and post-apply verification path without storing database credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).parent.resolve()
HOME_ROOT = HERE.parent

SQL_APPLY_STEPS = (
    {
        "name": "base_schema",
        "relative_path": "platform/supabase_schema.sql",
        "purpose": "Create HomePilot tables, indexes, RLS helpers, and RLS policies.",
    },
    {
        "name": "dashboard_views",
        "relative_path": "platform/dashboard_views.sql",
        "purpose": "Create tenant/module/partner-safe dashboard and export read models.",
    },
)

EXPECTED_OBJECTS = (
    "homepilot_tenants",
    "homepilot_memberships",
    "homepilot_modules",
    "homepilot_tenant_modules",
    "homepilot_properties",
    "homepilot_campaigns",
    "homepilot_campaign_targets",
    "homepilot_assessments",
    "homepilot_interactions",
    "homepilot_exports",
    "homepilot_property_intelligence",
    "homepilot_property_export",
    "homepilot_campaign_metrics",
    "homepilot_module_metrics",
    "homepilot_second_brain_edges",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def statement_count(sql: str) -> int:
    return sum(1 for statement in sql.split(";") if statement.strip())


def _step_record(step: dict[str, str], root: Path) -> dict[str, Any]:
    path = root / step["relative_path"]
    if not path.exists():
        return {
            "name": step["name"],
            "relative_path": step["relative_path"],
            "path": str(path),
            "purpose": step["purpose"],
            "status": "missing",
        }
    body = path.read_text(encoding="utf-8")
    return {
        "name": step["name"],
        "relative_path": step["relative_path"],
        "path": str(path),
        "purpose": step["purpose"],
        "status": "ready",
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "statement_count": statement_count(body),
    }


def build_apply_sql(root: Path = HOME_ROOT, release_label: str = "local", created_at: str | None = None) -> str:
    created_at = created_at or utc_now()
    chunks = [
        "-- HomePilot SQL apply bundle.",
        f"-- Release: {release_label}",
        f"-- Generated: {created_at}",
        "-- Apply with psql --set ON_ERROR_STOP=1 or paste into the Supabase SQL editor after review.",
        "",
        "begin;",
        "",
    ]
    for index, step in enumerate(SQL_APPLY_STEPS, start=1):
        path = root / step["relative_path"]
        chunks.extend([
            f"-- Step {index}: {step['name']}",
            f"-- Source: {step['relative_path']}",
            f"-- Purpose: {step['purpose']}",
            "",
        ])
        if path.exists():
            chunks.append(path.read_text(encoding="utf-8").rstrip())
            chunks.append("")
        else:
            chunks.append(f"-- MISSING SOURCE FILE: {step['relative_path']}")
            chunks.append("")
    chunks.extend([
        "commit;",
        "",
    ])
    return "\n".join(chunks)


def build_post_apply_verification_sql() -> str:
    values = ",\n  ".join(f"('{name}')" for name in EXPECTED_OBJECTS)
    return f"""-- HomePilot post-apply smoke verification.
-- This SQL is informational. The authoritative live proof is:
-- python3 platform/homepilot_live_schema_verification.py --live

with expected_objects(name) as (
  values
  {values}
)
select
  name as object_name,
  to_regclass('public.' || name) is not null as exists_in_public_schema
from expected_objects
order by name;
"""


def build_sql_apply_plan(
    root: Path = HOME_ROOT,
    release_label: str = "local",
    db_url_env: str = "HOMEPILOT_SUPABASE_DB_URL",
) -> dict[str, Any]:
    created_at = utc_now()
    steps = [_step_record(step, root) for step in SQL_APPLY_STEPS]
    missing = [step["relative_path"] for step in steps if step["status"] != "ready"]
    apply_sql = build_apply_sql(root=root, release_label=release_label, created_at=created_at)
    verification_sql = build_post_apply_verification_sql()
    status = "pass" if not missing else "fail"
    apply_order = [step["relative_path"] for step in steps]
    return {
        "plan_type": "homepilot_sql_apply_plan",
        "created_at": created_at,
        "release_label": release_label,
        "status": status,
        "root": str(root),
        "apply_order": apply_order,
        "transactional": True,
        "steps": steps,
        "issues": [f"Missing SQL source: {path}" for path in missing],
        "apply_bundle": {
            "statement_count": statement_count(apply_sql),
            "bytes": len(apply_sql.encode("utf-8")),
            "sha256": sha256_bytes(apply_sql.encode("utf-8")),
        },
        "post_apply_verification": {
            "object_count": len(EXPECTED_OBJECTS),
            "bytes": len(verification_sql.encode("utf-8")),
            "sha256": sha256_bytes(verification_sql.encode("utf-8")),
        },
        "operator_commands": {
            "psql_apply": f'psql "${db_url_env}" --set ON_ERROR_STOP=1 --file apply.sql',
            "psql_smoke_verify": f'psql "${db_url_env}" --set ON_ERROR_STOP=1 --file post_apply_verification.sql',
            "authoritative_verify": "python3 platform/homepilot_live_schema_verification.py --out-dir /tmp/homepilot_schema_verification_live --live",
        },
        "guardrails": {
            "stores_database_url": False,
            "stores_service_role_key": False,
            "stores_customer_tokens": False,
            "requires_review_before_apply": True,
            "requires_live_schema_verification_after_apply": True,
        },
        "rollback_note": "Create a Supabase backup or migration checkpoint before applying. Schema files are forward/idempotent; use Supabase restore/migration rollback for schema rollback and homepilot_recovery.py for tenant data rollback.",
    }


def render_sql_apply_runbook(plan: dict[str, Any]) -> str:
    lines = [
        "# HomePilot SQL Apply Plan",
        "",
        f"Release: {plan['release_label']}",
        f"Created: {plan['created_at']}",
        f"Status: {plan['status']}",
        f"Transactional: {str(plan['transactional']).lower()}",
        "",
        "## Apply Order",
        "",
    ]
    for index, step in enumerate(plan["steps"], start=1):
        lines.append(f"{index}. {step['relative_path']} - {step['purpose']}")
        lines.append(f"   - status: {step['status']}")
        lines.append(f"   - sha256: {step.get('sha256', 'missing')}")
    lines += [
        "",
        "## Commands",
        "",
        "```bash",
        plan["operator_commands"]["psql_apply"],
        plan["operator_commands"]["psql_smoke_verify"],
        plan["operator_commands"]["authoritative_verify"],
        "```",
        "",
        "## Guardrails",
        "",
        "- Review `apply.sql` before applying it to Supabase.",
        "- Keep database URLs, service-role keys, anon keys, fixture passwords, and customer tokens in environment variables only.",
        "- Archive `sql_apply_plan.json`, `apply.sql`, `post_apply_verification.sql`, and the live schema verification report together.",
        "- Production remains blocked until `homepilot_live_schema_verification.py --live` returns `production_verified: true`.",
        "",
        "## Rollback",
        "",
        plan["rollback_note"],
    ]
    if plan["issues"]:
        lines += ["", "## Issues", ""]
        lines.extend(f"- {issue}" for issue in plan["issues"])
    lines.append("")
    return "\n".join(lines)


def build_sql_apply_plan_pack(
    out_dir: Path,
    root: Path = HOME_ROOT,
    release_label: str = "local",
    db_url_env: str = "HOMEPILOT_SUPABASE_DB_URL",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = build_sql_apply_plan(root=root, release_label=release_label, db_url_env=db_url_env)
    apply_sql = build_apply_sql(root=root, release_label=release_label, created_at=plan["created_at"])
    verification_sql = build_post_apply_verification_sql()

    plan_path = out_dir / "sql_apply_plan.json"
    runbook_path = out_dir / "SQL_APPLY_PLAN.md"
    apply_path = out_dir / "apply.sql"
    verification_path = out_dir / "post_apply_verification.sql"

    plan["paths"] = {
        "sql_apply_plan": str(plan_path),
        "sql_apply_runbook": str(runbook_path),
        "apply_sql": str(apply_path),
        "post_apply_verification_sql": str(verification_path),
    }
    write_text(apply_path, apply_sql)
    write_text(verification_path, verification_sql)
    write_json(plan_path, plan)
    write_text(runbook_path, render_sql_apply_runbook(plan))
    return {
        "pack_type": "homepilot_sql_apply_plan_pack",
        "created_at": utc_now(),
        "status": plan["status"],
        "paths": plan["paths"],
        "plan": plan,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot SQL apply plan")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--release-label", default="local")
    parser.add_argument("--db-url-env", default="HOMEPILOT_SUPABASE_DB_URL")
    args = parser.parse_args()

    pack = build_sql_apply_plan_pack(
        out_dir=args.out_dir,
        release_label=args.release_label,
        db_url_env=args.db_url_env,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": pack["status"],
        "sql_apply_plan": pack["paths"]["sql_apply_plan"],
        "sql_apply_runbook": pack["paths"]["sql_apply_runbook"],
        "apply_sql": pack["paths"]["apply_sql"],
        "post_apply_verification_sql": pack["paths"]["post_apply_verification_sql"],
    }, indent=2, ensure_ascii=False))
    if pack["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
