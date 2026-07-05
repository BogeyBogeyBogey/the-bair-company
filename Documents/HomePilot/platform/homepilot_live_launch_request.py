#!/usr/bin/env python3
"""
Build a HomePilot live launch request pack.

Live readiness tells us what is missing. This pack turns that into a practical
operator/customer IT request: who owns each input, which env vars are needed,
which customer identities must be prepared, and what proof will unlock launch.
It never writes secret values.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECRET_MARKERS = ("service_key", "anon_key", "password", "token", "secret", "db_url", "database_url")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _owner_for_group(group_name: str) -> str:
    if group_name == "supabase":
        return "platform_admin"
    if group_name == "rls_fixture":
        return "homepilot_operator"
    if group_name == "customer_access":
        return "customer_success"
    return "homepilot_operator"


def _owner_label(owner: str) -> str:
    return {
        "platform_admin": "Platform admin / Supabase owner",
        "homepilot_operator": "HomePilot operator",
        "customer_success": "Customer success / tenant admin",
    }.get(owner, owner)


def _safe_example(check_name: str) -> str:
    if "url" in check_name:
        return "set-in-secret-manager"
    if any(marker in check_name for marker in SECRET_MARKERS):
        return "set-secret-value"
    return "optional-override"


def _task_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _input_tasks(live_readiness: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for group_name, group in (live_readiness.get("groups") or {}).items():
        for check in group.get("checks") or []:
            required = bool(check.get("required_for_live"))
            status = str(check.get("status") or "unknown")
            if status in {"pass", "default", "optional_missing"} and not required:
                continue
            if status == "pass":
                continue
            env_keys = list(check.get("accepted_keys") or [])
            primary_env = env_keys[0] if env_keys else ""
            owner = _owner_for_group(group_name)
            secret_key = f"{check.get('name', '')} {primary_env}".lower()
            tasks.append({
                "task_id": _task_id(f"{group_name}_{check.get('name')}"),
                "category": group_name,
                "owner": owner,
                "owner_label": _owner_label(owner),
                "status": "required",
                "input_name": check.get("name"),
                "env_var": primary_env,
                "accepted_env_vars": env_keys,
                "purpose": check.get("purpose"),
                "required_for_live": required,
                "current_status": status,
                "secret_value_required": any(marker in secret_key for marker in SECRET_MARKERS),
                "example_value": _safe_example(str(check.get("name") or "")),
            })
    for identity in live_readiness.get("customer_access", {}).get("identities") or []:
        if identity.get("credential_status") == "ready":
            continue
        owner = _owner_for_group("customer_access")
        email = identity.get("email") or "unknown"
        env_var = identity.get("token_env") or identity.get("password_env")
        tasks.append({
            "task_id": _task_id(f"customer_access_{email}"),
            "category": "customer_access",
            "owner": owner,
            "owner_label": _owner_label(owner),
            "status": "required",
            "input_name": f"credential for {email}",
            "env_var": env_var,
            "accepted_env_vars": [value for value in (identity.get("token_env"), identity.get("password_env")) if value],
            "purpose": f"Short-lived JWT token or password for planned {identity.get('role')} access probe.",
            "required_for_live": True,
            "current_status": identity.get("credential_status"),
            "secret_value_required": True,
            "example_value": "set-short-lived-token-or-password",
            "email": email,
            "role": identity.get("role"),
            "access_scope": identity.get("access_scope"),
            "partner_id": identity.get("partner_id"),
        })
    return tasks


def _summary(tasks: list[dict[str, Any]], live_readiness: dict[str, Any]) -> dict[str, Any]:
    by_owner: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for task in tasks:
        by_owner[task["owner"]] = by_owner.get(task["owner"], 0) + 1
        by_category[task["category"]] = by_category.get(task["category"], 0) + 1
    return {
        "live_readiness_status": live_readiness.get("status"),
        "ready_to_run_live_cutover": live_readiness.get("ready_to_run_live_cutover"),
        "task_count": len(tasks),
        "secret_task_count": len([task for task in tasks if task["secret_value_required"]]),
        "by_owner": dict(sorted(by_owner.items())),
        "by_category": dict(sorted(by_category.items())),
    }


def _write_tasks_csv(path: Path, tasks: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "task_id",
        "category",
        "owner_label",
        "status",
        "input_name",
        "env_var",
        "purpose",
        "required_for_live",
        "current_status",
        "secret_value_required",
        "access_scope",
        "partner_id",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for task in tasks:
            writer.writerow({field: task.get(field, "") for field in fields})


def _env_template(tasks: list[dict[str, Any]]) -> str:
    lines = [
        "# HomePilot live launch request env template",
        "# Fill values in a local shell or secret manager. Do not commit this file with real values.",
        "",
    ]
    seen = set()
    for task in tasks:
        env_var = task.get("env_var")
        if not env_var or env_var in seen:
            continue
        seen.add(env_var)
        lines.append(f"export {env_var}='{task['example_value']}'")
    lines.append("")
    return "\n".join(lines)


def _request_email(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "Subject: HomePilot live launch inputs needed",
        "",
        "Hi,",
        "",
        "We are ready for buyer review, but live launch is still blocked until the missing Supabase, RLS fixture, and planned customer access inputs are configured in the secret manager or local launch environment.",
        "",
        f"Open tasks: {summary['task_count']}",
        f"Supabase/platform tasks: {summary['by_category'].get('supabase', 0)}",
        f"RLS fixture tasks: {summary['by_category'].get('rls_fixture', 0)}",
        f"Customer access tasks: {summary['by_category'].get('customer_access', 0)}",
        "",
        "Please use LIVE_LAUNCH_CHECKLIST.csv for ownership and live_launch.env.template for env var names. Do not send secrets by email; store them in the agreed secret manager or set them locally for the live cutover session.",
        "",
        "Production remains no_go until live readiness is ready, the live schema verification passes, the live RLS launch probe passes, and customer access verification passes.",
        "",
        "Thanks,",
        "HomePilot",
        "",
    ]
    return "\n".join(lines)


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# HomePilot Live Launch Request",
        "",
        f"Created: {report['created_at']}",
        f"Release: {report['release_label']}",
        f"Status: {report['status']}",
        f"Live readiness: {summary['live_readiness_status']}",
        f"Ready to run live cutover: {str(summary['ready_to_run_live_cutover']).lower()}",
        "",
        "## Summary",
        "",
        f"- Open tasks: {summary['task_count']}",
        f"- Secret-bearing tasks: {summary['secret_task_count']}",
        f"- Platform admin tasks: {summary['by_owner'].get('platform_admin', 0)}",
        f"- HomePilot operator tasks: {summary['by_owner'].get('homepilot_operator', 0)}",
        f"- Customer success tasks: {summary['by_owner'].get('customer_success', 0)}",
        "",
        "## Required Inputs",
        "",
    ]
    if not report["tasks"]:
        lines.append("- None.")
    for task in report["tasks"]:
        lines.append(f"- {task['owner_label']}: `{task['env_var']}` - {task['purpose']}")
    lines += [
        "",
        "## Guardrails",
        "",
        "- This pack stores env var names only, not secret values.",
        "- Do not send service keys, database URLs, fixture passwords, JWTs, or customer passwords by email.",
        "- Production remains blocked until live schema verification, live RLS launch, and customer access verification pass.",
        "",
        "## Files",
        "",
    ]
    for label, path in report["paths"].items():
        lines.append(f"- {label}: {path}")
    lines.append("")
    return "\n".join(lines)


def _guardrails(report: dict[str, Any]) -> dict[str, Any]:
    joined = json.dumps(report, ensure_ascii=False)
    suspicious_values = []
    for pattern in (r"eyJ[A-Za-z0-9_-]{20,}\.", r"postgres(?:ql)?://[^'\"]+:[^@'\"]+@", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"):
        if re.search(pattern, joined):
            suspicious_values.append(pattern)
    return {
        "secrets_written": bool(suspicious_values),
        "suspicious_patterns": suspicious_values,
        "stores_env_var_names_only": not suspicious_values,
    }


def build_live_launch_request_pack(
    out_dir: Path,
    live_readiness_report_path: Path,
    account_access_plan_path: Path | None = None,
    release_label: str = "production-candidate",
) -> dict[str, Any]:
    live_readiness = load_json(live_readiness_report_path)
    if not live_readiness:
        raise ValueError(f"Missing live readiness report: {live_readiness_report_path}")
    account_access = load_json(account_access_plan_path)
    tasks = _input_tasks(live_readiness)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "report_type": "homepilot_live_launch_request",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": "ready" if not tasks else "action_required",
        "inputs": {
            "live_readiness_report": str(live_readiness_report_path),
            "account_access_plan": str(account_access_plan_path) if account_access_plan_path else None,
        },
        "summary": _summary(tasks, live_readiness),
        "tasks": tasks,
        "account_access": {
            "status": account_access.get("status") if account_access else None,
            "review_status": account_access.get("review_status") if account_access else None,
            "tenant": account_access.get("tenant", {}) if account_access else {},
            "enabled_modules": account_access.get("enabled_modules", []) if account_access else [],
        },
        "next_commands": [
            "source /path/to/live_launch.env",
            "python3 platform/homepilot_live_readiness.py --out-dir /tmp/homepilot_live_readiness --readiness-report /tmp/homepilot_readiness_pack/readiness_report.json --due-diligence-report /tmp/homepilot_due_diligence_pack/due_diligence_report.json --account-access-plan /tmp/homepilot_readiness_pack/account_access_smoke/account_access_plan.json",
            "python3 platform/homepilot_production_cutover.py --live --out-dir /tmp/homepilot_cutover_live --readiness-report /tmp/homepilot_readiness_pack/readiness_report.json --due-diligence-report /tmp/homepilot_due_diligence_pack/due_diligence_report.json --account-access-plan /tmp/homepilot_readiness_pack/account_access_smoke/account_access_plan.json",
        ],
        "paths": {
            "live_launch_request": str(out_dir / "live_launch_request.json"),
            "markdown": str(out_dir / "LIVE_LAUNCH_REQUEST.md"),
            "checklist_csv": str(out_dir / "LIVE_LAUNCH_CHECKLIST.csv"),
            "env_template": str(out_dir / "live_launch.env.template"),
            "request_email": str(out_dir / "LIVE_LAUNCH_REQUEST_EMAIL.txt"),
        },
    }
    report["guardrails"] = _guardrails(report)
    write_json(out_dir / "live_launch_request.json", report)
    write_text(out_dir / "LIVE_LAUNCH_REQUEST.md", render_markdown(report))
    _write_tasks_csv(out_dir / "LIVE_LAUNCH_CHECKLIST.csv", tasks)
    write_text(out_dir / "live_launch.env.template", _env_template(tasks))
    write_text(out_dir / "LIVE_LAUNCH_REQUEST_EMAIL.txt", _request_email(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot live launch request pack")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--live-readiness-report", required=True, type=Path)
    parser.add_argument("--account-access-plan", type=Path)
    parser.add_argument("--release-label", default="production-candidate")
    args = parser.parse_args()

    report = build_live_launch_request_pack(
        out_dir=args.out_dir,
        live_readiness_report_path=args.live_readiness_report,
        account_access_plan_path=args.account_access_plan,
        release_label=args.release_label,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": report["status"],
        "task_count": report["summary"]["task_count"],
        "live_launch_request": report["paths"]["live_launch_request"],
        "markdown": report["paths"]["markdown"],
        "checklist_csv": report["paths"]["checklist_csv"],
        "env_template": report["paths"]["env_template"],
        "request_email": report["paths"]["request_email"],
    }, indent=2, ensure_ascii=False))
    if report["guardrails"]["secrets_written"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
