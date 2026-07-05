#!/usr/bin/env python3
"""
Build the HomePilot live proof acceptance matrix.

This is a customer/IT review artifact. It defines the evidence that must exist
before HomePilot may move from buyer-ready to live/production-ready. It does not
execute commands, write to Supabase, store secrets, authorize outreach, or
override technical proof requirements.
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

CSV_FIELDS = [
    "key",
    "label",
    "stage",
    "status",
    "owner",
    "source_artifacts",
    "acceptance_criteria",
    "current_evidence",
    "blocker",
    "next_action",
    "safe_handling",
]


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


def _status(ok: bool, blocked: str = "blocked") -> str:
    return "pass" if ok else blocked


def _production_verified(production_proof: dict[str, Any] | None) -> bool:
    gate = (production_proof or {}).get("production_gate") or {}
    return bool(gate.get("verified") or (production_proof or {}).get("production_verified") is True)


def _live_inputs_closed(live_launch_request: dict[str, Any] | None) -> bool:
    summary = (live_launch_request or {}).get("summary") or {}
    return int(summary.get("task_count") or 0) == 0 and bool(live_launch_request)


def _live_readiness_ready(live_readiness: dict[str, Any] | None) -> bool:
    return bool((live_readiness or {}).get("ready_to_run_live_cutover") is True)


def _plan_validated(live_proof_plan: dict[str, Any] | None) -> bool:
    return bool(
        live_proof_plan
        and live_proof_plan.get("secret_scan", {}).get("status") == "pass"
        and live_proof_plan.get("plan_validation", {}).get("status") == "pass"
    )


def _partner_access_ready(partner_access_reconciliation: dict[str, Any] | None) -> bool:
    summary = (partner_access_reconciliation or {}).get("summary") or {}
    return bool(
        (partner_access_reconciliation or {}).get("production_ready") is True
        and int(summary.get("blockers") or 0) == 0
    )


def _partner_auth_ready(partner_auth_mapping: dict[str, Any] | None) -> bool:
    summary = (partner_auth_mapping or {}).get("summary") or {}
    return bool(
        (partner_auth_mapping or {}).get("status") in {"ready", "mapped", "pass"}
        and int(summary.get("mapped_count") or summary.get("partner_auth_mapped_count") or 0)
        >= int(summary.get("expected_count") or summary.get("partner_auth_expected_count") or 1)
    )


def _customer_signoff_ready(customer_signoff_reconciliation: dict[str, Any] | None, key: str) -> bool:
    return bool((customer_signoff_reconciliation or {}).get(key) is True)


def _public_data_ready(public_data_reconciliation: dict[str, Any] | None) -> bool:
    summary = (public_data_reconciliation or {}).get("summary") or {}
    first_wave_required = bool(summary.get("public_data_first_wave_required"))
    if not first_wave_required:
        return True
    return bool((public_data_reconciliation or {}).get("production_import_ready") is True)


def _missing_live_artifacts(production_proof: dict[str, Any] | None) -> set[str]:
    gate = (production_proof or {}).get("production_gate") or {}
    return {str(item) for item in gate.get("missing_live_artifacts") or []}


def _row(
    *,
    key: str,
    label: str,
    stage: str,
    ok: bool,
    owner: str,
    source_artifacts: list[str],
    acceptance_criteria: str,
    current_evidence: str,
    blocker: str,
    next_action: str,
    safe_handling: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "stage": stage,
        "status": _status(ok),
        "owner": owner,
        "source_artifacts": source_artifacts,
        "acceptance_criteria": acceptance_criteria,
        "current_evidence": current_evidence,
        "blocker": "" if ok else blocker,
        "next_action": next_action,
        "safe_handling": safe_handling,
    }


def build_live_proof_acceptance(
    *,
    live_readiness: dict[str, Any] | None = None,
    live_launch_request: dict[str, Any] | None = None,
    live_proof_plan: dict[str, Any] | None = None,
    production_proof: dict[str, Any] | None = None,
    launch_control_room: dict[str, Any] | None = None,
    partner_auth_mapping: dict[str, Any] | None = None,
    partner_access_reconciliation: dict[str, Any] | None = None,
    public_data_reconciliation: dict[str, Any] | None = None,
    customer_signoff_reconciliation: dict[str, Any] | None = None,
    customer_view_catalog: dict[str, Any] | None = None,
    release_label: str = "local",
) -> dict[str, Any]:
    production_ready = _production_verified(production_proof)
    missing = _missing_live_artifacts(production_proof)
    live_tasks = int(((live_launch_request or {}).get("summary") or {}).get("task_count") or 0)
    secret_tasks = int(((live_proof_plan or {}).get("summary") or {}).get("secret_task_count") or 0)
    customer_access_ready = "customer_access_report" not in missing and production_ready
    schema_ready = "schema_verification_report" not in missing and production_ready
    launch_ready = "launch_report" not in missing and production_ready
    rows = [
        _row(
            key="live_input_tasks_closed",
            label="Live input tasks closed",
            stage="live_launch",
            ok=_live_inputs_closed(live_launch_request),
            owner="Platform admin + HomePilot operator + customer success",
            source_artifacts=["LIVE_LAUNCH_REQUEST.md", "LIVE_LAUNCH_CHECKLIST.csv", "live_launch.env.template"],
            acceptance_criteria="All Supabase, RLS fixture, and planned customer-access env var tasks are complete; secret values stay outside the data room.",
            current_evidence=f"{live_tasks} live input tasks open; {secret_tasks} secret-bearing tasks expected.",
            blocker="Live environment values or customer-access inputs are still missing.",
            next_action="Complete the launch checklist through the approved secret channel, then rerun live readiness.",
            safe_handling="Store env var names only in artifacts; never store tokens, passwords, service-role keys, or raw contact data.",
        ),
        _row(
            key="live_readiness_regenerated",
            label="Live readiness regenerated and ready",
            stage="live_launch",
            ok=_live_readiness_ready(live_readiness),
            owner="HomePilot operator + IT owner",
            source_artifacts=["live_readiness.json", "LIVE_PROOF_COMMANDS.sh"],
            acceptance_criteria="The regenerated live readiness report has ready_to_run_live_cutover=true immediately before cutover.",
            current_evidence=f"live_readiness status={(live_readiness or {}).get('status')}; ready_to_run_live_cutover={(live_readiness or {}).get('ready_to_run_live_cutover')}",
            blocker="Live readiness is not ready to run cutover.",
            next_action="Load the secure env and rerun homepilot_live_readiness.py, then stop unless the ready gate passes.",
            safe_handling="The report may list missing env var names, never env values.",
        ),
        _row(
            key="live_proof_plan_self_validated",
            label="Live proof plan self-validated",
            stage="live_launch",
            ok=_plan_validated(live_proof_plan),
            owner="HomePilot operator",
            source_artifacts=["LIVE_PROOF_EXECUTION_PLAN.md", "LIVE_PROOF_EVIDENCE_MAP.csv", "LIVE_PROOF_COMMANDS.sh"],
            acceptance_criteria="plan_validation.status=pass and secret_scan.status=pass before any live command is used.",
            current_evidence=f"plan_validation={(live_proof_plan or {}).get('plan_validation', {}).get('status')}; secret_scan={(live_proof_plan or {}).get('secret_scan', {}).get('status')}",
            blocker="Live proof plan validation is missing or failed.",
            next_action="Regenerate the live proof plan and fix failing validation checks.",
            safe_handling="The command script must require explicit confirmations before live cutover.",
        ),
        _row(
            key="sql_apply_reviewed",
            label="SQL apply reviewed and manually confirmed",
            stage="live_launch",
            ok=production_ready,
            owner="IT owner + database admin",
            source_artifacts=["SQL_APPLY_PLAN.md", "apply.sql", "post_apply_verification.sql"],
            acceptance_criteria="Customer IT has reviewed/applied the SQL bundle and set HOMEPILOT_SQL_APPLY_CONFIRM=reviewed-sql-applied only after manual approval.",
            current_evidence="Manual SQL application is not proven by local buyer-review artifacts.",
            blocker="Reviewed SQL application is not confirmed by live proof evidence.",
            next_action="Review the SQL bundle with customer IT, apply through the approved database process, then run live schema verification.",
            safe_handling="Do not apply SQL from the portable data room without customer IT review and the secure launch session.",
        ),
        _row(
            key="live_schema_verified",
            label="Live schema contract verified",
            stage="production_rollout",
            ok=schema_ready,
            owner="IT owner + HomePilot operator",
            source_artifacts=["schema_verification.json", "PRODUCTION_PROOF.md"],
            acceptance_criteria="Live schema verification passes with contract_status=pass, live_status=pass, and production_verified=true.",
            current_evidence="schema_verification_report is missing from production proof." if "schema_verification_report" in missing else "schema verification accepted in production proof.",
            blocker="Live schema verification is missing or not production_verified=true.",
            next_action="Run live schema verification against the deployed Supabase/Postgres project after SQL apply.",
            safe_handling="Use metadata/proof reports; do not copy database secrets into evidence artifacts.",
        ),
        _row(
            key="live_rls_launch_verified",
            label="Live RLS launch verified",
            stage="production_rollout",
            ok=launch_ready,
            owner="IT owner + HomePilot operator",
            source_artifacts=["launch_report.json", "PRODUCTION_PROOF.md"],
            acceptance_criteria="Live RLS/launch report passes and production_verified=true with tenant/module/partner probe evidence.",
            current_evidence="launch_report is missing from production proof." if "launch_report" in missing else "launch report accepted in production proof.",
            blocker="Live RLS launch proof is missing or not production_verified=true.",
            next_action="Run the live launch/RLS probe chain and archive the launch report.",
            safe_handling="Probe planned fixtures and customer identities only; no cross-tenant raw data in summaries.",
        ),
        _row(
            key="customer_access_verified",
            label="Customer access verified",
            stage="production_rollout",
            ok=customer_access_ready,
            owner="Customer success + IT/security owner",
            source_artifacts=["customer_access_verification.json", "ACCESS_LENS_PROOF_MATRIX.csv", "CUSTOMER_VIEW_MATRIX.csv"],
            acceptance_criteria="Customer access verification passes with production_verified=true for planned tenant, module, and partner-scoped users.",
            current_evidence="customer_access_report is missing from production proof." if "customer_access_report" in missing else "customer access accepted in production proof.",
            blocker="Customer access proof is missing or not production_verified=true.",
            next_action="Run customer-access probes with real planned identities/JWTs and archive the redacted report.",
            safe_handling="Do not expose raw customer JWTs, passwords, or partner cross-scope rows.",
        ),
        _row(
            key="partner_auth_and_access_reconciled",
            label="Partner Auth and access reconciled",
            stage="production_rollout",
            ok=_partner_auth_ready(partner_auth_mapping) and _partner_access_ready(partner_access_reconciliation),
            owner="DAW network manager + customer success + IT/security",
            source_artifacts=["PARTNER_AUTH_MAPPING.md", "PARTNER_ACCESS_RECONCILIATION.md", "PARTNER_ACCESS_RECONCILIATION_MATRIX.csv"],
            acceptance_criteria="All expected partner renovators are mapped to Auth users and reconciled with customer-access proof.",
            current_evidence=f"partner_auth_status={(partner_auth_mapping or {}).get('status')}; partner_access_status={(partner_access_reconciliation or {}).get('status')}",
            blocker="Partner Auth mapping or access reconciliation is incomplete.",
            next_action="Map partner Auth users, rerun partner access reconciliation, then confirm assigned-record-only visibility.",
            safe_handling="Partner users must never see another partner's raw records.",
        ),
        _row(
            key="customer_signoff_ready",
            label="Customer signoff ready for live launch and production",
            stage="production_rollout",
            ok=_customer_signoff_ready(customer_signoff_reconciliation, "live_launch_ready")
            and _customer_signoff_ready(customer_signoff_reconciliation, "production_signoff_ready"),
            owner="DAW executive sponsor + campaign owner + customer success",
            source_artifacts=["CUSTOMER_SIGNOFF_RECONCILIATION.md", "CUSTOMER_SIGNOFF_EVIDENCE_TEMPLATE.csv", "FIRST_WAVE_LAUNCH_GATE.md"],
            acceptance_criteria="Buyer-review acceptance, first-wave go/no-go, live proof archived, partner access, public-data decisions, and production signoff are explicitly approved.",
            current_evidence=f"live_launch_ready={(customer_signoff_reconciliation or {}).get('live_launch_ready')}; production_signoff_ready={(customer_signoff_reconciliation or {}).get('production_signoff_ready')}",
            blocker="Customer signoff evidence is missing or blocked by live proof.",
            next_action="Collect signed/customer-approved decision references after technical proof passes.",
            safe_handling="Customer signoff cannot override failed technical proof.",
        ),
        _row(
            key="public_data_decisions_safe",
            label="Public-data decisions safe for first wave",
            stage="production_rollout",
            ok=_public_data_ready(public_data_reconciliation),
            owner="Legal/privacy owner + data owner",
            source_artifacts=["PUBLIC_DATA_RECONCILIATION.md", "PUBLIC_DATA_APPROVAL_CHECKLIST.csv", "ATTRIBUTION_REQUIREMENTS.csv"],
            acceptance_criteria="Public-data import is either not required for the first wave or every required source has licence, allowed-use, attribution, field allowlist, and live-proof approval.",
            current_evidence=f"public_data_status={(public_data_reconciliation or {}).get('status')}",
            blocker="Public-data approval or live-proof dependency remains unresolved.",
            next_action="Approve dataset-level licence/allowed-use decisions before importing public-data enrichments.",
            safe_handling="Public does not automatically mean reusable; blocked owner/contact scraping lanes stay blocked.",
        ),
        _row(
            key="customer_view_catalog_runtime_gate",
            label="Customer view catalog runtime gate",
            stage="production_rollout",
            ok=bool((customer_view_catalog or {}).get("summary", {}).get("live_access_ready") is True),
            owner="IT/security owner + customer success",
            source_artifacts=["CUSTOMER_VIEW_CATALOG.md", "CUSTOMER_VIEW_MATRIX.csv"],
            acceptance_criteria="Customer-facing views are catalogued, but runtime access remains disabled until live RLS/customer-access proof passes.",
            current_evidence=f"customer_view_status={(customer_view_catalog or {}).get('status')}; live_access_ready={(customer_view_catalog or {}).get('summary', {}).get('live_access_ready')}",
            blocker="Customer runtime access is not live-access-ready.",
            next_action="Enable runtime access only after live customer-access verification passes.",
            safe_handling="Catalog is not authorization; Supabase RLS and JWTs are the production access boundary.",
        ),
        _row(
            key="production_proof_gate_verified",
            label="Production proof gate verified",
            stage="production_rollout",
            ok=production_ready,
            owner="HomePilot operator + IT owner + customer success",
            source_artifacts=["production_proof.json", "PRODUCTION_PROOF.md", "market_ready_audit.json"],
            acceptance_criteria="Production proof has production_gate.verified=true and generated market/release artifacts preserve buyer/live/production decisions.",
            current_evidence=f"production_gate_verified={production_ready}; missing_live_artifacts={', '.join(sorted(missing)) or 'none'}",
            blocker="Production proof is not verified.",
            next_action="Regenerate release and market packs from live evidence only after every live proof artifact passes.",
            safe_handling="Do not hand-edit production proof; regenerate it from archived evidence.",
        ),
    ]
    blocked = [row for row in rows if row["status"] != "pass"]
    live_launch_blockers = [row for row in blocked if row["stage"] == "live_launch"]
    production_blockers = [row for row in blocked if row["stage"] == "production_rollout"]
    status = (
        "production_acceptance_ready"
        if production_ready and not blocked
        else "acceptance_criteria_ready_live_evidence_blocked"
        if _plan_validated(live_proof_plan)
        else "action_required"
    )
    return {
        "report_type": "homepilot_live_proof_acceptance_matrix",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": status,
        "summary": {
            "criterion_count": len(rows),
            "passed_count": len(rows) - len(blocked),
            "blocked_count": len(blocked),
            "live_launch_blockers": len(live_launch_blockers),
            "production_blockers": len(production_blockers),
            "live_launch_task_count": live_tasks,
            "production_verified": production_ready,
            "launch_control_status": (launch_control_room or {}).get("status"),
            "customer_access_live_ready": bool((customer_view_catalog or {}).get("summary", {}).get("live_access_ready") is True),
        },
        "criteria": rows,
        "guardrails": {
            "non_mutating": True,
            "no_supabase_writes": True,
            "no_outreach_authorized": True,
            "no_partner_portal_access_authorized": True,
            "no_secret_values_written": False,
            "no_raw_contact_values_written": True,
            "customer_signoff_cannot_override_technical_proof": True,
            "production_requires_live_schema_rls_customer_access": True,
        },
    }


def _secret_scan(report: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(report, ensure_ascii=False)
    findings = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(body)]
    return {
        "status": "pass" if not findings else "fail",
        "issue_count": len(findings),
        "patterns": findings,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# HomePilot Live Proof Acceptance Matrix",
        "",
        f"Release: {report['release_label']}",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        "",
        "This matrix defines what DAW, customer IT, customer success, and HomePilot must accept before buyer-ready evidence can become live-launch or production proof. It is a review artifact only.",
        "",
        "## Summary",
        "",
        f"- Criteria: {summary['criterion_count']}",
        f"- Passed: {summary['passed_count']}",
        f"- Blocked: {summary['blocked_count']}",
        f"- Live-launch blockers: {summary['live_launch_blockers']}",
        f"- Production blockers: {summary['production_blockers']}",
        f"- Live launch task count: {summary['live_launch_task_count']}",
        f"- Production verified: {summary['production_verified']}",
        "",
        "## Acceptance Criteria",
        "",
        "| Criterion | Stage | Status | Owner | Acceptance criteria | Blocker | Next action |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["criteria"]:
        blocker = row["blocker"] or "none"
        lines.append(
            f"| {row['label']} | {row['stage']} | {row['status']} | {row['owner']} | "
            f"{row['acceptance_criteria']} | {blocker} | {row['next_action']} |"
        )
    lines += [
        "",
        "## Guardrails",
        "",
        "- This matrix does not execute live commands or write to Supabase.",
        "- Secret values stay in the approved secret channel, never in the evidence room.",
        "- Customer signoff cannot override failed schema, RLS, or customer-access proof.",
        "- Partner portal access stays disabled until assigned-record-only visibility is proven with live identities.",
        "- Scores and public context remain opportunity signals, not homeowner intent.",
        "",
    ]
    return "\n".join(lines)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                **{field: row.get(field, "") for field in CSV_FIELDS},
                "source_artifacts": "; ".join(row.get("source_artifacts") or []),
            })


def build_live_proof_acceptance_pack(
    out_dir: Path,
    *,
    live_readiness: dict[str, Any] | None = None,
    live_launch_request: dict[str, Any] | None = None,
    live_proof_plan: dict[str, Any] | None = None,
    production_proof: dict[str, Any] | None = None,
    launch_control_room: dict[str, Any] | None = None,
    partner_auth_mapping: dict[str, Any] | None = None,
    partner_access_reconciliation: dict[str, Any] | None = None,
    public_data_reconciliation: dict[str, Any] | None = None,
    customer_signoff_reconciliation: dict[str, Any] | None = None,
    customer_view_catalog: dict[str, Any] | None = None,
    release_label: str = "local",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report = build_live_proof_acceptance(
        live_readiness=live_readiness,
        live_launch_request=live_launch_request,
        live_proof_plan=live_proof_plan,
        production_proof=production_proof,
        launch_control_room=launch_control_room,
        partner_auth_mapping=partner_auth_mapping,
        partner_access_reconciliation=partner_access_reconciliation,
        public_data_reconciliation=public_data_reconciliation,
        customer_signoff_reconciliation=customer_signoff_reconciliation,
        customer_view_catalog=customer_view_catalog,
        release_label=release_label,
    )
    report["paths"] = {
        "live_proof_acceptance": str(out_dir / "live_proof_acceptance_matrix.json"),
        "markdown": str(out_dir / "LIVE_PROOF_ACCEPTANCE_MATRIX.md"),
        "csv": str(out_dir / "LIVE_PROOF_ACCEPTANCE_MATRIX.csv"),
    }
    report["secret_scan"] = _secret_scan(report)
    report["guardrails"]["no_secret_values_written"] = report["secret_scan"]["status"] == "pass"
    write_json(out_dir / "live_proof_acceptance_matrix.json", report)
    write_text(out_dir / "LIVE_PROOF_ACCEPTANCE_MATRIX.md", render_markdown(report))
    _write_csv(out_dir / "LIVE_PROOF_ACCEPTANCE_MATRIX.csv", report["criteria"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the HomePilot live proof acceptance matrix")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--live-readiness", type=Path)
    parser.add_argument("--live-launch-request", type=Path)
    parser.add_argument("--live-proof-plan", type=Path)
    parser.add_argument("--production-proof", type=Path)
    parser.add_argument("--launch-control-room", type=Path)
    parser.add_argument("--partner-auth-mapping", type=Path)
    parser.add_argument("--partner-access-reconciliation", type=Path)
    parser.add_argument("--public-data-reconciliation", type=Path)
    parser.add_argument("--customer-signoff-reconciliation", type=Path)
    parser.add_argument("--customer-view-catalog", type=Path)
    parser.add_argument("--release-label", default="local")
    args = parser.parse_args()
    report = build_live_proof_acceptance_pack(
        args.out_dir,
        live_readiness=load_json(args.live_readiness),
        live_launch_request=load_json(args.live_launch_request),
        live_proof_plan=load_json(args.live_proof_plan),
        production_proof=load_json(args.production_proof),
        launch_control_room=load_json(args.launch_control_room),
        partner_auth_mapping=load_json(args.partner_auth_mapping),
        partner_access_reconciliation=load_json(args.partner_access_reconciliation),
        public_data_reconciliation=load_json(args.public_data_reconciliation),
        customer_signoff_reconciliation=load_json(args.customer_signoff_reconciliation),
        customer_view_catalog=load_json(args.customer_view_catalog),
        release_label=args.release_label,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": report["status"],
        "blocked": report["summary"]["blocked_count"],
        "markdown": report["paths"]["markdown"],
        "csv": report["paths"]["csv"],
    }, indent=2, ensure_ascii=False))
    if report["secret_scan"]["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
