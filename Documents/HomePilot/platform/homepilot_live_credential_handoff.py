#!/usr/bin/env python3
"""
Build a HomePilot live credential handoff pack.

The live launch request lists missing inputs. This pack turns those inputs into
a customer/IT-safe handoff contract: owners, env var names, secret channels,
validation commands, evidence to archive, and guardrails. It never stores secret
values, raw contact data, or live customer data.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECRET_PATTERNS = (
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"postgres(?:ql)?://[^:\s]+:[^@\s]{8,}@", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?:service[_-]?role|anon[_-]?key|password|token|secret)\s*[:=]\s*['\"][^'\"\n]{12,}['\"]", re.IGNORECASE),
)

FORBIDDEN_CHANNELS = (
    "email",
    "portable data room",
    "git",
    "shared spreadsheet",
    "ticket comments",
    "chat transcript",
)


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


def _safe_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "input"


def _redacted_task_id(task: dict[str, Any], index: int) -> str:
    category = str(task.get("category") or "live_input")
    if category == "customer_access":
        return f"customer_access_identity_{index}"
    base = str(task.get("task_id") or task.get("input_name") or f"input_{index}")
    base = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", "identity", base)
    return _safe_slug(base)


def _redacted_input_name(task: dict[str, Any], index: int) -> str:
    category = str(task.get("category") or "")
    input_name = str(task.get("input_name") or f"input {index}")
    if category == "customer_access":
        role = str(task.get("role") or "customer")
        scope = str(task.get("access_scope") or "tenant")
        return f"credential for planned {role} {scope} access probe"
    return re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", "planned identity", input_name)


def _owner_label(owner: str) -> str:
    return {
        "platform_admin": "Platform admin / Supabase owner",
        "homepilot_operator": "HomePilot operator",
        "customer_success": "Customer success / tenant admin",
        "it_owner": "Customer IT / security owner",
    }.get(owner, owner.replace("_", " ").title())


def _safe_channel(task: dict[str, Any]) -> str:
    category = str(task.get("category") or "")
    if category == "customer_access":
        return "approved customer secret manager or short-lived live proof session"
    if category == "supabase":
        return "Supabase owner secret manager or local operator shell for cutover"
    if category == "rls_fixture":
        return "temporary fixture credential vault or local live proof session"
    return "approved secret manager or local live proof session"


def _credential_kind(task: dict[str, Any]) -> str:
    text = " ".join(str(task.get(key) or "") for key in ("input_name", "env_var", "purpose")).lower()
    if "db_url" in text or "database_url" in text or "postgres" in text:
        return "postgres_metadata_url"
    if "service" in text and "key" in text:
        return "supabase_service_role_key"
    if "anon" in text and "key" in text:
        return "supabase_anon_key"
    if "password" in text and "fixture" in text:
        return "temporary_rls_fixture_password"
    if "token" in text or "customer access" in text or task.get("category") == "customer_access":
        return "short_lived_customer_access_token_or_password"
    if "url" in text:
        return "supabase_project_url"
    if "password" in text:
        return "temporary_password"
    return "live_configuration_input"


def _unlocks_gate(task: dict[str, Any]) -> str:
    category = str(task.get("category") or "")
    env_var = str(task.get("env_var") or "")
    if "DB_URL" in env_var or "DATABASE_URL" in env_var:
        return "live_schema_metadata_verification"
    if category == "supabase":
        return "live_cutover_and_module_seed"
    if category == "rls_fixture":
        return "live_rls_launch_probe"
    if category == "customer_access":
        return "customer_access_verification"
    return "live_readiness"


def _validation_command(task: dict[str, Any]) -> str:
    gate = _unlocks_gate(task)
    if gate == "live_schema_metadata_verification":
        return "python3 platform/homepilot_live_schema_verification.py --live --out-dir /tmp/homepilot_schema_live"
    if gate == "live_rls_launch_probe":
        return "python3 platform/homepilot_launch.py --live --out-dir /tmp/homepilot_rls_launch"
    if gate == "customer_access_verification":
        return "python3 platform/homepilot_customer_access_verification.py --live --out-dir /tmp/homepilot_customer_access_live"
    return "python3 platform/homepilot_live_readiness.py --out-dir /tmp/homepilot_live_readiness"


def _validation_artifact(task: dict[str, Any]) -> str:
    gate = _unlocks_gate(task)
    return {
        "live_schema_metadata_verification": "schema_verification.json with production_verified=true",
        "live_cutover_and_module_seed": "live_readiness.json ready plus cutover_report.json",
        "live_rls_launch_probe": "launch_report.json with production_verified=true",
        "customer_access_verification": "customer_access_verification.json with production_verified=true",
    }.get(gate, "live_readiness.json with ready_to_run_live_cutover=true")


def _safe_handling(task: dict[str, Any]) -> str:
    if task.get("secret_value_required"):
        return "Store the value only in the approved secret channel; archive only env var name, owner, timestamp, and validation artifact."
    return "Archive the configured env var name and validation result; do not copy live values into the evidence room."


def _evidence_to_archive(task: dict[str, Any]) -> str:
    return f"{_validation_artifact(task)}; LIVE_CREDENTIAL_HANDOFF_CHECKLIST.csv owner row signed off"


def _build_rows(live_launch_request: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, task in enumerate((live_launch_request or {}).get("tasks") or [], start=1):
        env_vars = [str(value) for value in (task.get("accepted_env_vars") or []) if value]
        if not env_vars and task.get("env_var"):
            env_vars = [str(task["env_var"])]
        row = {
            "handoff_id": _redacted_task_id(task, index),
            "category": task.get("category") or "live_input",
            "owner": task.get("owner") or "homepilot_operator",
            "owner_label": task.get("owner_label") or _owner_label(str(task.get("owner") or "homepilot_operator")),
            "status": "required" if task.get("status") != "ready" else "ready",
            "input_name": _redacted_input_name(task, index),
            "env_var": task.get("env_var") or (env_vars[0] if env_vars else ""),
            "accepted_env_vars": env_vars,
            "credential_kind": _credential_kind(task),
            "secret_value_required": bool(task.get("secret_value_required")),
            "required_for_live": bool(task.get("required_for_live", True)),
            "current_status": task.get("current_status") or "unknown",
            "safe_channel": _safe_channel(task),
            "forbidden_channels": list(FORBIDDEN_CHANNELS),
            "validation_command": _validation_command(task),
            "validation_artifact": _validation_artifact(task),
            "unlocks_gate": _unlocks_gate(task),
            "evidence_to_archive": _evidence_to_archive(task),
            "blocker": "live input missing or placeholder" if task.get("current_status") != "ready" else "",
            "safe_handling": _safe_handling(task),
            "access_scope": task.get("access_scope") or "",
            "partner_id": task.get("partner_id") or "",
        }
        rows.append(row)
    return rows


def _summary(
    rows: list[dict[str, Any]],
    live_readiness: dict[str, Any] | None,
    live_launch_request: dict[str, Any] | None,
    production_proof: dict[str, Any] | None,
) -> dict[str, Any]:
    env_vars = sorted({env for row in rows for env in row.get("accepted_env_vars", [])})
    owners = sorted({str(row.get("owner")) for row in rows if row.get("owner")})
    categories: dict[str, int] = {}
    for row in rows:
        category = str(row.get("category") or "live_input")
        categories[category] = categories.get(category, 0) + 1
    production_verified = bool((production_proof or {}).get("production_gate", {}).get("verified") is True)
    live_inputs_ready = bool(
        live_readiness
        and live_readiness.get("ready_to_run_live_cutover") is True
        and int((live_launch_request or {}).get("summary", {}).get("task_count") or len(rows)) == 0
    )
    return {
        "live_readiness_status": (live_readiness or {}).get("status"),
        "ready_to_run_live_cutover": bool((live_readiness or {}).get("ready_to_run_live_cutover") is True),
        "live_launch_request_status": (live_launch_request or {}).get("status"),
        "task_count": len(rows),
        "secret_task_count": len([row for row in rows if row.get("secret_value_required")]),
        "env_var_count": len(env_vars),
        "owner_count": len(owners),
        "by_category": dict(sorted(categories.items())),
        "env_var_names": env_vars,
        "owners": owners,
        "live_inputs_ready": live_inputs_ready,
        "production_verified": production_verified,
        "production_verified_label": f"production_verified={str(production_verified).lower()}",
    }


def _secret_scan(report: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(report, ensure_ascii=False)
    findings = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(body)]
    raw_contact_like = bool(re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", body))
    if raw_contact_like:
        findings.append("email_address")
    return {
        "status": "pass" if not findings else "fail",
        "issue_count": len(findings),
        "patterns": findings,
    }


def _write_checklist_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "handoff_id",
        "category",
        "owner_label",
        "status",
        "input_name",
        "env_var",
        "credential_kind",
        "secret_value_required",
        "required_for_live",
        "current_status",
        "safe_channel",
        "validation_artifact",
        "unlocks_gate",
        "evidence_to_archive",
        "blocker",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _write_channel_contract_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "handoff_id",
        "env_var",
        "safe_channel",
        "forbidden_channels",
        "safe_handling",
        "validation_command",
        "validation_artifact",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "handoff_id": row.get("handoff_id"),
                "env_var": row.get("env_var"),
                "safe_channel": row.get("safe_channel"),
                "forbidden_channels": "; ".join(row.get("forbidden_channels") or []),
                "safe_handling": row.get("safe_handling"),
                "validation_command": row.get("validation_command"),
                "validation_artifact": row.get("validation_artifact"),
            })


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# HomePilot Live Credential Handoff",
        "",
        f"Created: {report['created_at']}",
        f"Release: {report['release_label']}",
        f"Status: {report['status']}",
        "",
        "This handoff translates missing live launch inputs into a secret-safe customer/IT contract. It is non-mutating, stores env var names only, and does not prove production by itself.",
        "",
        "## Summary",
        "",
        f"- Open credential/config tasks: {summary['task_count']}",
        f"- Secret-bearing tasks: {summary['secret_task_count']}",
        f"- Env var names: {summary['env_var_count']}",
        f"- Owners: {summary['owner_count']}",
        f"- Live inputs ready: {str(summary['live_inputs_ready']).lower()}",
        f"- {summary['production_verified_label']}",
        f"- Secret scan: {report['secret_scan']['status']}",
        "",
        "## Required Inputs",
        "",
    ]
    if not report["handoff_rows"]:
        lines.append("- None. Live readiness has no open credential/config tasks.")
    for row in report["handoff_rows"]:
        secret_label = "secret" if row["secret_value_required"] else "configuration"
        lines.append(
            f"- `{row['env_var']}` ({secret_label}) owned by {row['owner_label']}: "
            f"unlocks {row['unlocks_gate']}; archive {row['validation_artifact']}."
        )
    lines += [
        "",
        "## Secret Channel Contract",
        "",
        "| Env Var | Safe Channel | Forbidden Channels | Validation Artifact |",
        "| --- | --- | --- | --- |",
    ]
    for row in report["handoff_rows"]:
        forbidden = ", ".join(row.get("forbidden_channels") or [])
        lines.append(f"| `{row['env_var']}` | {row['safe_channel']} | {forbidden} | {row['validation_artifact']} |")
    lines += [
        "",
        "## Guardrails",
        "",
        "- Env var names only; secret values stay in the approved secret manager or local live-proof session.",
        "- No raw customer contacts, JWTs, passwords, service keys, database URLs, or partner cross-tenant data in this pack.",
        "- No Supabase writes, outreach, imports, or partner portal access are authorized by this handoff.",
        "- Production remains no_go until live schema verification, live RLS launch, and customer access verification pass with production_verified=true.",
        "",
        "## Files",
        "",
    ]
    for label, path in report["paths"].items():
        lines.append(f"- {label}: {path}")
    lines.append("")
    return "\n".join(lines)


def build_live_credential_handoff_pack(
    out_dir: Path,
    *,
    live_readiness: dict[str, Any] | None = None,
    live_launch_request: dict[str, Any] | None = None,
    live_proof_plan: dict[str, Any] | None = None,
    production_proof: dict[str, Any] | None = None,
    release_label: str = "local",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = _build_rows(live_launch_request)
    report = {
        "handoff_type": "homepilot_live_credential_handoff",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": "ready_for_live_validation" if not rows and (live_readiness or {}).get("ready_to_run_live_cutover") is True else "handoff_required",
        "summary": _summary(rows, live_readiness, live_launch_request, production_proof),
        "handoff_rows": rows,
        "inputs": {
            "live_readiness_status": (live_readiness or {}).get("status"),
            "live_launch_request_status": (live_launch_request or {}).get("status"),
            "live_proof_plan_status": (live_proof_plan or {}).get("status"),
            "production_verified": bool((production_proof or {}).get("production_gate", {}).get("verified") is True),
        },
        "guardrails": {
            "non_mutating": True,
            "no_supabase_writes": True,
            "no_live_writes": True,
            "no_secret_values": True,
            "env_var_names_only": True,
            "no_raw_contact_data": True,
            "no_cross_tenant_data": True,
            "no_outreach_authorized": True,
            "approved_secret_channel_required": True,
            "production_requires_live_schema_rls_customer_access_proof": True,
        },
        "paths": {
            "live_credential_handoff": str(out_dir / "live_credential_handoff.json"),
            "markdown": str(out_dir / "LIVE_CREDENTIAL_HANDOFF.md"),
            "checklist_csv": str(out_dir / "LIVE_CREDENTIAL_HANDOFF_CHECKLIST.csv"),
            "secret_channel_contract": str(out_dir / "LIVE_SECRET_CHANNEL_CONTRACT.csv"),
        },
    }
    report["secret_scan"] = _secret_scan(report)
    report["guardrails"]["no_secret_values"] = report["secret_scan"]["status"] == "pass"
    write_json(out_dir / "live_credential_handoff.json", report)
    write_text(out_dir / "LIVE_CREDENTIAL_HANDOFF.md", render_markdown(report))
    _write_checklist_csv(out_dir / "LIVE_CREDENTIAL_HANDOFF_CHECKLIST.csv", rows)
    _write_channel_contract_csv(out_dir / "LIVE_SECRET_CHANNEL_CONTRACT.csv", rows)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot live credential handoff pack")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--live-readiness", type=Path)
    parser.add_argument("--live-launch-request", type=Path)
    parser.add_argument("--live-proof-plan", type=Path)
    parser.add_argument("--production-proof", type=Path)
    parser.add_argument("--release-label", default="local")
    args = parser.parse_args()

    report = build_live_credential_handoff_pack(
        args.out_dir,
        live_readiness=load_json(args.live_readiness),
        live_launch_request=load_json(args.live_launch_request),
        live_proof_plan=load_json(args.live_proof_plan),
        production_proof=load_json(args.production_proof),
        release_label=args.release_label,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": report["status"],
        "task_count": report["summary"]["task_count"],
        "secret_task_count": report["summary"]["secret_task_count"],
        "markdown": report["paths"]["markdown"],
        "checklist_csv": report["paths"]["checklist_csv"],
        "secret_channel_contract": report["paths"]["secret_channel_contract"],
        "secret_scan": report["secret_scan"]["status"],
    }, indent=2, ensure_ascii=False))
    if report["secret_scan"]["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
