#!/usr/bin/env python3
"""
Build the HomePilot live proof execution plan.

This is the operator bridge between buyer-review evidence and production proof.
It translates the existing live readiness request, cutover dry-run, release
index, and production proof blockers into a single ordered plan. The plan never
writes to Supabase, never stores secret values, and never authorizes outreach.
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
    r"eyJ[A-Za-z0-9_-]{20,}\.",
    r"postgres(?:ql)?://[^'\"\s]+:[^@'\"\s]+@",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"service_role=[A-Za-z0-9_-]{12,}",
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


def _count_tasks(live_launch_request: dict[str, Any] | None, category: str | None = None) -> int:
    tasks = (live_launch_request or {}).get("tasks") or []
    if category:
        return len([task for task in tasks if task.get("category") == category])
    return len(tasks)


def _secret_task_count(live_launch_request: dict[str, Any] | None) -> int:
    return len([task for task in (live_launch_request or {}).get("tasks") or [] if task.get("secret_value_required")])


def _first_path(*values: Any) -> str | None:
    for value in values:
        if value:
            return str(value)
    return None


def _path_from_readiness(readiness: dict[str, Any] | None, key: str, *parts: str) -> str | None:
    base = (readiness or {}).get("paths", {}).get(key)
    if not base:
        return None
    return str(Path(base, *parts))


def _production_blockers(production_proof: dict[str, Any] | None) -> list[str]:
    gate = (production_proof or {}).get("production_gate") or {}
    blockers = gate.get("blockers") or []
    return [str(blocker) for blocker in blockers]


def _execution_status(live_readiness: dict[str, Any] | None, production_proof: dict[str, Any] | None) -> str:
    if (production_proof or {}).get("production_gate", {}).get("verified") is True:
        return "production_verified"
    if live_readiness and live_readiness.get("ready_to_run_live_cutover") is True:
        return "ready_to_execute_live_proof"
    return "blocked_until_live_inputs"


def _redacted_command(value: str) -> str:
    # The command may contain local paths and env var names, but never inline secret values.
    return value.replace("\n", " ").strip()


def _commands(
    out_dir: Path,
    release_label: str,
    readiness_report_path: Path | None,
    due_diligence_report_path: Path | None,
    account_access_plan_path: Path | None,
    live_readiness_report_path: Path | None,
    live_launch_request_path: Path | None,
    artifact_index_path: Path | None,
    production_proof_path: Path | None,
) -> dict[str, str]:
    live_dir = out_dir / "live_execution"
    release_dir = out_dir.parent / "release_live"
    market_dir = out_dir.parent / "market_live"
    live_artifact_index = release_dir / "artifact_index.json"
    live_production_proof = release_dir / "production_proof.json"
    generated_live_readiness = live_dir / "live_readiness" / "live_readiness.json"
    readiness_arg = readiness_report_path or Path("/path/to/readiness_report.json")
    due_arg = due_diligence_report_path or Path("/path/to/due_diligence_report.json")
    access_arg = account_access_plan_path or Path("/path/to/account_access_plan.json")
    live_launch_request_arg = live_launch_request_path or Path("/path/to/live_launch_request.json")
    return {
        "source_env": "source /secure/path/homepilot_live.env",
        "rerun_live_readiness": _redacted_command(
            "python3 platform/homepilot_live_readiness.py "
            f"--out-dir {live_dir / 'live_readiness'} "
            f"--readiness-report {readiness_arg} "
            f"--due-diligence-report {due_arg} "
            f"--account-access-plan {access_arg} "
            f"--release-label {release_label}"
        ),
        "run_live_cutover": _redacted_command(
            "python3 platform/homepilot_production_cutover.py --live "
            f"--out-dir {live_dir / 'production_cutover'} "
            f"--readiness-report {readiness_arg} "
            f"--due-diligence-report {due_arg} "
            f"--account-access-plan {access_arg} "
            f"--release-label {release_label}"
        ),
        "verify_live_readiness_ready": _redacted_command(
            "python3 -c "
            "\"import json, sys; from pathlib import Path; "
            f"report=json.loads(Path('{generated_live_readiness}').read_text(encoding='utf-8')); "
            "ok=report.get('ready_to_run_live_cutover') is True; "
            "print({'ready_to_run_live_cutover': ok, 'status': report.get('status')}); "
            "sys.exit(0 if ok else 1)\""
        ),
        "regenerate_release": _redacted_command(
            "python3 platform/homepilot_release_pack.py "
            f"--out-dir {release_dir} "
            f"--readiness-report {readiness_arg} "
            f"--due-diligence-report {due_arg} "
            f"--live-readiness-report {generated_live_readiness} "
            f"--schema-verification-report {live_dir / 'production_cutover' / 'schema_verification' / 'schema_verification.json'} "
            f"--launch-report {live_dir / 'production_cutover' / 'launch' / 'launch_report.json'} "
            f"--customer-access-report {live_dir / 'production_cutover' / 'customer_access' / 'customer_access_verification.json'} "
            f"--release-label {release_label} "
            "--stage production_rollout --live"
        ),
        "regenerate_market": _redacted_command(
            "python3 platform/homepilot_market_readiness.py "
            f"--out-dir {market_dir} "
            f"--readiness-report {readiness_arg} "
            f"--due-diligence-report {due_arg} "
            f"--artifact-index {live_artifact_index} "
            f"--production-proof {live_production_proof} "
            f"--live-readiness-report {generated_live_readiness} "
            f"--live-launch-request {live_launch_request_arg} "
            f"--release-label {release_label}"
        ),
        "verify_production": _redacted_command(
            "python3 -c "
            "\"import json, sys; from pathlib import Path; "
            f"proof=json.loads(Path('{live_production_proof}').read_text(encoding='utf-8')); "
            "ok=proof.get('production_gate',{}).get('verified') is True; "
            "print({'production_verified': ok, 'status': proof.get('status')}); "
            "sys.exit(0 if ok else 1)\""
        ),
    }


def _step(
    key: str,
    label: str,
    owner: str,
    status: str,
    command_key: str | None,
    expected_artifact: str | None,
    pass_condition: str,
    guardrail: str,
    required_env_confirmations: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "step_key": key,
        "label": label,
        "owner": owner,
        "status": status,
        "command_key": command_key,
        "expected_artifact": expected_artifact,
        "pass_condition": pass_condition,
        "guardrail": guardrail,
        "required_env_confirmations": required_env_confirmations or {},
    }


def _execution_steps(
    commands: dict[str, str],
    live_readiness: dict[str, Any] | None,
    live_launch_request: dict[str, Any] | None,
    production_proof: dict[str, Any] | None,
    readiness_report_path: Path | None,
    due_diligence_report_path: Path | None,
    account_access_plan_path: Path | None,
    out_dir: Path,
) -> list[dict[str, Any]]:
    inputs_ready = bool(live_readiness and live_readiness.get("ready_to_run_live_cutover") is True)
    production_verified = bool((production_proof or {}).get("production_gate", {}).get("verified") is True)
    missing_tasks = _count_tasks(live_launch_request)
    return [
        _step(
            "complete_secret_inputs",
            "Complete live Supabase, RLS fixture, and planned customer-access inputs",
            "Platform admin + HomePilot operator + customer success",
            "pass" if missing_tasks == 0 else "blocked",
            None,
            (live_launch_request or {}).get("paths", {}).get("checklist_csv"),
            "LIVE_LAUNCH_CHECKLIST.csv has no required open tasks and secrets are stored outside the evidence room.",
            "Never send service keys, database URLs, fixture passwords, JWTs, or customer passwords in email or reports.",
        ),
        _step(
            "rerun_live_readiness",
            "Rerun live readiness after the secure env is loaded",
            "HomePilot operator",
            "pass" if inputs_ready else "waiting_for_inputs",
            "rerun_live_readiness",
            str(out_dir / "live_execution" / "live_readiness" / "live_readiness.json"),
            "live_readiness.status=ready and ready_to_run_live_cutover=true.",
            "This command reads env vars and writes redacted status only.",
        ),
        _step(
            "verify_live_readiness_ready",
            "Stop unless the regenerated live readiness report is ready",
            "HomePilot operator",
            "pass" if inputs_ready else "blocked",
            "verify_live_readiness_ready",
            str(out_dir / "live_execution" / "live_readiness" / "live_readiness.json"),
            "Regenerated live_readiness.json has ready_to_run_live_cutover=true.",
            "Prevents stale, missing, or incomplete live inputs from reaching the live cutover command.",
        ),
        _step(
            "review_apply_sql",
            "Apply the reviewed SQL bundle in Supabase/Postgres",
            "Customer IT / database owner",
            "manual_review",
            None,
            "SQL_APPLY_PLAN.md and apply.sql",
            "SQL has been applied by the authorized database owner and post-apply verification is ready to run.",
            "HomePilot does not silently apply SQL from the boardroom pack.",
        ),
        _step(
            "run_live_cutover",
            "Run live schema, module seed, RLS launch, and customer-access proof chain",
            "HomePilot operator + IT owner",
            "ready" if inputs_ready else "blocked",
            "run_live_cutover",
            str(out_dir / "live_execution" / "production_cutover" / "cutover_report.json"),
            "cutover_report.status=production_verified and nested schema/RLS/customer-access reports have production_verified=true.",
            "This is the first step that can touch live Supabase; run only after customer approval and secure env review.",
            {
                "HOMEPILOT_SQL_APPLY_CONFIRM": "reviewed-sql-applied",
                "HOMEPILOT_CUSTOMER_LIVE_PROOF_CONFIRM": "customer-approved-live-proof",
            },
        ),
        _step(
            "regenerate_release_pack",
            "Regenerate release evidence from live proof artifacts",
            "HomePilot operator",
            "ready_after_cutover",
            "regenerate_release",
            "artifact_index.json and production_proof.json",
            "release decisions are buyer_review=go, live_launch=go, production=go.",
            "Do not edit production proof by hand; regenerate it from archived evidence.",
        ),
        _step(
            "regenerate_market_pack",
            "Regenerate customer-facing market pack and portable data room",
            "HomePilot operator + customer success",
            "ready_after_release",
            "regenerate_market",
            "homepilot_boardroom_data_room.zip",
            "portable data room has production_verified=true evidence and no local path or secret leakage.",
            "Customer-facing materials must keep tenant/module/partner scope and avoid homeowner-intent claims.",
        ),
        _step(
            "verify_production_gate",
            "Run final machine-readable production gate check",
            "HomePilot operator",
            "pass" if production_verified else "blocked",
            "verify_production",
            "production_proof.json",
            "production_gate.verified=true.",
            "This verifies evidence; it is not a substitute for customer signoff or incident rollback readiness.",
        ),
    ]


def _evidence_map(
    live_readiness: dict[str, Any] | None,
    live_launch_request: dict[str, Any] | None,
    production_cutover: dict[str, Any] | None,
    production_proof: dict[str, Any] | None,
    artifact_index: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    schema_status = None
    launch_status = None
    customer_access_status = None
    if production_cutover:
        steps = {step.get("name"): step for step in production_cutover.get("steps", [])}
        schema_status = steps.get("schema_verification", {}).get("detail")
        launch_status = steps.get("rls_launch", {}).get("detail")
        customer_access_status = steps.get("customer_access_verification", {}).get("detail")
    return [
        {
            "artifact_key": "live_launch_request",
            "required_status": "ready",
            "current_status": (live_launch_request or {}).get("status"),
            "current_path": (live_launch_request or {}).get("paths", {}).get("live_launch_request"),
            "unlocks": "secure live input completion",
        },
        {
            "artifact_key": "live_readiness",
            "required_status": "ready / ready_to_run_live_cutover=true",
            "current_status": (live_readiness or {}).get("status"),
            "current_path": (live_readiness or {}).get("paths", {}).get("live_readiness"),
            "unlocks": "live cutover execution",
        },
        {
            "artifact_key": "schema_verification",
            "required_status": "pass / production_verified=true",
            "current_status": schema_status or "not_live_verified",
            "current_path": (production_cutover or {}).get("paths", {}).get("schema_verification"),
            "unlocks": "deployed schema and RLS policy confidence",
        },
        {
            "artifact_key": "rls_launch",
            "required_status": "pass / production_verified=true",
            "current_status": launch_status or "not_live_verified",
            "current_path": (production_cutover or {}).get("paths", {}).get("launch_report"),
            "unlocks": "live RLS fixture proof",
        },
        {
            "artifact_key": "customer_access_verification",
            "required_status": "pass / production_verified=true",
            "current_status": customer_access_status or "not_live_verified",
            "current_path": (production_cutover or {}).get("paths", {}).get("customer_access_verification"),
            "unlocks": "planned owner, manager, and partner-scoped access proof",
        },
        {
            "artifact_key": "production_proof",
            "required_status": "production_gate.verified=true",
            "current_status": (production_proof or {}).get("status"),
            "current_path": (production_proof or {}).get("paths", {}).get("production_proof"),
            "unlocks": "production go decision",
        },
        {
            "artifact_key": "release_index",
            "required_status": "production_ready / stage_status=pass",
            "current_status": (artifact_index or {}).get("status"),
            "current_path": (artifact_index or {}).get("paths", {}).get("artifact_index"),
            "unlocks": "boardroom and procurement release evidence",
        },
    ]


def _secret_scan(report: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(report, ensure_ascii=False)
    findings = [pattern for pattern in SECRET_PATTERNS if re.search(pattern, text)]
    return {
        "status": "pass" if not findings else "fail",
        "findings": findings,
    }


def _plan_validation(report: dict[str, Any]) -> dict[str, Any]:
    steps = report.get("execution_steps") or []
    step_keys = [str(step.get("step_key") or "") for step in steps]
    step_by_key = {str(step.get("step_key") or ""): step for step in steps}
    commands = report.get("commands") or {}

    def _before(left: str, right: str) -> bool:
        return left in step_keys and right in step_keys and step_keys.index(left) < step_keys.index(right)

    generated_live_readiness = (
        Path(report["paths"]["live_proof_plan"]).parent
        / "live_execution"
        / "live_readiness"
        / "live_readiness.json"
    )
    original_live_readiness = report.get("inputs", {}).get("live_readiness_report")
    checks = [
        {
            "key": "step_order",
            "status": "pass" if _before("rerun_live_readiness", "verify_live_readiness_ready") and _before("verify_live_readiness_ready", "run_live_cutover") else "fail",
            "detail": "Regenerated live readiness is checked before the live cutover command.",
        },
        {
            "key": "readiness_gate_command",
            "status": "pass" if "ready_to_run_live_cutover" in str(commands.get("verify_live_readiness_ready", "")) else "fail",
            "detail": "Readiness gate exits non-zero unless ready_to_run_live_cutover=true.",
        },
        {
            "key": "manual_cutover_confirmations",
            "status": "pass" if {
                "HOMEPILOT_SQL_APPLY_CONFIRM": "reviewed-sql-applied",
                "HOMEPILOT_CUSTOMER_LIVE_PROOF_CONFIRM": "customer-approved-live-proof",
            }.items() <= (step_by_key.get("run_live_cutover", {}).get("required_env_confirmations") or {}).items() else "fail",
            "detail": "Live cutover requires SQL-apply and customer live-proof confirmations.",
        },
        {
            "key": "downstream_uses_regenerated_readiness",
            "status": "pass" if all(
                str(generated_live_readiness) in str(commands.get(command_key, ""))
                for command_key in ("verify_live_readiness_ready", "regenerate_release", "regenerate_market")
            ) else "fail",
            "detail": "Readiness verification and downstream packs use the regenerated live readiness report.",
        },
        {
            "key": "stale_live_readiness_not_reused",
            "status": "pass" if not original_live_readiness or all(
                str(original_live_readiness) not in str(commands.get(command_key, ""))
                for command_key in ("verify_live_readiness_ready", "regenerate_release", "regenerate_market")
            ) else "fail",
            "detail": "Downstream live proof commands do not reuse the input smoke/stale live readiness report.",
        },
        {
            "key": "secret_scan_pass",
            "status": "pass" if report.get("secret_scan", {}).get("status") == "pass" else "fail",
            "detail": "Live proof plan and generated commands contain no detected secret values.",
        },
    ]
    failures = [check for check in checks if check["status"] != "pass"]
    return {
        "status": "pass" if not failures else "fail",
        "checks": checks,
        "failures": failures,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# HomePilot Live Proof Execution Plan",
        "",
        f"Created: {report['created_at']}",
        f"Release: {report['release_label']}",
        f"Status: {report['status']}",
        f"Production verified: {str(summary['production_verified']).lower()}",
        "",
        "## What This Plan Does",
        "",
        "This plan shows the exact handoff from buyer-ready evidence to live production proof. It does not execute live commands, store secrets, authorize outreach, or replace customer signoff.",
        "",
        "## Current Gate",
        "",
        f"- Live readiness: {summary['live_readiness_status']}",
        f"- Ready to run live cutover: {str(summary['ready_to_run_live_cutover']).lower()}",
        f"- Live launch tasks: {summary['live_launch_task_count']}",
        f"- Secret-bearing tasks: {summary['secret_task_count']}",
        f"- Production blockers: {summary['production_blocker_count']}",
        "",
        "## Execution Steps",
        "",
    ]
    for index, step in enumerate(report["execution_steps"], start=1):
        lines.extend([
            f"### {index}. {step['label']}",
            "",
            f"- Status: {step['status']}",
            f"- Owner: {step['owner']}",
            f"- Expected artifact: {step['expected_artifact']}",
            f"- Pass condition: {step['pass_condition']}",
            f"- Guardrail: {step['guardrail']}",
        ])
        if step.get("required_env_confirmations"):
            lines.append("- Required confirmations:")
            for env_name, expected_value in step["required_env_confirmations"].items():
                lines.append(f"  - `{env_name}={expected_value}`")
        if step.get("command_key"):
            lines.extend(["", "```bash", report["commands"][step["command_key"]], "```"])
        lines.append("")
    lines.extend(["## Evidence Map", ""])
    for item in report["evidence_map"]:
        lines.append(f"- `{item['artifact_key']}`: current {item['current_status']} / required {item['required_status']} / unlocks {item['unlocks']}")
    if report["production_blockers"]:
        lines.extend(["", "## Production Blockers", ""])
        for blocker in report["production_blockers"]:
            lines.append(f"- {blocker}")
    lines.extend(["", "## Guardrails", ""])
    for key, value in report["guardrails"].items():
        lines.append(f"- {key}: {str(value).lower() if isinstance(value, bool) else value}")
    if report.get("plan_validation"):
        lines.extend(["", "## Plan Validation", ""])
        lines.append(f"- Status: {report['plan_validation']['status']}")
        for check in report["plan_validation"]["checks"]:
            lines.append(f"- {check['key']}: {check['status']} - {check['detail']}")
    lines.append("")
    return "\n".join(lines)


def _write_evidence_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["artifact_key", "required_status", "current_status", "current_path", "unlocks"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def render_command_script(report: dict[str, Any]) -> str:
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        "# HomePilot live proof command script.",
        "# Review this file with customer IT before running. It contains no secret values.",
        "# To run live commands, load the secure env first and set:",
        "#   export HOMEPILOT_LIVE_PROOF_CONFIRM=run-live-proof",
        "# Before the live cutover step, also set the manual gate confirmations shown below.",
        "",
        'if [[ "${HOMEPILOT_LIVE_PROOF_CONFIRM:-}" != "run-live-proof" ]]; then',
        '  echo "Refusing to run live proof commands without HOMEPILOT_LIVE_PROOF_CONFIRM=run-live-proof"',
        "  exit 2",
        "fi",
        "",
    ]
    for step in report["execution_steps"]:
        command_key = step.get("command_key")
        if not command_key:
            lines.extend([f"# Manual step: {step['label']}", ""])
            continue
        for env_name, expected_value in step.get("required_env_confirmations", {}).items():
            lines.extend([
                f'if [[ "${{{env_name}:-}}" != "{expected_value}" ]]; then',
                f'  echo "Refusing to run {step["step_key"]}: set {env_name}={expected_value} after completing the required manual approval."',
                "  exit 2",
                "fi",
                "",
            ])
        lines.extend([
            f"# {step['label']}",
            report["commands"][command_key],
            "",
        ])
    return "\n".join(lines)


def build_live_proof_plan_pack(
    out_dir: Path,
    readiness_report_path: Path | None = None,
    due_diligence_report_path: Path | None = None,
    live_readiness_report_path: Path | None = None,
    live_launch_request_path: Path | None = None,
    production_cutover_report_path: Path | None = None,
    production_proof_path: Path | None = None,
    artifact_index_path: Path | None = None,
    account_access_plan_path: Path | None = None,
    release_label: str = "production-candidate",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    readiness = load_json(readiness_report_path)
    live_readiness = load_json(live_readiness_report_path)
    live_launch_request = load_json(live_launch_request_path)
    production_cutover = load_json(production_cutover_report_path)
    production_proof = load_json(production_proof_path)
    artifact_index = load_json(artifact_index_path)

    if not account_access_plan_path:
        candidate = _path_from_readiness(readiness, "account_access_smoke", "account_access_plan.json")
        account_access_plan_path = Path(candidate) if candidate else None

    commands = _commands(
        out_dir=out_dir,
        release_label=release_label,
        readiness_report_path=readiness_report_path,
        due_diligence_report_path=due_diligence_report_path,
        account_access_plan_path=account_access_plan_path,
        live_readiness_report_path=live_readiness_report_path,
        live_launch_request_path=live_launch_request_path,
        artifact_index_path=artifact_index_path,
        production_proof_path=production_proof_path,
    )
    execution_steps = _execution_steps(
        commands=commands,
        live_readiness=live_readiness,
        live_launch_request=live_launch_request,
        production_proof=production_proof,
        readiness_report_path=readiness_report_path,
        due_diligence_report_path=due_diligence_report_path,
        account_access_plan_path=account_access_plan_path,
        out_dir=out_dir,
    )
    evidence = _evidence_map(
        live_readiness=live_readiness,
        live_launch_request=live_launch_request,
        production_cutover=production_cutover,
        production_proof=production_proof,
        artifact_index=artifact_index,
    )
    blockers = _production_blockers(production_proof)
    report = {
        "report_type": "homepilot_live_proof_execution_plan",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": _execution_status(live_readiness, production_proof),
        "summary": {
            "live_readiness_status": (live_readiness or {}).get("status"),
            "ready_to_run_live_cutover": bool(live_readiness and live_readiness.get("ready_to_run_live_cutover") is True),
            "live_launch_task_count": _count_tasks(live_launch_request),
            "secret_task_count": _secret_task_count(live_launch_request),
            "supabase_task_count": _count_tasks(live_launch_request, "supabase"),
            "rls_fixture_task_count": _count_tasks(live_launch_request, "rls_fixture"),
            "customer_access_task_count": _count_tasks(live_launch_request, "customer_access"),
            "production_verified": bool((production_proof or {}).get("production_gate", {}).get("verified") is True),
            "production_blocker_count": len(blockers),
            "execution_step_count": len(execution_steps),
        },
        "inputs": {
            "readiness_report": str(readiness_report_path) if readiness_report_path else None,
            "due_diligence_report": str(due_diligence_report_path) if due_diligence_report_path else None,
            "live_readiness_report": str(live_readiness_report_path) if live_readiness_report_path else None,
            "live_launch_request": str(live_launch_request_path) if live_launch_request_path else None,
            "production_cutover_report": str(production_cutover_report_path) if production_cutover_report_path else None,
            "production_proof": str(production_proof_path) if production_proof_path else None,
            "artifact_index": str(artifact_index_path) if artifact_index_path else None,
            "account_access_plan": str(account_access_plan_path) if account_access_plan_path else None,
        },
        "commands": commands,
        "execution_steps": execution_steps,
        "evidence_map": evidence,
        "production_blockers": blockers,
        "guardrails": {
            "non_mutating_plan": True,
            "requires_explicit_shell_confirmation": True,
            "no_secret_values_written": True,
            "no_outreach_authorized": True,
            "no_partner_access_authorized_without_customer_access_proof": True,
            "production_requires_schema_rls_customer_access_verified": True,
            "manual_sql_and_customer_signoff_confirmations_required": True,
            "regenerated_live_readiness_gate_required": True,
            "plan_validation_required": True,
        },
        "paths": {
            "live_proof_plan": str(out_dir / "live_proof_execution_plan.json"),
            "markdown": str(out_dir / "LIVE_PROOF_EXECUTION_PLAN.md"),
            "evidence_map": str(out_dir / "LIVE_PROOF_EVIDENCE_MAP.csv"),
            "commands": str(out_dir / "LIVE_PROOF_COMMANDS.sh"),
        },
    }
    report["secret_scan"] = _secret_scan(report)
    report["plan_validation"] = _plan_validation(report)
    write_json(out_dir / "live_proof_execution_plan.json", report)
    write_text(out_dir / "LIVE_PROOF_EXECUTION_PLAN.md", render_markdown(report))
    _write_evidence_csv(out_dir / "LIVE_PROOF_EVIDENCE_MAP.csv", evidence)
    write_text(out_dir / "LIVE_PROOF_COMMANDS.sh", render_command_script(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HomePilot live proof execution plan")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--readiness-report", type=Path)
    parser.add_argument("--due-diligence-report", type=Path)
    parser.add_argument("--live-readiness-report", type=Path)
    parser.add_argument("--live-launch-request", type=Path)
    parser.add_argument("--production-cutover-report", type=Path)
    parser.add_argument("--production-proof", type=Path)
    parser.add_argument("--artifact-index", type=Path)
    parser.add_argument("--account-access-plan", type=Path)
    parser.add_argument("--release-label", default="production-candidate")
    args = parser.parse_args()
    report = build_live_proof_plan_pack(
        out_dir=args.out_dir,
        readiness_report_path=args.readiness_report,
        due_diligence_report_path=args.due_diligence_report,
        live_readiness_report_path=args.live_readiness_report,
        live_launch_request_path=args.live_launch_request,
        production_cutover_report_path=args.production_cutover_report,
        production_proof_path=args.production_proof,
        artifact_index_path=args.artifact_index,
        account_access_plan_path=args.account_access_plan,
        release_label=args.release_label,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": report["status"],
        "live_launch_task_count": report["summary"]["live_launch_task_count"],
        "production_verified": report["summary"]["production_verified"],
        "markdown": report["paths"]["markdown"],
        "evidence_map": report["paths"]["evidence_map"],
        "commands": report["paths"]["commands"],
        "secret_scan": report["secret_scan"]["status"],
        "plan_validation": report["plan_validation"]["status"],
    }, indent=2, ensure_ascii=False))
    if report["secret_scan"]["status"] != "pass" or report["plan_validation"]["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
