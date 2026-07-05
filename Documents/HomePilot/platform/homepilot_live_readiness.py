#!/usr/bin/env python3
"""
HomePilot live readiness doctor.

This builds the operator checklist for the final production cutover without
writing secrets. It checks whether the environment has the Supabase credentials,
fixture user credentials, and planned customer access credentials needed to run
the live schema/RLS/customer-access proof chain.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_customer_access_verification import load_account_access_plan
from homepilot_store import HOME_ROOT, load_dotenv_file


for env_path in (HOME_ROOT / ".env", HOME_ROOT / "platform" / ".env"):
    load_dotenv_file(env_path)


SUPABASE_ENV_GROUPS = (
    {
        "name": "supabase_url",
        "required_for_live": True,
        "accepted_keys": ("HOMEPILOT_SUPABASE_URL", "SUPABASE_URL"),
        "purpose": "Supabase project REST/Auth endpoint.",
    },
    {
        "name": "supabase_service_key",
        "required_for_live": True,
        "accepted_keys": ("HOMEPILOT_SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_KEY"),
        "purpose": "Service-role access for module seeding and fixture import.",
    },
    {
        "name": "supabase_anon_key",
        "required_for_live": True,
        "accepted_keys": ("HOMEPILOT_SUPABASE_ANON_KEY", "SUPABASE_ANON_KEY"),
        "purpose": "Anon key used by customer JWT/RLS probes.",
    },
    {
        "name": "supabase_db_url",
        "required_for_live": True,
        "accepted_keys": ("HOMEPILOT_SUPABASE_DB_URL", "SUPABASE_DB_URL", "DATABASE_URL"),
        "purpose": "Postgres connection URL for live schema metadata verification.",
    },
)

FIXTURE_ENV_GROUPS = (
    {
        "name": "window_fixture_email",
        "required_for_live": False,
        "accepted_keys": ("HOMEPILOT_RLS_WINDOW_EMAIL",),
        "default": "window.rls@example.com",
        "purpose": "WindowPilot fixture Auth email; optional because a deterministic default exists.",
    },
    {
        "name": "window_fixture_password",
        "required_for_live": True,
        "accepted_keys": ("HOMEPILOT_RLS_WINDOW_PASSWORD",),
        "purpose": "WindowPilot fixture Auth password for live RLS probe.",
    },
    {
        "name": "facade_fixture_email",
        "required_for_live": False,
        "accepted_keys": ("HOMEPILOT_RLS_FACADE_EMAIL",),
        "default": "facade.rls@example.com",
        "purpose": "FacadePilot tenant-wide fixture Auth email; optional because a deterministic default exists.",
    },
    {
        "name": "facade_fixture_password",
        "required_for_live": True,
        "accepted_keys": ("HOMEPILOT_RLS_FACADE_PASSWORD",),
        "purpose": "FacadePilot tenant-wide fixture Auth password for live RLS probe.",
    },
    {
        "name": "facade_partner_fixture_email",
        "required_for_live": False,
        "accepted_keys": ("HOMEPILOT_RLS_FACADE_PARTNER_EMAIL",),
        "default": "facade.partner.rls@example.com",
        "purpose": "FacadePilot partner-scoped fixture Auth email; optional because a deterministic default exists.",
    },
    {
        "name": "facade_partner_fixture_password",
        "required_for_live": True,
        "accepted_keys": ("HOMEPILOT_RLS_FACADE_PARTNER_PASSWORD",),
        "purpose": "FacadePilot partner-scoped fixture Auth password for live RLS probe.",
    },
)

PLACEHOLDER_FRAGMENTS = (
    "replace-",
    "your-",
    "example.com",
    "project-ref",
    "service-role-key",
    "anon-key",
    "postgresql://postgres:password@",
    "eyJ...",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _env_value(env: dict[str, str], keys: tuple[str, ...]) -> tuple[str, str]:
    for key in keys:
        value = str(env.get(key, "")).strip()
        if value:
            return key, value
    return "", ""


def _is_placeholder(value: str) -> bool:
    lower = value.lower()
    return any(fragment.lower() in lower for fragment in PLACEHOLDER_FRAGMENTS)


def _safe_env_label(email: str, role: str) -> str:
    raw = f"{role}_{email}".upper()
    return re.sub(r"[^A-Z0-9]+", "_", raw).strip("_")[:80]


def _env_group_check(group: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    key, value = _env_value(env, tuple(group["accepted_keys"]))
    configured = bool(value)
    placeholder = bool(value and _is_placeholder(value))
    required = bool(group.get("required_for_live"))
    status = "pass"
    if required and not configured:
        status = "missing"
    elif placeholder:
        status = "placeholder"
    elif not configured:
        status = "default" if group.get("default") else "optional_missing"
    return {
        "name": group["name"],
        "status": status,
        "required_for_live": required,
        "configured": configured,
        "configured_key": key or None,
        "accepted_keys": list(group["accepted_keys"]),
        "uses_default": not configured and bool(group.get("default")),
        "default": group.get("default"),
        "placeholder": placeholder,
        "purpose": group["purpose"],
    }


def _customer_access_checks(account_access_plan: dict[str, Any] | None, env: dict[str, str]) -> tuple[list[dict[str, Any]], list[str]]:
    if not account_access_plan:
        return [], ["Missing account access plan; customer identities cannot be checked."]
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    if account_access_plan.get("status") != "pass":
        failures.append(f"Account access plan status is {account_access_plan.get('status')!r}, expected 'pass'.")
    if account_access_plan.get("review_status") != "ready":
        failures.append(f"Account access plan review_status is {account_access_plan.get('review_status')!r}, expected 'ready'.")
    for index, invitee in enumerate(account_access_plan.get("invitees") or [], start=1):
        email = str(invitee.get("email") or "").strip().lower()
        role = str(invitee.get("role") or "").strip()
        user_id = str(invitee.get("user_id") or "").strip()
        partner_id = str(invitee.get("partner_id") or "").strip()
        label = _safe_env_label(email or f"invitee_{index}", role or "user")
        token_env = f"HOMEPILOT_ACCESS_{label}_TOKEN"
        password_env = f"HOMEPILOT_ACCESS_{label}_PASSWORD"
        token_present = bool(str(env.get(token_env, "")).strip())
        password_present = bool(str(env.get(password_env, "")).strip())
        credential_status = "ready" if token_present or password_present else "missing"
        if credential_status != "ready":
            failures.append(f"Missing customer access credential for {email or index}; set {token_env} or {password_env}.")
        if not user_id:
            failures.append(f"Invitee {email or index} is missing Supabase Auth user_id.")
        checks.append({
            "label": label.lower(),
            "email": email,
            "role": role,
            "user_id_present": bool(user_id),
            "access_scope": "partner" if partner_id else "tenant",
            "partner_id": partner_id or None,
            "token_env": token_env,
            "password_env": password_env,
            "token_present": token_present,
            "password_present": password_present,
            "credential_status": credential_status,
        })
    if not checks:
        failures.append("Account access plan has no invitees.")
    return checks, failures


def _summarize_group(name: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    missing = [check["name"] for check in checks if check["status"] == "missing"]
    placeholders = [check["name"] for check in checks if check["status"] == "placeholder"]
    return {
        "name": name,
        "status": "pass" if not missing and not placeholders else "fail",
        "missing": missing,
        "placeholders": placeholders,
        "checks": checks,
    }


def _template_lines(report: dict[str, Any]) -> list[str]:
    lines = [
        "# HomePilot live cutover environment template",
        "# Fill this in locally or in your secret manager. Never commit real values.",
        "",
    ]
    for section in ("supabase", "rls_fixture"):
        lines.append(f"# {section}")
        for check in report["groups"][section]["checks"]:
            key = check["accepted_keys"][0]
            if check.get("uses_default"):
                lines.append(f"# {key}={check['default']}")
            else:
                lines.append(f"export {key}='replace-{check['name']}'")
        lines.append("")
    if report["customer_access"]["identities"]:
        lines.append("# customer access probe identities")
        for identity in report["customer_access"]["identities"]:
            lines.append(f"export {identity['token_env']}='replace-short-lived-token'")
            lines.append(f"# export {identity['password_env']}='replace-password-only-if-token-unavailable'")
        lines.append("")
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Live Readiness",
        "",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        f"Ready to run live cutover: {str(report['ready_to_run_live_cutover']).lower()}",
        f"Secrets written: {str(report['guardrails']['secrets_written']).lower()}",
        "",
        "## Groups",
        "",
    ]
    for group in report["groups"].values():
        lines.append(f"- {group['name']}: {group['status']}; missing: {len(group['missing'])}; placeholders: {len(group['placeholders'])}")
    lines += [
        f"- customer_access: {report['customer_access']['status']}; identities: {len(report['customer_access']['identities'])}",
        "",
        "## Missing Live Inputs",
        "",
    ]
    missing = report["missing_live_inputs"]
    if missing:
        lines.extend(f"- {item}" for item in missing)
    else:
        lines.append("- none")
    lines += [
        "",
        "## Live Cutover Command",
        "",
        "```bash",
        report["commands"]["production_cutover"],
        "```",
        "",
    ]
    if report["paths"].get("env_template"):
        lines.extend(["## Template", "", f"- {report['paths']['env_template']}"])
    lines.append("")
    return "\n".join(lines)


def build_live_readiness_report(
    out_dir: Path,
    account_access_plan_path: Path | None = None,
    readiness_report_path: Path | None = None,
    due_diligence_report_path: Path | None = None,
    release_label: str = "production-candidate",
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = dict(os.environ if env is None else env)
    out_dir.mkdir(parents=True, exist_ok=True)
    account_access_plan = load_account_access_plan(account_access_plan_path) if account_access_plan_path else None

    supabase_checks = [_env_group_check(group, env) for group in SUPABASE_ENV_GROUPS]
    fixture_checks = [_env_group_check(group, env) for group in FIXTURE_ENV_GROUPS]
    customer_identities, customer_failures = _customer_access_checks(account_access_plan, env)

    groups = {
        "supabase": _summarize_group("supabase", supabase_checks),
        "rls_fixture": _summarize_group("rls_fixture", fixture_checks),
    }
    missing_live_inputs: list[str] = []
    for group in groups.values():
        for item in group["missing"]:
            missing_live_inputs.append(f"{group['name']}.{item} is missing.")
        for item in group["placeholders"]:
            missing_live_inputs.append(f"{group['name']}.{item} still looks like a placeholder.")
    missing_live_inputs.extend(customer_failures)

    customer_access_status = "pass" if account_access_plan and not customer_failures else "fail"
    ready = groups["supabase"]["status"] == "pass" and groups["rls_fixture"]["status"] == "pass" and customer_access_status == "pass"

    cutover_command = (
        "python3 platform/homepilot_production_cutover.py --live "
        f"--out-dir /tmp/homepilot_cutover_live "
        f"--readiness-report {readiness_report_path or '/path/to/readiness_report.json'} "
        f"--due-diligence-report {due_diligence_report_path or '/path/to/due_diligence_report.json'} "
        f"--account-access-plan {account_access_plan_path or '/path/to/account_access_plan.json'} "
        f"--release-label {release_label}"
    )
    report = {
        "report_type": "homepilot_live_readiness",
        "created_at": utc_now(),
        "status": "ready" if ready else "action_required",
        "ready_to_run_live_cutover": ready,
        "release_label": release_label,
        "inputs": {
            "readiness_report": str(readiness_report_path) if readiness_report_path else None,
            "due_diligence_report": str(due_diligence_report_path) if due_diligence_report_path else None,
            "account_access_plan": str(account_access_plan_path) if account_access_plan_path else None,
        },
        "groups": groups,
        "customer_access": {
            "status": customer_access_status,
            "plan_status": account_access_plan.get("status") if account_access_plan else None,
            "review_status": account_access_plan.get("review_status") if account_access_plan else None,
            "identities": customer_identities,
            "failures": customer_failures,
        },
        "missing_live_inputs": missing_live_inputs,
        "commands": {
            "production_cutover": cutover_command,
        },
        "guardrails": {
            "secrets_written": False,
            "service_role_key_written": False,
            "anon_key_written": False,
            "customer_tokens_written": False,
            "fixture_passwords_written": False,
        },
        "paths": {
            "live_readiness": str(out_dir / "live_readiness.json"),
            "markdown": str(out_dir / "LIVE_READINESS.md"),
            "env_template": str(out_dir / "live_cutover.env.template"),
        },
    }
    write_json(out_dir / "live_readiness.json", report)
    write_text(out_dir / "LIVE_READINESS.md", render_markdown(report))
    write_text(out_dir / "live_cutover.env.template", "\n".join(_template_lines(report)))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a redacted HomePilot live readiness checklist")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--account-access-plan", type=Path)
    parser.add_argument("--readiness-report", type=Path)
    parser.add_argument("--due-diligence-report", type=Path)
    parser.add_argument("--release-label", default="production-candidate")
    args = parser.parse_args()

    report = build_live_readiness_report(
        out_dir=args.out_dir,
        account_access_plan_path=args.account_access_plan,
        readiness_report_path=args.readiness_report,
        due_diligence_report_path=args.due_diligence_report,
        release_label=args.release_label,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": report["status"],
        "ready_to_run_live_cutover": report["ready_to_run_live_cutover"],
        "missing_live_inputs": report["missing_live_inputs"],
        "live_readiness": report["paths"]["live_readiness"],
        "markdown": report["paths"]["markdown"],
        "env_template": report["paths"]["env_template"],
    }, indent=2, ensure_ascii=False))
    if report["status"] != "ready":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
