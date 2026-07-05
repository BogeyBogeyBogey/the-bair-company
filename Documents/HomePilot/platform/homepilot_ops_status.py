#!/usr/bin/env python3
"""
Build a HomePilot operational status report.

Readiness, due diligence, preflight, release audit, optional live readiness,
live launch, and customer access evidence are useful separately. This module
turns them into one operator status page: what is ready, what is blocked, what
evidence is fresh, and what to do next.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_preflight import build_preflight_report
from homepilot_release_audit import build_release_audit


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _age_days(value: Any, now: datetime) -> int | None:
    parsed = _parse_time(value)
    if not parsed:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0, (now - parsed.astimezone(timezone.utc)).days)


def _check(name: str, status: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"name": name, "status": status, "detail": detail, **extra}


def _gate_statuses(readiness: dict[str, Any] | None) -> dict[str, str]:
    if not readiness:
        return {}
    return {str(gate.get("name")): str(gate.get("status")) for gate in readiness.get("gates", [])}


def _evidence_freshness(label: str, report: dict[str, Any] | None, now: datetime, max_age_days: int) -> dict[str, Any]:
    if not report:
        return _check(label, "fail", "Evidence report is missing.")
    age = _age_days(report.get("created_at"), now)
    if age is None:
        return _check(label, "warn", "Evidence report has no parseable created_at.")
    status = "pass" if age <= max_age_days else "warn"
    detail = f"Evidence age is {age} days; max recommended age is {max_age_days} days."
    return _check(label, status, detail, age_days=age, max_age_days=max_age_days)


def _artifact_check(due_diligence: dict[str, Any] | None, key: str, label: str) -> dict[str, Any]:
    paths = due_diligence.get("paths", {}) if due_diligence else {}
    path = paths.get(key)
    exists = bool(path and Path(path).exists())
    return _check(
        label,
        "pass" if exists else "warn",
        f"{key} artifact {'exists' if exists else 'is missing or not materialized' }.",
        path=path,
    )


def _overall_status(decisions: dict[str, str], checks: list[dict[str, Any]]) -> str:
    if decisions.get("production") == "go":
        return "production_operational"
    if decisions.get("buyer_review") == "go":
        return "buyer_review_ready"
    if any(check["status"] == "fail" for check in checks):
        return "action_required"
    return "review_required"


def build_ops_status(
    readiness: dict[str, Any] | None,
    due_diligence: dict[str, Any] | None,
    launch: dict[str, Any] | None = None,
    customer_access: dict[str, Any] | None = None,
    schema_verification: dict[str, Any] | None = None,
    live_readiness: dict[str, Any] | None = None,
    stage: str = "buyer_review",
    live: bool = False,
    env: dict[str, str] | None = None,
    release_label: str = "local",
    preflight_report: dict[str, Any] | None = None,
    release_audit_report: dict[str, Any] | None = None,
    max_evidence_age_days: int = 30,
) -> dict[str, Any]:
    preflight = preflight_report or build_preflight_report(
        readiness=readiness,
        due_diligence=due_diligence,
        launch=launch,
        customer_access=customer_access,
        schema_verification=schema_verification,
        live_readiness=live_readiness,
        env=env,
        stage=stage,
        live=live,
    )
    release_audit = release_audit_report or build_release_audit(
        readiness=readiness,
        due_diligence=due_diligence,
        live_readiness=live_readiness,
        launch=launch,
        customer_access=customer_access,
        schema_verification=schema_verification,
    )
    now = datetime.now(timezone.utc)
    decisions = preflight["decisions"]
    readiness_gates = _gate_statuses(readiness)
    failed_gates = {name: status for name, status in readiness_gates.items() if status == "fail"}
    non_pass_gates = {name: status for name, status in readiness_gates.items() if status != "pass"}
    redaction = due_diligence.get("redaction", {}) if due_diligence else {}
    local_health = preflight.get("healthchecks", {}).get("local", {})
    live_health = preflight.get("healthchecks", {}).get("live", {})
    production_proof_ready = bool(
        live_readiness
        and live_readiness.get("status") == "ready"
        and live_readiness.get("ready_to_run_live_cutover") is True
        and schema_verification
        and schema_verification.get("production_verified") is True
        and launch
        and launch.get("production_verified") is True
        and customer_access
        and customer_access.get("production_verified") is True
    )

    checks = [
        _check(
            "readiness_gates",
            "pass" if readiness and readiness.get("status") == "pass" and not failed_gates else "fail",
            f"{len(readiness_gates)} readiness gates checked; {len(failed_gates)} failed.",
            non_pass_gates=non_pass_gates,
        ),
        _check(
            "due_diligence",
            "pass" if due_diligence and due_diligence.get("status") in {"local_ready", "production_ready"} and redaction.get("status") == "pass" else "fail",
            f"Due diligence status is {due_diligence.get('status') if due_diligence else 'missing'}; redaction is {redaction.get('status')}.",
        ),
        _check(
            "local_health",
            "pass" if local_health.get("status") in {"pass", "warn"} else "fail",
            f"Local health status is {local_health.get('status')}.",
            summary=local_health.get("summary", {}),
        ),
        _check(
            "live_health",
            "pass" if decisions.get("live_launch") == "go" else "blocked",
            "Live launch is ready." if decisions.get("live_launch") == "go" else "Live launch still needs configured Supabase environment and proof.",
            summary=live_health.get("summary", {}),
        ),
        _check(
            "production_proof",
            "pass" if production_proof_ready else "blocked",
            "Live readiness, schema, launch, and customer access proof are present." if production_proof_ready else "Missing live readiness, schema verification, launch, and/or customer access report with production_verified=true.",
        ),
        _artifact_check(due_diligence, "data_dictionary", "data_dictionary_artifact"),
        _artifact_check(due_diligence, "api_contract", "api_contract_artifact"),
        _evidence_freshness("readiness_freshness", readiness, now, max_evidence_age_days),
        _evidence_freshness("due_diligence_freshness", due_diligence, now, max_evidence_age_days),
    ]
    if live_readiness:
        checks.append(_evidence_freshness("live_readiness_freshness", live_readiness, now, max_evidence_age_days))
    if launch:
        checks.append(_evidence_freshness("launch_freshness", launch, now, max_evidence_age_days))
    if customer_access:
        checks.append(_evidence_freshness("customer_access_freshness", customer_access, now, max_evidence_age_days))

    return {
        "report_type": "homepilot_ops_status",
        "created_at": utc_now(),
        "release_label": release_label,
        "requested_stage": stage,
        "status": _overall_status(decisions, checks),
        "decisions": decisions,
        "blockers": preflight["blockers"],
        "checks": checks,
        "open_actions": preflight.get("next_actions", []),
        "production_blockers": release_audit.get("blockers", {}).get("production", []),
        "evidence": {
            "readiness_status": readiness.get("status") if readiness else None,
            "readiness_gate_count": len(readiness_gates),
            "due_diligence_status": due_diligence.get("status") if due_diligence else None,
            "release_status": release_audit.get("status"),
            "live_readiness_status": live_readiness.get("status") if live_readiness else None,
            "live_readiness_ready_to_run_live_cutover": live_readiness.get("ready_to_run_live_cutover") if live_readiness else None,
            "schema_verification_status": schema_verification.get("status") if schema_verification else None,
            "schema_verification_production_verified": schema_verification.get("production_verified") if schema_verification else None,
            "launch_status": launch.get("status") if launch else None,
            "launch_production_verified": launch.get("production_verified") if launch else None,
            "customer_access_status": customer_access.get("status") if customer_access else None,
            "customer_access_production_verified": customer_access.get("production_verified") if customer_access else None,
        },
    }


def render_status_page(report: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Operational Status",
        "",
        f"Release: {report['release_label']}",
        f"Created: {report['created_at']}",
        f"Requested stage: {report['requested_stage']}",
        f"Status: {report['status']}",
        "",
        "## Decisions",
        "",
    ]
    for label, value in report["decisions"].items():
        lines.append(f"- {label}: {value}")
    lines += ["", "## Checks", ""]
    for check in report["checks"]:
        lines.append(f"- {check['name']}: {check['status']} - {check['detail']}")
    lines += ["", "## Open Actions", ""]
    for action in report["open_actions"]:
        lines.append(f"- {action['label']}: {action['status']} - {action['detail']}")
    lines += ["", "## Production Blockers", ""]
    blockers = report.get("production_blockers", [])
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- None.")
    lines.append("")
    return "\n".join(lines)


def render_ops_runbook(report: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Ops Runbook",
        "",
        "Use this after every buyer-review pack, live launch attempt, or production rollout.",
        "",
        "## Current Actions",
        "",
    ]
    for action in report["open_actions"]:
        lines.append(f"- {action['label']}: {action['detail']}")
    lines += [
        "",
        "## Standard Cadence",
        "",
        "- Rebuild readiness and due-diligence evidence after schema, dashboard, metric, or export changes.",
        "- Rebuild the release evidence bundle before customer/security review.",
        "- Run live healthcheck and RLS launch before production access.",
        "- Archive launch and cleanup evidence before removing live fixtures.",
        "",
    ]
    return "\n".join(lines)


def write_ops_status_pack(out_dir: Path, report: dict[str, Any]) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    status_path = out_dir / "ops_status.json"
    status_page_path = out_dir / "STATUS_PAGE.md"
    runbook_path = out_dir / "OPS_RUNBOOK.md"
    write_json(status_path, report)
    write_text(status_page_path, render_status_page(report))
    write_text(runbook_path, render_ops_runbook(report))
    return {
        "status": report["status"],
        "paths": {
            "ops_status": str(status_path),
            "status_page": str(status_page_path),
            "ops_runbook": str(runbook_path),
        },
        "report": report,
    }


def build_ops_status_pack(
    out_dir: Path,
    readiness_report_path: Path,
    due_diligence_report_path: Path,
    launch_report_path: Path | None = None,
    customer_access_report_path: Path | None = None,
    schema_verification_report_path: Path | None = None,
    live_readiness_report_path: Path | None = None,
    release_label: str = "local",
    stage: str = "buyer_review",
    live: bool = False,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    readiness = load_json(readiness_report_path)
    due_diligence = load_json(due_diligence_report_path)
    launch = load_json(launch_report_path)
    customer_access = load_json(customer_access_report_path)
    schema_verification = load_json(schema_verification_report_path)
    live_readiness = load_json(live_readiness_report_path)
    report = build_ops_status(
        readiness=readiness,
        due_diligence=due_diligence,
        live_readiness=live_readiness,
        launch=launch,
        customer_access=customer_access,
        schema_verification=schema_verification,
        release_label=release_label,
        stage=stage,
        live=live,
        env=env,
    )
    return write_ops_status_pack(out_dir, report)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot operational status report")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--readiness-report", required=True, type=Path)
    parser.add_argument("--due-diligence-report", required=True, type=Path)
    parser.add_argument("--launch-report", type=Path)
    parser.add_argument("--customer-access-report", type=Path)
    parser.add_argument("--schema-verification-report", type=Path)
    parser.add_argument("--live-readiness-report", type=Path)
    parser.add_argument("--release-label", default="local")
    parser.add_argument("--stage", choices=("buyer_review", "live_launch", "production_rollout"), default="buyer_review")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    pack = build_ops_status_pack(
        out_dir=args.out_dir,
        readiness_report_path=args.readiness_report,
        due_diligence_report_path=args.due_diligence_report,
        launch_report_path=args.launch_report,
        customer_access_report_path=args.customer_access_report,
        schema_verification_report_path=args.schema_verification_report,
        live_readiness_report_path=args.live_readiness_report,
        release_label=args.release_label,
        stage=args.stage,
        live=args.live,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": pack["status"],
        "decisions": pack["report"]["decisions"],
        "ops_status": pack["paths"]["ops_status"],
        "status_page": pack["paths"]["status_page"],
        "open_actions": pack["report"]["open_actions"],
    }, indent=2, ensure_ascii=False))
    if pack["status"] == "action_required":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
