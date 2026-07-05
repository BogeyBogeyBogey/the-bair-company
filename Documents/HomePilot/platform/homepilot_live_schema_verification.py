#!/usr/bin/env python3
"""
HomePilot live Supabase schema verification.

The deployment manifest proves what should be applied. This verifier proves
whether the target database actually exposes the expected HomePilot contract:
tables, columns, views, functions, security-invoker views, and RLS policies.

Dry-run mode checks the local SQL contract only. Live mode additionally queries
Postgres metadata through psql using HOMEPILOT_SUPABASE_DB_URL, SUPABASE_DB_URL,
or DATABASE_URL. Secrets are never written to the report.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).parent.resolve()
HOME_ROOT = HERE.parent

SQL_FILES = (
    HOME_ROOT / "platform" / "supabase_schema.sql",
    HOME_ROOT / "platform" / "dashboard_views.sql",
)

EXPECTED_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "homepilot_tenants": ("id", "name", "slug", "settings"),
    "homepilot_memberships": ("tenant_id", "user_id", "role", "partner_id"),
    "homepilot_modules": ("key", "label", "category", "metric_catalog"),
    "homepilot_tenant_modules": ("tenant_id", "module_key", "enabled"),
    "homepilot_properties": ("id", "tenant_id", "address", "core"),
    "homepilot_property_media": ("tenant_id", "property_id", "module_key", "metadata"),
    "homepilot_campaigns": ("id", "tenant_id", "module_key", "partner_id", "partner_name", "metadata"),
    "homepilot_campaign_targets": ("tenant_id", "campaign_id", "property_id", "module_key", "metadata"),
    "homepilot_assessments": ("id", "tenant_id", "property_id", "module_key", "metrics", "evidence"),
    "homepilot_interactions": ("tenant_id", "property_id", "campaign_id", "module_key", "interaction_type", "response_status", "metadata"),
    "homepilot_response_insights": ("tenant_id", "campaign_id", "module_key", "supporting_metrics"),
    "homepilot_exports": ("tenant_id", "module_key", "export_type", "filters", "row_count"),
    "homepilot_audit_events": ("tenant_id", "actor_user_id", "module_key", "event_type", "details"),
    "homepilot_platform_benchmarks": ("module_key", "benchmark_key", "cohort", "sample_size", "metrics"),
    "homepilot_source_runs": ("id", "tenant_id", "source_name", "source_url", "licence", "allowed_use", "status", "metadata"),
    "homepilot_geographies": ("id", "tenant_id", "source_run_id", "geography_type", "geography_key", "geometry_ref", "metadata"),
    "homepilot_public_features": ("tenant_id", "geography_id", "source_run_id", "feature_key", "feature_value", "licence", "allowed_use"),
    "homepilot_property_enrichments": ("tenant_id", "property_id", "source_run_id", "geography_id", "enrichment_type", "public_fields", "provenance"),
}

EXPECTED_VIEW_COLUMNS: dict[str, tuple[str, ...]] = {
    "homepilot_property_intelligence": (
        "tenant_id",
        "property_id",
        "address",
        "module_key",
        "partner_id",
        "partner_name",
        "score",
        "metrics",
        "campaign_status",
        "latest_response_status",
    ),
    "homepilot_property_export": (
        "tenant_id",
        "property_id",
        "address",
        "module_key",
        "partner_id",
        "partner_name",
        "score",
        "metrics",
    ),
    "homepilot_property_public_enrichment": (
        "tenant_id",
        "property_id",
        "address",
        "partner_id",
        "partner_name",
        "enrichment_type",
        "public_fields",
        "confidence",
        "provenance",
        "source_run_id",
        "source_name",
        "licence",
        "allowed_use",
        "attribution",
    ),
    "homepilot_campaign_metrics": (
        "tenant_id",
        "campaign_id",
        "module_key",
        "partner_id",
        "partner_name",
        "target_count",
        "contacted_count",
        "response_count",
        "appointment_count",
        "no_response_count",
        "response_rate_pct",
        "target_response_rate_pct",
    ),
    "homepilot_module_metrics": (
        "tenant_id",
        "module_key",
        "property_count",
        "top_opportunity_count",
        "contacted_count",
        "response_count",
        "appointment_count",
        "response_rate_pct",
        "target_response_rate_pct",
    ),
    "homepilot_second_brain_edges": (
        "tenant_id",
        "module_key",
        "source_type",
        "source_id",
        "target_type",
        "target_id",
        "edge_type",
    ),
}

EXPECTED_FUNCTIONS = (
    "homepilot_membership_role",
    "homepilot_membership_partner_id",
    "homepilot_partner_scope_matches",
    "homepilot_property_partner_id",
    "homepilot_campaign_partner_id",
    "homepilot_has_tenant_access",
    "homepilot_can_write_tenant",
    "homepilot_has_module_access",
    "homepilot_metrics_for_customer",
)

EXPECTED_POLICIES: dict[str, tuple[str, ...]] = {
    "homepilot_tenants": ("homepilot tenants read own",),
    "homepilot_memberships": ("homepilot memberships read own",),
    "homepilot_modules": ("homepilot modules read",),
    "homepilot_tenant_modules": ("homepilot tenant modules read own",),
    "homepilot_properties": ("homepilot properties read own", "homepilot properties write own"),
    "homepilot_property_media": ("homepilot media read own module",),
    "homepilot_campaigns": ("homepilot campaigns read own module",),
    "homepilot_campaign_targets": ("homepilot campaign targets read own module",),
    "homepilot_assessments": ("homepilot assessments read own module",),
    "homepilot_interactions": ("homepilot interactions read own module",),
    "homepilot_response_insights": ("homepilot response insights read own module",),
    "homepilot_exports": ("homepilot exports read own",),
    "homepilot_audit_events": ("homepilot audit events read own", "homepilot audit events insert managers"),
    "homepilot_source_runs": ("homepilot source runs read own", "homepilot source runs write managers"),
    "homepilot_geographies": ("homepilot geographies read own", "homepilot geographies write managers"),
    "homepilot_public_features": ("homepilot public features read own", "homepilot public features write managers"),
    "homepilot_property_enrichments": ("homepilot property enrichments read own", "homepilot property enrichments write managers"),
}

LOCAL_MARKERS = (
    "homepilot_memberships (\n  tenant_id uuid",
    "partner_id text",
    "homepilot_partner_scope_matches",
    "homepilot_membership_partner_id",
    "homepilot_property_partner_id",
    "homepilot_campaign_partner_id",
    "with (security_invoker = true)",
    "homepilot_property_intelligence",
    "homepilot_property_public_enrichment",
    "homepilot_source_runs",
    "homepilot_campaign_metrics",
    "homepilot public features read own",
    "'landing_page_scan'",
    "'appointment'",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _check(name: str, status: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"name": name, "status": status, "detail": detail, **extra}


def _sql_body() -> str:
    chunks: list[str] = []
    for path in SQL_FILES:
        chunks.append(path.read_text(encoding="utf-8", errors="ignore") if path.exists() else "")
    return "\n".join(chunks).lower()


def build_local_contract_checks() -> list[dict[str, Any]]:
    body = _sql_body()
    checks: list[dict[str, Any]] = []
    missing_files = [str(path) for path in SQL_FILES if not path.exists()]
    checks.append(_check(
        "local_sql_files",
        "pass" if not missing_files else "fail",
        "Required SQL files are present." if not missing_files else "One or more required SQL files are missing.",
        missing=missing_files,
    ))
    missing_markers = [marker for marker in LOCAL_MARKERS if marker.lower() not in body]
    checks.append(_check(
        "local_contract_markers",
        "pass" if not missing_markers else "fail",
        "Local SQL contains required tenant/module/partner/RLS markers." if not missing_markers else "Local SQL is missing required contract markers.",
        missing=missing_markers,
    ))
    return checks


def _values(names: tuple[str, ...] | list[str]) -> str:
    return ", ".join(f"('{name}')" for name in names)


def _metadata_sql() -> str:
    table_names = tuple(EXPECTED_TABLE_COLUMNS)
    view_names = tuple(EXPECTED_VIEW_COLUMNS)
    function_names = EXPECTED_FUNCTIONS
    return f"""
