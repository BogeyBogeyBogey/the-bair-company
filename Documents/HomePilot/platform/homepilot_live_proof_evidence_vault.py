#!/usr/bin/env python3
"""
Build the HomePilot live proof evidence vault.

The vault is a non-mutating archive index for enterprise review. It records
which proof artifacts exist, what they must prove, who owns them, and which live
gates remain blocked. It never stores secret values, raw contacts, or live data.
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
    "owner",
    "required_status",
    "current_status",
    "archived",
    "current_path",
    "freshness_rule",
    "pass_condition",
    "blocker",
    "archive_rule",
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


def _path_exists(path: Any) -> bool:
    return bool(path and Path(str(path)).exists())


def _production_verified(production_proof: dict[str, Any] | None) -> bool:
    gate = (production_proof or {}).get("production_gate") or {}
    return bool(gate.get("verified") or (production_proof or {}).get("production_verified") is True)


def _live_inputs_closed(live_launch_request: dict[str, Any] | None) -> bool:
    summary = (live_launch_request or {}).get("summary") or {}
    return bool(live_launch_request) and int(summary.get("task_count") or 0) == 0


def _plan_validated(live_proof_plan: dict[str, Any] | None) -> bool:
    return bool(
        live_proof_plan
        and live_proof_plan.get("secret_scan", {}).get("status") == "pass"
        and live_proof_plan.get("plan_validation", {}).get("status") == "pass"
    )


def _acceptance_ready(live_proof_acceptance: dict[str, Any] | None) -> bool:
    summary = (live_proof_acceptance or {}).get("summary") or {}
    return bool(
        live_proof_acceptance
        and live_proof_acceptance.get("secret_scan", {}).get("status") == "pass"
        and int(summary.get("criterion_count") or 0) > 0
    )


def _secret_scan(paths: list[Path]) -> dict[str, Any]:
    findings: list[str] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        body = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in SECRET_PATTERNS:
            if pattern.search(body):
                findings.append(f"{path.name}: {pattern.pattern}")
    return {
        "status": "pass" if not findings else "fail",
        "issue_count": len(findings),
        "findings": findings,
    }


def _row(
    *,
    key: str,
    label: str,
    stage: str,
    owner: str,
    required_status: str,
    current_status: str,
    current_path: str | None,
    freshness_rule: str,
    pass_condition: str,
    blocker: str,
    archive_rule: str,
    safe_handling: str,
) -> dict[str, Any]:
    archived = _path_exists(current_path)
    return {
        "key": key,
        "label": label,
        "stage": stage,
        "owner": owner,
        "required_status": required_status,
        "current_status": current_status,
        "archived": archived,
        "current_path": current_path or "",
        "freshness_rule": freshness_rule,
        "pass_condition": pass_condition,
        "blocker": "" if current_status == required_status else blocker,
        "archive_rule": archive_rule,
        "safe_handling": safe_handling,
    }


def _status_pass(value: bool) -> str:
    return "pass" if value else "blocked"


def _artifact_status(report: dict[str, Any] | None, ok: bool | None = None) -> str:
    if ok is not None:
        return _status_pass(ok)
    if not report:
        return "missing"
    status = str(report.get("status") or "review_ready")
    return "pass" if status in {"pass", "ready", "review_ready", "buyer_review_ready"} else status


def _build_rows(
    *,
    artifact_paths: dict[str, str | None],
    live_readiness: dict[str, Any] | None,
    live_launch_request: dict[str, Any] | None,
    live_proof_plan: dict[str, Any] | None,
    live_proof_acceptance: dict[str, Any] | None,
    production_proof: dict[str, Any] | None,
    launch_control_room: dict[str, Any] | None,
    partner_auth_mapping: dict[str, Any] | None,
    partner_access_reconciliation: dict[str, Any] | None,
    public_data_reconciliation: dict[str, Any] | None,
    customer_signoff_reconciliation: dict[str, Any] | None,
    first_wave_launch_gate: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    production_ready = _production_verified(production_proof)
    return [
        _row(
            key="schema_verification_report",
            label="Live schema metadata verification",
            stage="production_rollout",
            owner="IT owner + HomePilot operator",
            required_status="pass",
            current_status=_status_pass(production_ready),
            current_path=artifact_paths.get("schema_verification_report"),
            freshness_rule="Must be generated after SQL apply in the target Supabase project.",
            pass_condition="schema_verification.status=pass, live_status=pass, and production_verified=true.",
            blocker="Live schema verification is not archived with production_verified=true.",
            archive_rule="Archive JSON and Markdown/hash reference in the release room before portal access.",
            safe_handling="May include metadata, never service-role values or connection strings.",
        ),
        _row(
            key="rls_launch_report",
            label="Live RLS fixture launch and probe report",
            stage="production_rollout",
            owner="IT owner + security owner",
            required_status="pass",
            current_status=_status_pass(production_ready),
            current_path=artifact_paths.get("launch_report"),
            freshness_rule="Must be generated in the same live cutover run as customer access proof.",
            pass_condition="launch_report.status=pass and production_verified=true for tenant/module/partner RLS probes.",
            blocker="Live RLS launch/probe report is not production verified.",
            archive_rule="Archive after fixture cleanup plan is prepared and before first-wave authorization.",
            safe_handling="Probe identities are described by role/scope; raw credentials stay outside artifacts.",
        ),
        _row(
            key="customer_access_report",
            label="Live customer access verification",
            stage="production_rollout",
            owner="Customer success + IT owner",
            required_status="pass",
            current_status=_status_pass(production_ready),
            current_path=artifact_paths.get("customer_access_report"),
            freshness_rule="Must be generated with planned customer or test invitees immediately before go-live.",
            pass_condition="customer_access_verification.status=pass and production_verified=true.",
            blocker="Customer access proof is not production verified.",
            archive_rule="Archive report and access-lens proof before enabling customer portal access.",
            safe_handling="Use tenant/module/partner scopes only; do not store passwords or bearer tokens.",
        ),
        _row(
            key="production_proof_gate",
            label="Production proof manifest",
            stage="production_rollout",
            owner="HomePilot operator + IT owner",
            required_status="pass",
            current_status=_status_pass(production_ready),
            current_path=artifact_paths.get("production_proof"),
            freshness_rule="Must be rebuilt after live readiness, schema, RLS, and customer-access proof pass.",
            pass_condition="production_gate.verified=true and decisions.production=go.",
            blocker="Production proof exists only as blocked/no-go evidence.",
            archive_rule="Archive JSON and Markdown with artifact hashes in the release room.",
            safe_handling="Stores hashes and statuses only; no secret values or raw contact data.",
        ),
        _row(
            key="live_readiness_report",
            label="Redacted live readiness report",
            stage="live_launch",
            owner="HomePilot operator",
            required_status="pass",
            current_status=_status_pass(bool((live_readiness or {}).get("ready_to_run_live_cutover") is True)),
            current_path=artifact_paths.get("live_readiness_report"),
            freshness_rule="Regenerate immediately after secure env values are loaded and before live cutover.",
            pass_condition="ready_to_run_live_cutover=true.",
            blocker="Live readiness is missing or still reports open inputs.",
            archive_rule="Archive the redacted readiness JSON/Markdown; keep env values in secret channels.",
            safe_handling="Missing env var names are allowed; env values are forbidden.",
        ),
        _row(
            key="live_launch_request",
            label="Live launch request and checklist",
            stage="live_launch",
            owner="Platform admin + customer success",
            required_status="pass",
            current_status=_status_pass(_live_inputs_closed(live_launch_request)),
            current_path=artifact_paths.get("live_launch_request"),
            freshness_rule="Keep current until all launch checklist tasks are closed.",
            pass_condition="summary.task_count=0 and no secret values written.",
            blocker="Live input tasks remain open.",
            archive_rule="Archive checklist as owner assignment, not as credential storage.",
            safe_handling="Env var names and placeholders only.",
        ),
        _row(
            key="live_proof_execution_plan",
            label="Live proof execution plan",
            stage="live_launch",
            owner="HomePilot operator + IT owner",
            required_status="pass",
            current_status=_status_pass(_plan_validated(live_proof_plan)),
            current_path=artifact_paths.get("live_proof_plan"),
            freshness_rule="Regenerate when release paths, live readiness, or proof inputs change.",
            pass_condition="plan_validation.status=pass and secret_scan.status=pass.",
            blocker="Live proof plan has not self-validated.",
            archive_rule="Archive plan, evidence map, and guarded command script together.",
            safe_handling="Commands may reference env var names; they must not inline secrets.",
        ),
        _row(
            key="live_proof_acceptance_matrix",
            label="Customer/IT live proof acceptance matrix",
            stage="live_launch",
            owner="Executive sponsor + IT owner + customer success",
            required_status="pass",
            current_status=_status_pass(_acceptance_ready(live_proof_acceptance)),
            current_path=artifact_paths.get("live_proof_acceptance"),
            freshness_rule="Regenerate before customer/IT proof review meetings.",
            pass_condition="criterion_count>0 and secret_scan.status=pass.",
            blocker="Acceptance matrix is missing or failed secret scan.",
            archive_rule="Archive Markdown and CSV matrix in the buyer data room.",
            safe_handling="Acceptance can define required proof, but cannot override failing technical proof.",
        ),
        _row(
            key="live_launch_control_room",
            label="Live launch control room",
            stage="live_launch",
            owner="HomePilot operator + customer success",
            required_status="pass",
            current_status=_status_pass(bool(launch_control_room and launch_control_room.get("secret_scan", {}).get("status") == "pass")),
            current_path=artifact_paths.get("live_launch_control_room"),
            freshness_rule="Regenerate after first-wave, partner, public-data, signoff, or proof state changes.",
            pass_condition="secret_scan.status=pass and stage gates remain explicit.",
            blocker="Control room is missing or failed secret scan.",
            archive_rule="Archive with action board for launch meetings.",
            safe_handling="Control room stores blockers and env var names only.",
        ),
        _row(
            key="partner_auth_mapping",
            label="Partner Auth mapping",
            stage="live_launch",
            owner="DAW network manager + IT owner",
            required_status="pass",
            current_status=_artifact_status(partner_auth_mapping),
            current_path=artifact_paths.get("partner_auth_mapping"),
            freshness_rule="Refresh when partner roster or planned Auth users change.",
            pass_condition="All expected partner renovators have reviewed mapped Auth identities.",
            blocker="Partner Auth mapping is not complete.",
            archive_rule="Archive template, reviewed rows, issues, and membership review SQL.",
            safe_handling="Use user IDs and partner scopes; no passwords or invite secrets.",
        ),
        _row(
            key="partner_access_reconciliation",
            label="Partner access reconciliation",
            stage="production_rollout",
            owner="IT/security + DAW network manager",
            required_status="pass",
            current_status=_artifact_status(partner_access_reconciliation, bool((partner_access_reconciliation or {}).get("production_ready") is True)),
            current_path=artifact_paths.get("partner_access_reconciliation"),
            freshness_rule="Run after partner Auth mapping and customer access proof are ready.",
            pass_condition="production_ready=true and blockers=0.",
            blocker="Partner access is not reconciled for production.",
            archive_rule="Archive reconciliation report, matrix, and issue list before partner portal access.",
            safe_handling="Partner rows stay assigned-record only.",
        ),
        _row(
            key="public_data_reconciliation",
            label="Public-data production reconciliation",
            stage="production_rollout",
            owner="Legal/privacy owner + data owner",
            required_status="pass",
            current_status=_artifact_status(public_data_reconciliation, bool((public_data_reconciliation or {}).get("production_import_ready") is True)),
            current_path=artifact_paths.get("public_data_reconciliation"),
            freshness_rule="Run before production public-data import or source-backed customer claims.",
            pass_condition="production_import_ready=true for every required source.",
            blocker="Dataset approvals or live proof are incomplete.",
            archive_rule="Archive source matrix, reconciliation, and blocked-data register.",
            safe_handling="Source provenance is allowed; owner/contact scraping remains blocked by default.",
        ),
        _row(
            key="customer_signoff_reconciliation",
            label="Customer signoff reconciliation",
            stage="live_launch",
            owner="Executive sponsor + customer success",
            required_status="pass",
            current_status=_artifact_status(customer_signoff_reconciliation, bool((customer_signoff_reconciliation or {}).get("live_launch_ready") is True)),
            current_path=artifact_paths.get("customer_signoff_reconciliation"),
            freshness_rule="Refresh after every signed decision or customer go/no-go reference.",
            pass_condition="live_launch_ready=true and production_signoff_ready=true for production rollout.",
            blocker="Customer go/no-go or signoff evidence is missing.",
            archive_rule="Archive signoff matrix, issue list, intake, and evidence template.",
            safe_handling="Customer signoff references are proof pointers, not raw private data.",
        ),
        _row(
            key="first_wave_launch_gate",
            label="First-wave launch gate",
            stage="production_rollout",
            owner="DAW executive sponsor + campaign owner",
            required_status="pass",
            current_status=_artifact_status(first_wave_launch_gate, bool((first_wave_launch_gate or {}).get("launch_authorized") is True)),
            current_path=artifact_paths.get("first_wave_launch_gate"),
            freshness_rule="Regenerate immediately before first outreach or partner portal access.",
            pass_condition="launch_authorized=true after input, source, signoff, live proof, and customer go/no-go gates pass.",
            blocker="First wave remains blocked.",
            archive_rule="Archive launch gate JSON, Markdown, and checklist before any outreach.",
            safe_handling="Blocked gate is coordination evidence, not launch permission.",
        ),
    ]


def _summary(rows: list[dict[str, Any]], production_verified: bool) -> dict[str, Any]:
    archived = [row for row in rows if row["archived"]]
    passed = [row for row in rows if row["current_status"] == row["required_status"]]
    blocked = [row for row in rows if row["current_status"] != row["required_status"]]
    return {
        "required_count": len(rows),
        "archived_count": len(archived),
        "passed_count": len(passed),
        "blocked_count": len(blocked),
        "live_launch_blocked_count": len([row for row in blocked if row["stage"] == "live_launch"]),
        "production_blocked_count": len([row for row in blocked if row["stage"] == "production_rollout"]),
        "production_verified": production_verified,
        "production_verified_label": f"production_verified={str(production_verified).lower()}",
    }


def render_markdown(vault: dict[str, Any]) -> str:
    summary = vault["summary"]
    lines = [
        "# HomePilot Live Proof Evidence Vault",
        "",
        f"Release: {vault['release_label']}",
        f"Created: {vault['created_at']}",
        f"Status: {vault['status']}",
        "",
        "This vault is an archive index for live proof. It does not execute commands, write to Supabase, store secrets, authorize outreach, or turn buyer-review evidence into production proof.",
        "",
        "## Summary",
        "",
        f"- Required evidence rows: {summary['required_count']}",
        f"- Archived locally: {summary['archived_count']}",
        f"- Passed: {summary['passed_count']}",
        f"- Blocked: {summary['blocked_count']}",
        f"- Live-launch blockers: {summary['live_launch_blocked_count']}",
        f"- Production blockers: {summary['production_blocked_count']}",
        f"- {summary['production_verified_label']}",
        f"- Secret scan: {vault['secret_scan']['status']}",
        "",
        "## Evidence Archive",
        "",
        "| Evidence | Stage | Current | Required | Archived | Blocker |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in vault["evidence_rows"]:
        archived = "yes" if row["archived"] else "no"
        blocker = row["blocker"] or "none"
        lines.append(
            f"| {row['label']} | {row['stage']} | {row['current_status']} | {row['required_status']} | {archived} | {blocker} |"
        )
    lines += [
        "",
        "## Guardrails",
        "",
    ]
    for key, value in vault["guardrails"].items():
        lines.append(f"- {key}: {str(value).lower()}")
    lines.append("")
    return "\n".join(lines)


def write_archive_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})


def build_live_proof_evidence_vault(
    *,
    artifact_paths: dict[str, str | None] | None = None,
    live_readiness: dict[str, Any] | None = None,
    live_launch_request: dict[str, Any] | None = None,
    live_proof_plan: dict[str, Any] | None = None,
    live_proof_acceptance: dict[str, Any] | None = None,
    production_proof: dict[str, Any] | None = None,
    launch_control_room: dict[str, Any] | None = None,
    partner_auth_mapping: dict[str, Any] | None = None,
    partner_access_reconciliation: dict[str, Any] | None = None,
    public_data_reconciliation: dict[str, Any] | None = None,
    customer_signoff_reconciliation: dict[str, Any] | None = None,
    first_wave_launch_gate: dict[str, Any] | None = None,
    release_label: str = "local",
) -> dict[str, Any]:
    paths = artifact_paths or {}
    production_ready = _production_verified(production_proof)
    rows = _build_rows(
        artifact_paths=paths,
        live_readiness=live_readiness,
        live_launch_request=live_launch_request,
        live_proof_plan=live_proof_plan,
        live_proof_acceptance=live_proof_acceptance,
        production_proof=production_proof,
        launch_control_room=launch_control_room,
        partner_auth_mapping=partner_auth_mapping,
        partner_access_reconciliation=partner_access_reconciliation,
        public_data_reconciliation=public_data_reconciliation,
        customer_signoff_reconciliation=customer_signoff_reconciliation,
        first_wave_launch_gate=first_wave_launch_gate,
    )
    summary = _summary(rows, production_ready)
    return {
        "vault_type": "homepilot_live_proof_evidence_vault",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": "production_verified" if production_ready else "live_proof_blocked",
        "summary": summary,
        "evidence_rows": rows,
        "guardrails": {
            "derived_review_surface": True,
            "non_mutating": True,
            "no_supabase_writes": True,
            "no_live_writes": True,
            "no_outreach_authorized": True,
            "no_secret_values": True,
            "no_raw_contact_data": True,
            "no_cross_tenant_raw_data": True,
            "tenant_module_partner_scope_required": True,
            "production_requires_live_schema_rls_customer_access_proof": True,
        },
    }


def build_live_proof_evidence_vault_pack(
    out_dir: Path,
    *,
    artifact_paths: dict[str, str | None] | None = None,
    live_readiness: dict[str, Any] | None = None,
    live_launch_request: dict[str, Any] | None = None,
    live_proof_plan: dict[str, Any] | None = None,
    live_proof_acceptance: dict[str, Any] | None = None,
    production_proof: dict[str, Any] | None = None,
    launch_control_room: dict[str, Any] | None = None,
    partner_auth_mapping: dict[str, Any] | None = None,
    partner_access_reconciliation: dict[str, Any] | None = None,
    public_data_reconciliation: dict[str, Any] | None = None,
    customer_signoff_reconciliation: dict[str, Any] | None = None,
    first_wave_launch_gate: dict[str, Any] | None = None,
    release_label: str = "local",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "live_proof_evidence_vault": str(out_dir / "live_proof_evidence_vault.json"),
        "live_proof_evidence_vault_markdown": str(out_dir / "LIVE_PROOF_EVIDENCE_VAULT.md"),
        "live_proof_archive_index": str(out_dir / "LIVE_PROOF_ARCHIVE_INDEX.csv"),
    }
    vault = build_live_proof_evidence_vault(
        artifact_paths=artifact_paths,
        live_readiness=live_readiness,
        live_launch_request=live_launch_request,
        live_proof_plan=live_proof_plan,
        live_proof_acceptance=live_proof_acceptance,
        production_proof=production_proof,
        launch_control_room=launch_control_room,
        partner_auth_mapping=partner_auth_mapping,
        partner_access_reconciliation=partner_access_reconciliation,
        public_data_reconciliation=public_data_reconciliation,
        customer_signoff_reconciliation=customer_signoff_reconciliation,
        first_wave_launch_gate=first_wave_launch_gate,
        release_label=release_label,
    )
    vault["paths"] = paths
    vault["secret_scan"] = {"status": "not_run", "issue_count": 0, "findings": []}
    write_json(Path(paths["live_proof_evidence_vault"]), vault)
    write_text(Path(paths["live_proof_evidence_vault_markdown"]), render_markdown(vault))
    write_archive_csv(Path(paths["live_proof_archive_index"]), vault["evidence_rows"])
    scan = _secret_scan(Path(path) for path in paths.values())
    vault["secret_scan"] = scan
    if scan["status"] != "pass":
        vault["status"] = "failed_secret_scan"
    write_json(Path(paths["live_proof_evidence_vault"]), vault)
    write_text(Path(paths["live_proof_evidence_vault_markdown"]), render_markdown(vault))
    return vault


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HomePilot live proof evidence vault")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--live-readiness", type=Path)
    parser.add_argument("--live-launch-request", type=Path)
    parser.add_argument("--live-proof-plan", type=Path)
    parser.add_argument("--live-proof-acceptance", type=Path)
    parser.add_argument("--production-proof", type=Path)
    parser.add_argument("--release-label", default="local")
    args = parser.parse_args()
    vault = build_live_proof_evidence_vault_pack(
        args.out_dir,
        live_readiness=load_json(args.live_readiness),
        live_launch_request=load_json(args.live_launch_request),
        live_proof_plan=load_json(args.live_proof_plan),
        live_proof_acceptance=load_json(args.live_proof_acceptance),
        production_proof=load_json(args.production_proof),
        release_label=args.release_label,
    )
    print(json.dumps({
        "status": vault["status"],
        "output": str(args.out_dir),
        "required": vault["summary"]["required_count"],
        "blocked": vault["summary"]["blocked_count"],
        "markdown": vault["paths"]["live_proof_evidence_vault_markdown"],
        "archive_index": vault["paths"]["live_proof_archive_index"],
    }, indent=2, ensure_ascii=False))
    if vault["secret_scan"]["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
