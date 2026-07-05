#!/usr/bin/env python3
"""
HomePilot operational health checks.

This is the quick operator check for a market-ready online platform. By default
it is non-destructive and local: files, SQL contracts, client assets, and
configuration shape. With --live it also verifies Supabase REST reachability.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_store import HOME_ROOT, load_dotenv_file


HERE = Path(__file__).parent.resolve()

for env_path in (HOME_ROOT / ".env", HERE / ".env"):
    load_dotenv_file(env_path)

REQUIRED_FILES = (
    "platform/supabase_schema.sql",
    "platform/dashboard_views.sql",
    "platform/homepilot_account_access.py",
    "platform/homepilot_customer_access_verification.py",
    "platform/homepilot_api_contract.py",
    "platform/homepilot_processing_register.py",
    "platform/homepilot_store.py",
    "platform/homepilot_territory_plan.py",
    "platform/homepilot_visual_intelligence.py",
    "platform/homepilot_enrichment_refresh.py",
    "platform/homepilot_audit_trail.py",
    "platform/homepilot_campaign_learning.py",
    "platform/homepilot_customer_brief.py",
    "platform/homepilot_data_dictionary.py",
    "platform/homepilot_integrations.py",
    "platform/homepilot_integration_sync.py",
    "platform/homepilot_hosting.py",
    "platform/homepilot_launch.py",
    "platform/homepilot_live_schema_verification.py",
    "platform/homepilot_live_readiness.py",
    "platform/homepilot_opportunity_dossier.py",
    "platform/homepilot_ops_status.py",
    "platform/homepilot_monitoring.py",
    "platform/homepilot_portal.py",
    "platform/homepilot_source_ledger.py",
    "platform/homepilot_rls_probe.py",
    "platform/homepilot_recovery.py",
    "platform/homepilot_roi_forecast.py",
    "platform/homepilot_release_pack.py",
    "platform/homepilot_production_cutover.py",
    "platform/homepilot_deployment.py",
    "platform/homepilot_demo_room.py",
    "platform/homepilot_enrichment.py",
    "platform/PRODUCTION_LAUNCH.md",
    ".env.example",
    "client/index.html",
    "client/app.js",
    "client/styles.css",
    "client/sample-data.js",
    "client/live-config.js",
    "client/live-data.js",
)

DASHBOARD_SQL_MARKERS = (
    "with (security_invoker = true)",
    "homepilot_has_tenant_access",
    "homepilot_has_module_access",
    "homepilot_metrics_for_customer",
    "homepilot_property_intelligence",
    "homepilot_property_export",
    "homepilot_campaign_metrics",
    "homepilot_module_metrics",
    "homepilot_second_brain_edges",
)

SCHEMA_MARKERS = (
    "enable row level security",
    "homepilot_has_tenant_access",
    "homepilot_has_module_access",
    "homepilot_can_write_tenant",
    "homepilot_tenants",
    "homepilot_tenant_modules",
    "homepilot_platform_benchmarks",
    "homepilot_audit_events",
    "sample_size >= 10",
)

PLACEHOLDER_FRAGMENTS = (
    "your-homepilot-project",
    "service-role-key",
    "anon-key",
    "eyJ...",
    "replace-",
)

ENV_EXAMPLE_KEYS = (
    "HOMEPILOT_SUPABASE_URL",
    "HOMEPILOT_SUPABASE_SERVICE_KEY",
    "HOMEPILOT_SUPABASE_ANON_KEY",
    "HOMEPILOT_SUPABASE_DB_URL",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_ANON_KEY",
    "SUPABASE_DB_URL",
    "DATABASE_URL",
)

SECRET_LIKE_PATTERNS = {
    "jwt_like_token": re.compile(r"=\s*eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _check(name: str, status: str, **details: Any) -> dict[str, Any]:
    return {"name": name, "status": status, **details}


def _overall_status(checks: list[dict[str, Any]]) -> str:
    if any(check["status"] == "fail" for check in checks):
        return "fail"
    if any(check["status"] == "warn" for check in checks):
        return "warn"
    return "pass"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def check_required_files() -> dict[str, Any]:
    missing = [rel for rel in REQUIRED_FILES if not (HOME_ROOT / rel).exists()]
    return _check("required_files", "pass" if not missing else "fail", missing=missing, checked=len(REQUIRED_FILES))


def check_env_template() -> dict[str, Any]:
    path = HOME_ROOT / ".env.example"
    if not path.exists():
        return _check("env_template", "fail", missing=[".env.example"])
    body = _read(path)
    keys = set()
    for line in body.splitlines():
        if "=" in line and not line.strip().startswith("#"):
            keys.add(line.split("=", 1)[0].strip())
    missing = [key for key in ENV_EXAMPLE_KEYS if key not in keys]
    secret_like = [label for label, pattern in SECRET_LIKE_PATTERNS.items() if pattern.search(body)]
    has_launch_hint = "homepilot_launch.py rls-fixture" in body and "--window-password" in body and "--facade-password" in body
    has_schema_hint = "homepilot_live_schema_verification.py" in body and "HOMEPILOT_SUPABASE_DB_URL" in body
    has_live_readiness_hint = "homepilot_live_readiness.py" in body and "HOMEPILOT_RLS_WINDOW_PASSWORD" in body
    issues = []
    if missing:
        issues.append(f"missing keys: {missing}")
    if secret_like:
        issues.append(f"secret-like values present: {secret_like}")
    if not has_launch_hint:
        issues.append("missing live RLS launch fixture command hint")
    if not has_schema_hint:
        issues.append("missing live schema verification command hint")
    if not has_live_readiness_hint:
        issues.append("missing live readiness command hint")
    return _check(
        "env_template",
        "pass" if not issues else "fail",
        path=str(path),
        missing=missing,
        secret_like=secret_like,
        has_launch_hint=has_launch_hint,
        has_schema_hint=has_schema_hint,
        has_live_readiness_hint=has_live_readiness_hint,
        issues=issues,
    )


def check_dashboard_sql() -> dict[str, Any]:
    path = HERE / "dashboard_views.sql"
    if not path.exists():
        return _check("dashboard_sql", "fail", missing=["platform/dashboard_views.sql"])
    sql = _read(path).lower()
    missing = [marker for marker in DASHBOARD_SQL_MARKERS if marker not in sql]
    return _check("dashboard_sql", "pass" if not missing else "fail", missing=missing)


def check_schema_sql() -> dict[str, Any]:
    path = HERE / "supabase_schema.sql"
    if not path.exists():
        return _check("schema_sql", "fail", missing=["platform/supabase_schema.sql"])
    sql = _read(path).lower()
    missing = [marker for marker in SCHEMA_MARKERS if marker not in sql]
    rls_count = sql.count("enable row level security")
    status = "pass" if not missing and rls_count >= 8 else "fail"
    return _check("schema_sql", status, missing=missing, rls_marker_count=rls_count)


def check_client_assets() -> dict[str, Any]:
    html = HOME_ROOT / "client" / "index.html"
    app = HOME_ROOT / "client" / "app.js"
    styles = HOME_ROOT / "client" / "styles.css"
    missing = [str(path.relative_to(HOME_ROOT)) for path in (html, app, styles) if not path.exists()]
    if missing:
        return _check("client_assets", "fail", missing=missing)
    html_body = _read(html).lower()
    app_body = _read(app).lower()
    required = {
        "executive_view": "decision ledger" in html_body and "renderexecutive" in app_body,
        "trust_view": "source ledger" in html_body and "rendertrust" in app_body,
        "second_brain_tab": "second brain" in html_body or "brain" in app_body,
        "module_filters": "modulestack" in app_body.lower() or "modulestack" in html_body.lower(),
        "export_table": "export" in html_body and "rendertable" in app_body,
    }
    failed = [key for key, ok in required.items() if not ok]
    return _check("client_assets", "pass" if not failed else "fail", missing=missing, failed=failed)


def _env_value(env: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = env.get(key, "").strip()
        if value:
            return value
    return ""


def _is_placeholder(value: str) -> bool:
    lower = value.lower()
    return any(fragment.lower() in lower for fragment in PLACEHOLDER_FRAGMENTS)


def check_environment(env: dict[str, str] | None = None, require_live: bool = False) -> dict[str, Any]:
    env = dict(os.environ if env is None else env)
    url = _env_value(env, "HOMEPILOT_SUPABASE_URL", "SUPABASE_URL")
    service_key = _env_value(env, "HOMEPILOT_SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_KEY")
    anon_key = _env_value(env, "HOMEPILOT_SUPABASE_ANON_KEY", "SUPABASE_ANON_KEY")
    db_url = _env_value(env, "HOMEPILOT_SUPABASE_DB_URL", "SUPABASE_DB_URL", "DATABASE_URL")
    missing = []
    if not url:
        missing.append("HOMEPILOT_SUPABASE_URL")
    if not service_key:
        missing.append("HOMEPILOT_SUPABASE_SERVICE_KEY")
    if require_live and not anon_key:
        missing.append("HOMEPILOT_SUPABASE_ANON_KEY")
    if require_live and not db_url:
        missing.append("HOMEPILOT_SUPABASE_DB_URL")
    placeholders = [
        key for key, value in {
            "HOMEPILOT_SUPABASE_URL": url,
            "HOMEPILOT_SUPABASE_SERVICE_KEY": service_key,
            "HOMEPILOT_SUPABASE_ANON_KEY": anon_key,
            "HOMEPILOT_SUPABASE_DB_URL": db_url,
        }.items()
        if value and _is_placeholder(value)
    ]
    if require_live and (missing or placeholders):
        status = "fail"
    elif missing or placeholders:
        status = "warn"
    else:
        status = "pass"
    return _check(
        "environment",
        status,
        configured=bool(url and service_key),
        anon_configured=bool(anon_key),
        db_url_configured=bool(db_url),
        missing=missing,
        placeholders=placeholders,
        require_live=require_live,
    )


def check_live_supabase(url: str, service_key: str, require_live: bool = False) -> dict[str, Any]:
    if not url or not service_key:
        return _check(
            "live_supabase",
            "fail" if require_live else "warn",
            reason="Supabase URL/service key not configured.",
        )
    endpoint = f"{url.rstrip('/')}/rest/v1/homepilot_modules?select=key&limit=1"
    request = urllib.request.Request(endpoint, headers={
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
    })
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response.read()
            return _check("live_supabase", "pass", status_code=response.status)
    except urllib.error.HTTPError as exc:
        return _check("live_supabase", "fail", status_code=exc.code, error=exc.read().decode("utf-8", errors="replace")[:300])
    except Exception as exc:
        return _check("live_supabase", "fail", error=str(exc)[:300])


def build_healthcheck_report(
    env: dict[str, str] | None = None,
    live: bool = False,
    require_live: bool = False,
) -> dict[str, Any]:
    env = dict(os.environ if env is None else env)
    checks = [
        check_required_files(),
        check_env_template(),
        check_dashboard_sql(),
        check_schema_sql(),
        check_client_assets(),
        check_environment(env, require_live=require_live),
    ]
    if live or require_live:
        checks.append(check_live_supabase(
            _env_value(env, "HOMEPILOT_SUPABASE_URL", "SUPABASE_URL"),
            _env_value(env, "HOMEPILOT_SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_KEY"),
            require_live=require_live,
        ))
    return {
        "report_type": "homepilot_operational_healthcheck",
        "created_at": utc_now(),
        "status": _overall_status(checks),
        "live": live or require_live,
        "checks": checks,
        "summary": {
            "pass": sum(1 for check in checks if check["status"] == "pass"),
            "warn": sum(1 for check in checks if check["status"] == "warn"),
            "fail": sum(1 for check in checks if check["status"] == "fail"),
        },
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run HomePilot operational health checks")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--live", action="store_true", help="Also test Supabase REST reachability")
    parser.add_argument("--require-live", action="store_true", help="Fail when live Supabase config/connectivity is missing")
    args = parser.parse_args()

    report = build_healthcheck_report(live=args.live, require_live=args.require_live)
    if args.out:
        write_json(args.out, report)
    print(json.dumps({
        "status": report["status"],
        "live": report["live"],
        "summary": report["summary"],
        "checks": {check["name"]: check["status"] for check in report["checks"]},
        "output": str(args.out) if args.out else None,
    }, indent=2, ensure_ascii=False))
    if report["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