with
expected_tables(name) as (values {_values(table_names)}),
expected_views(name) as (values {_values(view_names)}),
expected_functions(name) as (values {_values(function_names)}),
table_columns as (
  select table_name, jsonb_agg(column_name order by ordinal_position) as columns
  from information_schema.columns
  where table_schema = 'public'
    and table_name in (select name from expected_tables)
  group by table_name
),
view_columns as (
  select table_name, jsonb_agg(column_name order by ordinal_position) as columns
  from information_schema.columns
  where table_schema = 'public'
    and table_name in (select name from expected_views)
  group by table_name
),
table_rls as (
  select c.relname as table_name, c.relrowsecurity as rls_enabled
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public'
    and c.relkind = 'r'
    and c.relname in (select name from expected_tables)
),
view_options as (
  select c.relname as view_name, coalesce(to_jsonb(c.reloptions), '[]'::jsonb) as reloptions
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public'
    and c.relkind in ('v', 'm')
    and c.relname in (select name from expected_views)
),
policies as (
  select tablename as table_name, jsonb_agg(policyname order by policyname) as policies
  from pg_policies
  where schemaname = 'public'
    and tablename in (select name from expected_tables)
  group by tablename
),
functions as (
  select p.proname as function_name, bool_or(p.prosecdef) as security_definer
  from pg_proc p
  join pg_namespace n on n.oid = p.pronamespace
  where n.nspname = 'public'
    and p.proname in (select name from expected_functions)
  group by p.proname
)
select jsonb_build_object(
  'tables', (
    select jsonb_object_agg(
      et.name,
      jsonb_build_object(
        'exists', tc.table_name is not null,
        'columns', coalesce(tc.columns, '[]'::jsonb),
        'rls_enabled', coalesce(tr.rls_enabled, false),
        'policies', coalesce(pol.policies, '[]'::jsonb)
      )
    )
    from expected_tables et
    left join table_columns tc on tc.table_name = et.name
    left join table_rls tr on tr.table_name = et.name
    left join policies pol on pol.table_name = et.name
  ),
  'views', (
    select jsonb_object_agg(
      ev.name,
      jsonb_build_object(
        'exists', vc.table_name is not null,
        'columns', coalesce(vc.columns, '[]'::jsonb),
        'reloptions', coalesce(vo.reloptions, '[]'::jsonb)
      )
    )
    from expected_views ev
    left join view_columns vc on vc.table_name = ev.name
    left join view_options vo on vo.view_name = ev.name
  ),
  'functions', (
    select jsonb_object_agg(
      ef.name,
      jsonb_build_object(
        'exists', fn.function_name is not null,
        'security_definer', coalesce(fn.security_definer, false)
      )
    )
    from expected_functions ef
    left join functions fn on fn.function_name = ef.name
  )
)::text;
"""


def _sanitize_error(value: str) -> str:
    value = re.sub(r"postgres(ql)?://[^\\s]+", "postgresql://[redacted]", value)
    value = re.sub(r"(password=)[^\\s]+", r"\1[redacted]", value, flags=re.IGNORECASE)
    return value[:1200]


def run_psql_metadata_query(db_url: str, psql_bin: str = "psql") -> dict[str, Any]:
    result = subprocess.run(
        [psql_bin, "--no-align", "--tuples-only", "--quiet", "--set", "ON_ERROR_STOP=1", db_url, "-c", _metadata_sql()],
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(_sanitize_error((result.stderr or result.stdout or "psql metadata query failed").strip()))
    output = (result.stdout or "").strip()
    if not output:
        raise RuntimeError("psql metadata query returned no output")
    return json.loads(output)


def evaluate_live_metadata(metadata: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    tables = metadata.get("tables", {}) if isinstance(metadata.get("tables"), dict) else {}
    views = metadata.get("views", {}) if isinstance(metadata.get("views"), dict) else {}
    functions = metadata.get("functions", {}) if isinstance(metadata.get("functions"), dict) else {}

    for table, expected_columns in EXPECTED_TABLE_COLUMNS.items():
        found = tables.get(table, {}) if isinstance(tables.get(table), dict) else {}
        columns = set(found.get("columns") or [])
        missing = [column for column in expected_columns if column not in columns]
        expected_policies = EXPECTED_POLICIES.get(table, ())
        policies = set(found.get("policies") or [])
        missing_policies = [policy for policy in expected_policies if policy not in policies]
        issues = []
        if not found.get("exists"):
            issues.append("missing table")
        if missing:
            issues.append(f"missing columns: {', '.join(missing)}")
        if not found.get("rls_enabled"):
            issues.append("RLS disabled")
        if missing_policies:
            issues.append(f"missing policies: {', '.join(missing_policies)}")
        status = "pass" if not issues else "fail"
        detail = f"{table} matches expected columns/RLS/policies." if status == "pass" else f"{table} has schema issues."
        checks.append(_check(
            f"table.{table}",
            status,
            detail,
            missing_columns=missing,
            missing_policies=missing_policies,
            rls_enabled=bool(found.get("rls_enabled")),
        ))
        failures.extend([f"{table}: {issue}" for issue in issues])

    for view, expected_columns in EXPECTED_VIEW_COLUMNS.items():
        found = views.get(view, {}) if isinstance(views.get(view), dict) else {}
        columns = set(found.get("columns") or [])
        missing = [column for column in expected_columns if column not in columns]
        reloptions = [str(option).lower() for option in (found.get("reloptions") or [])]
        security_invoker = any(option == "security_invoker=true" for option in reloptions)
        issues = []
        if not found.get("exists"):
            issues.append("missing view")
        if missing:
            issues.append(f"missing columns: {', '.join(missing)}")
        if not security_invoker:
            issues.append("security_invoker=true not reported")
        status = "pass" if not issues else "fail"
        detail = f"{view} is security-invoker and exposes expected columns." if status == "pass" else f"{view} has view contract issues."
        checks.append(_check(
            f"view.{view}",
            status,
            detail,
            missing_columns=missing,
            security_invoker=security_invoker,
        ))
        failures.extend([f"{view}: {issue}" for issue in issues])

    for function in EXPECTED_FUNCTIONS:
        found = functions.get(function, {}) if isinstance(functions.get(function), dict) else {}
        exists = bool(found.get("exists"))
        status = "pass" if exists else "fail"
        checks.append(_check(
            f"function.{function}",
            status,
            f"{function} exists." if exists else f"{function} is missing.",
            security_definer=bool(found.get("security_definer")),
        ))
        if not exists:
            failures.append(f"{function}: missing function")

    return checks, failures


def build_schema_verification_report(
    out_dir: Path,
    live: bool = False,
    db_url: str = "",
    env: dict[str, str] | None = None,
    psql_bin: str = "psql",
) -> dict[str, Any]:
    env = dict(os.environ if env is None else env)
    db_url = db_url or env.get("HOMEPILOT_SUPABASE_DB_URL") or env.get("SUPABASE_DB_URL") or env.get("DATABASE_URL") or ""
    out_dir.mkdir(parents=True, exist_ok=True)

    local_checks = build_local_contract_checks()
    local_failures = [check["detail"] for check in local_checks if check["status"] == "fail"]
    checks = list(local_checks)
    failures = list(local_failures)
    warnings: list[str] = []
    metadata_path = out_dir / "live_schema_metadata.json"

    live_metadata: dict[str, Any] | None = None
    if live:
        if not db_url:
            failures.append("Missing HOMEPILOT_SUPABASE_DB_URL, SUPABASE_DB_URL, or DATABASE_URL for live schema verification.")
            checks.append(_check("live.database_url", "fail", "No live database URL was provided."))
        elif shutil.which(psql_bin) is None:
            failures.append(f"psql binary {psql_bin!r} is not available.")
            checks.append(_check("live.psql", "fail", "psql is required for metadata verification."))
        else:
            checks.append(_check("live.psql", "pass", "psql is available."))
            try:
                live_metadata = run_psql_metadata_query(db_url, psql_bin=psql_bin)
                write_json(metadata_path, live_metadata)
                live_checks, live_failures = evaluate_live_metadata(live_metadata)
                checks.extend(live_checks)
                failures.extend(live_failures)
            except Exception as exc:  # pragma: no cover - exercised by integration environments.
                failures.append(_sanitize_error(str(exc)))
                checks.append(_check("live.metadata_query", "fail", "Live metadata query failed.", error=_sanitize_error(str(exc))))
    else:
        warnings.append("Dry-run mode: local SQL contract checked, live database metadata not queried.")
        checks.append(_check("live.metadata_query", "skipped", "Run with --live and a DB URL to verify the deployed Supabase schema."))

    contract_status = "pass" if not local_failures else "fail"
    live_status = "not_run" if not live else ("pass" if not failures else "fail")
    if live:
        status = "pass" if contract_status == "pass" and live_status == "pass" else "fail"
    else:
        status = "dry_run" if contract_status == "pass" else "fail"

    report = {
        "report_type": "homepilot_live_schema_verification",
        "created_at": utc_now(),
        "status": status,
        "mode": "live" if live else "dry_run",
        "production_verified": bool(live and status == "pass"),
        "contract_status": contract_status,
        "live_status": live_status,
        "db_url_present": bool(db_url),
        "checks": checks,
        "summary": {
            "tables_expected": len(EXPECTED_TABLE_COLUMNS),
            "views_expected": len(EXPECTED_VIEW_COLUMNS),
            "functions_expected": len(EXPECTED_FUNCTIONS),
            "policies_expected": sum(len(value) for value in EXPECTED_POLICIES.values()),
            "checks": len(checks),
            "failures": len(failures),
            "warnings": len(warnings),
        },
        "failures": failures,
        "warnings": warnings,
        "paths": {
            "schema_verification": str(out_dir / "schema_verification.json"),
            "runbook": str(out_dir / "SCHEMA_VERIFICATION.md"),
            "live_metadata": str(metadata_path) if live_metadata is not None else None,
        },
    }
    write_json(out_dir / "schema_verification.json", report)
    write_text(out_dir / "SCHEMA_VERIFICATION.md", render_schema_verification_runbook(report))
    return report


def render_schema_verification_runbook(report: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Live Schema Verification",
        "",
        f"Created: {report['created_at']}",
        f"Mode: {report['mode']}",
        f"Status: {report['status']}",
        f"Production verified: {str(report['production_verified']).lower()}",
        "",
        "## What This Proves",
        "",
        "- Local SQL still contains the HomePilot tenant/module/partner access contract.",
        "- Live mode verifies deployed public tables, required columns, RLS status, policies, views, and functions.",
        "- The report intentionally stores only metadata and never stores database credentials.",
        "",
        "## Live Command",
        "",
        "```bash",
        "HOMEPILOT_SUPABASE_DB_URL='postgresql://...' \\",
        "python3 platform/homepilot_live_schema_verification.py --out-dir /tmp/homepilot_schema_verification_live --live",
        "```",
        "",
        "## Checks",
        "",
    ]
    for check in report["checks"]:
        lines.append(f"- {check['name']}: {check['status']} - {check['detail']}")
    if report["failures"]:
        lines += ["", "## Failures", ""]
        lines.extend(f"- {failure}" for failure in report["failures"])
    if report["warnings"]:
        lines += ["", "## Warnings", ""]
        lines.extend(f"- {warning}" for warning in report["warnings"])
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify HomePilot local/live schema contract")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--db-url", default="")
    parser.add_argument("--psql-bin", default="psql")
    args = parser.parse_args()

    report = build_schema_verification_report(
        out_dir=args.out_dir,
        live=args.live,
        db_url=args.db_url,
        psql_bin=args.psql_bin,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": report["status"],
        "production_verified": report["production_verified"],
        "schema_verification": report["paths"]["schema_verification"],
        "runbook": report["paths"]["runbook"],
        "failures": report["failures"],
    }, indent=2, ensure_ascii=False))
    if report["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
