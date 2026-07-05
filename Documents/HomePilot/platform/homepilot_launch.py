#!/usr/bin/env python3
"""
HomePilot launch verification runner.

This orchestrates the final live gate for a market-ready customer platform:

1. Ensure Supabase Auth test users exist.
2. Build the tenant/module/partner RLS fixture with real auth user IDs.
3. Import onboarding and fixture data.
4. Run the RLS probe with customer JWTs.
5. Write one launch evidence report.

Dry-run mode performs every local step with deterministic fake user IDs and
skips network mutation/probing, so the flow can be tested safely.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_fixture_cleanup import build_fixture_cleanup_plan, write_sql as write_cleanup_sql
from homepilot_live_fixture import build_live_fixture
from homepilot_onboarding import import_onboarding_payload, load_onboarding_payload
from homepilot_platform import canonical_uuid
from homepilot_rls_probe import load_probe_config, run_probe, write_json
from homepilot_store import HOME_ROOT, HomePilotStore, load_dotenv_file, load_payload


for env_path in (HOME_ROOT / ".env", HOME_ROOT / "platform" / ".env"):
    load_dotenv_file(env_path)


FIXTURE_ENV_DEFAULTS = {
    "window_email": ("HOMEPILOT_RLS_WINDOW_EMAIL", "window.rls@example.com"),
    "window_password": ("HOMEPILOT_RLS_WINDOW_PASSWORD", "replace-window-password"),
    "facade_email": ("HOMEPILOT_RLS_FACADE_EMAIL", "facade.rls@example.com"),
    "facade_password": ("HOMEPILOT_RLS_FACADE_PASSWORD", "replace-facade-password"),
    "facade_partner_email": ("HOMEPILOT_RLS_FACADE_PARTNER_EMAIL", "facade.partner.rls@example.com"),
    "facade_partner_password": ("HOMEPILOT_RLS_FACADE_PARTNER_PASSWORD", "replace-facade-partner-password"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _fixture_env_value(name: str, current: str) -> str:
    env_key, default = FIXTURE_ENV_DEFAULTS[name]
    if current and current != default:
        return current
    return os.environ.get(env_key, "").strip() or current or default


def _headers(service_key: str) -> dict[str, str]:
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }


def _request_json(
    method: str,
    url: str,
    service_key: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=_headers(service_key), method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url}: {exc.code} - {body[:500]}") from exc
    if not body:
        return None
    return json.loads(body)


class SupabaseAuthAdmin:
    def __init__(self, url: str, service_key: str, dry_run: bool = False) -> None:
        self.url = url.rstrip("/")
        self.service_key = service_key
        self.dry_run = dry_run

    def _admin_url(self, path: str) -> str:
        return f"{self.url}/auth/v1/admin/{path.lstrip('/')}"

    def list_users(self) -> list[dict[str, Any]]:
        response = _request_json(
            "GET",
            self._admin_url("users?page=1&per_page=1000"),
            self.service_key,
        )
        if isinstance(response, dict) and isinstance(response.get("users"), list):
            return response["users"]
        if isinstance(response, list):
            return response
        raise RuntimeError("Supabase admin users endpoint returned an unexpected payload")

    def find_user_by_email(self, email: str) -> dict[str, Any] | None:
        if self.dry_run:
            return None
        normalized = email.strip().lower()
        for user in self.list_users():
            if str(user.get("email") or "").strip().lower() == normalized:
                return user
        return None

    def ensure_user(self, label: str, email: str, password: str) -> dict[str, Any]:
        if not email.strip():
            raise ValueError(f"{label} email is required")
        if not password.strip():
            raise ValueError(f"{label} password is required")
        if self.dry_run:
            return {
                "label": label,
                "email": email,
                "user_id": canonical_uuid("dry-run-auth-user", email),
                "status": "dry_run",
            }

        existing = self.find_user_by_email(email)
        if existing:
            return {
                "label": label,
                "email": email,
                "user_id": existing["id"],
                "status": "existing",
            }

        payload = {
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {
                "homepilot_fixture": True,
                "homepilot_fixture_label": label,
            },
        }
        created = _request_json("POST", self._admin_url("users"), self.service_key, payload)
        if not isinstance(created, dict) or not created.get("id"):
            raise RuntimeError(f"Supabase did not return a user id for {label}")
        return {
            "label": label,
            "email": email,
            "user_id": created["id"],
            "status": "created",
        }


def _assert_live_inputs(url: str, service_key: str, anon_key: str, passwords: list[str], skip_probe: bool) -> None:
    if not url or not service_key:
        raise ValueError("Live launch requires HOMEPILOT_SUPABASE_URL and HOMEPILOT_SUPABASE_SERVICE_KEY")
    if not skip_probe and not anon_key:
        raise ValueError("Live launch probe requires HOMEPILOT_SUPABASE_ANON_KEY")
    placeholders = [password for password in passwords if password.startswith("replace-")]
    if placeholders:
        raise ValueError("Replace placeholder fixture passwords before running a live launch")


def run_live_rls_launch(
    out_dir: Path,
    url: str = "",
    service_key: str = "",
    anon_key: str = "",
    dry_run: bool = False,
    skip_probe: bool = False,
    window_email: str = "window.rls@example.com",
    window_password: str = "replace-window-password",
    facade_email: str = "facade.rls@example.com",
    facade_password: str = "replace-facade-password",
    facade_partner_email: str = "facade.partner.rls@example.com",
    facade_partner_password: str = "replace-facade-partner-password",
) -> dict[str, Any]:
    window_email = _fixture_env_value("window_email", window_email)
    window_password = _fixture_env_value("window_password", window_password)
    facade_email = _fixture_env_value("facade_email", facade_email)
    facade_password = _fixture_env_value("facade_password", facade_password)
    facade_partner_email = _fixture_env_value("facade_partner_email", facade_partner_email)
    facade_partner_password = _fixture_env_value("facade_partner_password", facade_partner_password)

    if not dry_run:
        _assert_live_inputs(url, service_key, anon_key, [window_password, facade_password, facade_partner_password], skip_probe)

    out_dir.mkdir(parents=True, exist_ok=True)
    admin = SupabaseAuthAdmin(url=url, service_key=service_key, dry_run=dry_run)
    auth_users = [
        admin.ensure_user("window_customer", window_email, window_password),
        admin.ensure_user("facade_customer", facade_email, facade_password),
        admin.ensure_user("facade_partner", facade_partner_email, facade_partner_password),
    ]
    user_ids = {user["label"]: user["user_id"] for user in auth_users}

    fixture_manifest = build_live_fixture(
        out_dir=out_dir,
        window_email=window_email,
        window_password=window_password,
        window_user_id=user_ids["window_customer"],
        facade_email=facade_email,
        facade_password=facade_password,
        facade_user_id=user_ids["facade_customer"],
        facade_partner_email=facade_partner_email,
        facade_partner_password=facade_partner_password,
        facade_partner_user_id=user_ids["facade_partner"],
    )

    store = HomePilotStore(url=url, service_key=service_key, dry_run=dry_run)
    onboarding = load_onboarding_payload(Path(fixture_manifest["paths"]["onboarding"]))
    payload = load_payload(Path(fixture_manifest["paths"]["payload"]))
    import_counts = {
        "onboarding": import_onboarding_payload(store, onboarding),
        "payload": store.import_payload(payload),
    }

    probe_path = out_dir / "rls_probe_report.json"
    if dry_run:
        probe_report = {
            "report_type": "homepilot_rls_probe",
            "created_at": utc_now(),
            "status": "skipped_dry_run",
            "reason": "Dry-run launch does not call Supabase Auth or REST endpoints.",
        }
        write_json(probe_path, probe_report)
    elif skip_probe:
        probe_report = {
            "report_type": "homepilot_rls_probe",
            "created_at": utc_now(),
            "status": "skipped",
            "reason": "Probe was explicitly skipped.",
        }
        write_json(probe_path, probe_report)
    else:
        probe_config = load_probe_config(Path(fixture_manifest["paths"]["probe_config"]))
        probe_report = run_probe(probe_config, url=url, anon_key=anon_key, allow_empty=False)
        write_json(probe_path, probe_report)

    cleanup_plan_path = out_dir / "cleanup_plan.json"
    cleanup_sql_path = out_dir / "cleanup_plan.sql"
    cleanup_plan = build_fixture_cleanup_plan(
        {"fixture_manifest": fixture_manifest, "auth_users": auth_users},
        include_auth_users=True,
    )
    write_json(cleanup_plan_path, cleanup_plan)
    write_cleanup_sql(cleanup_sql_path, cleanup_plan["sql"])

    if dry_run:
        status = "dry_run"
        production_verified = False
    elif probe_report.get("status") == "pass":
        status = "pass"
        production_verified = True
    else:
        status = "fail"
        production_verified = False

    report = {
        "report_type": "homepilot_launch_rls_fixture",
        "created_at": utc_now(),
        "status": status,
        "production_verified": production_verified,
        "dry_run": dry_run,
        "auth_users": auth_users,
        "fixture_manifest": fixture_manifest,
        "imports": import_counts,
        "rls_probe": {
            "status": probe_report.get("status"),
            "path": str(probe_path),
        },
        "cleanup": {
            "status": cleanup_plan["status"],
            "tenant_count": cleanup_plan["tenant_count"],
            "path": str(cleanup_plan_path),
            "sql": str(cleanup_sql_path),
        },
        "paths": {
            "launch_report": str(out_dir / "launch_report.json"),
            "fixture_manifest": fixture_manifest["paths"]["manifest"],
            "onboarding": fixture_manifest["paths"]["onboarding"],
            "payload": fixture_manifest["paths"]["payload"],
            "probe_config": fixture_manifest["paths"]["probe_config"],
            "rls_probe_report": str(probe_path),
            "cleanup_plan": str(cleanup_plan_path),
            "cleanup_sql": str(cleanup_sql_path),
        },
    }
    write_json(out_dir / "launch_report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the HomePilot live RLS launch gate")
    parser.add_argument("--url", default=os.environ.get("HOMEPILOT_SUPABASE_URL") or os.environ.get("SUPABASE_URL") or "")
    parser.add_argument(
        "--service-key",
        default=os.environ.get("HOMEPILOT_SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY") or "",
    )
    parser.add_argument(
        "--anon-key",
        default=os.environ.get("HOMEPILOT_SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_ANON_KEY") or "",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    launch = sub.add_parser("rls-fixture", help="Bootstrap users, import fixture data, and run the RLS probe")
    launch.add_argument("--out-dir", required=True, type=Path)
    launch.add_argument("--dry-run", action="store_true")
    launch.add_argument("--skip-probe", action="store_true")
    launch.add_argument("--window-email", default=os.environ.get("HOMEPILOT_RLS_WINDOW_EMAIL", "window.rls@example.com"))
    launch.add_argument("--window-password", default=os.environ.get("HOMEPILOT_RLS_WINDOW_PASSWORD", "replace-window-password"))
    launch.add_argument("--facade-email", default=os.environ.get("HOMEPILOT_RLS_FACADE_EMAIL", "facade.rls@example.com"))
    launch.add_argument("--facade-password", default=os.environ.get("HOMEPILOT_RLS_FACADE_PASSWORD", "replace-facade-password"))
    launch.add_argument("--facade-partner-email", default=os.environ.get("HOMEPILOT_RLS_FACADE_PARTNER_EMAIL", "facade.partner.rls@example.com"))
    launch.add_argument("--facade-partner-password", default=os.environ.get("HOMEPILOT_RLS_FACADE_PARTNER_PASSWORD", "replace-facade-partner-password"))
    args = parser.parse_args()

    if args.cmd == "rls-fixture":
        report = run_live_rls_launch(
            out_dir=args.out_dir,
            url=args.url,
            service_key=args.service_key,
            anon_key=args.anon_key,
            dry_run=args.dry_run,
            skip_probe=args.skip_probe,
            window_email=args.window_email,
            window_password=args.window_password,
            facade_email=args.facade_email,
            facade_password=args.facade_password,
            facade_partner_email=args.facade_partner_email,
            facade_partner_password=args.facade_partner_password,
        )
        print(json.dumps({
            "output": str(args.out_dir),
            "status": report["status"],
            "production_verified": report["production_verified"],
            "launch_report": report["paths"]["launch_report"],
            "rls_probe": report["rls_probe"]["status"],
            "cleanup_plan": report["paths"]["cleanup_plan"],
        }, indent=2))
        if report["status"] == "fail":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
