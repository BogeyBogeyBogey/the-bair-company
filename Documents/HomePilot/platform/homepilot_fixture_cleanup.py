#!/usr/bin/env python3
"""
Cleanup planning for HomePilot live RLS fixtures.

The launch runner seeds temporary tenants and data to prove tenant/module RLS.
This module builds a reviewable cleanup plan after the evidence is written. It
does not execute destructive work by default; the SQL is meant for controlled
review and application after the launch report has been archived.
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FIXTURE_MARKER = "homepilot_live_fixture"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_uuid(value: Any, label: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{label} must be a UUID: {value}") from exc


def _sql_literal(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _sql_list(values: list[str]) -> str:
    return "(" + ", ".join(_sql_literal(value) for value in values) + ")"


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def _fixture_manifest_from_report(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("fixture_type") == "homepilot_live_rls_fixture":
        return data
    manifest = data.get("fixture_manifest")
    if isinstance(manifest, dict) and manifest.get("fixture_type") == "homepilot_live_rls_fixture":
        return manifest
    raise ValueError("Expected a fixture manifest or launch report with fixture_manifest")


def _auth_users_from_report(data: dict[str, Any]) -> list[dict[str, Any]]:
    users = data.get("auth_users", [])
    return users if isinstance(users, list) else []


def build_fixture_cleanup_plan(
    manifest_or_report: dict[str, Any],
    include_auth_users: bool = False,
) -> dict[str, Any]:
    fixture_manifest = _fixture_manifest_from_report(manifest_or_report)
    tenants = fixture_manifest.get("tenants", [])
    if not isinstance(tenants, list) or not tenants:
        raise ValueError("Fixture manifest must contain tenants")

    tenant_ids = []
    for index, tenant in enumerate(tenants):
        if not isinstance(tenant, dict):
            raise ValueError(f"Invalid tenant entry at index {index}: {tenant}")
        tenant_ids.append(_ensure_uuid(tenant.get("tenant_id"), f"tenants[{index}].tenant_id"))

    auth_users = []
    if include_auth_users:
        for user in _auth_users_from_report(manifest_or_report):
            if not isinstance(user, dict):
                continue
            user_id = user.get("user_id")
            if user_id:
                auth_users.append({
                    "label": user.get("label", ""),
                    "email": user.get("email", ""),
                    "user_id": _ensure_uuid(user_id, "auth_users.user_id"),
                    "status": user.get("status", ""),
                })

    ids = _sql_list(tenant_ids)
    marker = _sql_literal(FIXTURE_MARKER)
    sql = [
        "begin;",
        "-- Delete only HomePilot live RLS fixture tenants.",
        "-- The fixture marker guard prevents accidental deletion of real customer tenants.",
        "delete from public.homepilot_tenants",
        f"where id in {ids}",
        f"  and settings ->> 'fixture' = {marker};",
        "commit;",
    ]

    record_counts = fixture_manifest.get("record_counts") if isinstance(fixture_manifest.get("record_counts"), dict) else {}
    warnings = [
        "Archive launch_report.json and rls_probe_report.json before applying cleanup SQL.",
        "The SQL deletes fixture tenants; tenant foreign keys cascade fixture memberships, modules, properties, campaigns, targets, assessments, interactions, insights, and exports.",
    ]
    if auth_users:
        warnings.append("Auth user deletion is not included in SQL; remove fixture auth users separately after evidence is archived.")
    else:
        warnings.append("Auth users are not included; pass a launch report with include_auth_users to review temporary auth accounts.")

    return {
        "plan_type": "homepilot_live_fixture_cleanup",
        "created_at": utc_now(),
        "status": "ready_for_review",
        "tenant_ids": tenant_ids,
        "tenant_count": len(tenant_ids),
        "record_counts": record_counts,
        "auth_users": auth_users,
        "include_auth_users": include_auth_users,
        "sql": sql,
        "warnings": warnings,
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_sql(path: Path, sql_lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sql_lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build cleanup evidence for HomePilot live RLS fixtures")
    parser.add_argument("--json", required=True, type=Path, help="Fixture manifest or launch_report.json")
    parser.add_argument("--include-auth-users", action="store_true")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--sql-out", type=Path)
    args = parser.parse_args()

    plan = build_fixture_cleanup_plan(load_json(args.json), include_auth_users=args.include_auth_users)
    write_json(args.out, plan)
    if args.sql_out:
        write_sql(args.sql_out, plan["sql"])
    print(json.dumps({
        "output": str(args.out),
        "sql": str(args.sql_out) if args.sql_out else None,
        "status": plan["status"],
        "tenant_count": plan["tenant_count"],
    }, indent=2))


if __name__ == "__main__":
    main()
