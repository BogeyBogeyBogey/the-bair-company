#!/usr/bin/env python3
"""
Build a HomePilot market-ready gap audit.

This is a derived review surface. It does not create new production proof and it
does not write to Supabase. It maps the full market-ready platform objective to
current evidence, blockers, owners, and guardrails so buyer-review readiness is
not confused with live production readiness.
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


def _score_status(market_readiness: dict[str, Any], key: str) -> str:
    for row in market_readiness.get("scorecard") or []:
        if row.get("key") == key:
            return str(row.get("status") or "unknown")
    return "unknown"


def _entry_exists(manifest: dict[str, Any] | None, label: str) -> bool:
    if not manifest:
        return False
    for entry in manifest.get("entries") or []:
        if entry.get("label") == label:
            return bool(entry.get("exists"))
    return False


def _portable_core_ok(manifest: dict[str, Any] | None) -> bool:
    required_labels = (
        "Market readiness scorecard",
        "Boardroom data room index",
        "Intelligence Lab report",
        "Intelligence Lab JSON evidence",
        "Live launch control room",
        "Live launch action board",
    )
    return bool(manifest) and all(_entry_exists(manifest, label) for label in required_labels)


def _path_exists(path: Any) -> bool:
    return bool(path and Path(str(path)).exists())


def _requirement(
    key: str,
    label: str,
    stage: str,
    status: str,
    owner: str,
    evidence: list[str],
    blocker: str,
    next_action: str,
    *,
    production_required: bool = False,
    customer_visible: bool = True,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "stage": stage,
        "status": status,
        "owner": owner,
        "evidence": evidence,
        "blocker": blocker,
        "next_action": next_action,
        "production_required": production_required,
        "customer_visible": customer_visible,
    }


def _status_from_bool(ok: bool, blocked_status: str = "blocked") -> str:
    return "pass" if ok else blocked_status


def _live_proof_verified(production_proof: dict[str, Any] | None) -> bool:
    if not production_proof:
        return False
    gate = production_proof.get("production_gate")
    if isinstance(gate, dict):
        return bool(gate.get("verified"))
    return production_proof.get("decisions", {}).get("production") == "go"


def _build_requirements(
    market_readiness: dict[str, Any],
    launch_control_room: dict[str, Any] | None,
    live_proof_plan: dict[str, Any] | None,
    live_proof_acceptance: dict[str, Any] | None,
    live_credential_handoff: dict[str, Any] | None,
    live_proof_evidence_vault: dict[str, Any] | None,
    outcome_measurement_contract: dict[str, Any] | None,
    outcome_import_validation: dict[str, Any] | None,
    module_readiness_matrix: dict[str, Any] | None,
    production_proof: dict[str, Any] | None,
    portable_manifest: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    decisions = market_readiness.get("decisions") or {}
    paths = market_readiness.get("paths") or {}
    summary = market_readiness.get("summary") or {}
    control_summary = launch_control_room.get("summary") if launch_control_room else {}
    live_tasks = int(control_summary.get("live_launch_task_count") or summary.get("live_launch_task_count") or 0)
    first_wave_authorized = bool(control_summary.get("first_wave_launch_authorized"))
    production_verified = _live_proof_verified(production_proof)
    portable_ok = _portable_core_ok(portable_manifest)
    control_secret_ok = bool(launch_control_room and launch_control_room.get("secret_scan", {}).get("status") == "pass")
    plan_validation_ok = bool(
        live_proof_plan
        and live_proof_plan.get("secret_scan", {}).get("status") == "pass"
        and live_proof_plan.get("plan_validation", {}).get("status") == "pass"
    )
    acceptance_ok = bool(
        live_proof_acceptance
        and live_proof_acceptance.get("secret_scan", {}).get("status") == "pass"
        and int(live_proof_acceptance.get("summary", {}).get("criterion_count") or 0) > 0
    )
    credential_handoff_ok = bool(
        live_credential_handoff
        and live_credential_handoff.get("secret_scan", {}).get("status") == "pass"
        and live_credential_handoff.get("guardrails", {}).get("env_var_names_only") is True
        and _path_exists(paths.get("live_credential_handoff_markdown"))
        and _path_exists(paths.get("live_credential_handoff_checklist"))
        and _path_exists(paths.get("live_secret_channel_contract"))
    )
    vault_ok = bool(
        live_proof_evidence_vault
        and live_proof_evidence_vault.get("secret_scan", {}).get("status") == "pass"
        and int(live_proof_evidence_vault.get("summary", {}).get("required_count") or 0) > 0
        and _path_exists(paths.get("live_proof_evidence_vault_markdown"))
        and _path_exists(paths.get("live_proof_archive_index"))
    )
    outcome_contract_ok = bool(
        outcome_measurement_contract
        and outcome_measurement_contract.get("secret_scan", {}).get("status") == "pass"
        and int(outcome_measurement_contract.get("summary", {}).get("event_field_count") or 0) > 0
        and int(outcome_measurement_contract.get("summary", {}).get("metric_count") or 0) > 0
        and _path_exists(paths.get("outcome_measurement_contract_markdown"))
        and _path_exists(paths.get("outcome_event_schema"))
        and _path_exists(paths.get("outcome_sync_template"))
        and _path_exists(paths.get("outcome_reconciliation_checklist"))
    )
    outcome_import_ok = bool(
        outcome_import_validation
        and outcome_import_validation.get("secret_scan", {}).get("status") == "pass"
        and int(outcome_import_validation.get("summary", {}).get("row_count") or 0) > 0
        and int(outcome_import_validation.get("summary", {}).get("blocker_count") or 0) == 0
        and _path_exists(paths.get("outcome_import_validation_markdown"))
        and _path_exists(paths.get("outcome_import_issues"))
        and _path_exists(paths.get("outcome_import_review_rows"))
    )
    data_platform_blueprint = market_readiness.get("data_platform_blueprint") or {}
    data_platform_ok = bool(
        data_platform_blueprint
        and data_platform_blueprint.get("secret_scan", {}).get("status") == "pass"
        and _path_exists(paths.get("data_platform_blueprint_markdown"))
        and _path_exists(paths.get("data_platform_scope_matrix"))
    )
    module_readiness_ok = bool(
        module_readiness_matrix
        and module_readiness_matrix.get("secret_scan", {}).get("status") == "pass"
        and int(module_readiness_matrix.get("summary", {}).get("module_count") or 0) >= 7
        and int(module_readiness_matrix.get("summary", {}).get("buyer_ready_count") or 0) >= 7
        and _path_exists(paths.get("module_readiness_matrix_markdown"))
        and _path_exists(paths.get("module_readiness_matrix_csv"))
        and _path_exists(paths.get("module_metric_coverage"))
    )
    open_intelligence_production_ok = bool(
        _entry_exists(portable_manifest, "Open Intelligence production gate")
        and _entry_exists(portable_manifest, "Open Intelligence production gates CSV")
        and _entry_exists(portable_manifest, "Open Intelligence production runbook")
    )

    requirements = [
        _requirement(
            "buyer_data_room",
            "Customer-shareable buyer data room",
            "buyer_review",
            _status_from_bool(decisions.get("buyer_review") == "go" and portable_ok),
            "Sales lead + customer success",
            ["homepilot_boardroom_data_room.zip", "portable_data_room/index.html", "BOARDROOM_DATA_ROOM_INDEX.md"],
            "" if portable_ok else "Portable data room is missing or partial.",
            "Share the portable data room first; keep relative links, checksums, and local-path redaction intact.",
        ),
        _requirement(
            "demo_value_story",
            "Boardroom value story and demo package",
            "buyer_review",
            _status_from_bool(_score_status(market_readiness, "demo_value") == "pass"),
            "Executive sponsor + sales lead",
            ["MARKET_READINESS_SCORECARD.md", "BOARDROOM_REPORT.md", "dashboard/index.html"],
            "" if _score_status(market_readiness, "demo_value") == "pass" else "Demo value scorecard area is not pass.",
            "Use the boardroom report and DAW walkthrough as the buyer story; keep synthetic metrics labelled.",
        ),
        _requirement(
            "tenant_module_partner_scope",
            "Tenant, module, and partner scoped access model",
            "buyer_review",
            _status_from_bool(_score_status(market_readiness, "access_and_privacy") == "pass"),
            "IT/security owner + customer success",
            ["API_CONTRACT.md", "partner_cutdown_manifest.json", "CUSTOMER_ACCESS_PLAN.md"],
            "" if _score_status(market_readiness, "access_and_privacy") == "pass" else "Access/privacy scorecard area is not pass.",
            "Keep producer and partner scopes separate; production access still requires live RLS/customer probes.",
        ),
        _requirement(
            "data_platform_blueprint",
            "Shared data platform blueprint",
            "buyer_review",
            _status_from_bool(data_platform_ok),
            "IT/security owner + analytics owner + customer success",
            ["DATA_PLATFORM_BLUEPRINT.md", "DATA_PLATFORM_SCOPE_MATRIX.csv", "CUSTOMER_VIEW_CATALOG.md"],
            "" if data_platform_ok else "Data platform blueprint is missing or failed secret scan.",
            "Use this to review the one database spine across pilots while keeping tenant/module/partner/campaign/export boundaries explicit.",
        ),
        _requirement(
            "module_readiness_matrix",
            "Pilot module readiness matrix",
            "buyer_review",
            _status_from_bool(module_readiness_ok),
            "Product owner + analytics owner + customer success",
            ["MODULE_READINESS_MATRIX.md", "MODULE_READINESS_MATRIX.csv", "MODULE_METRIC_COVERAGE.csv"],
            "" if module_readiness_ok else "Module readiness matrix is missing, incomplete, or failed secret scan.",
            "Use this to review each pilot's metric, access, export, public-data, and live-proof gates before enabling modules for a tenant.",
        ),
        _requirement(
            "metric_semantics_governance",
            "Metric semantics, denominators, and governance",
            "buyer_review",
            _status_from_bool(_score_status(market_readiness, "data_governance") == "pass"),
            "Analytics owner + legal/privacy owner",
            ["DATA_DICTIONARY.md", "PROCESSING_REGISTER.md", "SOURCE_LEDGER.md"],
            "" if _score_status(market_readiness, "data_governance") == "pass" else "Data governance scorecard area is not pass.",
            "Keep response rates denominator-explicit and scores framed as opportunity signals, not homeowner intent.",
        ),
        _requirement(
            "open_intelligence_autoresearch",
            "Open Intelligence and autoresearch evidence",
            "buyer_review",
            _status_from_bool(
                _entry_exists(portable_manifest, "Intelligence Lab report")
                and _entry_exists(portable_manifest, "Intelligence Lab JSON evidence")
            ),
            "Marketing lead + customer success",
            ["INTELLIGENCE_LAB.md", "intelligence_lab.json", "dashboard Intelligence tab"],
            "" if _entry_exists(portable_manifest, "Intelligence Lab report") else "Intelligence Lab evidence is not in the portable data room.",
            "Use autoresearch as review evidence only; message tests require customer/legal approval before launch.",
        ),
        _requirement(
            "open_intelligence_production_gate",
            "Open Intelligence production gate and runbook",
            "buyer_review",
            _status_from_bool(open_intelligence_production_ok),
            "Marketing lead + IT/security owner + customer success",
            ["OPEN_INTELLIGENCE_PRODUCTION_GATE.md", "OPEN_INTELLIGENCE_PRODUCTION_GATES.csv", "OPEN_INTELLIGENCE_PRODUCTION_RUNBOOK.md"],
            "" if open_intelligence_production_ok else "Open Intelligence production gate, gate matrix, or runbook is missing from the portable data room.",
            "Use this to keep buyer-review decisions separate from live access, outreach, public-data import, outcome sync, monitoring, and production proof.",
        ),
        _requirement(
            "outcome_measurement_contract",
            "Closed-loop outcome measurement contract",
            "buyer_review",
            _status_from_bool(outcome_contract_ok),
            "Analyst + customer success + DAW/partner CRM owner",
            ["OUTCOME_MEASUREMENT_CONTRACT.md", "OUTCOME_EVENT_SCHEMA.csv", "OUTCOME_SYNC_TEMPLATE.csv", "OUTCOME_RECONCILIATION_CHECKLIST.csv"],
            "" if outcome_contract_ok else "Outcome measurement contract is missing, incomplete, or failed secret scan.",
            "Agree appointment, quote, won/lost, value, and loss-reason definitions plus approved source systems before outcome sync.",
        ),
        _requirement(
            "outcome_import_validation",
            "Outcome import dry-run validation",
            "buyer_review",
            _status_from_bool(outcome_import_ok),
            "Analyst + CRM owner + customer success",
            ["OUTCOME_IMPORT_VALIDATION.md", "OUTCOME_IMPORT_ISSUES.csv", "OUTCOME_IMPORT_REVIEW_ROWS.csv"],
            "" if outcome_import_ok else "Outcome import validation is missing, blocked, incomplete, or failed secret scan.",
            "Run this dry-run against filled customer CRM/sheet outcome rows before live sync; keep production sync blocked until live proof passes.",
        ),
        _requirement(
            "first_campaign_operating_model",
            "First-campaign operating model",
            "buyer_review",
            _status_from_bool(
                _path_exists(paths.get("first_campaign_launch_intake_markdown"))
                and _path_exists(paths.get("first_wave_launch_gate_markdown"))
                and _path_exists(paths.get("first_wave_database_handoff_markdown"))
            ),
            "Campaign owner + customer success",
            ["FIRST_CAMPAIGN_LAUNCH_INTAKE.md", "FIRST_CAMPAIGN_IMPORT_PLAN.md", "FIRST_WAVE_LAUNCH_GATE.md", "FIRST_WAVE_DATABASE_HANDOFF.md"],
            "" if _path_exists(paths.get("first_wave_database_handoff_markdown")) else "First-wave database handoff is missing.",
            "Collect customer CSVs, validate inputs, stage non-mutating import rows, prepare database review handoff, and keep launch blocked until go/no-go.",
        ),
        _requirement(
            "public_data_governance",
            "Public-data review and production intake",
            "buyer_review",
            _status_from_bool(
                _path_exists(paths.get("public_data_source_register_markdown"))
                and _path_exists(paths.get("public_data_production_intake_markdown"))
            ),
            "Legal/privacy owner + data owner",
            ["PUBLIC_DATA_SOURCE_REGISTER.md", "PUBLIC_DATA_PRODUCTION_INTAKE.md", "ATTRIBUTION_REQUIREMENTS.csv"],
            "" if _path_exists(paths.get("public_data_production_intake_markdown")) else "Public-data production intake is missing.",
            "Approve source licence, allowed use, field allowlist, attribution, and provenance before production import.",
        ),
        _requirement(
            "commercial_support_training",
            "Commercial, support, procurement, and training handoff",
            "buyer_review",
            _status_from_bool(
                _path_exists(paths.get("customer_pilot_proposal_markdown"))
                and _path_exists(paths.get("support_sla_plan_markdown"))
                and _path_exists(paths.get("customer_training_guide"))
            ),
            "Sales lead + support owner + customer success",
            ["CUSTOMER_PILOT_PROPOSAL.md", "SUPPORT_SLA_PLAN.md", "CUSTOMER_TRAINING_GUIDE.md"],
            "" if _path_exists(paths.get("customer_training_guide")) else "Training/support/commercial evidence is incomplete.",
            "Use these as review artifacts; commercial offer, SLA, and training plan still require customer agreement.",
        ),
        _requirement(
            "live_launch_control",
            "Live launch control room",
            "live_launch",
            _status_from_bool(bool(launch_control_room) and control_secret_ok, "blocked"),
            "HomePilot operator + IT owner",
            ["LIVE_LAUNCH_CONTROL_ROOM.md", "LIVE_LAUNCH_ACTION_BOARD.csv"],
            "" if launch_control_room and control_secret_ok else "Live launch control room is missing or secret scan failed.",
            "Use the control room as the launch meeting surface; it remains non-mutating and stores env var names only.",
            production_required=True,
        ),
        _requirement(
            "live_proof_plan_validated",
            "Live proof execution plan self-validation",
            "live_launch",
            _status_from_bool(plan_validation_ok, "blocked"),
            "HomePilot operator + IT owner",
            ["LIVE_PROOF_EXECUTION_PLAN.md", "LIVE_PROOF_COMMANDS.sh", "LIVE_PROOF_EVIDENCE_MAP.csv"],
            "" if plan_validation_ok else "Live proof plan validation is missing, failed, or secret scan failed.",
            "Regenerate the live proof plan and fix validation failures before live cutover.",
            production_required=True,
        ),
        _requirement(
            "live_proof_acceptance_matrix",
            "Live proof customer/IT acceptance matrix",
            "live_launch",
            _status_from_bool(acceptance_ok, "blocked"),
            "DAW executive sponsor + IT owner + customer success + HomePilot operator",
            ["LIVE_PROOF_ACCEPTANCE_MATRIX.md", "LIVE_PROOF_ACCEPTANCE_MATRIX.csv"],
            "" if acceptance_ok else "Live proof acceptance matrix is missing, empty, or secret scan failed.",
            "Use the matrix to agree which live schema, RLS, customer-access, partner-access, signoff, and production evidence must pass.",
            production_required=True,
        ),
        _requirement(
            "live_proof_evidence_vault",
            "Live proof evidence vault and archive index",
            "live_launch",
            _status_from_bool(vault_ok, "blocked"),
            "IT owner + security owner + customer success + HomePilot operator",
            ["LIVE_PROOF_EVIDENCE_VAULT.md", "LIVE_PROOF_ARCHIVE_INDEX.csv"],
            "" if vault_ok else "Live proof evidence vault is missing, empty, or failed secret scan.",
            "Use the vault to archive which live proof artifacts exist, which remain blocked, their freshness rules, owners, and safe handling requirements.",
            production_required=True,
        ),
        _requirement(
            "live_credential_handoff",
            "Live credential handoff and secret channel contract",
            "live_launch",
            _status_from_bool(credential_handoff_ok, "blocked"),
            "IT owner + security owner + customer success + HomePilot operator",
            ["LIVE_CREDENTIAL_HANDOFF.md", "LIVE_CREDENTIAL_HANDOFF_CHECKLIST.csv", "LIVE_SECRET_CHANNEL_CONTRACT.csv"],
            "" if credential_handoff_ok else "Live credential handoff is missing, incomplete, or failed secret scan.",
            "Use the handoff to assign env var names, approved secret channels, validation artifacts, and evidence archive rules before live proof.",
            production_required=True,
        ),
        _requirement(
            "live_inputs_ready",
            "Live Supabase/RLS/customer-access inputs",
            "live_launch",
            _status_from_bool(live_tasks == 0, "blocked"),
            "Platform admin + HomePilot operator + customer success",
            ["LIVE_READINESS.md", "LIVE_LAUNCH_REQUEST.md", "LIVE_LAUNCH_CHECKLIST.csv"],
            "" if live_tasks == 0 else f"{live_tasks} live input tasks remain.",
            "Configure Supabase, fixture, and planned customer-access credentials through the approved secret channel.",
            production_required=True,
        ),
        _requirement(
            "live_schema_rls_customer_access",
            "Live schema, RLS, and customer access proof",
            "production_rollout",
            _status_from_bool(production_verified, "blocked"),
            "IT owner + HomePilot operator + customer success",
            ["schema_verification.json", "launch_report.json", "customer_access_verification.json", "PRODUCTION_PROOF.md"],
            "" if production_verified else "Live schema, RLS launch, and customer access reports are not all production_verified=true.",
            "Run live schema verification, live RLS launch, and customer access probes; archive production_verified=true evidence.",
            production_required=True,
        ),
        _requirement(
            "first_wave_authorization",
            "First-wave outreach and partner access authorization",
            "production_rollout",
            _status_from_bool(first_wave_authorized, "blocked"),
            "DAW executive sponsor + campaign owner",
            ["FIRST_WAVE_LAUNCH_GATE.md", "CUSTOMER_GO_NO_GO_REFERENCE"],
            "" if first_wave_authorized else "First-wave launch_authorized is false.",
            "Obtain explicit customer go/no-go after customer inputs, live proof, source approval, and legal/message approvals pass.",
            production_required=True,
        ),
    ]
    return requirements


def _status(requirements: list[dict[str, Any]]) -> str:
    production_blockers = [row for row in requirements if row["production_required"] and row["status"] != "pass"]
    buyer_blockers = [row for row in requirements if row["stage"] == "buyer_review" and row["status"] != "pass"]
    if not buyer_blockers and not production_blockers:
        return "market_ready_production_verified"
    if not buyer_blockers:
        return "buyer_review_ready_production_blocked"
    return "action_required"


def _summary(requirements: list[dict[str, Any]]) -> dict[str, Any]:
    buyer = [row for row in requirements if row["stage"] == "buyer_review"]
    live = [row for row in requirements if row["stage"] == "live_launch"]
    production = [row for row in requirements if row["stage"] == "production_rollout"]
    blockers = [row for row in requirements if row["status"] != "pass"]
    return {
        "requirement_count": len(requirements),
        "passed_count": len([row for row in requirements if row["status"] == "pass"]),
        "blocked_count": len(blockers),
        "buyer_review_passed": len([row for row in buyer if row["status"] == "pass"]),
        "buyer_review_total": len(buyer),
        "live_launch_blockers": len([row for row in live if row["status"] != "pass"]),
        "production_blockers": len([row for row in production if row["status"] != "pass"]),
        "production_required_blockers": len([row for row in requirements if row["production_required"] and row["status"] != "pass"]),
    }


def _secret_scan(audit: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(audit, ensure_ascii=False)
    findings = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(body)]
    return {
        "status": "pass" if not findings else "fail",
        "issue_count": len(findings),
        "patterns": findings,
    }


def render_markdown(audit: dict[str, Any]) -> str:
    summary = audit["summary"]
    lines = [
        "# HomePilot Market-Ready Gap Audit",
        "",
        f"Release: {audit['release_label']}",
        f"Created: {audit['created_at']}",
        f"Status: {audit['status']}",
        "",
        "This audit maps the full market-ready platform objective to current evidence. It is a derived review surface: it does not write to Supabase, does not authorize outreach, and does not create production proof.",
        "",
        "## Summary",
        "",
        f"- Requirements: {summary['requirement_count']}",
        f"- Passed: {summary['passed_count']}",
        f"- Blocked: {summary['blocked_count']}",
        f"- Buyer-review requirements passed: {summary['buyer_review_passed']}/{summary['buyer_review_total']}",
        f"- Live-launch blockers: {summary['live_launch_blockers']}",
        f"- Production blockers: {summary['production_blockers']}",
        "",
        "## Requirements",
        "",
        "| Requirement | Stage | Status | Owner | Evidence | Blocker | Next action |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in audit["requirements"]:
        evidence = ", ".join(row["evidence"])
        blocker = row["blocker"] or "none"
        lines.append(
            f"| {row['label']} | {row['stage']} | {row['status']} | {row['owner']} | {evidence} | {blocker} | {row['next_action']} |"
        )
    lines += [
        "",
        "## Guardrails",
        "",
        "- Buyer-review ready is not the same as production verified.",
        "- Scores and public context are opportunity signals, not homeowner intent.",
        "- Partner views remain assigned-record only.",
        "- Public-data imports require dataset-level licence, allowed-use, attribution, and provenance approval.",
        "- No outreach, live imports, or partner portal access before live proof and explicit customer go/no-go.",
        "- Secret values stay in a secret manager or local launch session.",
        "",
    ]
    return "\n".join(lines)


def write_requirements_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "key",
        "label",
        "stage",
        "status",
        "owner",
        "evidence",
        "blocker",
        "next_action",
        "production_required",
        "customer_visible",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                **{field: row.get(field, "") for field in fields},
                "evidence": "; ".join(row.get("evidence") or []),
            })


def build_market_ready_audit_pack(
    out_dir: Path,
    *,
    market_readiness: dict[str, Any],
    launch_control_room: dict[str, Any] | None = None,
    live_proof_plan: dict[str, Any] | None = None,
    live_proof_acceptance: dict[str, Any] | None = None,
    live_credential_handoff: dict[str, Any] | None = None,
    live_proof_evidence_vault: dict[str, Any] | None = None,
    outcome_measurement_contract: dict[str, Any] | None = None,
    outcome_import_validation: dict[str, Any] | None = None,
    module_readiness_matrix: dict[str, Any] | None = None,
    production_proof: dict[str, Any] | None = None,
    portable_manifest: dict[str, Any] | None = None,
    release_label: str = "local",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    requirements = _build_requirements(
        market_readiness,
        launch_control_room,
        live_proof_plan,
        live_proof_acceptance,
        live_credential_handoff,
        live_proof_evidence_vault,
        outcome_measurement_contract,
        outcome_import_validation,
        module_readiness_matrix,
        production_proof,
        portable_manifest,
    )
    audit = {
        "audit_type": "homepilot_market_ready_gap_audit",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": _status(requirements),
        "summary": _summary(requirements),
        "requirements": requirements,
        "guardrails": {
            "derived_review_surface": True,
            "non_mutating": True,
            "no_supabase_writes": True,
            "production_requires_live_proof": True,
            "no_outreach_authorized": True,
            "secret_values_written": False,
        },
        "paths": {
            "market_ready_audit": str(out_dir / "market_ready_audit.json"),
            "market_ready_audit_markdown": str(out_dir / "MARKET_READY_GAP_AUDIT.md"),
            "market_ready_requirements": str(out_dir / "MARKET_READY_REQUIREMENTS.csv"),
        },
    }
    audit["secret_scan"] = _secret_scan(audit)
    audit["guardrails"]["secret_values_written"] = audit["secret_scan"]["status"] != "pass"
    write_json(out_dir / "market_ready_audit.json", audit)
    write_text(out_dir / "MARKET_READY_GAP_AUDIT.md", render_markdown(audit))
    write_requirements_csv(out_dir / "MARKET_READY_REQUIREMENTS.csv", requirements)
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot market-ready gap audit")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--market-readiness", required=True, type=Path)
    parser.add_argument("--launch-control-room", type=Path)
    parser.add_argument("--live-proof-plan", type=Path)
    parser.add_argument("--live-proof-acceptance", type=Path)
    parser.add_argument("--live-credential-handoff", type=Path)
    parser.add_argument("--live-proof-evidence-vault", type=Path)
    parser.add_argument("--outcome-measurement-contract", type=Path)
    parser.add_argument("--outcome-import-validation", type=Path)
    parser.add_argument("--module-readiness-matrix", type=Path)
    parser.add_argument("--production-proof", type=Path)
    parser.add_argument("--portable-manifest", type=Path)
    parser.add_argument("--release-label", default="local")
    args = parser.parse_args()
    audit = build_market_ready_audit_pack(
        args.out_dir,
        market_readiness=load_json(args.market_readiness) or {},
        launch_control_room=load_json(args.launch_control_room),
        live_proof_plan=load_json(args.live_proof_plan),
        live_proof_acceptance=load_json(args.live_proof_acceptance),
        live_credential_handoff=load_json(args.live_credential_handoff),
        live_proof_evidence_vault=load_json(args.live_proof_evidence_vault),
        outcome_measurement_contract=load_json(args.outcome_measurement_contract),
        outcome_import_validation=load_json(args.outcome_import_validation),
        module_readiness_matrix=load_json(args.module_readiness_matrix),
        production_proof=load_json(args.production_proof),
        portable_manifest=load_json(args.portable_manifest),
        release_label=args.release_label,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": audit["status"],
        "requirements": audit["summary"]["requirement_count"],
        "blocked": audit["summary"]["blocked_count"],
        "markdown": audit["paths"]["market_ready_audit_markdown"],
        "requirements_csv": audit["paths"]["market_ready_requirements"],
    }, indent=2, ensure_ascii=False))
    if audit["secret_scan"]["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
