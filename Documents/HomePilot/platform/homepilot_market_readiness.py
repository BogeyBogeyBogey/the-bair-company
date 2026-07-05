#!/usr/bin/env python3
"""
Build a HomePilot market-readiness scorecard.

This is the buyer-facing wrapper around the evidence room. It does not create
new proof. It translates existing readiness, due-diligence, release, live
readiness, and launch-request artifacts into a boardroom-readable scorecard,
data-room index, and action list.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from homepilot_first_campaign_import_plan import build_first_campaign_import_plan
from homepilot_first_campaign_input_validation import build_first_campaign_input_validation
from homepilot_first_wave_database_handoff import build_first_wave_database_handoff
from homepilot_first_wave_launch_gate import build_first_wave_launch_gate
from homepilot_data_platform_blueprint import build_data_platform_blueprint_pack
from homepilot_launch_control_room import build_launch_control_room_pack
from homepilot_live_credential_handoff import build_live_credential_handoff_pack
from homepilot_live_proof_acceptance import build_live_proof_acceptance_pack
from homepilot_live_proof_evidence_vault import build_live_proof_evidence_vault_pack
from homepilot_live_proof_plan import build_live_proof_plan_pack
from homepilot_market_ready_audit import build_market_ready_audit_pack
from homepilot_module_readiness_matrix import build_module_readiness_matrix_pack
from homepilot_outcome_import_validation import build_outcome_import_validation_pack
from homepilot_outcome_measurement_contract import build_outcome_measurement_contract_pack
from homepilot_customer_signoff_reconciliation import build_customer_signoff_reconciliation_pack
from homepilot_customer_view_catalog import build_customer_view_catalog_pack
from homepilot_partner_access_reconciliation import build_partner_access_reconciliation_pack
from homepilot_partner_auth_mapping import build_partner_auth_mapping_pack
from homepilot_public_data_reconciliation import build_public_data_reconciliation_pack
from homepilot_platform import PILOT_MODULES


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


TEXT_ARTIFACT_SUFFIXES = {
    ".csv",
    ".html",
    ".js",
    ".json",
    ".jsonl",
    ".md",
    ".sh",
    ".sql",
    ".txt",
}

LOCAL_PATH_PATTERN = re.compile(r"(?:file://)?/(?:private/tmp|tmp|var/folders|Users)/[^\s\"'<>),|]+")


def copy_portable_artifact(source: Path, target: Path) -> int:
    if source.suffix.lower() in TEXT_ARTIFACT_SUFFIXES:
        body = source.read_text(encoding="utf-8")
        redacted, redaction_count = LOCAL_PATH_PATTERN.subn("[portable-data-room]", body)
        target.write_text(redacted, encoding="utf-8")
        return redaction_count
    shutil.copy2(source, target)
    return 0


def _path_exists(path: str | None) -> bool:
    return bool(path and Path(path).exists())


def _dedupe_artifacts_by_label(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    index_by_label: dict[str, int] = {}
    for item in items:
        label = str(item.get("label") or "")
        if not label:
            deduped.append(item)
            continue
        existing_index = index_by_label.get(label)
        if existing_index is None:
            index_by_label[label] = len(deduped)
            deduped.append(item)
            continue
        existing = deduped[existing_index]
        if _path_exists(str(item.get("path")) if item.get("path") else None) and not _path_exists(
            str(existing.get("path")) if existing.get("path") else None
        ):
            deduped[existing_index] = item
    return deduped


def _gate_map(readiness: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not readiness:
        return {}
    return {str(gate.get("name")): gate for gate in readiness.get("gates", [])}


def _gate_pass(gates: dict[str, dict[str, Any]], name: str) -> bool:
    return gates.get(name, {}).get("status") == "pass"


def _path_from_readiness(readiness: dict[str, Any] | None, key: str, *parts: str) -> str | None:
    if not readiness:
        return None
    base = readiness.get("paths", {}).get(key)
    if not base:
        return None
    return str(Path(base, *parts))


def _json_from_readiness(readiness: dict[str, Any] | None, key: str, *parts: str) -> dict[str, Any] | None:
    path = _path_from_readiness(readiness, key, *parts)
    return load_json(Path(path)) if path else None


def _artifact(
    label: str,
    audience: str,
    why_it_matters: str,
    path: str | None,
    source: str,
    required_for: str = "buyer_review",
) -> dict[str, Any]:
    return {
        "label": label,
        "audience": audience,
        "why_it_matters": why_it_matters,
        "path": path,
        "exists": _path_exists(path),
        "source": source,
        "required_for": required_for,
    }


def _score(
    key: str,
    label: str,
    status: str,
    summary: str,
    evidence: list[str],
    caveat: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "summary": summary,
        "evidence": evidence,
        "caveat": caveat,
    }


def _decision_sources(
    artifact_index: dict[str, Any] | None,
    production_proof: dict[str, Any] | None,
) -> dict[str, str]:
    decisions = {}
    if artifact_index and isinstance(artifact_index.get("decisions"), dict):
        decisions.update({key: str(value) for key, value in artifact_index["decisions"].items()})
    if production_proof and isinstance(production_proof.get("decisions"), dict):
        decisions.update({key: str(value) for key, value in production_proof["decisions"].items()})
    return {
        "buyer_review": decisions.get("buyer_review", "unknown"),
        "live_launch": decisions.get("live_launch", "unknown"),
        "production": decisions.get("production", "unknown"),
    }


def _scorecard(
    readiness: dict[str, Any] | None,
    due_diligence: dict[str, Any] | None,
    artifact_index: dict[str, Any] | None,
    production_proof: dict[str, Any] | None,
    live_readiness: dict[str, Any] | None,
    live_launch_request: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    gates = _gate_map(readiness)
    decisions = _decision_sources(artifact_index, production_proof)
    redaction = due_diligence.get("redaction", {}) if due_diligence else {}
    live_task_count = live_launch_request.get("summary", {}).get("task_count") if live_launch_request else None
    missing_live_artifacts = production_proof.get("production_gate", {}).get("missing_live_artifacts", []) if production_proof else []

    demo_ready = all(
        _gate_pass(gates, name)
        for name in ("enterprise_demo_room_smoke", "boardroom_report_smoke", "partner_cutdown_smoke", "visual_intelligence_smoke")
    )
    governance_ready = all(
        _gate_pass(gates, name)
        for name in ("data_dictionary_smoke", "api_contract_smoke", "processing_register_smoke", "compliance_smoke", "retention_smoke", "source_ledger_smoke")
    ) and redaction.get("status") == "pass"
    access_ready = all(
        _gate_pass(gates, name)
        for name in ("account_access_smoke", "customer_access_verification_smoke", "benchmark_privacy_smoke", "partner_cutdown_smoke")
    )
    deployment_ready = all(
        _gate_pass(gates, name)
        for name in ("deployment_manifest_smoke", "schema_verification_smoke", "launch_dry_run")
    )
    buyer_ready = (
        readiness
        and readiness.get("status") == "pass"
        and due_diligence
        and due_diligence.get("status") in {"local_ready", "production_ready"}
        and decisions["buyer_review"] == "go"
    )
    live_ready = (
        live_readiness
        and live_readiness.get("status") == "ready"
        and live_readiness.get("ready_to_run_live_cutover") is True
        and decisions["live_launch"] == "go"
    )
    production_ready = production_proof and production_proof.get("production_gate", {}).get("verified") is True

    return [
        _score(
            "demo_value",
            "Customer value demo",
            "pass" if demo_ready else "blocked",
            "Enterprise demo room, boardroom report, partner cutdowns, and visual intelligence are locally ready.",
            ["enterprise_demo_room_smoke", "boardroom_report_smoke", "partner_cutdown_smoke", "visual_intelligence_smoke"],
            "Synthetic demo evidence only; do not present as live customer performance.",
        ),
        _score(
            "buyer_review",
            "Buyer/security review",
            "pass" if buyer_ready else "blocked",
            "Readiness, due diligence, release audit, and redaction evidence support buyer review.",
            ["readiness_report", "due_diligence_report", "release_audit", "production_proof"],
            "Buyer review can be green while production remains blocked.",
        ),
        _score(
            "access_and_privacy",
            "Tenant, module, partner access",
            "pass" if access_ready else "blocked",
            "Local access planning, customer-access dry-run, benchmark privacy, and partner cutdown checks pass.",
            ["account_access_smoke", "customer_access_verification_smoke", "benchmark_privacy_smoke", "partner_cutdown_smoke"],
            "Live partner/customer access still needs real Supabase JWT probes.",
        ),
        _score(
            "data_governance",
            "Data governance and explainability",
            "pass" if governance_ready else "blocked",
            "Dictionary, API contract, processing register, compliance, retention, source ledger, and redaction checks are ready.",
            ["data_dictionary_smoke", "api_contract_smoke", "processing_register_smoke", "compliance_smoke", "retention_smoke", "source_ledger_smoke"],
            "Public-data imports still require dataset-level licence review.",
        ),
        _score(
            "deployment_evidence",
            "Deployment evidence",
            "pass" if deployment_ready else "blocked",
            "Deployment manifest, SQL apply plan, local schema contract, and dry-run launch chain are available.",
            ["deployment_manifest_smoke", "schema_verification_smoke", "launch_dry_run", "sql_apply_plan"],
            "SQL apply plan is non-mutating; production needs live schema verification after apply.",
        ),
        _score(
            "live_launch",
            "Live launch readiness",
            "pass" if live_ready else "blocked",
            f"Live launch is blocked by {live_task_count if live_task_count is not None else 'unknown'} missing input tasks.",
            ["live_readiness", "live_launch_request"],
            "Missing inputs must be supplied through a secret manager or local launch session, not email.",
        ),
        _score(
            "production_rollout",
            "Production rollout",
            "pass" if production_ready else "blocked",
            "Production is blocked until live readiness, schema verification, launch/RLS, and customer access proof all pass.",
            ["production_proof", "schema_verification_report", "launch_report", "customer_access_report"],
            f"Missing live proof: {', '.join(missing_live_artifacts) if missing_live_artifacts else 'none listed'}.",
        ),
    ]


def _data_room(
    readiness: dict[str, Any] | None,
    due_diligence: dict[str, Any] | None,
    artifact_index: dict[str, Any] | None,
    production_proof: dict[str, Any] | None,
    live_readiness_path: str | None,
    live_launch_request_path: str | None,
) -> list[dict[str, Any]]:
    generated = artifact_index.get("generated_evidence", {}) if artifact_index else {}
    referenced = artifact_index.get("referenced_artifacts", {}) if artifact_index else {}
    due_paths = due_diligence.get("paths", {}) if due_diligence else {}
    proof_paths = production_proof.get("paths", {}) if production_proof else {}
    return [
        _artifact("Readiness report", "IT, security, operator", "Shows all local buyer-review gates and their status.", readiness.get("paths", {}).get("readiness_report") if readiness else None, "readiness"),
        _artifact("Due diligence report", "Security, legal, procurement", "Summarizes access matrices, source hashes, and redaction status.", due_paths.get("due_diligence_report"), "due_diligence"),
        _artifact("Executive due diligence summary", "Boardroom, procurement", "Short non-technical evidence summary for enterprise review.", due_paths.get("executive_summary"), "due_diligence"),
        _artifact("Production proof", "Security, IT", "Tamper-evident hash and production blocker manifest.", proof_paths.get("production_proof") or generated.get("production_proof"), "production_proof"),
        _artifact("Production cutover report", "Operator, IT owner", "Dry-run evidence chain for the controlled production cutover sequence without live writes.", generated.get("production_cutover_report"), "release_pack", "live_launch"),
        _artifact("Production cutover runbook", "Operator, IT owner, customer success", "Step-by-step cutover runbook covering live readiness, schema verification, module seed, RLS launch, customer access, and release audit gates.", generated.get("production_cutover_runbook"), "release_pack", "live_launch"),
        _artifact("Release notes", "All stakeholders", "Single release-room overview with decisions and referenced artifacts.", generated.get("release_notes"), "release_pack"),
        _artifact("Handoff checklist", "Operator, customer success", "Operational checklist for buyer review, live launch, and production rollout.", generated.get("handoff_checklist"), "release_pack"),
        _artifact("SQL apply plan", "IT owner, database admin", "Reviewable SQL bundle and post-apply smoke SQL.", generated.get("sql_apply_runbook"), "deployment", "live_launch"),
        _artifact("Apply SQL", "IT owner, database admin", "Ordered SQL bundle for Supabase review/application.", generated.get("apply_sql"), "deployment", "live_launch"),
        _artifact("Live readiness", "Operator, IT owner", "Redacted report of missing live credentials and proof inputs.", live_readiness_path, "live_readiness", "live_launch"),
        _artifact("Live launch request", "IT owner, customer success", "Owner-assigned checklist and safe credential request summary.", live_launch_request_path, "live_launch_request", "live_launch"),
        _artifact("Live launch checklist", "IT owner, customer success", "CSV task list for missing Supabase, fixture, and customer-access inputs.", referenced.get("live_launch_checklist"), "live_launch_request", "live_launch"),
        _artifact("Live credential handoff", "IT owner, security, customer success, HomePilot operator", "Secret-safe handoff contract for live Supabase, RLS fixture, and customer-access env vars, safe channels, validation artifacts, and evidence archive rules.", generated.get("live_credential_handoff_markdown"), "market_readiness", "live_launch"),
        _artifact("Live credential checklist", "IT owner, customer success, HomePilot operator", "Excel-ready owner checklist for every live credential/config input without storing secret values.", generated.get("live_credential_handoff_checklist"), "market_readiness", "live_launch"),
        _artifact("Live secret channel contract", "IT owner, security, HomePilot operator", "CSV contract showing approved secret channels, forbidden channels, validation commands, and artifacts for each live input.", generated.get("live_secret_channel_contract"), "market_readiness", "live_launch"),
        _artifact("Access lens proof matrix", "IT/security, DAW network manager, customer success", "CSV proof that dashboard access lenses map to planned tenant, module, and partner-scoped customer identities before live RLS/JWT verification.", _path_from_readiness(readiness, "customer_access_verification_smoke", "ACCESS_LENS_PROOF_MATRIX.csv"), "readiness", "live_launch"),
        _artifact("Live proof evidence vault", "Boardroom, IT owner, security, customer success, HomePilot operator", "Archive index showing which live proof artifacts exist, which are blocked, who owns each proof, freshness rules, pass conditions, and safe handling rules.", generated.get("live_proof_evidence_vault_markdown"), "market_readiness", "live_launch"),
        _artifact("Live proof archive index", "IT owner, security, customer success, HomePilot operator", "Excel-ready vault index for schema verification, RLS launch, customer access, partner access, public-data, signoff, first-wave, and production proof.", generated.get("live_proof_archive_index"), "market_readiness", "live_launch"),
        _artifact("Boardroom report", "Boardroom, sales leadership", "Executive opportunity, partner, and work-queue report.", _path_from_readiness(readiness, "boardroom_report_smoke", "BOARDROOM_REPORT.md"), "readiness"),
        _artifact("Open Intelligence model card", "Boardroom, DAW marketing leadership, customer success", "Customer-readable model card, data-collaboration room, activation planner, outcome loop, and guardrails inspired by Open Intelligence but translated to tenant-scoped renovation opportunities.", _path_from_readiness(readiness, "enterprise_demo_room_smoke", "customer_package", "data", "open_intelligence", "OPEN_INTELLIGENCE.md"), "readiness"),
        _artifact("Open Intelligence boardroom brief", "Boardroom, DAW marketing leadership, network manager", "One-page executive decision brief that turns Open Intelligence evidence into DAW decisions, proof stack, owners, blockers, and launch guardrails.", _path_from_readiness(readiness, "enterprise_demo_room_smoke", "customer_package", "data", "open_intelligence", "OPEN_INTELLIGENCE_BOARDROOM_BRIEF.md"), "readiness"),
        _artifact("Open Intelligence decision matrix", "Boardroom, DAW marketing leadership, analyst", "Excel-ready decision matrix for first-wave focus, partner routing, segment-message tests, marketing measurement, and safe data use.", _path_from_readiness(readiness, "enterprise_demo_room_smoke", "customer_package", "data", "open_intelligence", "OPEN_INTELLIGENCE_DECISION_MATRIX.csv"), "readiness"),
        _artifact("Open Intelligence JSON evidence", "Analytics, IT/security, customer success", "Machine-readable evidence for model card, model lab, data-collaboration rules, marketing-impact planner, activation paths, outcome metrics, and guardrails.", _path_from_readiness(readiness, "enterprise_demo_room_smoke", "customer_package", "data", "open_intelligence", "open_intelligence.json"), "readiness"),
        _artifact("Marketing impact planner", "DAW marketing leadership, network manager, legal, customer success", "CSV of reviewable activation lanes, audiences, record counts, expected impact, approval requirements, measurement events, and guardrails before any live outreach.", _path_from_readiness(readiness, "enterprise_demo_room_smoke", "customer_package", "data", "open_intelligence", "MARKETING_IMPACT_PLANNER.csv"), "readiness"),
        _artifact("Open Intelligence measurement loop", "DAW network manager, campaign operations, analyst", "CSV measurement loop that keeps denominators explicit across pre-wave baseline, contacted measurement, partner effectiveness, message learning, and commercial outcome sync.", _path_from_readiness(readiness, "enterprise_demo_room_smoke", "customer_package", "data", "open_intelligence", "MEASUREMENT_LOOP.csv"), "readiness"),
        _artifact("Open Intelligence production gate", "Boardroom, IT/security, legal, customer success", "Customer-readable production gate that separates buyer-review readiness from live access, outreach, public-data import, outcome sync, monitoring, and production proof.", _path_from_readiness(readiness, "enterprise_demo_room_smoke", "customer_package", "data", "open_intelligence", "OPEN_INTELLIGENCE_PRODUCTION_GATE.md"), "readiness", "live_launch"),
        _artifact("Open Intelligence production gates CSV", "IT/security, analytics, customer success", "Excel-ready gate matrix with owner, evidence, buyer-review status, production status, blockers, pass conditions, and guardrails.", _path_from_readiness(readiness, "enterprise_demo_room_smoke", "customer_package", "data", "open_intelligence", "OPEN_INTELLIGENCE_PRODUCTION_GATES.csv"), "readiness", "live_launch"),
        _artifact("Open Intelligence production runbook", "Operator, IT/security, customer success", "Step-by-step operating runbook for turning Open Intelligence from review evidence into a controlled live production workflow.", _path_from_readiness(readiness, "enterprise_demo_room_smoke", "customer_package", "data", "open_intelligence", "OPEN_INTELLIGENCE_PRODUCTION_RUNBOOK.md"), "readiness", "live_launch"),
        _artifact("Outcome measurement contract", "DAW executive sponsor, CRM owner, analyst, customer success", "Closed-loop appointment, quote, won/lost, value, and loss-reason measurement contract with explicit denominators and source-system approval gates.", generated.get("outcome_measurement_contract_markdown"), "market_readiness", "buyer_review"),
        _artifact("Outcome event schema", "CRM owner, analyst, IT/security", "Excel-ready event schema for tenant-, module-, partner-, campaign-, and property-scoped outcome imports without raw contact data.", generated.get("outcome_event_schema"), "market_readiness", "buyer_review"),
        _artifact("Outcome sync template", "CRM owner, partner manager, customer success", "Synthetic template showing how approved CRM/sheet outcome rows should be structured before any live sync.", generated.get("outcome_sync_template"), "market_readiness", "buyer_review"),
        _artifact("Outcome reconciliation checklist", "DAW executive sponsor, CRM owner, legal, customer success", "Checklist for approving metric definitions, source systems, live access proof, first-wave authorization, and outcome-import dry run.", generated.get("outcome_reconciliation_checklist"), "market_readiness", "buyer_review"),
        _artifact("Outcome import dry-run validation", "CRM owner, analyst, customer success, IT/security", "Dry-run validation report for customer-approved outcome CSV rows before any live CRM or Supabase sync.", generated.get("outcome_import_validation_markdown"), "market_readiness", "buyer_review"),
        _artifact("Outcome import issues", "CRM owner, analyst, customer success", "Excel-ready blocker/warning list for outcome rows, including scope, idempotency, source reference, privacy, and value checks.", generated.get("outcome_import_issues"), "market_readiness", "buyer_review"),
        _artifact("Outcome import review rows", "CRM owner, analyst, customer success", "Redacted review rows showing how validated outcome events reconcile to tenant, module, partner, campaign, and property scope.", generated.get("outcome_import_review_rows"), "market_readiness", "buyer_review"),
        _artifact("Module readiness matrix", "Boardroom, IT/security, analyst, customer success", "Audit-grade per-pilot matrix showing catalog, metric visibility, export readiness, public-data lanes, scope filters, and live-production gates.", generated.get("module_readiness_matrix_markdown"), "market_readiness", "buyer_review"),
        _artifact("Module readiness CSV", "IT/security, analyst, customer success", "Excel-ready module-by-module readiness matrix across FacadePilot, WindowPilot, RoofPilot, GardenPilot, PoolPilot, PorchPilot, DrivewayPilot, and future module review.", generated.get("module_readiness_matrix_csv"), "market_readiness", "buyer_review"),
        _artifact("Module metric coverage", "Analyst, product owner, customer success", "Excel-ready metric coverage file showing which module metrics are dashboard-visible, export-visible, benchmark-visible, and primary score fields.", generated.get("module_metric_coverage"), "market_readiness", "buyer_review"),
        _artifact("Intelligence Lab report", "Boardroom, DAW network manager, customer success", "Autoresearch evidence for lead priority, partner waves, campaign segments, and message tests with launch guardrails.", _path_from_readiness(readiness, "boardroom_report_smoke", "intelligence_lab", "INTELLIGENCE_LAB.md"), "readiness"),
        _artifact("Intelligence Lab JSON evidence", "Analytics, IT, customer success", "Machine-readable autoresearch family scores, paths, guardrails, scope-leakage evidence, and compliance evidence.", _path_from_readiness(readiness, "boardroom_report_smoke", "intelligence_lab", "intelligence_lab.json"), "readiness"),
        _artifact("Partner cutdown manifest", "Producer network, partner managers", "Evidence that partner packages are scoped and leakage-audited.", _path_from_readiness(readiness, "partner_cutdown_smoke", "partner_cutdown_manifest.json"), "readiness"),
        _artifact("Data dictionary", "Analytics, IT, legal", "Definitions for customer-facing metrics, tables, exports, and surfaces.", due_paths.get("data_dictionary_markdown"), "due_diligence"),
        _artifact("API contract", "IT, integration owner", "Supabase/PostgREST read-model contract and RLS expectations.", due_paths.get("api_contract_markdown"), "due_diligence"),
        _artifact("Processing register", "Legal, privacy", "Processing activities, categories, controls, retention, and risks.", due_paths.get("processing_register_markdown"), "due_diligence"),
        _artifact("Demo dashboard", "Sales, boardroom", "Synthetic enterprise demo dashboard for the property-intelligence story.", referenced.get("enterprise_demo_room_dashboard"), "readiness"),
    ]


def _actions(
    scorecard: list[dict[str, Any]],
    live_launch_request: dict[str, Any] | None,
    production_proof: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    actions = []
    if live_launch_request and live_launch_request.get("status") == "action_required":
        actions.append({
            "priority": 1,
            "owner": "Platform admin / Supabase owner",
            "action": "Configure Supabase URL, service-role key, anon key, and database URL through the agreed secret channel.",
            "source": "live_launch_request",
            "status": "required",
        })
        actions.append({
            "priority": 2,
            "owner": "HomePilot operator",
            "action": "Prepare temporary RLS fixture passwords for WindowPilot, FacadePilot tenant-wide, and FacadePilot partner probes.",
            "source": "live_launch_request",
            "status": "required",
        })
        actions.append({
            "priority": 3,
            "owner": "Customer success / tenant admin",
            "action": "Prepare short-lived customer access tokens or passwords for owner, manager, and partner-scoped verification users.",
            "source": "live_launch_request",
            "status": "required",
        })
    if production_proof and production_proof.get("production_gate", {}).get("verified") is not True:
        actions += [
            {
                "priority": 4,
                "owner": "Database / IT owner",
                "action": "Apply reviewed SQL and run live schema verification with production_verified=true.",
                "source": "production_proof",
                "status": "required",
            },
            {
                "priority": 5,
                "owner": "HomePilot operator",
                "action": "Run live RLS launch fixture and archive launch_report.json plus rls_probe_report.json.",
                "source": "production_proof",
                "status": "required",
            },
            {
                "priority": 6,
                "owner": "Customer success / tenant admin",
                "action": "Run customer access verification with planned invitees and archive production_verified=true evidence.",
                "source": "production_proof",
                "status": "required",
            },
        ]
    if not actions:
        actions.append({
            "priority": 1,
            "owner": "HomePilot operator",
            "action": "Archive release evidence and review fixture cleanup plan.",
            "source": "scorecard",
            "status": "ready",
        })
    return actions


def _stakeholder_views(report: dict[str, Any]) -> dict[str, Any]:
    decisions = report["decisions"]
    return {
        "boardroom": {
            "headline": "HomePilot is buyer-review ready and demo-ready; production waits for live proof.",
            "look_at": ["MARKET_READINESS_SCORECARD.md", "BOARDROOM_REPORT.md", "INTELLIGENCE_LAB.md", "LIVE_LAUNCH_CONTROL_ROOM.md", "BOARDROOM_DATA_ROOM_INDEX.md", "PRODUCTION_PROOF.md"],
            "decision": decisions["buyer_review"],
        },
        "it_security": {
            "headline": "Local contracts, access plans, redaction, SQL apply plan, procurement answers, live-launch control, and production blockers are explicit.",
            "look_at": ["LIVE_LAUNCH_CONTROL_ROOM.md", "LIVE_LAUNCH_ACTION_BOARD.csv", "PROCUREMENT_SECURITY_REVIEW.md", "SECURITY_QUESTIONNAIRE.csv", "SQL_APPLY_PLAN.md", "API_CONTRACT.md"],
            "decision": decisions["live_launch"],
        },
        "customer_success": {
            "headline": "The rollout and support plans turn buyer review into named workstreams, training, escalation, and first-campaign support.",
            "look_at": ["CUSTOMER_TRAINING_GUIDE.md", "TRAINING_SESSION_PLAN.csv", "CUSTOMER_ROLLOUT_PLAN.md", "SUPPORT_SLA_PLAN.md"],
            "decision": decisions["live_launch"],
        },
        "sales": {
            "headline": "Use the boardroom report, Intelligence Lab, demo dashboard, partner cutdowns, scorecard, pilot proposal, and role guide for the enterprise story.",
            "look_at": ["CUSTOMER_PILOT_PROPOSAL.md", "CUSTOMER_MODULE_EXPANSION_PLAN.md", "CUSTOMER_TRAINING_GUIDE.md", "BOARDROOM_REPORT.md", "INTELLIGENCE_LAB.md"],
            "decision": decisions["buyer_review"],
        },
    }


def _write_actions_csv(path: Path, actions: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["priority", "owner", "action", "source", "status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for action in actions:
            writer.writerow({field: action.get(field, "") for field in fields})


def _score_status(report: dict[str, Any], key: str) -> str:
    for row in report["scorecard"]:
        if row["key"] == key:
            return str(row["status"])
    return "unknown"


def build_acceptance_plan(report: dict[str, Any]) -> dict[str, Any]:
    decisions = report["decisions"]
    criteria = [
        {
            "stage": "buyer_review",
            "criterion": "Boardroom value story is demonstrable.",
            "owner": "Executive sponsor / sales lead",
            "status": _score_status(report, "demo_value"),
            "evidence": ["homepilot_boardroom_data_room.zip", "Boardroom report", "Demo dashboard", "Market readiness scorecard"],
            "acceptance_test": "Buyer can inspect the demo, boardroom report, partner cutdowns, and visual intelligence without using live customer data.",
        },
        {
            "stage": "buyer_review",
            "criterion": "Tenant, module, and partner scoping is reviewable.",
            "owner": "IT/security owner",
            "status": _score_status(report, "access_and_privacy"),
            "evidence": ["API contract", "Account access plan", "Customer access dry-run", "Partner cutdown manifest"],
            "acceptance_test": "Buyer can see which roles, modules, partners, exports, and metrics are visible, and which live probes remain required.",
        },
        {
            "stage": "buyer_review",
            "criterion": "Data governance and explainability are documented.",
            "owner": "Legal/privacy owner",
            "status": _score_status(report, "data_governance"),
            "evidence": ["Data dictionary", "Processing register", "Source ledger", "Due diligence report"],
            "acceptance_test": "Buyer can trace visible metrics to definitions, processing purposes, retention rules, and source caveats.",
        },
        {
            "stage": "buyer_review",
            "criterion": "Public-data enrichment has a reviewable storage and provenance contract.",
            "owner": "Legal/privacy owner / IT-security owner",
            "status": _score_status(report, "data_governance"),
            "evidence": ["PUBLIC_DATA_SOURCE_REGISTER.md", "PUBLIC_DATA_SOURCE_MATRIX.csv", "ATTRIBUTION_REQUIREMENTS.csv", "SQL apply plan"],
            "acceptance_test": "Buyer can see that approved public data lands in source-run/geography/public-feature/property-enrichment tables with licence, allowed use, attribution, retrieval metadata, transform version, confidence, and provenance before appearing in customer dashboards.",
        },
        {
            "stage": "buyer_review",
            "criterion": "Deployment evidence is ready for IT review.",
            "owner": "Database / platform owner",
            "status": _score_status(report, "deployment_evidence"),
            "evidence": ["SQL apply plan", "Apply SQL", "Deployment manifest", "Schema verification dry-run"],
            "acceptance_test": "Buyer IT can review the SQL bundle, checksums, apply order, post-apply verification, and non-mutating dry-run proof.",
        },
        {
            "stage": "live_launch",
            "criterion": "Live launch inputs are supplied through the agreed secret channel.",
            "owner": "Platform admin / customer success",
            "status": "pass" if decisions["live_launch"] == "go" else "blocked",
            "evidence": ["Live readiness", "Live launch request", "Live launch checklist"],
            "acceptance_test": "Supabase URL/keys, fixture passwords, and customer access credentials exist in env/secret manager; no secret values are stored in reports.",
        },
        {
            "stage": "production_rollout",
            "criterion": "Live schema, RLS launch, and customer access are production verified.",
            "owner": "HomePilot operator / IT owner",
            "status": "pass" if decisions["production"] == "go" else "blocked",
            "evidence": ["Production proof", "Live schema verification", "Launch report", "Customer access verification"],
            "acceptance_test": "All live reports show production_verified=true and customer JWT probes pass before paying customer access is enabled.",
        },
    ]
    stage_statuses = {
        stage: "pass" if all(row["status"] == "pass" for row in criteria if row["stage"] == stage) else "blocked"
        for stage in ("buyer_review", "live_launch", "production_rollout")
    }
    return {
        "plan_type": "homepilot_customer_acceptance_plan",
        "created_at": utc_now(),
        "release_label": report["release_label"],
        "status": "buyer_review_ready" if stage_statuses["buyer_review"] == "pass" else "action_required",
        "decisions": decisions,
        "stage_statuses": stage_statuses,
        "criteria": criteria,
        "signoff_roles": [
            {"role": "Executive sponsor", "signs_off": "Buyer-review value story and next-step business case."},
            {"role": "IT/security owner", "signs_off": "Access model, SQL review, live readiness, and RLS/customer-access proof."},
            {"role": "Legal/privacy owner", "signs_off": "Processing register, public-data caveats, retention, and contact-basis controls."},
            {"role": "Customer success owner", "signs_off": "Invitees, partner cutdowns, launch checklist, and training/handoff readiness."},
        ],
        "guardrails": {
            "synthetic_demo_not_live_performance": True,
            "no_homeowner_intent_without_response": True,
            "production_requires_live_proof": True,
            "secrets_written": bool(report["summary"].get("secrets_written")),
        },
    }


def render_acceptance_plan_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Customer Acceptance Plan",
        "",
        f"Release: {plan['release_label']}",
        f"Created: {plan['created_at']}",
        f"Status: {plan['status']}",
        "",
        "## Stage Decisions",
        "",
    ]
    for stage, status in plan["stage_statuses"].items():
        lines.append(f"- {stage}: {status}")
    lines += [
        "",
        "## Acceptance Criteria",
        "",
        "| Stage | Status | Owner | Criterion | Acceptance Test | Evidence |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in plan["criteria"]:
        evidence = ", ".join(row["evidence"])
        lines.append(f"| {row['stage']} | {row['status']} | {row['owner']} | {row['criterion']} | {row['acceptance_test']} | {evidence} |")
    lines += [
        "",
        "## Signoff Roles",
        "",
    ]
    for role in plan["signoff_roles"]:
        lines.append(f"- {role['role']}: {role['signs_off']}")
    lines += [
        "",
        "## Guardrails",
        "",
        "- Synthetic demo metrics are not live customer performance.",
        "- A scored property is an opportunity signal, not homeowner purchase intent.",
        "- Public-data enrichment must stay in the source-run/geography/public-feature/property-enrichment layer until licence, allowed use, attribution, and provenance are approved.",
        "- Production remains no-go until live schema, RLS launch, and customer access verification all pass with production_verified=true.",
        "- Secret values must stay in environment variables or a secret manager, never in the acceptance pack.",
        "",
    ]
    return "\n".join(lines)


def _write_acceptance_csv(path: Path, criteria: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["stage", "status", "owner", "criterion", "acceptance_test", "evidence"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in criteria:
            writer.writerow({
                "stage": row["stage"],
                "status": row["status"],
                "owner": row["owner"],
                "criterion": row["criterion"],
                "acceptance_test": row["acceptance_test"],
                "evidence": "; ".join(row["evidence"]),
            })


def build_customer_rollout_plan(report: dict[str, Any]) -> dict[str, Any]:
    acceptance = report["customer_acceptance_plan"]
    stage_statuses = acceptance["stage_statuses"]
    decisions = report["decisions"]
    buyer_status = stage_statuses.get("buyer_review", "blocked")
    live_status = stage_statuses.get("live_launch", "blocked")
    production_status = stage_statuses.get("production_rollout", "blocked")
    first_campaign_status = "ready" if production_status == "pass" else "blocked"
    optimization_status = "ready" if production_status == "pass" else "blocked"
    workstreams = [
        {
            "stage": "buyer_review",
            "workstream": "Executive alignment and commercial scope",
            "status": buyer_status,
            "accountable": "Executive sponsor / sales lead",
            "customer_input": "Confirm modules, regions, partner network shape, success definition, and demo audience.",
            "homepilot_action": "Walk through the boardroom data room, scorecard, acceptance plan, partner cutdowns, and production caveats.",
            "evidence": ["homepilot_boardroom_data_room.zip", "MARKET_READINESS_SCORECARD.md", "CUSTOMER_ACCEPTANCE_PLAN.md"],
        },
        {
            "stage": "buyer_review",
            "workstream": "Legal, privacy, and contact-basis review",
            "status": buyer_status,
            "accountable": "Legal/privacy owner",
            "customer_input": "Confirm lawful campaign basis, retention expectations, public-data appetite, and blocked data categories.",
            "homepilot_action": "Review processing register, data dictionary, source ledger, redaction status, and homeowner-intent wording guardrails.",
            "evidence": ["PROCESSING_REGISTER.md", "DATA_DICTIONARY.md", "SOURCE_LEDGER.md"],
        },
        {
            "stage": "live_launch",
            "workstream": "IT and Supabase launch inputs",
            "status": live_status,
            "accountable": "IT/security owner",
            "customer_input": "Supply Supabase/project credentials, fixture credentials, and planned customer-access test users through the agreed secret channel.",
            "homepilot_action": "Run live readiness, SQL review, schema verification, live launch/RLS fixture, and customer access probes.",
            "evidence": ["LIVE_LAUNCH_REQUEST.md", "LIVE_LAUNCH_CHECKLIST.csv", "SQL_APPLY_PLAN.md"],
        },
        {
            "stage": "live_launch",
            "workstream": "Producer and partner access model",
            "status": live_status,
            "accountable": "Customer success owner / partner manager",
            "customer_input": "Confirm DAW producer users, partner renovator list, partner territories, invitees, and role names.",
            "homepilot_action": "Create tenant-wide producer access and partner-scoped access; verify each partner sees only assigned records.",
            "evidence": ["ACCOUNT_ACCESS_PLAN.md", "CUSTOMER_ACCESS_VERIFICATION.md", "partner_cutdown_manifest.json"],
        },
        {
            "stage": "production_rollout",
            "workstream": "Production proof archive",
            "status": production_status,
            "accountable": "HomePilot operator / IT owner",
            "customer_input": "Approve evidence archive location and fixture cleanup timing after live proof is captured.",
            "homepilot_action": "Archive production proof, schema verification, launch/RLS, customer access, cleanup plan, and release audit.",
            "evidence": ["PRODUCTION_PROOF.md", "schema_verification.json", "launch_report.json", "customer_access_verification.json"],
        },
        {
            "stage": "first_campaign",
            "workstream": "Campaign operations and partner handoff",
            "status": first_campaign_status,
            "accountable": "Customer success owner / campaign owner",
            "customer_input": "Confirm first campaign batch, message variants, partner assignment, capacity limits, and follow-up SLA.",
            "homepilot_action": "Publish scoped dashboards/exports, partner cutdowns, response ledger, no-response backlog, and next-action queues.",
            "evidence": ["BOARDROOM_REPORT.md", "TERRITORY_PLAN.md", "CAMPAIGN_LEARNING.md", "ROI_FORECAST.md"],
        },
        {
            "stage": "optimization",
            "workstream": "Learning loop and expansion plan",
            "status": optimization_status,
            "accountable": "Executive sponsor / customer success owner",
            "customer_input": "Review campaign outcomes, objection patterns, partner performance, and next-region/module appetite.",
            "homepilot_action": "Run response analysis, benchmark-safe summaries, source-refresh checks, and next-wave opportunity ranking.",
            "evidence": ["CAMPAIGN_LEARNING.md", "market_readiness_actions.csv", "MONITORING_RUNBOOK.md"],
        },
    ]
    raci = [
        {
            "role": "Executive sponsor",
            "responsible_for": "Business case, budget, go/no-go escalation, and 30/60/90-day value review.",
            "buyer_review": "A",
            "live_launch": "C",
            "production_rollout": "C",
            "first_campaign": "A",
        },
        {
            "role": "IT/security owner",
            "responsible_for": "Supabase review, credential channel, SQL apply approval, RLS/customer-access proof, and evidence archive.",
            "buyer_review": "C",
            "live_launch": "A",
            "production_rollout": "A",
            "first_campaign": "C",
        },
        {
            "role": "Legal/privacy owner",
            "responsible_for": "Processing register, contact basis, public-data licence boundaries, retention, and wording guardrails.",
            "buyer_review": "A",
            "live_launch": "C",
            "production_rollout": "C",
            "first_campaign": "C",
        },
        {
            "role": "Customer success owner",
            "responsible_for": "Invitees, training, partner onboarding, first campaign rhythm, and customer-facing support.",
            "buyer_review": "R",
            "live_launch": "R",
            "production_rollout": "R",
            "first_campaign": "A",
        },
        {
            "role": "HomePilot operator",
            "responsible_for": "Evidence pack generation, live verification commands, rollout artifact updates, and technical support.",
            "buyer_review": "R",
            "live_launch": "R",
            "production_rollout": "R",
            "first_campaign": "R",
        },
        {
            "role": "Partner manager",
            "responsible_for": "Partner list, territory assignment, partner-scoped training, and partner feedback loop.",
            "buyer_review": "C",
            "live_launch": "C",
            "production_rollout": "I",
            "first_campaign": "R",
        },
    ]
    training = [
        {
            "module": "Boardroom data-room walkthrough",
            "audience": "DAW leadership, sales, procurement",
            "outcome": "Can explain buyer-ready evidence, live blockers, and why synthetic demo metrics are not production claims.",
        },
        {
            "module": "Tenant, module, and partner scoping",
            "audience": "IT/security, customer success, partner manager",
            "outcome": "Can explain what DAW sees, what each renovator sees, and how WindowPilot/FacadePilot-style module access is separated.",
        },
        {
            "module": "Partner cutdown workflow",
            "audience": "Partner manager, customer success",
            "outcome": "Can generate, inspect, and share partner-scoped packages without cross-partner leakage.",
        },
        {
            "module": "Campaign operations and response memory",
            "audience": "Sales/campaign operators",
            "outcome": "Can use contact status, response, no-response backlog, objections, next actions, and exports without calling scores purchase intent.",
        },
        {
            "module": "Live launch evidence and support",
            "audience": "IT/security, HomePilot operator",
            "outcome": "Can run or review live readiness, schema verification, RLS/customer-access probes, production proof, and cleanup archive.",
        },
    ]
    success_plan = [
        {
            "horizon": "30_days",
            "goal": "Complete buyer review and live-launch intake.",
            "measures": ["Signed module/partner scope", "Live inputs supplied through secret channel", "Training plan accepted"],
            "exit_condition": "Live readiness can run without missing input tasks.",
        },
        {
            "horizon": "60_days",
            "goal": "Complete production proof and first campaign setup.",
            "measures": ["Live schema verification pass", "RLS/customer-access proof pass", "Partner invitees verified", "First campaign batch approved"],
            "exit_condition": "Production proof is archived with production_verified=true before customer access is enabled.",
        },
        {
            "horizon": "90_days",
            "goal": "Run first learning loop and decide expansion.",
            "measures": ["Response rate reported with denominator", "No-response backlog reviewed", "Partner performance review complete", "Next module/territory shortlist agreed"],
            "exit_condition": "DAW/customer sees what worked, what did not respond, and which next campaign is recommended.",
        },
    ]
    return {
        "plan_type": "homepilot_customer_rollout_plan",
        "created_at": utc_now(),
        "release_label": report["release_label"],
        "status": "buyer_review_ready" if buyer_status == "pass" else "action_required",
        "decisions": decisions,
        "stage_statuses": {
            "buyer_review": buyer_status,
            "live_launch": live_status,
            "production_rollout": production_status,
            "first_campaign": first_campaign_status,
            "optimization": optimization_status,
        },
        "workstreams": workstreams,
        "raci": raci,
        "training": training,
        "success_plan": success_plan,
        "guardrails": {
            "tenant_module_partner_scope_required": True,
            "partner_packages_assigned_records_only": True,
            "synthetic_demo_not_live_performance": True,
            "production_requires_live_proof": True,
            "public_data_requires_dataset_level_licence_review": True,
        },
    }


def render_customer_rollout_plan_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Customer Rollout Plan",
        "",
        f"Release: {plan['release_label']}",
        f"Created: {plan['created_at']}",
        f"Status: {plan['status']}",
        "",
        "## Stage Status",
        "",
    ]
    for stage, status in plan["stage_statuses"].items():
        lines.append(f"- {stage}: {status}")
    lines += [
        "",
        "## Workstreams",
        "",
        "| Stage | Status | Accountable | Workstream | Customer Input | HomePilot Action | Evidence |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in plan["workstreams"]:
        lines.append(
            f"| {row['stage']} | {row['status']} | {row['accountable']} | {row['workstream']} | "
            f"{row['customer_input']} | {row['homepilot_action']} | {', '.join(row['evidence'])} |"
        )
    lines += [
        "",
        "## RACI",
        "",
        "R = responsible, A = accountable, C = consulted, I = informed.",
        "",
        "| Role | Buyer Review | Live Launch | Production Rollout | First Campaign | Responsibility |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in plan["raci"]:
        lines.append(
            f"| {row['role']} | {row['buyer_review']} | {row['live_launch']} | {row['production_rollout']} | "
            f"{row['first_campaign']} | {row['responsible_for']} |"
        )
    lines += [
        "",
        "## Training",
        "",
        "| Module | Audience | Outcome |",
        "| --- | --- | --- |",
    ]
    for row in plan["training"]:
        lines.append(f"| {row['module']} | {row['audience']} | {row['outcome']} |")
    lines += [
        "",
        "## 30/60/90-Day Success Plan",
        "",
        "| Horizon | Goal | Measures | Exit Condition |",
        "| --- | --- | --- | --- |",
    ]
    for row in plan["success_plan"]:
        lines.append(f"| {row['horizon']} | {row['goal']} | {', '.join(row['measures'])} | {row['exit_condition']} |")
    lines += [
        "",
        "## Guardrails",
        "",
        "- Every customer-visible workflow must preserve tenant, module, partner, and campaign scope.",
        "- Partner packages and partner users must see assigned records only.",
        "- Synthetic demo metrics are not live customer performance.",
        "- Production remains no-go until live schema, RLS launch, and customer access verification all pass with production_verified=true.",
        "- Public-data enrichment requires dataset-level licence review before production import.",
        "",
    ]
    return "\n".join(lines)


def _write_rollout_csv(path: Path, workstreams: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["stage", "status", "accountable", "workstream", "customer_input", "homepilot_action", "evidence"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in workstreams:
            writer.writerow({
                "stage": row["stage"],
                "status": row["status"],
                "accountable": row["accountable"],
                "workstream": row["workstream"],
                "customer_input": row["customer_input"],
                "homepilot_action": row["homepilot_action"],
                "evidence": "; ".join(row["evidence"]),
            })


def build_first_campaign_launch_intake(report: dict[str, Any]) -> dict[str, Any]:
    stage_statuses = report["customer_rollout_plan"]["stage_statuses"]
    live_status = stage_statuses.get("live_launch", "blocked")
    production_status = stage_statuses.get("production_rollout", "blocked")
    first_campaign_status = "ready" if production_status == "pass" else "blocked"
    launch_decision = (
        "ready_for_first_wave"
        if first_campaign_status == "ready"
        else "blocked_until_customer_inputs_and_live_proof"
    )
    input_requirements = [
        {
            "stage": "scope",
            "owner": "Executive sponsor / DAW network manager",
            "input": "Campaign scope and success definition",
            "required_detail": "Initial module, regions, partner count, target volume, response-rate denominator, appointment target, and success-review date.",
            "homepilot_use": "Locks dashboard filters, boardroom KPIs, value-realization metrics, and first-wave go/no-go criteria.",
            "evidence": "CUSTOMER_VALUE_REALIZATION_PLAN.md; EXECUTIVE_DECISION_LOG.csv; CUSTOMER_PILOT_PROPOSAL.md",
            "status": "pending_customer_confirmation",
        },
        {
            "stage": "partner_network",
            "owner": "Partner manager",
            "input": "Partner renovator roster",
            "required_detail": "Partner id, company name, region/cities, contact owner, invitees, role, capacity, service area, language, and escalation contact.",
            "homepilot_use": "Creates partner scope, partner cutdowns, partner dashboards, access verification rows, and territory assignment.",
            "evidence": "ACCOUNT_ACCESS_PLAN.md; partner_cutdown_manifest.json; CUSTOMER_ACCESS_VERIFICATION.md",
            "status": "pending_customer_file",
        },
        {
            "stage": "territory",
            "owner": "DAW network manager / analyst",
            "input": "Territory and assignment rules",
            "required_detail": "Postcodes/cities/regions per partner, exclusions, capacity caps, overlap rules, and fallback owner for unassigned opportunities.",
            "homepilot_use": "Prevents partner leakage and makes partner comparisons fair by assigned territory and capacity.",
            "evidence": "TERRITORY_PLAN.md; partner_summary.csv; ROLLOUT_WORKSTREAMS.csv",
            "status": "pending_customer_file",
        },
        {
            "stage": "source_data",
            "owner": "Customer data owner / HomePilot operator",
            "input": "Approved property/import source",
            "required_detail": "Tenant-scoped property source, address columns, source provenance, refresh date, dedupe rule, import owner, and allowed modules.",
            "homepilot_use": "Builds the property spine, source ledger, import audit, enrichment backlog, and Excel export rows.",
            "evidence": "SOURCE_LEDGER.md; DATA_VENDOR_PLAN.md; DATA_DICTIONARY.md",
            "status": "pending_customer_file",
        },
        {
            "stage": "contact_basis",
            "owner": "Legal/privacy owner",
            "input": "Contact basis and suppression rules",
            "required_detail": "Lawful contact basis, approved channels, opt-out method, suppression/do-not-contact list, retention review date, and claim language.",
            "homepilot_use": "Blocks unsafe outreach rows and proves that scores are opportunity signals, not homeowner intent claims.",
            "evidence": "PROCESSING_REGISTER.md; compliance_audit.json; retention_report.json",
            "status": "pending_legal_review",
        },
        {
            "stage": "message",
            "owner": "DAW marketing owner / legal/privacy owner",
            "input": "Message variants and offer approval",
            "required_detail": "Language variants, partner co-branding, claims, disclaimers, CTA, unsubscribe/opt-out wording, and response routing.",
            "homepilot_use": "Connects campaign response and objections to message variants without unsafe intent language.",
            "evidence": "CAMPAIGN_LEARNING.md; CUSTOMER_TRAINING_GUIDE.md; PROCESSING_REGISTER.md",
            "status": "pending_customer_approval",
        },
        {
            "stage": "channel_ops",
            "owner": "Campaign operations owner",
            "input": "Sender/channel and response handling",
            "required_detail": "Direct mail/email/call channel owner, sender identity, reply inbox or phone flow, CRM status mapping, SLA, and escalation path.",
            "homepilot_use": "Turns responses into interaction rows, no-response backlog, appointments, and partner work queues.",
            "evidence": "INTEGRATION_RUNBOOK.md; SYNC_RUNBOOK.md; SUPPORT_ESCALATION_MATRIX.csv",
            "status": "pending_customer_approval",
        },
        {
            "stage": "partner_ops",
            "owner": "Partner manager / partner renovators",
            "input": "Partner capacity and follow-up SLA",
            "required_detail": "Weekly appointment capacity, lead acceptance rules, response SLA, rejected-reason taxonomy, and partner feedback cadence.",
            "homepilot_use": "Keeps partner performance readable and avoids assigning more opportunities than partners can follow up.",
            "evidence": "ROLE_CHEATSHEET.csv; TRAINING_SESSION_PLAN.csv; SUPPORT_SLA_PLAN.md",
            "status": "pending_partner_confirmation",
        },
        {
            "stage": "live_access",
            "owner": "IT/security owner / Supabase owner",
            "input": "Live portal and access proof",
            "required_detail": "Supabase/project credentials, customer test users, partner-scoped test users, live schema verification, RLS probe, and customer access verification.",
            "homepilot_use": "Proves DAW sees the network view and each partner sees only assigned records before live use.",
            "evidence": "LIVE_LAUNCH_REQUEST.md; schema_verification.json; launch_report.json; customer_access_verification.json",
            "status": live_status,
        },
        {
            "stage": "first_wave_go_no_go",
            "owner": "Executive sponsor / HomePilot operator",
            "input": "First-wave launch decision",
            "required_detail": "Approved batch size, partner assignment, suppression applied, message approved, live proof archived, support owner assigned, and rollback/pause rule agreed.",
            "homepilot_use": "Allows first live campaign batch to start with auditable scope and a clear pause rule.",
            "evidence": "PRODUCTION_PROOF.md; FIRST_CAMPAIGN_LAUNCH_INTAKE.md; FIRST_CAMPAIGN_LAUNCH_CHECKLIST.csv",
            "status": first_campaign_status,
        },
    ]
    partner_roster_fields = [
        "partner_id",
        "partner_name",
        "legal_company_name",
        "region",
        "cities_or_postcodes",
        "language",
        "capacity_per_month",
        "service_categories",
        "primary_contact_name",
        "primary_contact_email_or_secret_channel_ref",
        "portal_role",
        "escalation_owner",
    ]
    wave_plan = [
        {
            "wave": "wave_0_internal_rehearsal",
            "status": "ready_after_buyer_review",
            "batch_size": "synthetic/demo only",
            "purpose": "Use the DAW demo and partner cutdowns to rehearse boardroom story, access boundaries, and partner handoff.",
            "exit_gate": "Stakeholders can explain what is synthetic, what is live-blocked, and what evidence is needed next.",
        },
        {
            "wave": "wave_1_live_smoke",
            "status": "blocked_until_live_proof",
            "batch_size": "operator/customer-approved fixture or tiny customer-approved sample",
            "purpose": "Verify live schema, RLS, customer access, import/source provenance, suppression, and export controls.",
            "exit_gate": "Production proof has production_verified=true and no partner leakage findings.",
        },
        {
            "wave": "wave_2_first_campaign",
            "status": "blocked_until_first_wave_go",
            "batch_size": "customer-approved first batch by partner capacity",
            "purpose": "Start first DAW campaign with approved channels, message variants, partner assignments, and support owner.",
            "exit_gate": "Response, no-response, appointment, objection, and partner follow-up metrics are visible with denominator labels.",
        },
        {
            "wave": "wave_3_scale_decision",
            "status": "blocked_until_learning_review",
            "batch_size": "next territory or partner wave",
            "purpose": "Use campaign learning and partner performance to decide scale, pause, or module expansion.",
            "exit_gate": "Executive decision log records scale/repeat/pause decision and next approved module or territory.",
        },
    ]
    go_no_go_gates = [
        {
            "gate": "tenant_module_partner_scope",
            "owner": "IT/security owner",
            "required_evidence": "Tenant/module entitlements, partner roster, live RLS probe, customer access verification.",
            "decision": "blocked_until_live_proof",
        },
        {
            "gate": "contact_basis_and_suppression",
            "owner": "Legal/privacy owner",
            "required_evidence": "Contact basis, source provenance, opt-out method, suppression list applied, retention metadata.",
            "decision": "blocked_until_legal_review",
        },
        {
            "gate": "message_and_claim_approval",
            "owner": "DAW marketing owner + legal/privacy owner",
            "required_evidence": "Approved message variants, CTA, disclaimers, language versions, no unproven homeowner-intent wording.",
            "decision": "blocked_until_customer_approval",
        },
        {
            "gate": "partner_capacity_and_follow_up",
            "owner": "Partner manager",
            "required_evidence": "Capacity per partner, SLA, response routing, rejected-reason taxonomy, escalation owner.",
            "decision": "blocked_until_partner_confirmation",
        },
        {
            "gate": "public_data_and_source_provenance",
            "owner": "Data owner + legal/privacy owner",
            "required_evidence": "Approved property source, source ledger, public-data approvals if used, field allowlists, provenance badges.",
            "decision": "blocked_until_source_approval",
        },
        {
            "gate": "support_and_pause_rule",
            "owner": "Customer success owner / HomePilot operator",
            "required_evidence": "Support owner, incident path, pause/rollback rule, daily first-wave check rhythm.",
            "decision": "blocked_until_owner_assigned",
        },
    ]
    return {
        "intake_type": "homepilot_first_campaign_launch_intake",
        "created_at": utc_now(),
        "release_label": report["release_label"],
        "status": "first_campaign_inputs_required",
        "launch_decision": launch_decision,
        "scenario": {
            "default_customer": "DAW producer network",
            "initial_module": "facadepilot",
            "expected_partner_renovators": 10,
            "tenant_module_partner_scope_required": True,
        },
        "summary": {
            "input_requirements": len(input_requirements),
            "partner_roster_fields": len(partner_roster_fields),
            "go_no_go_gates": len(go_no_go_gates),
            "wave_count": len(wave_plan),
            "live_status": live_status,
            "production_status": production_status,
            "first_campaign_status": first_campaign_status,
        },
        "input_requirements": input_requirements,
        "partner_roster_template_fields": partner_roster_fields,
        "wave_plan": wave_plan,
        "go_no_go_gates": go_no_go_gates,
        "guardrails": {
            "scores_are_opportunity_signals_not_intent": True,
            "contact_basis_required_before_outreach": True,
            "suppression_list_required_before_outreach": True,
            "partner_scope_required_before_partner_access": True,
            "message_claims_require_customer_approval": True,
            "public_data_imports_require_dataset_approval": True,
            "live_proof_required_before_customer_access": True,
        },
    }


def render_first_campaign_launch_intake_markdown(intake: dict[str, Any]) -> str:
    lines = [
        "# HomePilot First Campaign Launch Intake",
        "",
        f"Release: {intake['release_label']}",
        f"Created: {intake['created_at']}",
        f"Status: {intake['status']}",
        f"Launch decision: {intake['launch_decision']}",
        "",
        "This intake is the bridge from an impressive buyer demo to a controlled first live campaign.",
        "It lists the customer files, approvals, owners, and live-proof gates needed before DAW or another enterprise customer starts outreach.",
        "",
        "## Scenario",
        "",
    ]
    for key, value in intake["scenario"].items():
        lines.append(f"- {key}: {value}")
    lines += [
        "",
        "## Input Requirements",
        "",
        "| Stage | Owner | Input | Required Detail | Status |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in intake["input_requirements"]:
        lines.append(
            f"| {row['stage']} | {row['owner']} | {row['input']} | "
            f"{row['required_detail']} | {row['status']} |"
        )
    lines += [
        "",
        "## Partner Roster Template Fields",
        "",
    ]
    lines.extend(f"- `{field}`" for field in intake["partner_roster_template_fields"])
    lines += [
        "",
        "## Wave Plan",
        "",
        "| Wave | Status | Batch Size | Purpose | Exit Gate |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in intake["wave_plan"]:
        lines.append(f"| {row['wave']} | {row['status']} | {row['batch_size']} | {row['purpose']} | {row['exit_gate']} |")
    lines += [
        "",
        "## Go/No-Go Gates",
        "",
        "| Gate | Owner | Required Evidence | Decision |",
        "| --- | --- | --- | --- |",
    ]
    for row in intake["go_no_go_gates"]:
        lines.append(f"| {row['gate']} | {row['owner']} | {row['required_evidence']} | {row['decision']} |")
    lines += [
        "",
        "## Guardrails",
        "",
        "- Scores are opportunity signals, not homeowner purchase intent.",
        "- Contact basis, opt-out method, suppression handling, and retention metadata are required before outreach.",
        "- Partner access is blocked until partner scope and live RLS/customer-access proof are complete.",
        "- Message variants and claims need DAW/customer approval before campaign use.",
        "- Public-data enrichment can inform the campaign only after dataset-level approvals.",
        "- First-wave launch remains blocked until live proof and customer go/no-go are archived.",
        "",
    ]
    return "\n".join(lines)


def _write_first_campaign_checklist_csv(path: Path, requirements: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["stage", "owner", "input", "required_detail", "homepilot_use", "evidence", "status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in requirements:
            writer.writerow({field: row.get(field, "") for field in fields})


def build_customer_input_template_pack(report: dict[str, Any]) -> dict[str, Any]:
    first_campaign = report["first_campaign_launch_intake"]
    templates = [
        {
            "key": "partner_roster_template",
            "file_name": "PARTNER_ROSTER_TEMPLATE.csv",
            "label": "Partner roster template",
            "purpose": "Collect DAW renovator identities, regions, capacity, roles, and secure invite/contact references before partner-scoped access is created.",
            "owner": "Partner manager",
            "required_before": "partner_access_setup",
            "fields": [
                "partner_id",
                "partner_name",
                "legal_company_name",
                "region",
                "cities_or_postcodes",
                "language",
                "capacity_per_month",
                "service_categories",
                "primary_contact_name",
                "primary_contact_email_or_secret_channel_ref",
                "portal_role",
                "escalation_owner",
                "partner_scope_notes",
                "status",
            ],
            "sample_rows": [
                {
                    "partner_id": "renotec-antwerp",
                    "partner_name": "Renotec Gevelwerken",
                    "legal_company_name": "customer_to_confirm",
                    "region": "Antwerp",
                    "cities_or_postcodes": "Antwerpen; Mechelen; Lier",
                    "language": "nl",
                    "capacity_per_month": "220",
                    "service_categories": "facade insulation; crepi",
                    "primary_contact_name": "secure_channel_reference_only",
                    "primary_contact_email_or_secret_channel_ref": "secret://daw/partner/renotec-antwerp/contact",
                    "portal_role": "partner_renovator",
                    "escalation_owner": "DAW partner manager",
                    "partner_scope_notes": "assigned_records_only",
                    "status": "draft",
                }
            ],
        },
        {
            "key": "territory_assignment_template",
            "file_name": "TERRITORY_ASSIGNMENT_TEMPLATE.csv",
            "label": "Territory assignment template",
            "purpose": "Define which partner owns which cities, postcodes, exclusions, fallback rules, and capacity caps.",
            "owner": "DAW network manager / analyst",
            "required_before": "first_campaign_batch_selection",
            "fields": [
                "partner_id",
                "region",
                "cities_or_postcodes",
                "included_postcodes",
                "excluded_postcodes",
                "capacity_cap",
                "overlap_rule",
                "fallback_owner",
                "assignment_priority",
                "notes",
                "status",
            ],
            "sample_rows": [
                {
                    "partner_id": "renotec-antwerp",
                    "region": "Antwerp",
                    "cities_or_postcodes": "Antwerpen; Mechelen; Lier",
                    "included_postcodes": "2000-2990",
                    "excluded_postcodes": "customer_to_confirm",
                    "capacity_cap": "220",
                    "overlap_rule": "nearest_partner_then_capacity",
                    "fallback_owner": "DAW network manager",
                    "assignment_priority": "1",
                    "notes": "demo values; customer to confirm",
                    "status": "draft",
                }
            ],
        },
        {
            "key": "property_source_template",
            "file_name": "PROPERTY_SOURCE_TEMPLATE.csv",
            "label": "Property source template",
            "purpose": "Document the tenant-scoped source file or system used to build the property spine and exportable source ledger.",
            "owner": "Customer data owner / HomePilot operator",
            "required_before": "customer_import",
            "fields": [
                "source_file_name",
                "source_owner",
                "tenant_id",
                "module_key",
                "allowed_modules",
                "address_column",
                "postcode_column",
                "city_column",
                "source_provenance",
                "refresh_date",
                "dedupe_rule",
                "public_data_used",
                "contact_basis_source",
                "import_status",
            ],
            "sample_rows": [
                {
                    "source_file_name": "daw_facadepilot_wave1_properties.csv",
                    "source_owner": "DAW data owner",
                    "tenant_id": "daw-belgium",
                    "module_key": "facadepilot",
                    "allowed_modules": "facadepilot",
                    "address_column": "address",
                    "postcode_column": "postcode",
                    "city_column": "city",
                    "source_provenance": "customer-approved property list",
                    "refresh_date": "2026-07-01",
                    "dedupe_rule": "normalized_address_postcode_city",
                    "public_data_used": "none_until_approved",
                    "contact_basis_source": "separate legal review",
                    "import_status": "pending_customer_file",
                }
            ],
        },
        {
            "key": "suppression_list_template",
            "file_name": "SUPPRESSION_LIST_TEMPLATE.csv",
            "label": "Suppression list template",
            "purpose": "Capture opt-outs, do-not-contact rules, exclusions, wrong-address feedback, and retention dates before outreach.",
            "owner": "Legal/privacy owner",
            "required_before": "outreach",
            "fields": [
                "suppression_id",
                "source_owner",
                "match_type",
                "property_or_hash_reference",
                "postcode",
                "city",
                "module_key",
                "reason",
                "opt_out_method",
                "effective_from",
                "delete_after",
                "notes",
            ],
            "sample_rows": [
                {
                    "suppression_id": "sup-001",
                    "source_owner": "DAW legal/privacy owner",
                    "match_type": "property_id_or_hash",
                    "property_or_hash_reference": "hash_or_customer_property_id",
                    "postcode": "customer_to_confirm",
                    "city": "customer_to_confirm",
                    "module_key": "facadepilot",
                    "reason": "do_not_contact",
                    "opt_out_method": "customer suppression workflow",
                    "effective_from": "2026-07-01",
                    "delete_after": "2027-07-01",
                    "notes": "do not include raw personal contact data in the data room",
                }
            ],
        },
        {
            "key": "message_approval_template",
            "file_name": "MESSAGE_APPROVAL_TEMPLATE.csv",
            "label": "Message approval template",
            "purpose": "Approve campaign variants, claims, CTAs, opt-out wording, languages, and partner co-branding before first-wave use.",
            "owner": "DAW marketing owner + legal/privacy owner",
            "required_before": "message_send",
            "fields": [
                "message_variant",
                "language",
                "module_key",
                "channel",
                "partner_branding_allowed",
                "claim_summary",
                "prohibited_claims_checked",
                "cta",
                "opt_out_wording",
                "marketing_owner",
                "legal_owner",
                "approval_status",
                "approved_at",
                "notes",
            ],
            "sample_rows": [
                {
                    "message_variant": "energy_savings",
                    "language": "nl",
                    "module_key": "facadepilot",
                    "channel": "direct_mail",
                    "partner_branding_allowed": "yes_after_partner_approval",
                    "claim_summary": "opportunity for facade insulation review",
                    "prohibited_claims_checked": "no homeowner intent; no guaranteed savings",
                    "cta": "book consult or request more info",
                    "opt_out_wording": "customer-approved opt-out text",
                    "marketing_owner": "DAW marketing owner",
                    "legal_owner": "DAW legal/privacy owner",
                    "approval_status": "pending",
                    "approved_at": "",
                    "notes": "use opportunity language only",
                }
            ],
        },
        {
            "key": "partner_capacity_template",
            "file_name": "PARTNER_CAPACITY_TEMPLATE.csv",
            "label": "Partner capacity and follow-up template",
            "purpose": "Confirm each partner's monthly capacity, follow-up SLA, appointment slots, rejection taxonomy, and escalation path.",
            "owner": "Partner manager / partner renovators",
            "required_before": "first_wave_assignment",
            "fields": [
                "partner_id",
                "capacity_per_month",
                "appointment_slots_per_week",
                "response_sla_hours",
                "accepted_statuses",
                "rejection_reasons_allowed",
                "feedback_cadence",
                "escalation_owner",
                "capacity_status",
                "notes",
            ],
            "sample_rows": [
                {
                    "partner_id": "renotec-antwerp",
                    "capacity_per_month": "220",
                    "appointment_slots_per_week": "12",
                    "response_sla_hours": "24",
                    "accepted_statuses": "responded; appointment; customer",
                    "rejection_reasons_allowed": "out_of_area; no_capacity; duplicate; customer_unreachable",
                    "feedback_cadence": "weekly",
                    "escalation_owner": "DAW partner manager",
                    "capacity_status": "pending_partner_confirmation",
                    "notes": "do not over-assign beyond confirmed capacity",
                }
            ],
        },
    ]
    return {
        "pack_type": "homepilot_customer_input_template_pack",
        "created_at": utc_now(),
        "release_label": report["release_label"],
        "status": "ready_for_customer_input",
        "source_intake": first_campaign["intake_type"],
        "launch_decision": first_campaign["launch_decision"],
        "templates": templates,
        "summary": {
            "template_count": len(templates),
            "total_fields": sum(len(template["fields"]) for template in templates),
            "first_campaign_inputs_required": len(first_campaign["input_requirements"]),
        },
        "guardrails": {
            "templates_are_not_customer_approval": True,
            "no_secret_values_in_templates": True,
            "no_raw_personal_contact_data_required": True,
            "contact_basis_required_before_outreach": True,
            "partner_scope_required_before_partner_access": True,
            "live_proof_required_before_customer_access": True,
        },
    }


def render_customer_input_templates_markdown(pack: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Customer Input Templates",
        "",
        f"Release: {pack['release_label']}",
        f"Created: {pack['created_at']}",
        f"Status: {pack['status']}",
        f"Launch decision: {pack['launch_decision']}",
        "",
        "These CSV templates let DAW or another enterprise customer provide the operational inputs needed for the first controlled campaign wave.",
        "They are templates only: campaign launch still requires customer approval, contact-basis review, suppression, partner scope, and live proof.",
        "",
        "## Templates",
        "",
        "| File | Owner | Required Before | Purpose |",
        "| --- | --- | --- | --- |",
    ]
    for template in pack["templates"]:
        lines.append(
            f"| `{template['file_name']}` | {template['owner']} | "
            f"{template['required_before']} | {template['purpose']} |"
        )
    lines += [
        "",
        "## Field Catalog",
        "",
    ]
    for template in pack["templates"]:
        lines += [
            f"### {template['label']}",
            "",
        ]
        lines.extend(f"- `{field}`" for field in template["fields"])
        lines.append("")
    lines += [
        "## Guardrails",
        "",
        "- Templates contain placeholders only and must not store real secret values.",
        "- Raw personal contact details should stay in the customer's approved system or secret channel, not in the portable data room.",
        "- Contact basis, opt-out method, suppression handling, and retention metadata are required before outreach.",
        "- Partner access remains blocked until partner scope and live RLS/customer-access proof are complete.",
        "- First-wave launch remains blocked until the customer signs off the completed templates and live proof.",
        "",
    ]
    return "\n".join(lines)


def _write_customer_template_csv(path: Path, template: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = template["fields"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in template["sample_rows"]:
            writer.writerow({field: row.get(field, "") for field in fields})


def _example_partner_specs() -> list[dict[str, Any]]:
    return [
        {
            "id": "daw-partner-01",
            "name": "Demo Gevelrenovator 01",
            "company": "Synthetic Demo Partner 01 BV",
            "region": "Antwerp",
            "cities": "Antwerpen; Mechelen; Lier",
            "postcodes": "2000-2099",
            "language": "nl",
            "capacity": 90,
            "slots": 8,
        },
        {
            "id": "daw-partner-02",
            "name": "Demo Gevelrenovator 02",
            "company": "Synthetic Demo Partner 02 BV",
            "region": "Flemish Brabant",
            "cities": "Leuven; Aarschot; Tienen",
            "postcodes": "3000-3099",
            "language": "nl",
            "capacity": 85,
            "slots": 7,
        },
        {
            "id": "daw-partner-03",
            "name": "Demo Gevelrenovator 03",
            "company": "Synthetic Demo Partner 03 BV",
            "region": "East Flanders",
            "cities": "Gent; Aalst; Sint-Niklaas",
            "postcodes": "9000-9099",
            "language": "nl",
            "capacity": 100,
            "slots": 9,
        },
        {
            "id": "daw-partner-04",
            "name": "Demo Gevelrenovator 04",
            "company": "Synthetic Demo Partner 04 BV",
            "region": "West Flanders",
            "cities": "Brugge; Kortrijk; Roeselare",
            "postcodes": "8000-8099",
            "language": "nl",
            "capacity": 80,
            "slots": 7,
        },
        {
            "id": "daw-partner-05",
            "name": "Demo Gevelrenovator 05",
            "company": "Synthetic Demo Partner 05 BV",
            "region": "Limburg",
            "cities": "Hasselt; Genk; Sint-Truiden",
            "postcodes": "3500-3599",
            "language": "nl",
            "capacity": 75,
            "slots": 6,
        },
        {
            "id": "daw-partner-06",
            "name": "Demo Gevelrenovator 06",
            "company": "Synthetic Demo Partner 06 SRL",
            "region": "Brussels",
            "cities": "Bruxelles; Anderlecht; Uccle",
            "postcodes": "1000-1099",
            "language": "fr",
            "capacity": 70,
            "slots": 6,
        },
        {
            "id": "daw-partner-07",
            "name": "Demo Gevelrenovator 07",
            "company": "Synthetic Demo Partner 07 SRL",
            "region": "Walloon Brabant",
            "cities": "Wavre; Nivelles; Waterloo",
            "postcodes": "1300-1399",
            "language": "fr",
            "capacity": 72,
            "slots": 6,
        },
        {
            "id": "daw-partner-08",
            "name": "Demo Gevelrenovator 08",
            "company": "Synthetic Demo Partner 08 SRL",
            "region": "Hainaut",
            "cities": "Mons; Charleroi; Tournai",
            "postcodes": "7000-7099",
            "language": "fr",
            "capacity": 95,
            "slots": 8,
        },
        {
            "id": "daw-partner-09",
            "name": "Demo Gevelrenovator 09",
            "company": "Synthetic Demo Partner 09 SRL",
            "region": "Liege",
            "cities": "Liege; Verviers; Huy",
            "postcodes": "4000-4099",
            "language": "fr",
            "capacity": 88,
            "slots": 7,
        },
        {
            "id": "daw-partner-10",
            "name": "Demo Gevelrenovator 10",
            "company": "Synthetic Demo Partner 10 SRL",
            "region": "Namur",
            "cities": "Namur; Dinant; Gembloux",
            "postcodes": "5000-5099",
            "language": "fr",
            "capacity": 78,
            "slots": 6,
        },
    ]


def build_example_completed_customer_inputs(template_pack: dict[str, Any]) -> dict[str, Any]:
    partners = _example_partner_specs()
    rows_by_key: dict[str, list[dict[str, Any]]] = {
        "partner_roster_template": [
            {
                "partner_id": partner["id"],
                "partner_name": partner["name"],
                "legal_company_name": partner["company"],
                "region": partner["region"],
                "cities_or_postcodes": partner["cities"],
                "language": partner["language"],
                "capacity_per_month": str(partner["capacity"]),
                "service_categories": "facade insulation; crepi",
                "primary_contact_name": "secure_channel_reference_only",
                "primary_contact_email_or_secret_channel_ref": f"secret://example/daw/partner/{partner['id']}/contact",
                "portal_role": "partner_renovator",
                "escalation_owner": "DAW partner manager",
                "partner_scope_notes": "assigned_records_only",
                "status": "confirmed",
            }
            for partner in partners
        ],
        "territory_assignment_template": [
            {
                "partner_id": partner["id"],
                "region": partner["region"],
                "cities_or_postcodes": partner["cities"],
                "included_postcodes": partner["postcodes"],
                "excluded_postcodes": "none",
                "capacity_cap": str(partner["capacity"]),
                "overlap_rule": "nearest_partner_then_capacity",
                "fallback_owner": "DAW network manager",
                "assignment_priority": str(index),
                "notes": "synthetic example; customer to replace with approved territory plan",
                "status": "approved",
            }
            for index, partner in enumerate(partners, start=1)
        ],
        "property_source_template": [
            {
                "source_file_name": "synthetic_daw_facadepilot_wave1_properties.csv",
                "source_owner": "DAW data owner",
                "tenant_id": "daw-belgium",
                "module_key": "facadepilot",
                "allowed_modules": "facadepilot",
                "address_column": "address",
                "postcode_column": "postcode",
                "city_column": "city",
                "source_provenance": "synthetic customer-approved property list example",
                "refresh_date": "2026-07-01",
                "dedupe_rule": "normalized_address_postcode_city",
                "public_data_used": "none_until_approved",
                "contact_basis_source": "approved legal review example",
                "import_status": "ready_for_import",
            }
        ],
        "suppression_list_template": [
            {
                "suppression_id": "syn-sup-001",
                "source_owner": "DAW legal/privacy owner",
                "match_type": "hash",
                "property_or_hash_reference": "hash:synthetic_example_do_not_contact_001",
                "postcode": "2000",
                "city": "Antwerpen",
                "module_key": "facadepilot",
                "reason": "do_not_contact",
                "opt_out_method": "customer suppression workflow",
                "effective_from": "2026-07-01",
                "delete_after": "2027-07-01",
                "notes": "synthetic hash-only example; no raw personal contact data",
            }
        ],
        "message_approval_template": [
            {
                "message_variant": "crepi_opportunity_review",
                "language": "nl",
                "module_key": "facadepilot",
                "channel": "direct_mail",
                "partner_branding_allowed": "yes_after_partner_approval",
                "claim_summary": "opportunity for facade insulation review",
                "prohibited_claims_checked": "no homeowner intent; no guaranteed savings",
                "cta": "book consult or request more info",
                "opt_out_wording": "customer-approved opt-out text",
                "marketing_owner": "DAW marketing owner",
                "legal_owner": "DAW legal/privacy owner",
                "approval_status": "approved",
                "approved_at": "2026-07-01T09:00:00+02:00",
                "notes": "synthetic approved example; use opportunity language only",
            },
            {
                "message_variant": "crepi_opportunity_review",
                "language": "fr",
                "module_key": "facadepilot",
                "channel": "direct_mail",
                "partner_branding_allowed": "yes_after_partner_approval",
                "claim_summary": "opportunity for facade insulation review",
                "prohibited_claims_checked": "no homeowner intent; no guaranteed savings",
                "cta": "book consult or request more info",
                "opt_out_wording": "customer-approved opt-out text",
                "marketing_owner": "DAW marketing owner",
                "legal_owner": "DAW legal/privacy owner",
                "approval_status": "approved",
                "approved_at": "2026-07-01T09:15:00+02:00",
                "notes": "synthetic approved example; use opportunity language only",
            },
        ],
        "partner_capacity_template": [
            {
                "partner_id": partner["id"],
                "capacity_per_month": str(partner["capacity"]),
                "appointment_slots_per_week": str(partner["slots"]),
                "response_sla_hours": "24",
                "accepted_statuses": "responded; appointment; customer",
                "rejection_reasons_allowed": "out_of_area; no_capacity; duplicate; customer_unreachable",
                "feedback_cadence": "weekly",
                "escalation_owner": "DAW partner manager",
                "capacity_status": "confirmed",
                "notes": "synthetic confirmed capacity example",
            }
            for partner in partners
        ],
    }
    templates = []
    for template in template_pack["templates"]:
        rows = rows_by_key.get(template["key"], [])
        templates.append({
            "key": template["key"],
            "file_name": template["file_name"],
            "label": template["label"],
            "fields": template["fields"],
            "rows": rows,
            "row_count": len(rows),
        })
    return {
        "pack_type": "homepilot_example_completed_customer_inputs",
        "created_at": utc_now(),
        "release_label": template_pack["release_label"],
        "status": "synthetic_example_ready",
        "example_scope": "DAW producer network, FacadePilot, 10 synthetic partner renovators",
        "summary": {
            "template_count": len(templates),
            "partner_count": len(partners),
            "total_example_rows": sum(template["row_count"] for template in templates),
            "module_key": "facadepilot",
            "tenant_id": "daw-belgium",
        },
        "templates": templates,
        "guardrails": {
            "synthetic_example_only": True,
            "not_customer_approval": True,
            "not_production_data": True,
            "no_raw_personal_contact_data": True,
            "secret_references_are_placeholders": True,
            "live_proof_still_required": True,
        },
    }


def write_example_completed_customer_inputs(out_dir: Path, pack: dict[str, Any]) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for template in pack["templates"]:
        path = out_dir / template["file_name"]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=template["fields"])
            writer.writeheader()
            for row in template["rows"]:
                writer.writerow({field: row.get(field, "") for field in template["fields"]})
        paths[template["key"]] = str(path)
    return paths


def render_example_completed_customer_inputs_markdown(
    pack: dict[str, Any],
    validation: dict[str, Any] | None = None,
) -> str:
    lines = [
        "# HomePilot Example Completed Customer Inputs",
        "",
        f"Release: {pack['release_label']}",
        f"Created: {pack['created_at']}",
        f"Status: {pack['status']}",
        f"Scope: {pack['example_scope']}",
        "",
        "This is a synthetic DAW-style completed input set for demo and onboarding purposes.",
        "It shows what the six customer CSVs look like when partner roster, territories, property source, suppression, message approval, and capacity are filled correctly.",
        "",
        "## Demo Outcome",
        "",
        f"- Partner renovators: {pack['summary']['partner_count']}",
        f"- Example rows: {pack['summary']['total_example_rows']}",
        f"- Tenant: {pack['summary']['tenant_id']}",
        f"- Module: {pack['summary']['module_key']}",
    ]
    if validation:
        lines += [
            f"- Input validation status: {validation['status']}",
            f"- First-wave decision: {validation['first_wave_decision']}",
            f"- Remaining blockers: {validation['summary']['blockers']}",
        ]
    lines += [
        "",
        "## Files",
        "",
        "| File | Rows | What It Demonstrates |",
        "| --- | ---: | --- |",
    ]
    purposes = {
        "partner_roster_template": "10 partner renovators with assigned-record-only scope and secret-channel contact references.",
        "territory_assignment_template": "Approved Belgian territory slices with capacity caps and overlap rule.",
        "property_source_template": "A customer-approved synthetic property-source example for FacadePilot.",
        "suppression_list_template": "Hash-only suppression handling with retention metadata.",
        "message_approval_template": "Approved NL/FR campaign messages with prohibited-claim checks.",
        "partner_capacity_template": "Confirmed partner capacity, appointment slots, SLA, and rejection taxonomy.",
    }
    for template in pack["templates"]:
        lines.append(
            f"| `{template['file_name']}` | {template['row_count']} | "
            f"{purposes.get(template['key'], 'Synthetic completed input rows.')} |"
        )
    lines += [
        "",
        "## Guardrails",
        "",
        "- This is synthetic example data, not DAW production data or customer approval.",
        "- Secret references are placeholders and do not contain real credentials or contact details.",
        "- A happy-path input validation still does not authorize outreach.",
        "- First-wave launch remains blocked until explicit customer go/no-go and live schema/RLS/customer-access proof are archived.",
        "",
    ]
    return "\n".join(lines)


def build_daw_boardroom_demo_walkthrough(report: dict[str, Any]) -> dict[str, Any]:
    decisions = report["decisions"]
    buyer_go = decisions.get("buyer_review") == "go"
    example_validation = report.get("example_first_campaign_input_validation", {})
    scenario = {
        "customer": "DAW producer network",
        "module": "facadepilot",
        "network_shape": "1 producer, 10 partner renovators, partner-scoped follow-up",
        "demo_duration": "45-60 minutes",
        "data_status": "synthetic demo and buyer-review evidence",
        "success_outcome": "DAW understands where value sits, how partner scope works, and exactly which live inputs unlock the first campaign.",
    }
    agenda = [
        {
            "minute": "0-5",
            "section": "Frame the promise",
            "artifact": "MARKET_READINESS_SCORECARD.md",
            "speaker_goal": "Explain that HomePilot is a tenant-safe property-intelligence platform, not only a lead generator.",
            "proof_point": "Buyer review is go while live launch and production remain no-go.",
            "guardrail": "Synthetic demo metrics are not production results.",
        },
        {
            "minute": "5-12",
            "section": "Show the DAW executive view",
            "artifact": "dashboard/index.html and BOARDROOM_REPORT.md",
            "speaker_goal": "Show network volume, facade m2, estimated pipeline, responses, appointments, and no-response backlog.",
            "proof_point": "DAW sees aggregate network performance and partner drilldown.",
            "guardrail": "Scores are opportunity signals, not homeowner purchase intent.",
        },
        {
            "minute": "12-18",
            "section": "Explain Open Intelligence decisions",
            "artifact": "dashboard Intelligence tab, OPEN_INTELLIGENCE_BOARDROOM_BRIEF.md, INTELLIGENCE_LAB.md",
            "speaker_goal": "Show the five DAW boardroom decisions first, then the autoresearch evidence behind lead priority, partner waves, campaign segments, and message tests.",
            "proof_point": "The decision cockpit links focus, partner routing, message/segment testing, measurement, and safe data use to evidence and blockers.",
            "guardrail": "Autoresearch is review evidence, not permission to start outreach.",
        },
        {
            "minute": "18-25",
            "section": "Prove partner separation",
            "artifact": "partner_cutdown_manifest.json and partner packages",
            "speaker_goal": "Show what one renovator receives and what stays hidden from other partners.",
            "proof_point": "Partner packages are scoped to assigned records with leakage evidence.",
            "guardrail": "Live partner access still requires RLS/customer-access proof.",
        },
        {
            "minute": "25-32",
            "section": "Make the second brain tangible",
            "artifact": "dashboard second-brain graph",
            "speaker_goal": "Use graph, filters, zoom/fit, move mode, and public-context panel to explain why the platform learns over campaigns.",
            "proof_point": "Visuals connect partner, territory, property, signal, response, objection, and next action.",
            "guardrail": "The graph is a navigation layer; source tables and snapshots remain metric truth.",
        },
        {
            "minute": "32-40",
            "section": "Turn demo into first campaign",
            "artifact": "CUSTOMER_INPUT_TEMPLATES.md and EXAMPLE_COMPLETED_CUSTOMER_INPUTS.md",
            "speaker_goal": "Show the six customer inputs DAW must provide and the synthetic completed example for 10 partners.",
            "proof_point": f"Happy-path validation status is {example_validation.get('status', 'not_generated')} with decision {example_validation.get('first_wave_decision', 'not_generated')}.",
            "guardrail": "Example inputs are onboarding material, not DAW production approval.",
        },
        {
            "minute": "40-48",
            "section": "Answer procurement and public-data questions",
            "artifact": "PROCUREMENT_SECURITY_REVIEW.md and PUBLIC_DATA_SOURCE_REGISTER.md",
            "speaker_goal": "Show legal/privacy boundaries, blocked data lanes, approved-source workflow, and public-data provenance path.",
            "proof_point": "Public enrichment has source-run/provenance tables and blocked lanes by default.",
            "guardrail": "Public data still needs dataset-level licence and allowed-use approval before production import.",
        },
        {
            "minute": "48-60",
            "section": "Close on decisions",
            "artifact": "LIVE_LAUNCH_REQUEST.md, LIVE_LAUNCH_CHECKLIST.csv, CUSTOMER_PILOT_PROPOSAL.md",
            "speaker_goal": "Ask for named owners, live inputs, first-wave scope, and pilot decision.",
            "proof_point": "The data room contains owner-assigned tasks and production proof requirements.",
            "guardrail": "No outreach or customer access before live schema/RLS/customer-access proof and explicit go/no-go.",
        },
    ]
    screen_sequence = [
        {
            "step": 1,
            "screen": "portable_data_room/index.html",
            "operator_action": "Open the portable data room and show that files are relative, checksummed, and customer-shareable.",
            "audience_question": "Can we share this internally with IT, legal, sales, and partner managers?",
            "success_signal": "DAW understands this is the first review package.",
            "caveat": "It is buyer-review evidence, not production proof.",
        },
        {
            "step": 2,
            "screen": "market-readiness.html",
            "operator_action": "Point to buyer_review=go and live_launch/production=no_go.",
            "audience_question": "What is ready now and what is still missing?",
            "success_signal": "DAW sees a professional go/no-go model.",
            "caveat": "Live proof is the main blocker, not demo quality.",
        },
        {
            "step": 3,
            "screen": "dashboard/index.html",
            "operator_action": "Filter to FacadePilot and walk through network KPIs, partner comparison, top opportunities, and no-response backlog.",
            "audience_question": "Which regions and partners should receive the first wave?",
            "success_signal": "DAW can name a partner wave and territory logic.",
            "caveat": "Opportunity scores are signals, not buyer intent.",
        },
        {
            "step": 4,
            "screen": "dashboard/boardroom-report.html",
            "operator_action": "Show executive summary, Intelligence Lab Evidence, steering matrix, work queues, recommendations, and caveats.",
            "audience_question": "Can leadership understand this without using the full dashboard?",
            "success_signal": "Sponsor sees a boardroom-readable layer.",
            "caveat": "Derived report; reconcile production metrics against source tables/views.",
        },
        {
            "step": 5,
            "section": "Open Intelligence decisions",
            "screen": "dashboard/index.html#intelligence",
            "supporting_artifacts": "OPEN_INTELLIGENCE_BOARDROOM_BRIEF.md; OPEN_INTELLIGENCE_DECISION_MATRIX.csv; INTELLIGENCE_LAB.md",
            "operator_action": "Open the Intelligence tab, start with the Boardroom decisions cockpit, then show priority model, partner wave, segments, message tests, denominator, scope leakage, and forbidden-claim checks.",
            "audience_question": "Which DAW decisions can this evidence support today, and what remains blocked before activation?",
            "success_signal": "DAW sees five decision-ready questions backed by a repeatable optimization loop instead of a static lead list.",
            "caveat": "Autoresearch is review evidence and still requires customer approval plus live proof before launch.",
        },
        {
            "step": 6,
            "screen": "second-brain graph",
            "operator_action": "Use zoom, fit, move mode, and public-context panels to explain relationships and learning loops.",
            "audience_question": "Why is this more than an Excel export?",
            "success_signal": "DAW sees memory across properties, campaigns, responses, objections, and next actions.",
            "caveat": "Graph counts are visual navigation, not source-of-truth reporting.",
        },
        {
            "step": 7,
            "screen": "partner cutdown package",
            "operator_action": "Open one partner package and show assigned-record-only rows, partner report, and leakage audit.",
            "audience_question": "Can one renovator see another renovator's data?",
            "success_signal": "Partner separation is clear.",
            "caveat": "Live portal access still needs RLS/customer-access probes.",
        },
        {
            "step": 8,
            "screen": "exports",
            "operator_action": "Show Excel-friendly export fields, response status, next action, and source/provenance references.",
            "audience_question": "Can operations use this immediately?",
            "success_signal": "DAW sees immediate operational value.",
            "caveat": "Exports must stay tenant/module/partner scoped.",
        },
        {
            "step": 9,
            "screen": "EXAMPLE_COMPLETED_CUSTOMER_INPUTS.md",
            "operator_action": "Show the synthetic completed DAW input example and happy-path validation.",
            "audience_question": "What exactly do we need to provide before the first wave?",
            "success_signal": "DAW sees a concrete intake path.",
            "caveat": "Synthetic examples are not customer approvals.",
        },
        {
            "step": 10,
            "screen": "PUBLIC_DATA_SOURCE_REGISTER.md",
            "operator_action": "Show approved-review, legal-review, and blocked data lanes.",
            "audience_question": "Which public data can improve prioritization legally?",
            "success_signal": "DAW understands official/open-data enrichment without overreach.",
            "caveat": "Dataset-level approval is required before import.",
        },
        {
            "step": 11,
            "screen": "LIVE_LAUNCH_REQUEST.md",
            "operator_action": "End with owner-assigned live inputs and the first-wave go/no-go gates.",
            "audience_question": "Who must do what next?",
            "success_signal": "Meeting ends with named owners and decisions.",
            "caveat": "No production access or outreach until live proof passes.",
        },
    ]
    stakeholder_questions = [
        {
            "stakeholder": "Executive sponsor",
            "question": "Why should DAW fund this instead of buying leads?",
            "answer": "Because DAW gets a reusable property-intelligence memory: opportunity volume, partner routing, response/no-response learning, exports, and module expansion on one tenant-safe spine.",
            "show_artifact": "CUSTOMER_VALUE_REALIZATION_PLAN.md",
            "guardrail": "Do not call unresponded opportunities buyer intent.",
        },
        {
            "stakeholder": "DAW network manager",
            "question": "How do I compare and steer 10 renovators?",
            "answer": "Use partner performance, territory, capacity, response rate, appointments, and no-response backlog to decide partner waves and follow-up.",
            "show_artifact": "BOARDROOM_REPORT.md and ROLE_CHEATSHEET.csv",
            "guardrail": "Partners see assigned records only.",
        },
        {
            "stakeholder": "Marketing and campaign lead",
            "question": "Which marketing decisions can we actually make from this?",
            "answer": "Use the Open Intelligence boardroom decision cockpit to choose first-wave focus, partner routing, segment-message tests, measurement loop, and safe data use, then review the Intelligence Lab evidence behind each choice.",
            "show_artifact": "OPEN_INTELLIGENCE_BOARDROOM_BRIEF.md, OPEN_INTELLIGENCE_DECISION_MATRIX.csv, and dashboard Intelligence tab",
            "guardrail": "Message tests are drafts and require customer/legal approval before use.",
        },
        {
            "stakeholder": "Partner renovator",
            "question": "What do I get and what do others see?",
            "answer": "Each partner gets assigned opportunities, own statuses, own follow-up queue, own scoped exports, and no raw data from other partners.",
            "show_artifact": "partner_cutdown_manifest.json",
            "guardrail": "Production portal access requires live RLS/customer proof.",
        },
        {
            "stakeholder": "IT/security",
            "question": "How do we know tenant and partner access is safe?",
            "answer": "Local contracts define tenant/module/partner RLS, customer access verification, and release proof. Live launch requires deployed metadata verification and customer JWT probes.",
            "show_artifact": "SQL_APPLY_PLAN.md and PRODUCTION_PROOF.md",
            "guardrail": "Do not claim production until reports show production_verified=true.",
        },
        {
            "stakeholder": "Legal/privacy",
            "question": "What data is blocked by default?",
            "answer": "Owner/cadastral personal data, scraped personal contact details, unsupported individual EPC labels, and homeowner-intent claims from scores are blocked unless explicitly approved.",
            "show_artifact": "BLOCKED_DATA_REGISTER.csv",
            "guardrail": "Public does not always mean reusable.",
        },
        {
            "stakeholder": "Campaign operator",
            "question": "What happens after the demo?",
            "answer": "DAW fills the six CSVs, validates inputs, supplies live proof through approved channels, and signs first-wave go/no-go.",
            "show_artifact": "CUSTOMER_INPUT_TEMPLATES.md and FIRST_CAMPAIGN_INPUT_VALIDATION.md",
            "guardrail": "Validation is not launch approval.",
        },
    ]
    proof_map = [
        {
            "claim": "DAW can see aggregate network performance and partner drilldown.",
            "artifact": "BOARDROOM_REPORT.md and dashboard network view",
            "proof_status": "synthetic_demo_ready",
        },
        {
            "claim": "DAW can review five boardroom decisions and why a first partner wave, segment, and message test is recommended.",
            "artifact": "OPEN_INTELLIGENCE_BOARDROOM_BRIEF.md, OPEN_INTELLIGENCE_DECISION_MATRIX.csv, INTELLIGENCE_LAB.md, and dashboard Intelligence tab",
            "proof_status": "autoresearch_review_evidence_ready",
        },
        {
            "claim": "Partners can receive scoped handoff packages.",
            "artifact": "partner_cutdown_manifest.json",
            "proof_status": "local_leakage_audit_ready",
        },
        {
            "claim": "The first campaign intake is operationally concrete.",
            "artifact": "CUSTOMER_INPUT_TEMPLATES.md and EXAMPLE_COMPLETED_CUSTOMER_INPUTS.md",
            "proof_status": "happy_path_example_ready",
        },
        {
            "claim": "Public-data enrichment has a governed lane.",
            "artifact": "PUBLIC_DATA_PRODUCTION_INTAKE.md",
            "proof_status": "approval_workflow_ready",
        },
        {
            "claim": "Production access is intentionally blocked until live proof.",
            "artifact": "PRODUCTION_PROOF.md and LIVE_LAUNCH_REQUEST.md",
            "proof_status": "blocked_until_live_proof",
        },
    ]
    follow_up_decisions = [
        {
            "decision": "Approve first paid pilot scope",
            "owner": "Executive sponsor",
            "artifact": "CUSTOMER_PILOT_PROPOSAL.md",
            "blocked_until": "commercial/legal agreement",
        },
        {
            "decision": "Confirm 10 partner roster and territories",
            "owner": "DAW network manager / partner manager",
            "artifact": "PARTNER_ROSTER_TEMPLATE.csv and TERRITORY_ASSIGNMENT_TEMPLATE.csv",
            "blocked_until": "customer-approved partner input files",
        },
        {
            "decision": "Approve message, contact basis, and suppression",
            "owner": "Legal/privacy and marketing owner",
            "artifact": "MESSAGE_APPROVAL_TEMPLATE.csv and SUPPRESSION_LIST_TEMPLATE.csv",
            "blocked_until": "approved customer files and go/no-go",
        },
        {
            "decision": "Supply live platform proof inputs",
            "owner": "IT/security owner",
            "artifact": "LIVE_LAUNCH_REQUEST.md and live_launch.env.template",
            "blocked_until": "Supabase/RLS/customer-access credentials through approved secret channel",
        },
        {
            "decision": "Run first controlled wave",
            "owner": "Customer success owner / campaign owner",
            "artifact": "FIRST_CAMPAIGN_INPUT_VALIDATION.md",
            "blocked_until": "customer input validation plus live proof plus explicit first-wave go/no-go",
        },
    ]
    return {
        "walkthrough_type": "homepilot_daw_boardroom_demo_walkthrough",
        "created_at": utc_now(),
        "release_label": report["release_label"],
        "status": "buyer_demo_ready" if buyer_go else "action_required",
        "decisions": decisions,
        "scenario": scenario,
        "agenda": agenda,
        "screen_sequence": screen_sequence,
        "stakeholder_questions": stakeholder_questions,
        "proof_map": proof_map,
        "follow_up_decisions": follow_up_decisions,
        "success_criteria": [
            "DAW can explain the difference between HomePilot, FacadePilot, tenant, producer network, and partner renovator.",
            "DAW can use the Intelligence tab to name five boardroom decisions, their evidence, their owners, and their blockers.",
            "DAW can name which KPIs matter for the first crepi campaign and which denominator each rate uses.",
            "DAW understands partner-scoped visibility and why partner cutdowns are assigned-record-only.",
            "DAW sees the exact six inputs needed for first-wave campaign setup.",
            "DAW leaves with named owners for live proof, first campaign inputs, and pilot decision.",
        ],
        "guardrails": {
            "synthetic_demo_not_live_performance": True,
            "scores_are_not_homeowner_intent": True,
            "partner_scope_required_before_partner_access": True,
            "public_data_requires_dataset_approval": True,
            "live_proof_required_before_launch": True,
        },
    }


def render_daw_boardroom_demo_walkthrough_markdown(walkthrough: dict[str, Any]) -> str:
    lines = [
        "# HomePilot DAW Boardroom Demo Walkthrough",
        "",
        f"Release: {walkthrough['release_label']}",
        f"Created: {walkthrough['created_at']}",
        f"Status: {walkthrough['status']}",
        "",
        "This is the operator talk track for the first DAW buyer demo. It tells the same story as the data room, but in meeting order.",
        "",
        "## Scenario",
        "",
    ]
    for key, value in walkthrough["scenario"].items():
        lines.append(f"- {key}: {value}")
    lines += [
        "",
        "## Agenda",
        "",
        "| Time | Section | Artifact | Speaker Goal | Proof Point | Guardrail |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in walkthrough["agenda"]:
        lines.append(
            f"| {row['minute']} | {row['section']} | `{row['artifact']}` | "
            f"{row['speaker_goal']} | {row['proof_point']} | {row['guardrail']} |"
        )
    lines += [
        "",
        "## Screen Sequence",
        "",
        "| Step | Screen | Operator Action | Expected Question | Success Signal | Caveat |",
        "| ---: | --- | --- | --- | --- | --- |",
    ]
    for row in walkthrough["screen_sequence"]:
        lines.append(
            f"| {row['step']} | `{row['screen']}` | {row['operator_action']} | "
            f"{row['audience_question']} | {row['success_signal']} | {row['caveat']} |"
        )
    lines += [
        "",
        "## Stakeholder Questions",
        "",
        "| Stakeholder | Likely Question | Answer | Show | Guardrail |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in walkthrough["stakeholder_questions"]:
        lines.append(
            f"| {row['stakeholder']} | {row['question']} | {row['answer']} | "
            f"`{row['show_artifact']}` | {row['guardrail']} |"
        )
    lines += [
        "",
        "## Proof Map",
        "",
        "| Claim | Artifact | Proof Status |",
        "| --- | --- | --- |",
    ]
    for row in walkthrough["proof_map"]:
        lines.append(f"| {row['claim']} | `{row['artifact']}` | {row['proof_status']} |")
    lines += [
        "",
        "## Follow-Up Decisions",
        "",
        "| Decision | Owner | Artifact | Blocked Until |",
        "| --- | --- | --- | --- |",
    ]
    for row in walkthrough["follow_up_decisions"]:
        lines.append(f"| {row['decision']} | {row['owner']} | `{row['artifact']}` | {row['blocked_until']} |")
    lines += [
        "",
        "## Success Criteria",
        "",
    ]
    lines.extend(f"- {item}" for item in walkthrough["success_criteria"])
    lines += [
        "",
        "## Guardrails",
        "",
        "- Synthetic demo metrics are not live DAW performance.",
        "- Scores are opportunity signals, not homeowner purchase intent.",
        "- Partner renovators must see assigned records only.",
        "- Public data needs dataset-level approval before production import.",
        "- First-wave launch requires completed customer inputs, live proof, and explicit go/no-go.",
        "",
    ]
    return "\n".join(lines)


def _write_daw_demo_checklist_csv(path: Path, walkthrough: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "phase",
        "step",
        "section",
        "artifact",
        "supporting_artifacts",
        "owner",
        "operator_action",
        "audience_question",
        "success_check",
        "guardrail",
    ]
    rows = []
    for row in walkthrough["screen_sequence"]:
        rows.append({
            "phase": "demo_screen",
            "step": row["step"],
            "section": row.get("section", ""),
            "artifact": row["screen"],
            "supporting_artifacts": row.get("supporting_artifacts", ""),
            "owner": "HomePilot operator",
            "operator_action": row["operator_action"],
            "audience_question": row["audience_question"],
            "success_check": row["success_signal"],
            "guardrail": row["caveat"],
        })
    for row in walkthrough["follow_up_decisions"]:
        rows.append({
            "phase": "follow_up_decision",
            "step": row["decision"],
            "section": "Follow-up decisions",
            "artifact": row["artifact"],
            "supporting_artifacts": "",
            "owner": row["owner"],
            "operator_action": f"Assign owner and collect evidence in {row['artifact']}.",
            "audience_question": row["decision"],
            "success_check": row["blocked_until"],
            "guardrail": "Do not mark complete until the named evidence exists.",
        })
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def build_daw_first_campaign_control_room(report: dict[str, Any]) -> dict[str, Any]:
    decisions = report["decisions"]
    first_campaign = report.get("first_campaign_launch_intake", {})
    input_validation = report.get("first_campaign_input_validation", {})
    example_validation = report.get("example_first_campaign_input_validation", {})
    public_intake = report.get("public_data_production_intake", {})
    expected_partners = first_campaign.get("scenario", {}).get("expected_partner_renovators", 10)
    customer_input_blockers = input_validation.get("summary", {}).get("blockers")
    example_blockers = example_validation.get("summary", {}).get("blockers")
    live_launch_go = decisions.get("live_launch") == "go"
    buyer_go = decisions.get("buyer_review") == "go"
    status = "buyer_review_control_ready" if buyer_go else "action_required"
    first_wave_decision = "ready_for_first_wave_review" if live_launch_go else "blocked_until_customer_inputs_and_live_proof"
    launch_lanes = [
        {
            "lane": "Buyer story and DAW sponsor alignment",
            "owner": "HomePilot operator / executive sponsor",
            "status": "ready_for_buyer_review" if buyer_go else "action_required",
            "evidence": "MARKET_READINESS_SCORECARD.md, DAW_BOARDROOM_DEMO_WALKTHROUGH.md, CUSTOMER_PILOT_PROPOSAL.md",
            "next_decision": "Approve first paid pilot scope and name a DAW business owner.",
            "blocker": "Commercial/legal agreement before production work starts.",
        },
        {
            "lane": "Partner wave design",
            "owner": "DAW network manager / partner manager",
            "status": "customer_input_required",
            "evidence": "PARTNER_ROSTER_TEMPLATE.csv, TERRITORY_ASSIGNMENT_TEMPLATE.csv, EXAMPLE_COMPLETED_CUSTOMER_INPUTS.md",
            "next_decision": f"Confirm {expected_partners} partner renovators, territories, and capacity caps.",
            "blocker": "Customer-approved roster, territory split, and capacity rows are still required.",
        },
        {
            "lane": "Campaign claims, contact basis, and suppression",
            "owner": "Legal/privacy owner / marketing owner",
            "status": "customer_input_required",
            "evidence": "MESSAGE_APPROVAL_TEMPLATE.csv, SUPPRESSION_LIST_TEMPLATE.csv, FIRST_CAMPAIGN_INPUT_VALIDATION.md",
            "next_decision": "Approve messages, opt-out wording, suppression process, and contact-basis evidence.",
            "blocker": "Validation can flag issues, but it is not legal approval.",
        },
        {
            "lane": "Public-data enrichment approvals",
            "owner": "Legal/privacy owner / data owner",
            "status": public_intake.get("production_import_decision", "approval_required"),
            "evidence": "PUBLIC_DATA_PRODUCTION_INTAKE.md, PUBLIC_DATA_APPROVAL_CHECKLIST.csv, BLOCKED_DATA_REGISTER.csv",
            "next_decision": "Approve dataset-level licence, allowed use, field allowlist, attribution, and provenance.",
            "blocker": "No production import before dataset approval and live proof.",
        },
        {
            "lane": "Live platform and access proof",
            "owner": "IT/security owner / HomePilot operator",
            "status": decisions.get("live_launch", "no_go"),
            "evidence": "LIVE_LAUNCH_REQUEST.md, SQL_APPLY_PLAN.md, PRODUCTION_PROOF.md",
            "next_decision": "Supply live Supabase/RLS/customer-access inputs through approved secret channels.",
            "blocker": "Production stays no-go until live schema, RLS, and customer access reports all pass with production_verified=true.",
        },
        {
            "lane": "First-wave go/no-go",
            "owner": "Customer success owner / campaign owner",
            "status": first_wave_decision,
            "evidence": "FIRST_CAMPAIGN_INPUT_VALIDATION.md, LIVE_LAUNCH_CHECKLIST.csv, CUSTOMER_VALUE_REALIZATION_PLAN.md",
            "next_decision": "Run a controlled first wave only after customer inputs, live proof, and explicit go/no-go are archived.",
            "blocker": "Synthetic completed examples are training material, not DAW approval.",
        },
    ]
    partner_wave_plan = [
        {
            "wave": "Wave 0",
            "timing": "Demo day to T+2 business days",
            "scope": "DAW sponsor, network manager, IT/security, legal/privacy, HomePilot operator",
            "objective": "Convert the impressive demo into named owners, scope, and first-wave decisions.",
            "entry_gate": "Buyer-review pack shared.",
            "exit_gate": "Pilot owner, IT owner, legal owner, and partner manager named.",
        },
        {
            "wave": "Wave 1",
            "timing": "T+3 to T+7 business days",
            "scope": "Ten partner renovators, approved territories, approved source list, approved messages.",
            "objective": "Collect and validate all customer inputs without storing secrets or raw personal contact details in the data room.",
            "entry_gate": "Customer uses the six first-campaign templates.",
            "exit_gate": "Input validation shows customer_inputs_ready or a reviewed blocker list.",
        },
        {
            "wave": "Wave 2",
            "timing": "After live proof",
            "scope": "Controlled FacadePilot first wave for DAW producer network.",
            "objective": "Launch only the scoped campaign, track response/no-response, and protect partner boundaries.",
            "entry_gate": "Live schema, RLS, customer access, contact basis, suppression, message, and go/no-go proof archived.",
            "exit_gate": "First appointments, response learning, no-response backlog, and partner follow-up queues reviewed.",
        },
        {
            "wave": "Wave 3",
            "timing": "30-day value review",
            "scope": "Optimization across partner capacity, territory, message variants, and follow-up SLAs.",
            "objective": "Move from campaign activity to learning loop and value proof.",
            "entry_gate": "First-wave metrics reconciled with denominator-explicit response rates.",
            "exit_gate": "Scale, pause, or refine decision captured in EXECUTIVE_DECISION_LOG.csv.",
        },
        {
            "wave": "Wave 4",
            "timing": "60/90-day expansion review",
            "scope": "Additional territories, partner waves, and optional WindowPilot/RoofPilot/GardenPilot-style modules.",
            "objective": "Grow HomePilot on the shared property spine only where entitlements, data, and value proof justify it.",
            "entry_gate": "Value-realization plan shows agreed KPI progress.",
            "exit_gate": "Expansion decision tree has a customer-approved next move.",
        },
    ]
    operating_cadence = [
        {
            "cadence": "Before every DAW meeting",
            "owner": "HomePilot operator",
            "check": "Open the control room, market readiness scorecard, DAW demo walkthrough, and live launch request.",
            "evidence": "DAW_FIRST_CAMPAIGN_CONTROL_ROOM.md, MARKET_READINESS_SCORECARD.md, LIVE_LAUNCH_REQUEST.md",
        },
        {
            "cadence": "Daily during input collection",
            "owner": "Customer success owner",
            "check": "Review missing customer CSVs, validation blockers, partner capacity, suppression, and message approval.",
            "evidence": "FIRST_CAMPAIGN_INPUT_VALIDATION.md, FIRST_CAMPAIGN_INPUT_ISSUES.csv",
        },
        {
            "cadence": "Before live cutover",
            "owner": "IT/security owner",
            "check": "Verify live readiness, schema verification, RLS launch fixture, and customer access proof.",
            "evidence": "LIVE_READINESS.md, SQL_APPLY_PLAN.md, PRODUCTION_PROOF.md",
        },
        {
            "cadence": "Weekly after first launch",
            "owner": "DAW network manager / customer success owner",
            "check": "Review response rate denominator, appointments, partner backlog, no-response follow-up, and learning actions.",
            "evidence": "CUSTOMER_VALUE_REALIZATION_PLAN.md, VALUE_REALIZATION_METRICS.csv, BOARDROOM_REPORT.md",
        },
    ]
    action_board = [
        {
            "priority": "P1",
            "track": "pilot_scope",
            "owner": "Executive sponsor",
            "status": "decision_required",
            "action": "Approve first paid pilot scope and first-wave success criteria.",
            "evidence": "CUSTOMER_PILOT_PROPOSAL.md, PILOT_SCOPE_CHECKLIST.csv",
            "exit_condition": "Pilot scope signed or marked no-go.",
        },
        {
            "priority": "P1",
            "track": "live_proof",
            "owner": "IT/security owner",
            "status": decisions.get("live_launch", "no_go"),
            "action": "Provide live Supabase and customer-access inputs through approved secret channels.",
            "evidence": "LIVE_LAUNCH_REQUEST.md, live_launch.env.template",
            "exit_condition": "Live schema/RLS/customer-access reports pass with production_verified=true.",
        },
        {
            "priority": "P1",
            "track": "partner_scope",
            "owner": "DAW network manager",
            "status": "customer_input_required",
            "action": f"Confirm the {expected_partners} partner renovators, territories, fallback owners, and capacity caps.",
            "evidence": "PARTNER_ROSTER_TEMPLATE.csv, TERRITORY_ASSIGNMENT_TEMPLATE.csv, PARTNER_CAPACITY_TEMPLATE.csv",
            "exit_condition": "First-campaign validation accepts partner roster, territories, and capacity.",
        },
        {
            "priority": "P1",
            "track": "campaign_compliance",
            "owner": "Legal/privacy owner",
            "status": "approval_required",
            "action": "Approve contact basis, suppression handling, message claims, opt-out copy, and first-wave go/no-go.",
            "evidence": "PROPERTY_SOURCE_TEMPLATE.csv, SUPPRESSION_LIST_TEMPLATE.csv, MESSAGE_APPROVAL_TEMPLATE.csv, FIRST_CAMPAIGN_INPUT_VALIDATION.md",
            "exit_condition": "Validation has no customer-input blockers and legal go/no-go is archived.",
        },
        {
            "priority": "P2",
            "track": "public_data",
            "owner": "Data owner / legal/privacy owner",
            "status": public_intake.get("production_import_decision", "approval_required"),
            "action": "Select approved public-data lanes and record licence, allowed use, field allowlist, attribution, and provenance.",
            "evidence": "PUBLIC_DATA_PRODUCTION_INTAKE.md, PUBLIC_DATA_APPROVAL_CHECKLIST.csv",
            "exit_condition": "No production import runs until dataset approvals and live proof exist.",
        },
        {
            "priority": "P2",
            "track": "operator_training",
            "owner": "Customer success owner",
            "status": "ready_for_buyer_review",
            "action": "Train DAW roles on executive, network-manager, partner-renovator, legal, IT, and operator views.",
            "evidence": "CUSTOMER_TRAINING_GUIDE.md, ROLE_CHEATSHEET.csv",
            "exit_condition": "Each role can state what they can see, what is blocked, and what they do first.",
        },
        {
            "priority": "P2",
            "track": "value_measurement",
            "owner": "Executive sponsor / analyst",
            "status": "ready_for_buyer_review",
            "action": "Agree KPI definitions, response-rate denominator, partner-performance dimensions, and 30/60/90-day decision gates.",
            "evidence": "CUSTOMER_VALUE_REALIZATION_PLAN.md, VALUE_REALIZATION_METRICS.csv, EXECUTIVE_DECISION_LOG.csv",
            "exit_condition": "DAW accepts the measurement plan before first-wave claims are made.",
        },
    ]
    decision_board = [
        {
            "decision": "Buyer review",
            "current_state": decisions.get("buyer_review", "unknown"),
            "green_when": "Data room, demo, security, governance, rollout, and first-campaign artifacts are reviewable.",
            "evidence": "homepilot_boardroom_data_room.zip",
        },
        {
            "decision": "Live launch",
            "current_state": decisions.get("live_launch", "unknown"),
            "green_when": "Live readiness inputs, schema verification, RLS launch fixture, and customer access proof pass.",
            "evidence": "LIVE_LAUNCH_REQUEST.md, PRODUCTION_PROOF.md",
        },
        {
            "decision": "First campaign",
            "current_state": first_wave_decision,
            "green_when": "Customer inputs validate, live proof passes, contact basis/suppression/message approvals are archived, and DAW gives explicit go/no-go.",
            "evidence": "FIRST_CAMPAIGN_INPUT_VALIDATION.md, LIVE_LAUNCH_CHECKLIST.csv",
        },
        {
            "decision": "Scale or expand modules",
            "current_state": "blocked_until_first_wave_value_review",
            "green_when": "30/60/90-day value proof supports expansion and tenant-module entitlements are approved.",
            "evidence": "CUSTOMER_MODULE_EXPANSION_PLAN.md, EXPANSION_DECISION_TREE.csv",
        },
    ]
    return {
        "control_room_type": "homepilot_daw_first_campaign_control_room",
        "created_at": utc_now(),
        "release_label": report["release_label"],
        "status": status,
        "first_wave_decision": first_wave_decision,
        "decisions": decisions,
        "scenario": {
            "customer": "DAW producer network",
            "module": "facadepilot",
            "expected_partner_renovators": expected_partners,
            "data_status": "synthetic demo and buyer-review evidence until customer inputs and live proof are supplied",
        },
        "summary": {
            "launch_lanes": len(launch_lanes),
            "partner_waves": len(partner_wave_plan),
            "action_items": len(action_board),
            "customer_input_validation_status": input_validation.get("status", "not_generated"),
            "customer_input_blockers": customer_input_blockers,
            "example_validation_status": example_validation.get("status", "not_generated"),
            "example_validation_blockers": example_blockers,
        },
        "launch_lanes": launch_lanes,
        "partner_wave_plan": partner_wave_plan,
        "operating_cadence": operating_cadence,
        "action_board": action_board,
        "decision_board": decision_board,
        "proof_requirements": [
            "Customer-approved partner roster, territories, property source/contact basis, suppression, message approval, and partner capacity.",
            "Live schema verification with production_verified=true.",
            "Live RLS launch fixture and customer access verification with production_verified=true.",
            "Dataset-level public-data approvals before any production public-data import.",
            "Explicit DAW first-wave go/no-go before outreach or partner portal access.",
        ],
        "guardrails": {
            "control_room_is_not_customer_approval": True,
            "synthetic_examples_are_training_material": True,
            "live_proof_required_before_first_wave": True,
            "partner_scope_required_before_partner_access": True,
            "public_data_requires_dataset_approval": True,
            "response_rate_denominator_must_be_contacted_records": True,
        },
    }


def render_daw_first_campaign_control_room_markdown(control_room: dict[str, Any]) -> str:
    lines = [
        "# HomePilot DAW First Campaign Control Room",
        "",
        f"Release: {control_room['release_label']}",
        f"Created: {control_room['created_at']}",
        f"Status: {control_room['status']}",
        f"First-wave decision: {control_room['first_wave_decision']}",
        "",
        "This is the operational cockpit for moving DAW from boardroom demo to a controlled first FacadePilot campaign.",
        "It keeps partner scope, customer inputs, public-data approvals, live proof, and go/no-go decisions in one place.",
        "",
        "## Scenario",
        "",
    ]
    for key, value in control_room["scenario"].items():
        lines.append(f"- {key}: {value}")
    lines += [
        "",
        "## Launch Lanes",
        "",
        "| Lane | Owner | Status | Evidence | Next Decision | Blocker |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in control_room["launch_lanes"]:
        lines.append(
            f"| {row['lane']} | {row['owner']} | {row['status']} | `{row['evidence']}` | "
            f"{row['next_decision']} | {row['blocker']} |"
        )
    lines += [
        "",
        "## Partner Wave Plan",
        "",
        "| Wave | Timing | Scope | Objective | Entry Gate | Exit Gate |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in control_room["partner_wave_plan"]:
        lines.append(
            f"| {row['wave']} | {row['timing']} | {row['scope']} | {row['objective']} | "
            f"{row['entry_gate']} | {row['exit_gate']} |"
        )
    lines += [
        "",
        "## Operating Cadence",
        "",
        "| Cadence | Owner | Check | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for row in control_room["operating_cadence"]:
        lines.append(f"| {row['cadence']} | {row['owner']} | {row['check']} | `{row['evidence']}` |")
    lines += [
        "",
        "## Action Board",
        "",
        "| Priority | Track | Owner | Status | Action | Evidence | Exit Condition |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in control_room["action_board"]:
        lines.append(
            f"| {row['priority']} | {row['track']} | {row['owner']} | {row['status']} | "
            f"{row['action']} | `{row['evidence']}` | {row['exit_condition']} |"
        )
    lines += [
        "",
        "## Decision Board",
        "",
        "| Decision | Current State | Green When | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for row in control_room["decision_board"]:
        lines.append(
            f"| {row['decision']} | {row['current_state']} | {row['green_when']} | `{row['evidence']}` |"
        )
    lines += [
        "",
        "## Proof Requirements",
        "",
    ]
    lines.extend(f"- {item}" for item in control_room["proof_requirements"])
    lines += [
        "",
        "## Guardrails",
        "",
        "- The control room is an operator/customer-success cockpit, not customer approval.",
        "- Synthetic examples show the workflow; they are not DAW production inputs.",
        "- First-wave launch requires completed customer inputs, live proof, and explicit go/no-go.",
        "- Partner renovators must receive assigned-record-only data.",
        "- Public-data imports require dataset-level approval, provenance, and attribution.",
        "- Response-rate claims must keep contacted-record denominator explicit.",
        "",
    ]
    return "\n".join(lines)


def _write_daw_first_campaign_action_board_csv(path: Path, control_room: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["priority", "track", "owner", "status", "action", "evidence", "exit_condition"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in control_room["action_board"]:
            writer.writerow({field: row.get(field, "") for field in fields})


def build_procurement_review_pack(report: dict[str, Any]) -> dict[str, Any]:
    decisions = report["decisions"]
    production_go = decisions.get("production") == "go"
    live_go = decisions.get("live_launch") == "go"
    questions = [
        {
            "domain": "Platform scope",
            "question": "What is HomePilot and which products share the platform?",
            "answer": "HomePilot is the shared tenant-safe property-intelligence layer for FacadePilot, WindowPilot, RoofPilot, GardenPilot, PoolPilot, PorchPilot, DrivewayPilot, and future renovation pilots.",
            "status": "ready",
            "owner": "HomePilot operator",
            "evidence": ["DATA_DICTIONARY.md", "MARKET_READINESS_SCORECARD.md"],
            "caveat": "Product modules expose only entitled metrics and rows.",
        },
        {
            "domain": "Tenant isolation",
            "question": "Can one customer see another customer's raw addresses, responses, or campaign learnings?",
            "answer": "The local contract requires tenant scoping on raw rows, exports, audit events, and customer-visible packages. Partner renovators are further scoped to assigned records inside producer networks.",
            "status": "ready_local",
            "owner": "IT/security owner",
            "evidence": ["API_CONTRACT.md", "ACCOUNT_ACCESS_PLAN.md", "CUSTOMER_ACCESS_VERIFICATION.md"],
            "caveat": "Production isolation still requires live Supabase RLS and customer JWT probes.",
        },
        {
            "domain": "Live production proof",
            "question": "Has the production database, RLS, and customer access been verified live?",
            "answer": "Not yet. Buyer review is ready, but production remains no-go until live schema verification, launch/RLS probes, and customer access verification all pass with production_verified=true.",
            "status": "blocked",
            "owner": "HomePilot operator / IT owner",
            "evidence": ["PRODUCTION_PROOF.md", "LIVE_LAUNCH_REQUEST.md", "LIVE_LAUNCH_CHECKLIST.csv"],
            "caveat": "This is the primary remaining production blocker.",
        },
        {
            "domain": "Data categories",
            "question": "Which data categories can the platform process?",
            "answer": "Tenant-scoped property/address records, module assessments, campaign targets, interaction statuses, response summaries, exports, audit events, and approved source/enrichment metadata.",
            "status": "ready",
            "owner": "Legal/privacy owner",
            "evidence": ["PROCESSING_REGISTER.md", "DATA_DICTIONARY.md", "SOURCE_LEDGER.md"],
            "caveat": "Do not import owner data, personal contact data, or non-public EPC/address-level energy data without explicit legal basis and licence review.",
        },
        {
            "domain": "Public data and enrichment",
            "question": "Can public/open data be used for prioritization?",
            "answer": "Yes, when each dataset has recorded provenance, licence, retrieval date, allowed use, and geography level. Official address/geospatial and aggregate statistical data are preferred.",
            "status": "review_required",
            "owner": "Legal/privacy owner / data owner",
            "evidence": ["DATA_VENDOR_PLAN.md", "ENRICHMENT_REFRESH_RUNBOOK.md", "SOURCE_LEDGER.md"],
            "caveat": "Dataset-level licence review is required before production import.",
        },
        {
            "domain": "Lead claims",
            "question": "Does a high score mean the homeowner has buying intent?",
            "answer": "No. A score is an opportunity signal. Buying intent may only be claimed when an interaction or status shows explicit engagement, such as responded, appointment, or customer.",
            "status": "ready",
            "owner": "Sales/customer success owner",
            "evidence": ["PROCESSING_REGISTER.md", "CAMPAIGN_LEARNING.md", "OPPORTUNITY_DOSSIER.md"],
            "caveat": "Sales language must avoid presenting inferred scores as homeowner intent.",
        },
        {
            "domain": "Secrets and credentials",
            "question": "Are secrets stored in customer reports or data-room files?",
            "answer": "No. Launch request and refresh tooling use environment variables or a secret channel and write env var names/placeholders only. The portable data room redacts local machine paths.",
            "status": "ready_local",
            "owner": "Platform admin / HomePilot operator",
            "evidence": ["LIVE_LAUNCH_REQUEST.md", "DATA_ROOM_MANIFEST.json", "PRODUCTION_PROOF.md"],
            "caveat": "Actual live credentials still need to be supplied through the agreed secret channel.",
        },
        {
            "domain": "Exports and auditability",
            "question": "Can the customer export data and audit what was included?",
            "answer": "Yes. Customer packages include scoped exports, manifest evidence, export logs, audit trails, and row-count checks tied to tenant/module filters.",
            "status": "ready_local",
            "owner": "Customer success owner",
            "evidence": ["BOARDROOM_DATA_ROOM_INDEX.md", "SOURCE_LEDGER.md", "DATA_DICTIONARY.md"],
            "caveat": "Production exports must be generated only after live access proof passes.",
        },
        {
            "domain": "Retention and deletion",
            "question": "Is there a retention and deletion workflow?",
            "answer": "The local readiness pack includes retention checks and per-property delete-plan tooling, with review gates before campaign handoff.",
            "status": "ready_local",
            "owner": "Legal/privacy owner",
            "evidence": ["PROCESSING_REGISTER.md", "PRODUCTION_READINESS.md"],
            "caveat": "Customer-specific retention periods still need signoff.",
        },
        {
            "domain": "Incident and monitoring",
            "question": "How are operational issues monitored and escalated?",
            "answer": "Monitoring artifacts define alert ownership, cadence, production blockers, and remediation for access, portal, CRM delivery, data quality, compliance, exports, and benchmark privacy.",
            "status": "ready_local",
            "owner": "HomePilot operator / customer success owner",
            "evidence": ["MONITORING_RUNBOOK.md", "alert_matrix.csv", "OPS_RUNBOOK.md"],
            "caveat": "Live alert channels and customer escalation contacts must be confirmed before production.",
        },
        {
            "domain": "Subprocessors and vendors",
            "question": "Which subprocessors or external vendors are required?",
            "answer": "Supabase/Postgres is the planned live data platform. Public-data and enrichment vendors are optional and must be approved per source, licence, endpoint, and credential path.",
            "status": "review_required",
            "owner": "IT/security owner / legal owner",
            "evidence": ["SQL_APPLY_PLAN.md", "DATA_VENDOR_PLAN.md", "LIVE_LAUNCH_REQUEST.md"],
            "caveat": "Final subprocessor list is customer- and deployment-specific.",
        },
        {
            "domain": "Support and SLA",
            "question": "Is a support/SLA model ready?",
            "answer": "The rollout and support plans define operational owners, priority levels, response targets, escalation, first-campaign support, and incident-response steps.",
            "status": "ready_local",
            "owner": "Executive sponsor / customer success owner",
            "evidence": ["SUPPORT_SLA_PLAN.md", "SUPPORT_ESCALATION_MATRIX.csv", "INCIDENT_RESPONSE_PLAYBOOK.md", "OPS_RUNBOOK.md"],
            "caveat": "This is operational readiness, not a signed contractual SLA; customer contact channels and final terms still need agreement.",
        },
    ]
    risks = [
        {
            "risk": "Live database and RLS proof missing",
            "severity": "high",
            "status": "blocked" if not production_go else "controlled",
            "owner": "IT/security owner",
            "mitigation": "Run live schema verification, live RLS launch fixture, customer access verification, and archive production proof before enabling paying access.",
            "evidence": ["PRODUCTION_PROOF.md", "LIVE_LAUNCH_REQUEST.md"],
        },
        {
            "risk": "Cross-tenant or cross-partner leakage in exports or dashboards",
            "severity": "high",
            "status": "controlled_local",
            "owner": "HomePilot operator",
            "mitigation": "Use tenant/module/partner filters before package generation and verify partner cutdowns plus live RLS probes.",
            "evidence": ["partner_cutdown_manifest.json", "CUSTOMER_ACCESS_VERIFICATION.md", "API_CONTRACT.md"],
        },
        {
            "risk": "Public-data licence mismatch",
            "severity": "medium",
            "status": "review_required",
            "owner": "Legal/privacy owner",
            "mitigation": "Require dataset-level licence, allowed-use, retrieval-date, and attribution review before production import.",
            "evidence": ["DATA_VENDOR_PLAN.md", "SOURCE_LEDGER.md"],
        },
        {
            "risk": "Sales overclaims homeowner intent from model scores",
            "severity": "medium",
            "status": "controlled_local",
            "owner": "Sales/customer success owner",
            "mitigation": "Use opportunity/priority language until explicit responded, appointment, or customer status exists.",
            "evidence": ["PROCESSING_REGISTER.md", "CAMPAIGN_LEARNING.md"],
        },
        {
            "risk": "Live credentials sent through unsafe channels",
            "severity": "high",
            "status": "blocked" if not live_go else "controlled",
            "owner": "Platform admin",
            "mitigation": "Use env variables or agreed secret manager; reports store placeholders and env var names only.",
            "evidence": ["LIVE_LAUNCH_REQUEST.md", "LIVE_LAUNCH_CHECKLIST.csv"],
        },
        {
            "risk": "Customer-specific retention or deletion policy not signed off",
            "severity": "medium",
            "status": "review_required",
            "owner": "Legal/privacy owner",
            "mitigation": "Review processing register, retention checks, and delete-plan workflow before live campaign data is retained.",
            "evidence": ["PROCESSING_REGISTER.md", "PRODUCTION_READINESS.md"],
        },
    ]
    status = "production_ready" if production_go else "buyer_review_ready" if decisions.get("buyer_review") == "go" else "action_required"
    return {
        "pack_type": "homepilot_procurement_security_review",
        "created_at": utc_now(),
        "release_label": report["release_label"],
        "status": status,
        "decisions": decisions,
        "not_legal_advice": True,
        "summary": {
            "questions": len(questions),
            "ready_or_local_ready": len([row for row in questions if row["status"] in {"ready", "ready_local"}]),
            "review_required": len([row for row in questions if row["status"] == "review_required"]),
            "blocked": len([row for row in questions if row["status"] == "blocked"]),
            "production_go": production_go,
        },
        "questionnaire": questions,
        "risk_register": risks,
        "guardrails": {
            "no_secrets_written": not bool(report["summary"].get("secrets_written")),
            "production_requires_live_proof": True,
            "tenant_module_partner_scope_required": True,
            "public_data_requires_dataset_level_licence_review": True,
            "scores_are_not_homeowner_intent": True,
        },
    }


def render_procurement_review_markdown(pack: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Procurement & Security Review",
        "",
        f"Release: {pack['release_label']}",
        f"Created: {pack['created_at']}",
        f"Status: {pack['status']}",
        "",
        "This is a structured enterprise review artifact, not legal advice.",
        "",
        "## Decision State",
        "",
    ]
    for key, value in pack["decisions"].items():
        lines.append(f"- {key}: {value}")
    lines += [
        "",
        "## Questionnaire",
        "",
        "| Domain | Status | Owner | Question | Answer | Evidence | Caveat |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in pack["questionnaire"]:
        lines.append(
            f"| {row['domain']} | {row['status']} | {row['owner']} | {row['question']} | "
            f"{row['answer']} | {', '.join(row['evidence'])} | {row['caveat']} |"
        )
    lines += [
        "",
        "## Risk Register",
        "",
        "| Severity | Status | Owner | Risk | Mitigation | Evidence |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in pack["risk_register"]:
        lines.append(
            f"| {row['severity']} | {row['status']} | {row['owner']} | {row['risk']} | "
            f"{row['mitigation']} | {', '.join(row['evidence'])} |"
        )
    lines += [
        "",
        "## Guardrails",
        "",
        "- Production remains no-go until live schema, RLS launch, and customer access verification all pass with production_verified=true.",
        "- Scores are opportunity signals, not homeowner purchase intent.",
        "- Public/open data requires dataset-level licence review before production import.",
        "- Secret values must stay in environment variables or a secret manager, never in reports or portable data-room files.",
        "",
    ]
    return "\n".join(lines)


def _write_security_questionnaire_csv(path: Path, questions: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["domain", "status", "owner", "question", "answer", "evidence", "caveat"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in questions:
            writer.writerow({
                "domain": row["domain"],
                "status": row["status"],
                "owner": row["owner"],
                "question": row["question"],
                "answer": row["answer"],
                "evidence": "; ".join(row["evidence"]),
                "caveat": row["caveat"],
            })


def _write_procurement_risk_csv(path: Path, risks: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["severity", "status", "owner", "risk", "mitigation", "evidence"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in risks:
            writer.writerow({
                "severity": row["severity"],
                "status": row["status"],
                "owner": row["owner"],
                "risk": row["risk"],
                "mitigation": row["mitigation"],
                "evidence": "; ".join(row["evidence"]),
            })


def build_support_readiness_pack(report: dict[str, Any]) -> dict[str, Any]:
    decisions = report["decisions"]
    production_go = decisions.get("production") == "go"
    live_go = decisions.get("live_launch") == "go"
    tiers = [
        {
            "priority": "P1",
            "label": "Critical access, data exposure, or production outage",
            "examples": "Cross-tenant/partner visibility, suspected secret leak, live RLS failure, portal unavailable for all customer users.",
            "target_acknowledgement": "1 business hour draft target",
            "target_update": "Every 2 business hours until contained",
            "owner": "HomePilot operator / IT-security owner",
            "status": "draft_pending_live_channels" if not production_go else "ready_pending_contract",
        },
        {
            "priority": "P2",
            "label": "Campaign-blocking workflow issue",
            "examples": "Scoped export fails, partner package cannot be generated, live dashboard data is materially wrong for an active campaign.",
            "target_acknowledgement": "4 business hours draft target",
            "target_update": "Every business day until resolved",
            "owner": "Customer success owner / HomePilot operator",
            "status": "draft_pending_live_channels" if not live_go else "ready_pending_contract",
        },
        {
            "priority": "P3",
            "label": "Non-blocking data, report, or refresh issue",
            "examples": "Source refresh delay, enrichment backlog question, report wording issue, metric reconciliation request.",
            "target_acknowledgement": "Next business day draft target",
            "target_update": "At agreed checkpoint or next release-room update",
            "owner": "HomePilot operator / analytics owner",
            "status": "ready_for_buyer_review",
        },
        {
            "priority": "P4",
            "label": "Training, usage, and advisory request",
            "examples": "Dashboard walkthrough, partner onboarding question, new module discussion, first-campaign operating advice.",
            "target_acknowledgement": "2 business days draft target",
            "target_update": "Scheduled with customer success cadence",
            "owner": "Customer success owner",
            "status": "ready_for_buyer_review",
        },
    ]
    escalation = [
        {
            "trigger": "Suspected tenant/module/partner leakage",
            "priority": "P1",
            "primary_owner": "IT/security owner",
            "backup_owner": "HomePilot operator",
            "first_action": "Disable affected customer access, preserve evidence, rerun scoped package/RLS verification, and open incident log.",
            "evidence": ["CUSTOMER_ACCESS_VERIFICATION.md", "PRODUCTION_PROOF.md", "MONITORING_RUNBOOK.md"],
            "channel_needed": "Security escalation channel before production",
        },
        {
            "trigger": "Portal or export unavailable for active campaign",
            "priority": "P2",
            "primary_owner": "Customer success owner",
            "backup_owner": "HomePilot operator",
            "first_action": "Confirm scope, reproduce with current package/export manifest, communicate workaround, and schedule fix.",
            "evidence": ["PORTAL_README.md", "HOSTING_RUNBOOK.md", "BOARDROOM_DATA_ROOM_INDEX.md"],
            "channel_needed": "Customer success channel before first campaign",
        },
        {
            "trigger": "Metric disagreement or executive reporting question",
            "priority": "P3",
            "primary_owner": "Analytics owner / HomePilot operator",
            "backup_owner": "Customer success owner",
            "first_action": "Reconcile against data dictionary, source ledger, dashboard snapshot, and denominator caveats.",
            "evidence": ["DATA_DICTIONARY.md", "SOURCE_LEDGER.md", "BOARDROOM_REPORT.md"],
            "channel_needed": "Named analytics reviewer before first boardroom review",
        },
        {
            "trigger": "Partner onboarding or training request",
            "priority": "P4",
            "primary_owner": "Partner manager",
            "backup_owner": "Customer success owner",
            "first_action": "Use rollout training modules, partner cutdown pack, and assigned-record-only guardrail walkthrough.",
            "evidence": ["CUSTOMER_ROLLOUT_PLAN.md", "partner_cutdown_manifest.json", "ROLLOUT_WORKSTREAMS.csv"],
            "channel_needed": "Partner manager contact list before first partner wave",
        },
    ]
    incident_steps = [
        {
            "step": "Detect and classify",
            "owner": "First responder",
            "action": "Classify P1-P4, record tenant/module/partner scope, affected artifact/user, and discovery time.",
            "output": "Incident log entry",
        },
        {
            "step": "Contain",
            "owner": "IT/security owner / HomePilot operator",
            "action": "For access or leakage concerns, pause affected access/package sharing and preserve current evidence.",
            "output": "Containment note and affected-scope list",
        },
        {
            "step": "Verify scope",
            "owner": "HomePilot operator",
            "action": "Rerun relevant package audit, export manifest check, RLS/customer-access probe, or source-ledger reconciliation.",
            "output": "Verification report path and pass/fail summary",
        },
        {
            "step": "Communicate",
            "owner": "Customer success owner",
            "action": "Send customer-facing update with impact, current status, next checkpoint, and owner.",
            "output": "Customer update record",
        },
        {
            "step": "Remediate",
            "owner": "Assigned technical owner",
            "action": "Apply scoped fix, regenerate affected evidence, and re-run the relevant verifier before reopening access.",
            "output": "Updated artifact and verifier output",
        },
        {
            "step": "Archive and learn",
            "owner": "HomePilot operator / executive sponsor",
            "action": "Archive final evidence, root cause, customer impact, prevention item, and whether SLA targets were met.",
            "output": "Post-incident review",
        },
    ]
    service_boundaries = {
        "included": [
            "Data-room and buyer-review evidence regeneration.",
            "Tenant/module/partner scope triage for packages, dashboards, and exports.",
            "First-campaign support for partner cutdowns, response memory, and boardroom reporting.",
            "Metric reconciliation against data dictionary, source ledger, and dashboard snapshots.",
            "Live launch verification support after credentials and customer test users are supplied.",
        ],
        "requires_customer_input": [
            "Named production escalation contacts and channels.",
            "Final SLA response targets, service hours, and holiday calendar.",
            "Customer-specific retention/legal terms and public-data approvals.",
            "Live Supabase credentials, customer invitees, and vendor endpoint approvals.",
        ],
        "excluded": [
            "Legal advice or final privacy/legal signoff.",
            "Guarantees for unsupported third-party public datasets or unapproved vendors.",
            "Production operation before live schema, RLS, and customer access proof pass.",
            "Sharing or storing secret values in reports, emails, or portable data-room files.",
        ],
    }
    return {
        "pack_type": "homepilot_support_sla_plan",
        "created_at": utc_now(),
        "release_label": report["release_label"],
        "status": "production_support_ready" if production_go else "buyer_review_support_ready",
        "decisions": decisions,
        "not_contractual_sla": True,
        "summary": {
            "priority_tiers": len(tiers),
            "escalation_triggers": len(escalation),
            "incident_steps": len(incident_steps),
            "production_go": production_go,
            "live_launch_go": live_go,
        },
        "priority_tiers": tiers,
        "escalation_matrix": escalation,
        "incident_response": incident_steps,
        "service_boundaries": service_boundaries,
        "guardrails": {
            "production_requires_live_proof": True,
            "no_secrets_in_support_artifacts": True,
            "tenant_module_partner_scope_required": True,
            "legal_terms_require_customer_signoff": True,
        },
    }


def render_support_sla_markdown(pack: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Support & SLA Plan",
        "",
        f"Release: {pack['release_label']}",
        f"Created: {pack['created_at']}",
        f"Status: {pack['status']}",
        "",
        "This is an operational support model for enterprise review, not a signed contractual SLA.",
        "",
        "## Priority Tiers",
        "",
        "| Priority | Status | Owner | Target Acknowledgement | Target Update | Examples |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in pack["priority_tiers"]:
        lines.append(
            f"| {row['priority']} {row['label']} | {row['status']} | {row['owner']} | "
            f"{row['target_acknowledgement']} | {row['target_update']} | {row['examples']} |"
        )
    lines += [
        "",
        "## Service Boundaries",
        "",
        "Included:",
    ]
    lines.extend(f"- {item}" for item in pack["service_boundaries"]["included"])
    lines += ["", "Requires Customer Input:"]
    lines.extend(f"- {item}" for item in pack["service_boundaries"]["requires_customer_input"])
    lines += ["", "Excluded:"]
    lines.extend(f"- {item}" for item in pack["service_boundaries"]["excluded"])
    lines += [
        "",
        "## Guardrails",
        "",
        "- Production support depends on live schema, RLS launch, and customer access verification passing with production_verified=true.",
        "- Secret values must stay in environment variables or a secret manager, never in support artifacts.",
        "- Tenant, module, partner, and campaign scope must be preserved in every support investigation.",
        "- Final legal, retention, and SLA terms require customer signoff.",
        "",
    ]
    return "\n".join(lines)


def render_incident_playbook_markdown(pack: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Incident Response Playbook",
        "",
        f"Release: {pack['release_label']}",
        f"Created: {pack['created_at']}",
        "",
        "## Response Steps",
        "",
        "| Step | Owner | Action | Output |",
        "| --- | --- | --- | --- |",
    ]
    for row in pack["incident_response"]:
        lines.append(f"| {row['step']} | {row['owner']} | {row['action']} | {row['output']} |")
    lines += [
        "",
        "## Escalation Triggers",
        "",
        "| Priority | Trigger | Primary Owner | First Action | Evidence | Channel Needed |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in pack["escalation_matrix"]:
        lines.append(
            f"| {row['priority']} | {row['trigger']} | {row['primary_owner']} | {row['first_action']} | "
            f"{', '.join(row['evidence'])} | {row['channel_needed']} |"
        )
    lines.append("")
    return "\n".join(lines)


def _write_support_escalation_csv(path: Path, escalation: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["priority", "trigger", "primary_owner", "backup_owner", "first_action", "evidence", "channel_needed"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in escalation:
            writer.writerow({
                "priority": row["priority"],
                "trigger": row["trigger"],
                "primary_owner": row["primary_owner"],
                "backup_owner": row["backup_owner"],
                "first_action": row["first_action"],
                "evidence": "; ".join(row["evidence"]),
                "channel_needed": row["channel_needed"],
            })


def build_customer_pilot_proposal(report: dict[str, Any]) -> dict[str, Any]:
    decisions = report["decisions"]
    buyer_go = decisions.get("buyer_review") == "go"
    live_go = decisions.get("live_launch") == "go"
    production_go = decisions.get("production") == "go"
    deliverables = [
        {
            "phase": "Buyer review",
            "deliverable": "Boardroom evidence room",
            "owner": "HomePilot operator / sales lead",
            "description": "Portable data room with scorecard, boardroom report, governance, rollout, procurement/security, support, and proof caveats.",
            "acceptance": "Customer can inspect the evidence room without local paths, secrets, or live production overclaims.",
            "evidence": ["homepilot_boardroom_data_room.zip", "MARKET_READINESS_SCORECARD.md"],
            "status": "ready" if buyer_go else "action_required",
        },
        {
            "phase": "Pilot setup",
            "deliverable": "Tenant/module/partner scope confirmation",
            "owner": "Executive sponsor / customer success owner",
            "description": "Confirm first tenant, first module, producer/partner users, partner territories, campaign batch, and success metrics.",
            "acceptance": "Pilot scope checklist is completed and accepted before live setup.",
            "evidence": ["PILOT_SCOPE_CHECKLIST.csv", "CUSTOMER_ROLLOUT_PLAN.md"],
            "status": "ready_for_customer_input",
        },
        {
            "phase": "Live launch",
            "deliverable": "Production access proof",
            "owner": "IT/security owner / HomePilot operator",
            "description": "Run live schema verification, RLS launch fixture, and customer-access verification with production_verified=true.",
            "acceptance": "Production proof is archived before paying customer access is enabled.",
            "evidence": ["LIVE_LAUNCH_REQUEST.md", "PRODUCTION_PROOF.md"],
            "status": "blocked" if not production_go else "ready",
        },
        {
            "phase": "First campaign",
            "deliverable": "Partner-scoped campaign package",
            "owner": "Customer success owner / partner manager",
            "description": "Generate scoped dashboards, exports, boardroom report, partner cutdowns, territory plan, response learning, and ROI forecast.",
            "acceptance": "Partners see only assigned records and DAW/producer sees aggregate network performance.",
            "evidence": ["BOARDROOM_REPORT.md", "partner_cutdown_manifest.json", "ROI_FORECAST.md"],
            "status": "blocked" if not production_go else "ready",
        },
        {
            "phase": "Optimization",
            "deliverable": "Learning and expansion review",
            "owner": "Executive sponsor / customer success owner",
            "description": "Review response/no-response patterns, objections, partner capacity, next territory, next module, and source-enrichment backlog.",
            "acceptance": "Customer receives recommended next campaign and expansion decision options.",
            "evidence": ["CAMPAIGN_LEARNING.md", "TERRITORY_PLAN.md", "DATA_VENDOR_PLAN.md"],
            "status": "blocked" if not production_go else "ready",
        },
    ]
    milestones = [
        {
            "milestone": "M0 buyer review",
            "timing": "Before commercial signoff",
            "owner": "Executive sponsor / sales lead",
            "exit_condition": "Data room accepted for buyer review and production blockers understood.",
            "status": "ready" if buyer_go else "action_required",
        },
        {
            "milestone": "M1 pilot kickoff",
            "timing": "After buyer review",
            "owner": "Customer success owner",
            "exit_condition": "Pilot scope, partner list, campaign batch, support contacts, and secret channel confirmed.",
            "status": "ready_for_customer_input",
        },
        {
            "milestone": "M2 live proof",
            "timing": "Before customer access",
            "owner": "IT/security owner / HomePilot operator",
            "exit_condition": "Live schema, RLS launch, and customer access verification all pass with production_verified=true.",
            "status": "blocked" if not production_go else "ready",
        },
        {
            "milestone": "M3 first campaign package",
            "timing": "After live proof",
            "owner": "Campaign owner / partner manager",
            "exit_condition": "Scoped dashboard/export/partner package generated and access-audited.",
            "status": "blocked" if not production_go else "ready",
        },
        {
            "milestone": "M4 pilot readout",
            "timing": "After first response cycle",
            "owner": "Executive sponsor / customer success owner",
            "exit_condition": "Learning review completed with next campaign/module recommendation.",
            "status": "blocked" if not production_go else "ready",
        },
    ]
    success_metrics = [
        "Zero tenant/module/partner leakage in packages, exports, and live RLS probes.",
        "First campaign response rate reported with explicit denominator.",
        "Partner onboarding completed for the agreed first partner wave.",
        "No-response backlog and top objections converted into next-wave experiments.",
        "Customer can export scoped data and reconcile metrics against the data dictionary and source ledger.",
        "Production proof archived before any paying customer access is enabled.",
    ]
    assumptions = [
        {
            "category": "Commercial",
            "assumption": "Pilot pricing, invoicing, and term length are placeholders until agreed with the customer.",
            "status": "customer_decision_required",
        },
        {
            "category": "Scope",
            "assumption": "Initial enterprise pilot is designed for one producer tenant, one first module, and an agreed partner wave, with expansion after pilot readout.",
            "status": "ready_for_buyer_review",
        },
        {
            "category": "Data",
            "assumption": "Synthetic demo metrics are not live customer performance and cannot be used as production claims.",
            "status": "guardrail",
        },
        {
            "category": "Live launch",
            "assumption": "Live Supabase credentials, customer test users, and customer access credentials must be supplied through the agreed secret channel.",
            "status": "blocked" if not live_go else "ready",
        },
        {
            "category": "Legal/privacy",
            "assumption": "Customer legal/privacy review controls contact basis, retention terms, public-data approvals, and final DPA/procurement language.",
            "status": "customer_decision_required",
        },
        {
            "category": "Support",
            "assumption": "Support targets are draft operational targets until final SLA terms, service hours, and escalation channels are agreed.",
            "status": "customer_decision_required",
        },
    ]
    return {
        "proposal_type": "homepilot_customer_pilot_proposal",
        "created_at": utc_now(),
        "release_label": report["release_label"],
        "status": "buyer_review_proposal_ready" if buyer_go else "action_required",
        "decisions": decisions,
        "not_contractual_offer": True,
        "recommended_pilot": {
            "customer_pattern": "DAW-style producer network",
            "initial_module": "facadepilot",
            "tenant_model": "one producer tenant with partner-scoped renovator access",
            "partner_wave": "up to 10 renovators in the first Belgian producer network wave",
            "campaign_goal": "prove scoped property intelligence, partner handoff, response memory, and next-wave recommendations before scale-up",
        },
        "deliverables": deliverables,
        "milestones": milestones,
        "success_metrics": success_metrics,
        "commercial_assumptions": assumptions,
        "out_of_scope": [
            "Signed legal contract, DPA, final SLA, or fixed pricing terms.",
            "Live customer access before production proof passes.",
            "Unapproved public-data imports, owner data, non-public EPC data, or scraped personal contact data.",
            "Guaranteed homeowner response, purchase intent, or renovation conversion.",
            "Cross-customer raw data sharing or partner visibility into another partner's records.",
        ],
        "decision_requests": [
            "Approve first tenant/module/partner scope.",
            "Choose pilot commercial model and billing owner.",
            "Nominate executive, IT/security, legal/privacy, customer success, and partner-manager owners.",
            "Approve secret channel and live launch input owner.",
            "Confirm first campaign territory, partner capacity, and response follow-up SLA.",
        ],
        "guardrails": {
            "production_requires_live_proof": True,
            "scores_are_not_homeowner_intent": True,
            "tenant_module_partner_scope_required": True,
            "pricing_requires_customer_agreement": True,
        },
    }


def render_customer_pilot_proposal_markdown(proposal: dict[str, Any]) -> str:
    pilot = proposal["recommended_pilot"]
    lines = [
        "# HomePilot Customer Pilot Proposal",
        "",
        f"Release: {proposal['release_label']}",
        f"Created: {proposal['created_at']}",
        f"Status: {proposal['status']}",
        "",
        "This is a buyer-review pilot proposal, not a signed contractual offer.",
        "",
        "## Recommended Pilot",
        "",
        f"- Customer pattern: {pilot['customer_pattern']}",
        f"- Initial module: {pilot['initial_module']}",
        f"- Tenant model: {pilot['tenant_model']}",
        f"- Partner wave: {pilot['partner_wave']}",
        f"- Campaign goal: {pilot['campaign_goal']}",
        "",
        "## Deliverables",
        "",
        "| Phase | Status | Owner | Deliverable | Acceptance | Evidence |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in proposal["deliverables"]:
        lines.append(
            f"| {row['phase']} | {row['status']} | {row['owner']} | {row['deliverable']} - {row['description']} | "
            f"{row['acceptance']} | {', '.join(row['evidence'])} |"
        )
    lines += [
        "",
        "## Milestones",
        "",
        "| Milestone | Timing | Status | Owner | Exit Condition |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in proposal["milestones"]:
        lines.append(f"| {row['milestone']} | {row['timing']} | {row['status']} | {row['owner']} | {row['exit_condition']} |")
    lines += [
        "",
        "## Success Metrics",
        "",
    ]
    lines.extend(f"- {metric}" for metric in proposal["success_metrics"])
    lines += ["", "## Commercial Assumptions", ""]
    for row in proposal["commercial_assumptions"]:
        lines.append(f"- {row['category']} ({row['status']}): {row['assumption']}")
    lines += ["", "## Out Of Scope", ""]
    lines.extend(f"- {item}" for item in proposal["out_of_scope"])
    lines += ["", "## Decisions Requested", ""]
    lines.extend(f"- {item}" for item in proposal["decision_requests"])
    lines += [
        "",
        "## Guardrails",
        "",
        "- Production remains no-go until live schema, RLS launch, and customer access verification all pass with production_verified=true.",
        "- Scores are opportunity signals, not homeowner purchase intent.",
        "- Tenant, module, partner, and campaign scope must be preserved in every pilot artifact.",
        "- Pricing, legal terms, final SLA, and DPA language require customer agreement.",
        "",
    ]
    return "\n".join(lines)


def _write_pilot_scope_csv(path: Path, proposal: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["milestone", "timing", "status", "owner", "exit_condition"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in proposal["milestones"]:
            writer.writerow({field: row.get(field, "") for field in fields})


def _write_commercial_assumptions_csv(path: Path, proposal: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["category", "status", "assumption"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in proposal["commercial_assumptions"]:
            writer.writerow({field: row.get(field, "") for field in fields})


def build_customer_training_plan(report: dict[str, Any]) -> dict[str, Any]:
    decisions = report["decisions"]
    buyer_go = decisions.get("buyer_review") == "go"
    production_go = decisions.get("production") == "go"
    roles = [
        {
            "role": "Executive sponsor",
            "can_see": "Boardroom scorecard, pilot proposal, commercial assumptions, rollout status, production blockers.",
            "must_not_see": "Partner-renovator-only raw rows, raw cross-tenant data, secrets, or unredacted local paths.",
            "primary_artifacts": ["MARKET_READINESS_SCORECARD.md", "CUSTOMER_PILOT_PROPOSAL.md", "COMMERCIAL_ASSUMPTIONS.csv"],
            "first_actions": "Approve first tenant/module/partner scope, name owners, and decide pilot go/no-go.",
            "guardrails": "Buyer review can be go while production remains no-go until live proof passes.",
        },
        {
            "role": "DAW producer/network manager",
            "can_see": "Aggregate producer-network performance, partner comparison, territories, response/no-response learning, and partner drilldowns.",
            "must_not_see": "Other tenants' raw campaigns, unapproved benchmark details, secrets, or unsupported homeowner-intent claims.",
            "primary_artifacts": ["BOARDROOM_REPORT.md", "CUSTOMER_ROLLOUT_PLAN.md", "ROLE_CHEATSHEET.csv"],
            "first_actions": "Confirm the renovator list, territories, partner capacities, first campaign wave, and response follow-up rhythm.",
            "guardrails": "Scores are opportunity signals; only responses, appointments, or customers indicate explicit engagement.",
        },
        {
            "role": "Partner renovator",
            "can_see": "Assigned properties, own campaign statuses, own follow-up queue, scoped exports, and own partner report.",
            "must_not_see": "Another partner's assigned addresses, responses, pipeline values, notes, or campaign learning.",
            "primary_artifacts": ["partner_cutdown_manifest.json", "CUSTOMER_TRAINING_GUIDE.md", "ROLE_CHEATSHEET.csv"],
            "first_actions": "Open assigned-record-only package, review top opportunities, update follow-up status, and report capacity constraints.",
            "guardrails": "Partner access must be tenant, module, campaign, and partner scoped before any live customer access.",
        },
        {
            "role": "IT/security owner",
            "can_see": "Procurement/security pack, SQL apply plan, API contract, production proof, live launch checklist, support escalation.",
            "must_not_see": "Secret values in artifacts, personal contact data without legal basis, or production claims without live reports.",
            "primary_artifacts": ["PROCUREMENT_SECURITY_REVIEW.md", "SQL_APPLY_PLAN.md", "PRODUCTION_PROOF.md"],
            "first_actions": "Review SQL/apply plan, approve secret channel, provide live inputs, and verify live schema/RLS/customer access evidence.",
            "guardrails": "No production access until live schema, RLS launch, and customer access reports all pass with production_verified=true.",
        },
        {
            "role": "Customer success / campaign operator",
            "can_see": "Rollout workstreams, training sessions, support plan, first campaign queues, exports, and response memory.",
            "must_not_see": "Raw cross-tenant learnings, unapproved public-data imports, or partner data outside the assigned support scope.",
            "primary_artifacts": ["CUSTOMER_TRAINING_GUIDE.md", "TRAINING_SESSION_PLAN.csv", "SUPPORT_SLA_PLAN.md"],
            "first_actions": "Schedule training, validate invitees, rehearse exports, and prepare first campaign support cadence.",
            "guardrails": "Support/SLA targets are draft until final customer agreement; sensitive data stays scoped.",
        },
        {
            "role": "Analyst / HomePilot operator",
            "can_see": "Data dictionary, source ledger, metric caveats, release evidence, portable data-room manifest, and regeneration commands.",
            "must_not_see": "Secrets, unsupported scraped personal signals, or customer-identifying cross-tenant examples in shared outputs.",
            "primary_artifacts": ["DATA_DICTIONARY.md", "SOURCE_LEDGER.md", "DATA_ROOM_MANIFEST.json"],
            "first_actions": "Reconcile metrics, regenerate packs, verify portable redaction, and document source freshness before customer use.",
            "guardrails": "Public data requires dataset-level licence/provenance review before production import.",
        },
    ]
    sessions = [
        {
            "session": "Boardroom walkthrough",
            "audience": "Executive sponsor, DAW leadership, sales lead",
            "duration": "45 min",
            "objective": "Explain the value story, buyer-review status, live blockers, and what the demo proves versus does not prove.",
            "materials": ["MARKET_READINESS_SCORECARD.md", "CUSTOMER_PILOT_PROPOSAL.md", "market-readiness.html"],
            "exit_check": "Sponsor can explain why buyer review is go and production is still no-go.",
        },
        {
            "session": "DAW producer/network manager session",
            "audience": "DAW network manager, partner manager, customer success",
            "duration": "60 min",
            "objective": "Use partner comparison, territory view, response/no-response learning, and campaign queues to steer ten renovators.",
            "materials": ["BOARDROOM_REPORT.md", "CUSTOMER_ROLLOUT_PLAN.md", "ROLE_CHEATSHEET.csv"],
            "exit_check": "Manager can choose a partner wave, explain visibility, and name first follow-up actions.",
        },
        {
            "session": "Partner renovator session",
            "audience": "Partner renovators and partner manager",
            "duration": "45 min",
            "objective": "Show assigned-record-only package, top opportunities, follow-up statuses, exports, and support route.",
            "materials": ["partner_cutdown_manifest.json", "ROLE_CHEATSHEET.csv", "SUPPORT_ESCALATION_MATRIX.csv"],
            "exit_check": "Partner can confirm they see only their own assigned records and know how to update status.",
        },
        {
            "session": "IT/security proof session",
            "audience": "IT/security owner, database owner, HomePilot operator",
            "duration": "60 min",
            "objective": "Review SQL apply plan, API contract, RLS expectations, production proof, live launch inputs, and evidence archive.",
            "materials": ["PROCUREMENT_SECURITY_REVIEW.md", "SQL_APPLY_PLAN.md", "PRODUCTION_PROOF.md"],
            "exit_check": "IT owner can list the exact live reports required before customer access.",
        },
        {
            "session": "Public-data provenance session",
            "audience": "Legal/privacy owner, IT/security owner, analyst, HomePilot operator",
            "duration": "45 min",
            "objective": "Review which official/open-data lanes may enrich prioritization and how homepilot_source_runs, homepilot_geographies, homepilot_public_features, and homepilot_property_enrichments keep licence/provenance separate from campaign contact basis.",
            "materials": ["PUBLIC_DATA_SOURCE_REGISTER.md", "PUBLIC_DATA_SOURCE_MATRIX.csv", "ATTRIBUTION_REQUIREMENTS.csv"],
            "exit_check": "Reviewer can name the approved enrichment tables, blocked owner/EPC/contact lanes, and dataset-level licence gate before any production import.",
        },
        {
            "session": "Customer success operations session",
            "audience": "Customer success owner, campaign operator, support owner",
            "duration": "60 min",
            "objective": "Run the first-campaign workflow: invitees, training, exports, response memory, no-response backlog, escalation, and follow-up cadence.",
            "materials": ["TRAINING_SESSION_PLAN.csv", "SUPPORT_SLA_PLAN.md", "ROLLOUT_WORKSTREAMS.csv"],
            "exit_check": "Operator can schedule training, export scoped data, and route P1/P2 support issues.",
        },
        {
            "session": "Analyst/operator evidence refresh session",
            "audience": "Analyst, HomePilot operator",
            "duration": "45 min",
            "objective": "Refresh the data dictionary, source ledger, portable manifest, scorecard, and release pack without leaking local paths or secrets.",
            "materials": ["DATA_DICTIONARY.md", "SOURCE_LEDGER.md", "DATA_ROOM_MANIFEST.json"],
            "exit_check": "Operator can regenerate and verify the data room before the next customer review.",
        },
    ]
    checkpoints = [
        {
            "stage": "buyer_review",
            "checkpoint": "All buyer-facing roles understand what is demo evidence, what is production proof, and what remains blocked.",
            "status": "ready" if buyer_go else "action_required",
        },
        {
            "stage": "pilot_kickoff",
            "checkpoint": "DAW confirms partner wave, territories, invitees, support contacts, and first campaign follow-up ownership.",
            "status": "ready_for_customer_input",
        },
        {
            "stage": "live_launch",
            "checkpoint": "IT/security signs off live inputs, SQL review, and exact RLS/customer-access proof path.",
            "status": "blocked" if not production_go else "ready",
        },
        {
            "stage": "first_campaign",
            "checkpoint": "Partner renovators complete assigned-record-only walkthrough before receiving live access.",
            "status": "blocked" if not production_go else "ready",
        },
    ]
    return {
        "plan_type": "homepilot_customer_training_plan",
        "created_at": utc_now(),
        "release_label": report["release_label"],
        "status": "buyer_review_training_ready" if buyer_go else "action_required",
        "decisions": decisions,
        "roles": roles,
        "sessions": sessions,
        "adoption_checkpoints": checkpoints,
        "guardrails": {
            "synthetic_demo_not_live_performance": True,
            "scores_are_not_homeowner_intent": True,
            "production_requires_live_proof": True,
            "tenant_module_partner_scope_required": True,
            "support_sla_and_pricing_require_agreement": True,
        },
    }


def render_customer_training_guide_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Customer Training Guide",
        "",
        f"Release: {plan['release_label']}",
        f"Created: {plan['created_at']}",
        f"Status: {plan['status']}",
        "",
        "This guide turns the buyer-review data room into role-based adoption steps for DAW, partner renovators, IT/security, customer success, and HomePilot operators.",
        "",
        "## Role Playbooks",
        "",
        "| Role | Can See | Must Not See | First Actions | Guardrail |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in plan["roles"]:
        lines.append(f"| {row['role']} | {row['can_see']} | {row['must_not_see']} | {row['first_actions']} | {row['guardrails']} |")
    lines += [
        "",
        "## Training Sessions",
        "",
        "| Session | Audience | Duration | Objective | Materials | Exit Check |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in plan["sessions"]:
        lines.append(
            f"| {row['session']} | {row['audience']} | {row['duration']} | {row['objective']} | "
            f"{', '.join(row['materials'])} | {row['exit_check']} |"
        )
    lines += [
        "",
        "## Adoption Checkpoints",
        "",
        "| Stage | Status | Checkpoint |",
        "| --- | --- | --- |",
    ]
    for row in plan["adoption_checkpoints"]:
        lines.append(f"| {row['stage']} | {row['status']} | {row['checkpoint']} |")
    lines += [
        "",
        "## Guardrails",
        "",
        "- Synthetic demo metrics are not live customer performance.",
        "- A scored property is an opportunity signal, not homeowner purchase intent.",
        "- Public data must be source-attributed, licence-reviewed, and stored as enrichment/provenance, not as campaign contact basis.",
        "- Production remains no-go until live schema, RLS launch, and customer access verification all pass with production_verified=true.",
        "- Tenant, module, partner, and campaign scope must be preserved for every dashboard, export, package, and training example.",
        "- Support/SLA targets, pricing, legal terms, and DPA language stay draft until customer agreement.",
        "",
    ]
    return "\n".join(lines)


def _write_training_session_csv(path: Path, sessions: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["session", "audience", "duration", "objective", "materials", "exit_check"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in sessions:
            writer.writerow({
                "session": row["session"],
                "audience": row["audience"],
                "duration": row["duration"],
                "objective": row["objective"],
                "materials": "; ".join(row["materials"]),
                "exit_check": row["exit_check"],
            })


def _write_role_cheatsheet_csv(path: Path, roles: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["role", "can_see", "must_not_see", "primary_artifacts", "first_actions", "guardrails"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in roles:
            writer.writerow({
                "role": row["role"],
                "can_see": row["can_see"],
                "must_not_see": row["must_not_see"],
                "primary_artifacts": "; ".join(row["primary_artifacts"]),
                "first_actions": row["first_actions"],
                "guardrails": row["guardrails"],
            })


def build_value_realization_plan(report: dict[str, Any]) -> dict[str, Any]:
    decisions = report["decisions"]
    buyer_go = decisions.get("buyer_review") == "go"
    production_go = decisions.get("production") == "go"
    outcome_tracks = [
        {
            "track": "Executive value case",
            "owner": "Executive sponsor / sales lead",
            "objective": "Show why a DAW-style producer network should fund the pilot and which value questions the first campaign answers.",
            "current_status": "ready" if buyer_go else "action_required",
            "evidence": ["MARKET_READINESS_SCORECARD.md", "CUSTOMER_PILOT_PROPOSAL.md", "VALUE_REALIZATION_METRICS.csv"],
        },
        {
            "track": "Producer-network steering",
            "owner": "DAW producer/network manager",
            "objective": "Compare territories, partners, capacity, response/no-response, facade volume, and follow-up queues without exposing partner-private raw rows.",
            "current_status": "ready" if buyer_go else "action_required",
            "evidence": ["BOARDROOM_REPORT.md", "ROLE_CHEATSHEET.csv", "partner_cutdown_manifest.json"],
        },
        {
            "track": "Campaign learning loop",
            "owner": "Customer success / campaign operator",
            "objective": "Turn contacted, responded, appointment, objection, and no-response patterns into next-wave experiments.",
            "current_status": "blocked" if not production_go else "ready",
            "evidence": ["CAMPAIGN_LEARNING.md", "ROLLOUT_WORKSTREAMS.csv", "EXECUTIVE_DECISION_LOG.csv"],
        },
        {
            "track": "Trust and access proof",
            "owner": "IT/security owner",
            "objective": "Prove that tenant, module, partner, export, and customer access controls hold before customer access is enabled.",
            "current_status": "blocked" if not production_go else "ready",
            "evidence": ["PRODUCTION_PROOF.md", "CUSTOMER_ACCESS_VERIFICATION.md", "PROCUREMENT_SECURITY_REVIEW.md"],
        },
        {
            "track": "Expansion readiness",
            "owner": "Executive sponsor / HomePilot operator",
            "objective": "Decide whether to expand by territory, partner wave, or next pilot module after the first measured campaign cycle.",
            "current_status": "blocked" if not production_go else "ready",
            "evidence": ["TERRITORY_PLAN.md", "ROI_FORECAST.md", "DATA_VENDOR_PLAN.md"],
        },
    ]
    metrics = [
        {
            "metric": "Visible property count",
            "owner": "Analyst / HomePilot operator",
            "why_it_matters": "Shows the addressable scoped universe for the tenant/module/partner view.",
            "grain": "tenant/module/partner snapshot",
            "definition": "Distinct visible properties after tenant, module, and optional partner filters.",
            "baseline_source": "dashboard snapshot or homepilot_property_intelligence",
            "target_direction": "contextual",
            "guardrail": "Never compare raw cross-tenant address counts without anonymized benchmark rules.",
        },
        {
            "metric": "Top opportunity count",
            "owner": "DAW producer/network manager",
            "why_it_matters": "Prioritizes where campaign and partner capacity should go first.",
            "grain": "tenant/module/campaign or partner",
            "definition": "High-priority opportunities using the agreed A/A+ or score threshold.",
            "baseline_source": "dashboard views and boardroom report",
            "target_direction": "higher",
            "guardrail": "Scores are opportunity signals, not homeowner purchase intent.",
        },
        {
            "metric": "Estimated facade m2",
            "owner": "DAW producer/network manager",
            "why_it_matters": "Gives DAW a volume lens for crepi demand and partner capacity planning.",
            "grain": "facadepilot tenant/module/partner snapshot",
            "definition": "Sum of estimated visible facade area for scoped FacadePilot properties.",
            "baseline_source": "module metrics and dashboard snapshot",
            "target_direction": "contextual",
            "guardrail": "Proxy estimate only; not a measured survey quantity.",
        },
        {
            "metric": "Estimated pipeline value",
            "owner": "Executive sponsor",
            "why_it_matters": "Connects opportunity volume to a commercial business case.",
            "grain": "tenant/module/campaign or partner",
            "definition": "Sum of tenant-private estimated opportunity value for the scoped visible set.",
            "baseline_source": "dashboard snapshot and ROI forecast",
            "target_direction": "higher",
            "guardrail": "Commercial estimate; keep tenant-private and avoid accounting-grade claims.",
        },
        {
            "metric": "Contacted count",
            "owner": "Campaign operator",
            "why_it_matters": "Separates generated opportunities from actually touched campaign targets.",
            "grain": "campaign/module/partner",
            "definition": "Targets with sent, scanned, clicked, responded, appointment, customer, or no_response status.",
            "baseline_source": "campaign targets and campaign metrics",
            "target_direction": "higher within approved campaign scope",
            "guardrail": "Respect contact basis, opt-out, and retention controls.",
        },
        {
            "metric": "Response count",
            "owner": "Campaign operator",
            "why_it_matters": "Shows actual engagement, not just opportunity scoring.",
            "grain": "campaign/module/partner",
            "definition": "Targets with responded, appointment, or customer status.",
            "baseline_source": "campaign metrics and interactions",
            "target_direction": "higher",
            "guardrail": "Only explicit statuses count as engagement.",
        },
        {
            "metric": "Response rate pct",
            "owner": "Executive sponsor / analyst",
            "why_it_matters": "Creates a simple campaign effectiveness KPI for boardroom comparison.",
            "grain": "campaign/module/partner",
            "definition": "Response count divided by contacted count; target_response_rate_pct is kept only for all-target audit context.",
            "baseline_source": "campaign metrics and source ledger",
            "target_direction": "higher",
            "guardrail": "Label contacted response rate and all-target response rate separately.",
        },
        {
            "metric": "Appointment count",
            "owner": "Partner manager",
            "why_it_matters": "Connects campaign response to partner follow-up workload.",
            "grain": "campaign/module/partner",
            "definition": "Targets with appointment or customer conversion status, depending on the agreed report definition.",
            "baseline_source": "campaign metrics and interactions",
            "target_direction": "higher",
            "guardrail": "Standardize whether customer counts as conversion before executive reporting.",
        },
        {
            "metric": "No-response backlog",
            "owner": "Customer success / campaign operator",
            "why_it_matters": "Gives a concrete retargeting and message-variant backlog.",
            "grain": "campaign/module/partner",
            "definition": "Contacted targets currently marked no_response.",
            "baseline_source": "campaign metrics and campaign learning",
            "target_direction": "lower after follow-up",
            "guardrail": "Do not over-contact; apply contact-basis and opt-out rules.",
        },
        {
            "metric": "Partner response variance",
            "owner": "DAW producer/network manager",
            "why_it_matters": "Shows which renovators need capacity support, better territory fit, or different follow-up scripts.",
            "grain": "producer network / partner",
            "definition": "Difference between partner response rates inside the same tenant/module campaign context.",
            "baseline_source": "boardroom partner summary and campaign metrics",
            "target_direction": "lower unexplained variance",
            "guardrail": "Partner comparison stays inside the producer tenant; partners do not see each other's raw rows.",
        },
        {
            "metric": "Access audit pass",
            "owner": "IT/security owner",
            "why_it_matters": "Turns privacy and scoping into a measurable launch gate.",
            "grain": "package/access verification run",
            "definition": "All required tenant/module/partner leakage, export, and RLS/customer-access checks pass.",
            "baseline_source": "access audit, partner cutdown manifest, customer access verification, production proof",
            "target_direction": "pass",
            "guardrail": "Production access requires live RLS/customer JWT proof, not only local package checks.",
        },
        {
            "metric": "Evidence freshness",
            "owner": "HomePilot operator",
            "why_it_matters": "Keeps the customer from buying on stale demo or outdated source assumptions.",
            "grain": "release pack / source inventory",
            "definition": "Required evidence artifacts exist, are current enough for the review, and have source caveats recorded.",
            "baseline_source": "artifact index, production proof, source inventory",
            "target_direction": "fresh",
            "guardrail": "Public-data licences and live production sources must be rechecked before customer claims.",
        },
    ]
    decisions_log = [
        {
            "decision": "Accept buyer-review evidence room",
            "owner": "Executive sponsor",
            "due_stage": "buyer_review",
            "required_evidence": ["homepilot_boardroom_data_room.zip", "MARKET_READINESS_SCORECARD.md", "CUSTOMER_PILOT_PROPOSAL.md"],
            "exit_criteria": "Customer accepts the value story, caveats, pilot scope, and remaining live blockers.",
            "current_status": "ready" if buyer_go else "action_required",
        },
        {
            "decision": "Approve value metric baseline",
            "owner": "Executive sponsor / analyst",
            "due_stage": "pilot_kickoff",
            "required_evidence": ["VALUE_REALIZATION_METRICS.csv", "DATA_DICTIONARY.md", "BOARDROOM_REPORT.md"],
            "exit_criteria": "Customer agrees the first-campaign KPIs, denominators, and which metrics are tenant-private.",
            "current_status": "ready_for_customer_input",
        },
        {
            "decision": "Release live launch inputs",
            "owner": "IT/security owner",
            "due_stage": "live_launch",
            "required_evidence": ["LIVE_LAUNCH_REQUEST.md", "LIVE_LAUNCH_CHECKLIST.csv", "SQL_APPLY_PLAN.md"],
            "exit_criteria": "Supabase and customer-access inputs exist through the agreed secret channel.",
            "current_status": "blocked" if not production_go else "ready",
        },
        {
            "decision": "Enable first customer access",
            "owner": "IT/security owner / HomePilot operator",
            "due_stage": "production_rollout",
            "required_evidence": ["PRODUCTION_PROOF.md", "schema_verification.json", "customer_access_verification.json"],
            "exit_criteria": "Live schema, RLS launch, and customer access all pass with production_verified=true.",
            "current_status": "blocked" if not production_go else "ready",
        },
        {
            "decision": "Launch first campaign wave",
            "owner": "DAW producer/network manager",
            "due_stage": "first_campaign",
            "required_evidence": ["TERRITORY_PLAN.md", "ROLLOUT_WORKSTREAMS.csv", "partner_cutdown_manifest.json"],
            "exit_criteria": "Partner wave, territories, capacity, follow-up SLA, and scoped packages are approved.",
            "current_status": "blocked" if not production_go else "ready",
        },
        {
            "decision": "Scale, repeat, or pause",
            "owner": "Executive sponsor",
            "due_stage": "pilot_readout",
            "required_evidence": ["CAMPAIGN_LEARNING.md", "ROI_FORECAST.md", "VALUE_REALIZATION_METRICS.csv"],
            "exit_criteria": "Customer reviews response/no-response, partner performance, ROI assumptions, and next territory/module options.",
            "current_status": "blocked" if not production_go else "ready",
        },
    ]
    return {
        "plan_type": "homepilot_value_realization_plan",
        "created_at": utc_now(),
        "release_label": report["release_label"],
        "status": "buyer_review_value_ready" if buyer_go else "action_required",
        "decisions": decisions,
        "outcome_tracks": outcome_tracks,
        "metrics": metrics,
        "decision_log": decisions_log,
        "guardrails": {
            "synthetic_demo_not_live_performance": True,
            "scores_are_not_homeowner_intent": True,
            "response_rate_denominator_required": True,
            "tenant_private_value_metrics": True,
            "production_requires_live_proof": True,
        },
    }


def render_value_realization_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Value Realization Plan",
        "",
        f"Release: {plan['release_label']}",
        f"Created: {plan['created_at']}",
        f"Status: {plan['status']}",
        "",
        "This plan explains how a buyer turns the HomePilot data room into a measurable business case after the first campaign cycle.",
        "",
        "## Outcome Tracks",
        "",
        "| Track | Status | Owner | Objective | Evidence |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in plan["outcome_tracks"]:
        lines.append(
            f"| {row['track']} | {row['current_status']} | {row['owner']} | {row['objective']} | {', '.join(row['evidence'])} |"
        )
    lines += [
        "",
        "## Value Metrics",
        "",
        "| Metric | Owner | Grain | Definition | Target Direction | Guardrail |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in plan["metrics"]:
        lines.append(
            f"| {row['metric']} | {row['owner']} | {row['grain']} | {row['definition']} | "
            f"{row['target_direction']} | {row['guardrail']} |"
        )
    lines += [
        "",
        "## Executive Decision Log",
        "",
        "| Decision | Stage | Status | Owner | Exit Criteria | Evidence |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in plan["decision_log"]:
        lines.append(
            f"| {row['decision']} | {row['due_stage']} | {row['current_status']} | {row['owner']} | "
            f"{row['exit_criteria']} | {', '.join(row['required_evidence'])} |"
        )
    lines += [
        "",
        "## Guardrails",
        "",
        "- Synthetic demo metrics are not live customer performance.",
        "- Opportunity scores are not homeowner purchase intent.",
        "- Response rate must always state its denominator.",
        "- Estimated value, partner performance, and pipeline metrics are tenant-private unless a separate aggregate benchmark policy applies.",
        "- Production remains no-go until live schema, RLS launch, and customer access verification all pass with production_verified=true.",
        "",
    ]
    return "\n".join(lines)


def _write_value_metrics_csv(path: Path, metrics: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["metric", "owner", "why_it_matters", "grain", "definition", "baseline_source", "target_direction", "guardrail"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in metrics:
            writer.writerow({field: row.get(field, "") for field in fields})


def _write_decision_log_csv(path: Path, decisions_log: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["decision", "owner", "due_stage", "required_evidence", "exit_criteria", "current_status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in decisions_log:
            writer.writerow({
                "decision": row["decision"],
                "owner": row["owner"],
                "due_stage": row["due_stage"],
                "required_evidence": "; ".join(row["required_evidence"]),
                "exit_criteria": row["exit_criteria"],
                "current_status": row["current_status"],
            })


def build_module_expansion_plan(report: dict[str, Any]) -> dict[str, Any]:
    decisions = report["decisions"]
    buyer_go = decisions.get("buyer_review") == "go"
    production_go = decisions.get("production") == "go"
    module_context = {
        "facadepilot": {
            "buyer_question": "Where is facade/crepi renovation demand highest and which partner should follow up first?",
            "initial_play": "DAW-style producer network, partner renovator campaigns, facade m2 volume, response/no-response memory.",
            "public_data_candidates": "BeSt address match, parcel/building geometry, statistical sector building age/income context where licensed.",
            "expansion_trigger": "First facade campaign proves partner-scoped access and response learning.",
        },
        "windowpilot": {
            "buyer_question": "Which homes have visible window replacement or energy-upgrade signals?",
            "initial_play": "Energy story, glazing/frame signals, visible window count, replacement urgency, cross-sell after facade outreach.",
            "public_data_candidates": "Official address/geography, building-age context, renovation policy context; avoid non-public EPC reuse.",
            "expansion_trigger": "Facade response mentions comfort, energy, insulation, or visible window condition.",
        },
        "roofpilot": {
            "buyer_question": "Which roofs show renovation, solar, moss, storm, or material opportunities?",
            "initial_play": "Roof score, area, age/material signal, solar cross-sell fit, territory clustering.",
            "public_data_candidates": "Building footprint, roof/parcel geometry where licensed, weather/storm context only with source approval.",
            "expansion_trigger": "Territory has high exterior renovation density or customer wants envelope bundle campaigns.",
        },
        "gardenpilot": {
            "buyer_question": "Which homes have outdoor-living, privacy, maintenance, or garden-upgrade potential?",
            "initial_play": "Garden area, outdoor living fit, privacy fit, maintenance signal, seasonal campaign planning.",
            "public_data_candidates": "Parcel/garden geometry, land-use context, flood/soil themes only after licence review.",
            "expansion_trigger": "Partner network adds outdoor contractors or first-wave households show outdoor-project objections.",
        },
        "poolpilot": {
            "buyer_question": "Which properties fit high-value pool campaigns without overclaiming purchase intent?",
            "initial_play": "Pool fit, sun exposure, access quality, terrain complexity, premium outdoor segmentation.",
            "public_data_candidates": "Parcel/garden geometry, sun/terrain context where licensed, no personal wealth inference without legal basis.",
            "expansion_trigger": "Customer wants premium outdoor upsell after garden or facade segmentation is trusted.",
        },
        "porchpilot": {
            "buyer_question": "Which front-house entries can support porch or entrance upgrade campaigns?",
            "initial_play": "Entry visibility, front-house upgrade fit, porch style fit, facade/door/window cross-sell.",
            "public_data_candidates": "Street/frontage context and building morphology where licensed.",
            "expansion_trigger": "Facade/window campaigns identify front-entry improvement or curb-appeal demand.",
        },
        "drivewaypilot": {
            "buyer_question": "Which driveways show surface, drainage, or EV-ready upgrade opportunities?",
            "initial_play": "Driveway area, surface condition, drainage risk, EV charger fit, outdoor contractor planning.",
            "public_data_candidates": "Parcel/impervious-surface context, street access, flood/drainage layers where licensed.",
            "expansion_trigger": "Customer wants property exterior bundle or EV/home-energy adjacent campaign.",
        },
    }
    modules = []
    for module_key, definition in PILOT_MODULES.items():
        context = module_context[module_key]
        benchmarkable = [metric.label for metric in definition.metrics if metric.visibility == "benchmarkable"]
        tenant_private = [metric.label for metric in definition.metrics if metric.visibility != "benchmarkable"]
        modules.append({
            "module_key": module_key,
            "label": definition.label,
            "category": definition.category,
            "primary_score_key": definition.primary_score_key,
            "metric_count": len(definition.metrics),
            "benchmarkable_metrics": benchmarkable,
            "tenant_private_metrics": tenant_private,
            "buyer_question": context["buyer_question"],
            "initial_play": context["initial_play"],
            "public_data_candidates": context["public_data_candidates"],
            "expansion_trigger": context["expansion_trigger"],
            "readiness_status": "catalog_ready",
            "live_status": "blocked_until_production_proof" if not production_go else "ready_for_live_scope",
            "access_guardrail": "tenant_id, module_key, optional partner_id, metric visibility, export scope, and live RLS/customer-access proof are mandatory.",
        })
    decision_tree = [
        {
            "stage": "buyer_review",
            "trigger": "Customer asks whether HomePilot is only FacadePilot.",
            "recommendation": "Show shared property spine, module catalog, module-specific metrics, and entitlement-based visibility.",
            "evidence": ["CUSTOMER_MODULE_EXPANSION_PLAN.md", "MODULE_VALUE_MATRIX.csv", "DATA_DICTIONARY.md"],
            "guardrail": "Do not imply modules are enabled for a tenant until tenant_modules and customer scope say so.",
            "current_status": "ready" if buyer_go else "action_required",
        },
        {
            "stage": "pilot_kickoff",
            "trigger": "DAW confirms FacadePilot first wave and asks what comes next.",
            "recommendation": "Use FacadePilot as the proof module, then choose WindowPilot/RoofPilot/outdoor modules from response themes and partner capacity.",
            "evidence": ["CUSTOMER_PILOT_PROPOSAL.md", "VALUE_REALIZATION_METRICS.csv", "EXPANSION_DECISION_TREE.csv"],
            "guardrail": "Expansion decisions must preserve tenant/module/partner scoping and response-rate denominator definitions.",
            "current_status": "ready_for_customer_input",
        },
        {
            "stage": "first_campaign",
            "trigger": "First response cycle produces objections, no-response clusters, partner capacity signals, or cross-sell demand.",
            "recommendation": "Map learnings to the next module, next territory, or next partner wave before adding new data sources.",
            "evidence": ["CAMPAIGN_LEARNING.md", "TERRITORY_PLAN.md", "EXECUTIVE_DECISION_LOG.csv"],
            "guardrail": "A response theme can suggest expansion; it is not proof of homeowner purchase intent for another product.",
            "current_status": "blocked" if not production_go else "ready",
        },
        {
            "stage": "module_activation",
            "trigger": "Customer approves a new module such as WindowPilot or RoofPilot.",
            "recommendation": "Enable the module in tenant_modules, generate scoped assessments, update package/export visibility, and rerun access verification.",
            "evidence": ["API_CONTRACT.md", "CUSTOMER_ACCESS_VERIFICATION.md", "PRODUCTION_PROOF.md"],
            "guardrail": "Unknown metrics remain hidden by default and live access requires RLS/customer JWT proof.",
            "current_status": "blocked" if not production_go else "ready",
        },
        {
            "stage": "portfolio_scale",
            "trigger": "Customer wants multiple modules, multiple partner types, or benchmark-safe learning.",
            "recommendation": "Use aggregate-only benchmarks with minimum cohort thresholds; keep raw rows tenant-private and partner-scoped.",
            "evidence": ["DATA_DICTIONARY.md", "PROCESSING_REGISTER.md", "VALUE_REALIZATION_METRICS.csv"],
            "guardrail": "No raw cross-customer learning, addresses, responses, notes, or partner rows may leak into benchmark surfaces.",
            "current_status": "blocked" if not production_go else "ready",
        },
    ]
    platform_rules = [
        "One shared HomePilot property spine can support many renovation pilots.",
        "A purchased module grants access only to that tenant's rows and that module's entitled metrics.",
        "Producer networks can compare partners; partner renovators see assigned records only.",
        "Metric visibility controls dashboard, export, customer package, and benchmark surfaces.",
        "Public-data enrichment needs source URL, licence, retrieval date, allowed use, and geography level before production import.",
        "Production access requires live schema verification, live RLS launch, and customer access verification with production_verified=true.",
    ]
    return {
        "plan_type": "homepilot_module_expansion_plan",
        "created_at": utc_now(),
        "release_label": report["release_label"],
        "status": "buyer_review_expansion_ready" if buyer_go else "action_required",
        "decisions": decisions,
        "modules": modules,
        "decision_tree": decision_tree,
        "platform_rules": platform_rules,
        "guardrails": {
            "tenant_module_scope_required": True,
            "partner_scope_required_for_producer_networks": True,
            "unknown_metrics_hidden_by_default": True,
            "public_data_requires_dataset_level_licence_review": True,
            "production_requires_live_proof": True,
        },
    }


def render_module_expansion_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Module Expansion Plan",
        "",
        f"Release: {plan['release_label']}",
        f"Created: {plan['created_at']}",
        f"Status: {plan['status']}",
        "",
        "This plan explains how HomePilot grows from a first FacadePilot/DAW buyer review into a tenant-safe multi-module property-intelligence platform.",
        "",
        "## Platform Rules",
        "",
    ]
    lines.extend(f"- {rule}" for rule in plan["platform_rules"])
    lines += [
        "",
        "## Module Value Matrix",
        "",
        "| Module | Category | Primary Score | Metric Count | Buyer Question | Expansion Trigger | Live Status |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in plan["modules"]:
        lines.append(
            f"| {row['label']} (`{row['module_key']}`) | {row['category']} | {row['primary_score_key']} | "
            f"{row['metric_count']} | {row['buyer_question']} | {row['expansion_trigger']} | {row['live_status']} |"
        )
    lines += [
        "",
        "## Expansion Decision Tree",
        "",
        "| Stage | Status | Trigger | Recommendation | Evidence | Guardrail |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in plan["decision_tree"]:
        lines.append(
            f"| {row['stage']} | {row['current_status']} | {row['trigger']} | {row['recommendation']} | "
            f"{', '.join(row['evidence'])} | {row['guardrail']} |"
        )
    lines += [
        "",
        "## Guardrails",
        "",
        "- A customer who bought WindowPilot sees WindowPilot metrics only for their tenant unless more modules are explicitly enabled.",
        "- DAW as producer may see aggregate network and partner drilldown; partner renovators still see assigned records only.",
        "- Unknown metrics stay hidden by default on dashboard, export, customer-package, and benchmark surfaces.",
        "- Public-data enrichment requires dataset-level licence and provenance review before production import.",
        "- Production remains no-go until live schema, RLS launch, and customer access verification all pass with production_verified=true.",
        "",
    ]
    return "\n".join(lines)


def _write_module_value_matrix_csv(path: Path, modules: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "module_key",
        "label",
        "category",
        "primary_score_key",
        "metric_count",
        "benchmarkable_metrics",
        "tenant_private_metrics",
        "buyer_question",
        "initial_play",
        "public_data_candidates",
        "expansion_trigger",
        "readiness_status",
        "live_status",
        "access_guardrail",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in modules:
            writer.writerow({
                **{field: row.get(field, "") for field in fields},
                "benchmarkable_metrics": "; ".join(row["benchmarkable_metrics"]),
                "tenant_private_metrics": "; ".join(row["tenant_private_metrics"]),
            })


def _write_expansion_decision_tree_csv(path: Path, decision_tree: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["stage", "trigger", "recommendation", "evidence", "guardrail", "current_status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in decision_tree:
            writer.writerow({
                "stage": row["stage"],
                "trigger": row["trigger"],
                "recommendation": row["recommendation"],
                "evidence": "; ".join(row["evidence"]),
                "guardrail": row["guardrail"],
                "current_status": row["current_status"],
            })


def build_public_data_source_register(report: dict[str, Any]) -> dict[str, Any]:
    decisions = report["decisions"]
    buyer_go = decisions.get("buyer_review") == "go"
    sources = [
        {
            "source": "Statbel open data",
            "publisher": "Statistics Belgium",
            "url": "https://statbel.fgov.be/en/open-data",
            "licence_or_terms": "CC BY 4.0 on checked page",
            "checked_on": "2026-06-26",
            "update_frequency": "dataset-specific",
            "recommended_status": "approved_for_review",
            "allowed_use": "Aggregate housing, building stock, land use, taxable income, Census, and geography context where dataset metadata confirms reuse.",
            "suggested_homepilot_fields": "stat_sector_building_age_mix; stat_sector_income_band; municipality_housing_context; land_use_context",
            "attribution": "Credit Statbel / Statistics Belgium and preserve dataset metadata.",
            "production_gate": "Select dataset, store retrieval date and licence, and prefer aggregate area-level fields.",
        },
        {
            "source": "BeSt Addresses",
            "publisher": "FPS BOSA",
            "url": "https://data.gov.be/en/datasets/fpsbosa-dis-best-full",
            "licence_or_terms": "CC Attribution 4.0 on checked listing",
            "checked_on": "2026-06-26",
            "update_frequency": "weekly",
            "recommended_status": "approved_for_review",
            "allowed_use": "Official Belgian address normalization, address IDs, street/house/postcode/municipality fields, and coordinates.",
            "suggested_homepilot_fields": "official_address_id; street; house_number; postcode; municipality; lat; lon; match_confidence",
            "attribution": "Credit FPS BOSA / BeSt and preserve download/version metadata.",
            "production_gate": "Build transform, record source run, and reconcile against tenant import before campaign use.",
        },
        {
            "source": "Cadastral parcels monthly situation",
            "publisher": "FPS Finance / data.gov.be / geo.be",
            "url": "https://data.gov.be/en/datasets/1d797df0-c988-11ed-abc3-0050569393d1",
            "licence_or_terms": "Freely downloadable shapefiles on checked listing; verify current terms before import",
            "checked_on": "2026-06-26",
            "update_frequency": "monthly",
            "recommended_status": "review_required",
            "allowed_use": "Parcel geometry and area context; no cadastral owner data.",
            "suggested_homepilot_fields": "parcel_id; parcel_area_m2; geometry_reference; fiscal_situation_code_where_allowed",
            "attribution": "Credit official source and retain geometry/source metadata.",
            "production_gate": "Verify current licence/terms, exclude owner data, and store geometry references separately from campaign contact basis.",
        },
        {
            "source": "Datavindplaats Vlaanderen",
            "publisher": "Flemish public-sector data catalogue",
            "url": "https://www.vlaanderen.be/datavindplaats",
            "licence_or_terms": "dataset-level licence required",
            "checked_on": "2026-06-26",
            "update_frequency": "dataset-specific",
            "recommended_status": "candidate_catalogue",
            "allowed_use": "Discovery of Flemish address, building, environment, land-use, flood, soil, and geodata services.",
            "suggested_homepilot_fields": "building_register_reference; land_use_class; flood_risk_flag; soil_or_drainage_context",
            "attribution": "Follow selected dataset attribution and terms.",
            "production_gate": "Approve each selected dataset before import; do not rely on catalogue page alone.",
        },
        {
            "source": "VEKA public pages and tools",
            "publisher": "Vlaams Energie- en Klimaatagentschap",
            "url": "https://www.vlaanderen.be/veka",
            "licence_or_terms": "public information page; not address-level open EPC proof",
            "checked_on": "2026-06-26",
            "update_frequency": "page/tool-specific",
            "recommended_status": "context_only",
            "allowed_use": "Energy/renovation policy story, educational dashboard context, subsidy/premium guidance links.",
            "suggested_homepilot_fields": "renovation_policy_context; premium_story_angle; energy_story_fit_context",
            "attribution": "Link to official VEKA pages/tools where used.",
            "production_gate": "Do not import or infer individual EPC labels unless a separate legal basis and licensed dataset exists.",
        },
        {
            "source": "OpenStreetMap",
            "publisher": "OpenStreetMap contributors / OSM Foundation",
            "url": "https://www.openstreetmap.org/copyright",
            "licence_or_terms": "ODbL with attribution and share-alike obligations",
            "checked_on": "2026-06-26",
            "update_frequency": "community-updated",
            "recommended_status": "legal_review_required",
            "allowed_use": "Map context, fallback building/road/access tags where ODbL obligations are acceptable.",
            "suggested_homepilot_fields": "osm_building_id; road_access_tag; building_tag; surrounding_context",
            "attribution": "Credit OpenStreetMap and contributors; review derived database obligations.",
            "production_gate": "Legal review before mixing OSM-derived data into proprietary exports or customer datasets.",
        },
        {
            "source": "Brussels and Wallonia open/geodata portals",
            "publisher": "Regional public-data portals",
            "url": "https://opendata.brussels.be/pages/home/; https://geoportail.wallonie.be/home.html",
            "licence_or_terms": "dataset-level licence required",
            "checked_on": "2026-06-26",
            "update_frequency": "dataset-specific",
            "recommended_status": "candidate_catalogue",
            "allowed_use": "Regional geodata discovery for Brussels and Wallonia where selected datasets are licensed.",
            "suggested_homepilot_fields": "regional_geometry_reference; planning_zone_flag; environment_context",
            "attribution": "Follow selected portal/dataset attribution.",
            "production_gate": "Approve each selected dataset and record provenance before import.",
        },
    ]
    blocked = [
        {
            "candidate": "Cadastral owner data",
            "risk": "Personal/ownership data is not the same as open parcel geometry.",
            "default_rule": "Do not import for lead generation without explicit legal basis and privacy review.",
            "allowed_exception": "Customer-provided or legally approved owner/contact basis with documented processing purpose.",
        },
        {
            "candidate": "Individual EPC labels by address",
            "risk": "Address-level EPC can be tied to a property/owner context and is not automatically open for commercial reuse.",
            "default_rule": "Use only owner-provided, customer-provided, or clearly licensed aggregate/open datasets.",
            "allowed_exception": "Explicit legal basis, licence, retention rule, and customer approval.",
        },
        {
            "candidate": "Personal contact details from scraping",
            "risk": "GDPR, ePrivacy, consent, and unfair outreach risk.",
            "default_rule": "Keep contact basis separate, documented, opt-out capable, and customer-approved.",
            "allowed_exception": "Approved customer CRM/contact source with lawful basis and suppression handling.",
        },
        {
            "candidate": "Google Street View imagery extraction beyond permitted APIs or terms",
            "risk": "Platform terms, copyright, derivative-use, and display restrictions.",
            "default_rule": "Use only permitted API outputs/workflows and retain provenance.",
            "allowed_exception": "Reviewed provider terms and approved integration runbook.",
        },
        {
            "candidate": "Social media or person-level signals",
            "risk": "Sensitive profiling and consent risk.",
            "default_rule": "Avoid for HomePilot scoring.",
            "allowed_exception": "Explicit consent and legal/privacy review.",
        },
    ]
    attribution = [
        {
            "requirement": "source_run_metadata",
            "description": "Every public-data import records source name, publisher, URL, licence/terms, retrieval date, update frequency, transform version, and operator.",
            "evidence": "homepilot_source_runs; SOURCE_LEDGER.md; PUBLIC_DATA_SOURCE_MATRIX.csv",
        },
        {
            "requirement": "separate_enrichment_layer",
            "description": "Public features live in enrichment/source tables instead of replacing raw pilot metrics or campaign contact basis.",
            "evidence": "homepilot_property_enrichments; homepilot_public_features; processing register",
        },
        {
            "requirement": "dashboard_provenance_badge",
            "description": "Customer dashboards label enriched fields as public/contextual signals and not homeowner intent.",
            "evidence": "DATA_DICTIONARY.md; boardroom caveats; source ledger",
        },
        {
            "requirement": "licence_review_before_production",
            "description": "Dataset-level licence, allowed use, attribution, export/display rights, and ODbL/share-alike implications are checked before production import.",
            "evidence": "DATA_VENDOR_PLAN.md; PUBLIC_DATA_SOURCE_REGISTER.md; PROCUREMENT_RISK_REGISTER.csv",
        },
    ]
    implementation_contract = {
        "storage_tables": [
            {
                "table": "homepilot_source_runs",
                "purpose": "One row per public/open-data retrieval or import run with source URL, publisher, licence, allowed use, attribution, retrieval timestamps, transform version, operator, status, and metadata.",
                "production_gate": "A source run must exist before enriched fields are displayed or exported.",
            },
            {
                "table": "homepilot_geographies",
                "purpose": "Tenant-scoped geography keys such as official address, statistical sector, municipality, parcel, building, or custom zone, with geometry reference and source metadata.",
                "production_gate": "Geometry/reference data must be licensed and must not include owner/contact data.",
            },
            {
                "table": "homepilot_public_features",
                "purpose": "Reusable area/geography features such as building-age share, income band, land-use class, flood-risk flag, or other licensed public context.",
                "production_gate": "Feature rows need source_run_id, licence, allowed_use, attribution, and confidence where applicable.",
            },
            {
                "table": "homepilot_property_enrichments",
                "purpose": "Approved public enrichment linked to a tenant-scoped property, keeping public_fields and provenance separate from campaign targets, interactions, and contact basis.",
                "production_gate": "Only approved public_fields may be exposed through customer dashboards or exports.",
            },
        ],
        "customer_read_model": "homepilot_property_public_enrichment",
        "required_columns": [
            "tenant_id",
            "property_id",
            "enrichment_type",
            "public_fields",
            "confidence",
            "provenance",
            "source_run_id",
            "source_name",
            "licence",
            "allowed_use",
            "attribution",
            "retrieval_finished_at",
            "transform_version",
        ],
        "access_boundary": "security_invoker view plus tenant access, partner scope, and underlying table RLS",
    }
    return {
        "register_type": "homepilot_public_data_source_register",
        "created_at": utc_now(),
        "release_label": report["release_label"],
        "status": "buyer_review_public_data_ready" if buyer_go else "action_required",
        "decisions": decisions,
        "sources_checked_on": "2026-06-26",
        "sources": sources,
        "blocked_or_high_risk": blocked,
        "attribution_requirements": attribution,
        "implementation_contract": implementation_contract,
        "guardrails": {
            "dataset_level_licence_required": True,
            "owner_data_blocked_by_default": True,
            "address_level_epc_blocked_without_legal_basis": True,
            "contact_scraping_blocked_by_default": True,
            "osm_odbl_review_required": True,
            "production_requires_source_run_metadata": True,
            "public_enrichment_separate_from_campaign_basis": True,
        },
    }


def build_public_data_production_intake(
    report: dict[str, Any],
    public_register: dict[str, Any],
) -> dict[str, Any]:
    source_profiles = {
        "Statbel open data": {
            "lane": "Statistical-sector context",
            "data_category": "aggregate_non_personal",
            "approval_owner": "Legal/privacy owner + analytics owner",
            "module_fit": "FacadePilot, WindowPilot, RoofPilot, GardenPilot, PoolPilot, PorchPilot, DrivewayPilot",
            "approved_fields_to_review": "statistical-sector building-age mix, housing type mix, income band, land-use context",
            "blocked_fields": "Household-level or person-level inference; raw microdata; claims of homeowner intent",
            "storage_target": "homepilot_geographies; homepilot_public_features; homepilot_property_enrichments",
            "customer_surface": "Territory planning, message-fit context, public-data provenance panel",
            "approval_status": "dataset_level_approval_required",
            "next_step": "Select exact Statbel datasets and store licence, retrieval date, update cadence, and attribution in homepilot_source_runs.",
        },
        "BeSt Addresses": {
            "lane": "Official address and geocode matching",
            "data_category": "official_address_reference",
            "approval_owner": "Data engineering owner + legal/privacy owner",
            "module_fit": "All HomePilot modules",
            "approved_fields_to_review": "official address id, normalized address, postcode, municipality, coordinates, match confidence",
            "blocked_fields": "Personal contact data; ownership data; outreach basis",
            "storage_target": "homepilot_source_runs; homepilot_geographies; homepilot_property_enrichments",
            "customer_surface": "Address QA, export QA, map accuracy, duplicate detection",
            "approval_status": "dataset_level_approval_required",
            "next_step": "Build a transform with source-run metadata and reconcile against tenant-provided address imports before campaign use.",
        },
        "Cadastral parcels monthly situation": {
            "lane": "Parcel geometry and area context",
            "data_category": "geometry_only_review_required",
            "approval_owner": "Legal/privacy owner + geospatial owner",
            "module_fit": "GardenPilot, DrivewayPilot, RoofPilot, FacadePilot, PoolPilot",
            "approved_fields_to_review": "parcel geometry reference, parcel area, geometry hash, allowed fiscal situation code",
            "blocked_fields": "Cadastral owner data; property-owner identity; contact basis",
            "storage_target": "homepilot_geographies; homepilot_public_features; homepilot_property_enrichments",
            "customer_surface": "Sizing context, territory maps, opportunity evidence panel",
            "approval_status": "legal_review_required",
            "next_step": "Confirm current licence/terms, document owner-data exclusion, and approve geometry-only transform.",
        },
        "Datavindplaats Vlaanderen": {
            "lane": "Flemish catalogue dataset selection",
            "data_category": "catalogue_selection_required",
            "approval_owner": "Product owner + legal/privacy owner",
            "module_fit": "All modules, depending on selected dataset",
            "approved_fields_to_review": "building register reference, land-use class, flood risk flag, soil/drainage context",
            "blocked_fields": "Any selected dataset without licence, allowed-use, attribution, and update-frequency review",
            "storage_target": "homepilot_source_runs; homepilot_geographies; homepilot_public_features",
            "customer_surface": "Module-specific public context panels and partner territory planning",
            "approval_status": "dataset_selection_required",
            "next_step": "Pick exact datasets from the catalogue and create one approval row per dataset before import.",
        },
        "VEKA public pages and tools": {
            "lane": "Energy and renovation policy context",
            "data_category": "context_link_only",
            "approval_owner": "Customer success owner + legal/privacy owner",
            "module_fit": "FacadePilot, WindowPilot, RoofPilot",
            "approved_fields_to_review": "policy context links, premium/subsidy story angle, educational dashboard copy",
            "blocked_fields": "Individual EPC labels by address unless licensed or customer/owner-provided",
            "storage_target": "homepilot_source_runs for context references; no address-level EPC import by default",
            "customer_surface": "Educational panels, message angles, customer-success training",
            "approval_status": "context_scope_required",
            "next_step": "Approve link/context-only use and keep individual EPC data out unless a separate lawful source is supplied.",
        },
        "OpenStreetMap": {
            "lane": "Map/building/road context",
            "data_category": "odbl_review_required",
            "approval_owner": "Legal/privacy owner + data engineering owner",
            "module_fit": "All modules where fallback map or accessibility context is useful",
            "approved_fields_to_review": "OSM ids, building tags, road/access tags, surrounding context",
            "blocked_fields": "Proprietary export mixing before ODbL/share-alike review; Google-derived data",
            "storage_target": "homepilot_source_runs; homepilot_geographies; homepilot_public_features",
            "customer_surface": "Map UX, fallback geometry, accessibility context",
            "approval_status": "legal_review_required",
            "next_step": "Review ODbL obligations and decide whether OSM-derived database outputs can be exported to customers.",
        },
        "Brussels and Wallonia open/geodata portals": {
            "lane": "Regional geodata catalogue selection",
            "data_category": "catalogue_selection_required",
            "approval_owner": "Product owner + legal/privacy owner",
            "module_fit": "All modules, depending on region and selected dataset",
            "approved_fields_to_review": "regional geometry reference, planning zone flag, environment context",
            "blocked_fields": "Portal-level assumptions without dataset-level licence and attribution review",
            "storage_target": "homepilot_source_runs; homepilot_geographies; homepilot_public_features",
            "customer_surface": "Regional territory planning, zone caveats, public-context panels",
            "approval_status": "dataset_selection_required",
            "next_step": "Select exact Brussels/Wallonia datasets and approve one import contract per dataset.",
        },
    }

    dataset_approvals = []
    for source in public_register["sources"]:
        profile = source_profiles[source["source"]]
        dataset_approvals.append({
            "lane": profile["lane"],
            "source": source["source"],
            "publisher": source["publisher"],
            "url": source["url"],
            "licence_or_terms": source["licence_or_terms"],
            "update_frequency": source["update_frequency"],
            "data_category": profile["data_category"],
            "approval_owner": profile["approval_owner"],
            "approval_status": profile["approval_status"],
            "allowed_use": source["allowed_use"],
            "approved_fields_to_review": profile["approved_fields_to_review"],
            "blocked_fields": profile["blocked_fields"],
            "module_fit": profile["module_fit"],
            "storage_target": profile["storage_target"],
            "customer_surface": profile["customer_surface"],
            "required_evidence": "licence_or_terms; allowed_use; attribution; retrieval_date; update_frequency; transform_version; source_run_id; field_allowlist; RLS/customer-access proof",
            "next_step": profile["next_step"],
            "production_import_decision": "do_not_import_yet",
        })

    gate_checklist = [
        {
            "gate": "dataset_level_licence_and_allowed_use",
            "owner": "Legal/privacy owner",
            "required_evidence": "Source URL, publisher, licence/terms, commercial reuse, export/display rights, attribution text.",
            "status": "pending",
        },
        {
            "gate": "field_allowlist_and_blocklist",
            "owner": "Product owner + analytics owner",
            "required_evidence": "Approved public fields, blocked fields, module fit, and customer-visible labels.",
            "status": "pending",
        },
        {
            "gate": "privacy_and_contact_basis_separation",
            "owner": "Legal/privacy owner",
            "required_evidence": "Confirmation that public enrichment is not used as contact basis and does not add owner/contact data.",
            "status": "pending",
        },
        {
            "gate": "source_run_and_transform_contract",
            "owner": "Data engineering owner",
            "required_evidence": "Source-run metadata, transform version, retrieval schedule, checksums where available, and provenance mapping.",
            "status": "contract_ready_pending_live_import",
        },
        {
            "gate": "dashboard_and_export_attribution",
            "owner": "Customer success owner + legal/privacy owner",
            "required_evidence": "Dashboard provenance badge, export attribution note, and customer-facing caveat language.",
            "status": "pending",
        },
        {
            "gate": "live_schema_rls_and_customer_access",
            "owner": "Platform admin / Supabase owner",
            "required_evidence": "Live schema verification, RLS probe, and customer access verification with production_verified=true.",
            "status": "blocked_until_live_proof",
        },
        {
            "gate": "production_import_go_no_go",
            "owner": "Executive sponsor + HomePilot operator",
            "required_evidence": "All source approvals complete plus live proof archived in the release pack.",
            "status": "blocked",
        },
    ]

    return {
        "intake_type": "homepilot_public_data_production_intake",
        "created_at": utc_now(),
        "release_label": report["release_label"],
        "status": "approval_required",
        "production_import_decision": "blocked_until_dataset_approvals_and_live_proof",
        "source_register_status": public_register["status"],
        "summary": {
            "dataset_approval_rows": len(dataset_approvals),
            "approval_gates": len(gate_checklist),
            "ready_contract_tables": len(public_register["implementation_contract"]["storage_tables"]),
            "blocked_or_high_risk_lanes": len(public_register["blocked_or_high_risk"]),
        },
        "dataset_approvals": dataset_approvals,
        "gate_checklist": gate_checklist,
        "live_import_sequence": [
            "Customer/legal approves exact dataset rows and field allowlist.",
            "Data owner records source-run metadata and transform version.",
            "Operator imports into source-run/geography/public-feature/property-enrichment tables.",
            "Live schema verification, RLS probe, and customer-access verification pass with production_verified=true.",
            "Customer dashboards expose only approved fields with provenance and attribution.",
        ],
        "guardrails": {
            "production_imports_blocked_until_approved": True,
            "owner_data_blocked_by_default": True,
            "individual_epc_blocked_without_legal_basis": True,
            "scraped_contact_data_blocked": True,
            "osm_requires_odbl_review": True,
            "public_context_is_not_homeowner_intent": True,
            "tenant_module_partner_scope_required": True,
        },
    }


def render_public_data_production_intake_markdown(intake: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Public Data Production Intake",
        "",
        f"Release: {intake['release_label']}",
        f"Created: {intake['created_at']}",
        f"Status: {intake['status']}",
        f"Production import decision: {intake['production_import_decision']}",
        "",
        "This intake turns the public-data source register into a concrete legal, data-engineering, and customer-success approval workflow.",
        "It is intentionally conservative: no public-data import is production-approved until dataset-level approval and live access proof are archived.",
        "",
        "## Dataset Approval Matrix",
        "",
        "| Lane | Source | Data Category | Owner | Status | Production Decision |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in intake["dataset_approvals"]:
        lines.append(
            f"| {row['lane']} | {row['source']} | {row['data_category']} | "
            f"{row['approval_owner']} | {row['approval_status']} | {row['production_import_decision']} |"
        )
    lines += [
        "",
        "## Approval Gates",
        "",
        "| Gate | Owner | Required Evidence | Status |",
        "| --- | --- | --- | --- |",
    ]
    for gate in intake["gate_checklist"]:
        lines.append(f"| {gate['gate']} | {gate['owner']} | {gate['required_evidence']} | {gate['status']} |")
    lines += [
        "",
        "## Live Import Sequence",
        "",
    ]
    lines.extend(f"{index}. {step}" for index, step in enumerate(intake["live_import_sequence"], start=1))
    lines += [
        "",
        "## Guardrails",
        "",
        "- Public-data production imports are blocked until dataset-level approvals and live proof are complete.",
        "- Owner data, scraped contact data, and individual EPC labels remain blocked by default.",
        "- Cadastral parcel use is geometry-only unless a separate legal review says otherwise.",
        "- OSM data requires ODbL attribution/share-alike review before proprietary export or database mixing.",
        "- Public context can support prioritization and education, but it is not homeowner purchase intent.",
        "- Every approved import must preserve tenant, module, and partner scope.",
        "",
    ]
    return "\n".join(lines)


def _write_public_data_approval_csv(path: Path, approvals: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "lane",
        "source",
        "publisher",
        "url",
        "licence_or_terms",
        "update_frequency",
        "data_category",
        "approval_owner",
        "approval_status",
        "allowed_use",
        "approved_fields_to_review",
        "blocked_fields",
        "module_fit",
        "storage_target",
        "customer_surface",
        "required_evidence",
        "next_step",
        "production_import_decision",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in approvals:
            writer.writerow({field: row.get(field, "") for field in fields})


def render_public_data_register_markdown(register: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Public Data Source Register",
        "",
        f"Release: {register['release_label']}",
        f"Created: {register['created_at']}",
        f"Status: {register['status']}",
        f"Sources checked on: {register['sources_checked_on']}",
        "",
        "This register summarizes which public-data lanes are suitable for buyer review, which require dataset-level approval, and which are blocked by default.",
        "",
        "## Source Matrix",
        "",
        "| Source | Status | Licence / Terms | Allowed Use | Production Gate |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in register["sources"]:
        lines.append(
            f"| {row['source']} | {row['recommended_status']} | {row['licence_or_terms']} | "
            f"{row['allowed_use']} | {row['production_gate']} |"
        )
    lines += [
        "",
        "## Blocked Or High-Risk Lanes",
        "",
        "| Candidate | Risk | Default Rule | Allowed Exception |",
        "| --- | --- | --- | --- |",
    ]
    for row in register["blocked_or_high_risk"]:
        lines.append(f"| {row['candidate']} | {row['risk']} | {row['default_rule']} | {row['allowed_exception']} |")
    lines += [
        "",
        "## Attribution And Provenance Requirements",
        "",
        "| Requirement | Description | Evidence |",
        "| --- | --- | --- |",
    ]
    for row in register["attribution_requirements"]:
        lines.append(f"| {row['requirement']} | {row['description']} | {row['evidence']} |")
    contract = register["implementation_contract"]
    lines += [
        "",
        "## Implementation Contract",
        "",
        f"Customer read model: `{contract['customer_read_model']}`",
        "",
        "| Table | Purpose | Production Gate |",
        "| --- | --- | --- |",
    ]
    for row in contract["storage_tables"]:
        lines.append(f"| `{row['table']}` | {row['purpose']} | {row['production_gate']} |")
    lines += [
        "",
        f"Access boundary: {contract['access_boundary']}",
        "",
        "Required read-model columns:",
        "",
    ]
    lines.extend(f"- `{column}`" for column in contract["required_columns"])
    lines += [
        "",
        "## Guardrails",
        "",
        "- Dataset-level licence and allowed-use review is required before production import.",
        "- Cadastral owner data, scraped personal contact details, and individual EPC labels are blocked by default.",
        "- OSM-derived data requires ODbL attribution/share-alike review before proprietary export or database mixing.",
        "- Public-data context can strengthen prioritization, but it must not be presented as homeowner purchase intent.",
        "- Public enrichment stays separate from campaign contact basis and is exposed through the tenant/partner-scoped enrichment read model only after approval.",
        "- Every production import needs source-run metadata, provenance, retrieval date, and transform version.",
        "",
    ]
    return "\n".join(lines)


def _write_public_source_matrix_csv(path: Path, sources: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "source",
        "publisher",
        "url",
        "licence_or_terms",
        "checked_on",
        "update_frequency",
        "recommended_status",
        "allowed_use",
        "suggested_homepilot_fields",
        "attribution",
        "production_gate",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in sources:
            writer.writerow({field: row.get(field, "") for field in fields})


def _write_blocked_data_csv(path: Path, blocked: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["candidate", "risk", "default_rule", "allowed_exception"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in blocked:
            writer.writerow({field: row.get(field, "") for field in fields})


def _write_attribution_requirements_csv(path: Path, requirements: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["requirement", "description", "evidence"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in requirements:
            writer.writerow({field: row.get(field, "") for field in fields})


def render_scorecard_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Market Readiness Scorecard",
        "",
        f"Release: {report['release_label']}",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        "",
        "## Decisions",
        "",
    ]
    for label, value in report["decisions"].items():
        lines.append(f"- {label}: {value}")
    signoff = report.get("customer_signoff_reconciliation") or {}
    if signoff:
        signoff_summary = signoff.get("summary") or {}
        lines += [
            "",
            "## Customer Decision Board",
            "",
            f"- Status: {signoff.get('status')}",
            f"- Signed/approved: {signoff_summary.get('signed_decision_count', 0)}/{signoff_summary.get('decision_count', 0)}",
            f"- Ready for customer decision: {signoff_summary.get('ready_for_review_count', 0)}",
            f"- Live-launch blockers: {signoff_summary.get('live_launch_blockers', 0)}",
            f"- Production blockers: {signoff_summary.get('production_blockers', 0)}",
            f"- Signoff evidence rows applied: {signoff_summary.get('signoff_evidence_rows_applied', 0)}",
            "",
            "Buyer-ready is not customer-approved until signed references are archived; customer signoff CSVs cannot replace live schema, RLS, or customer-access proof.",
            "",
            "| Decision | Stage | Signoff | Blocks Live | Blocks Production | Next Action |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for row in signoff.get("decision_matrix") or []:
            lines.append(
                f"| {row['decision_area']} | {row['required_stage']} | {row['signoff_status']} | {str(row['blocks_live_launch']).lower()} | {str(row['blocks_production']).lower()} | {row['next_action']} |"
            )
    lines += [
        "",
        "## Data Platform Blueprint",
        "",
    ]
    data_platform_blueprint = report.get("data_platform_blueprint") or {}
    if data_platform_blueprint:
        blueprint_summary = data_platform_blueprint.get("summary") or {}
        blueprint_scope = data_platform_blueprint.get("current_customer_scope") or {}
        lines += [
            f"- Status: {data_platform_blueprint.get('status')}",
            f"- Architecture rule: `{data_platform_blueprint.get('architecture_rule')}`",
            f"- Shared model: {blueprint_summary.get('shared_database_model')}",
            f"- Pilot modules in catalog: {blueprint_summary.get('module_count')}",
            f"- Current enabled modules: {', '.join(blueprint_scope.get('module_labels') or [])}",
            f"- Access lenses: {blueprint_summary.get('access_lens_count')}",
            f"- Export surfaces: {blueprint_summary.get('export_surface_count')}",
            f"- {blueprint_summary.get('production_verified_label', 'production_verified=false')}",
            "",
            "The blueprint makes the platform model reviewable: one property spine can serve FacadePilot, WindowPilot, RoofPilot, GardenPilot, PoolPilot, PorchPilot, DrivewayPilot, and future modules while every customer-facing row remains tenant-, module-, and partner-scoped.",
            "",
            "Evidence:",
            f"- Data platform blueprint: {report.get('paths', {}).get('data_platform_blueprint_markdown')}",
            f"- Data platform scope matrix: {report.get('paths', {}).get('data_platform_scope_matrix')}",
        ]
    else:
        lines.append("- Status: not_generated")
    lines += [
        "",
        "## Module Readiness Matrix",
        "",
    ]
    module_readiness = report.get("module_readiness_matrix") or {}
    if module_readiness:
        module_summary = module_readiness.get("summary") or {}
        lines += [
            f"- Status: {module_readiness.get('status')}",
            f"- Pilot modules in catalog: {module_summary.get('module_count')}",
            f"- Enabled in current customer scope: {module_summary.get('enabled_module_count')}",
            f"- Buyer-ready modules: {module_summary.get('buyer_ready_count')}",
            f"- Production-ready modules: {module_summary.get('production_ready_count')}",
            f"- Metric rows covered: {module_summary.get('metric_coverage_count')}",
            f"- {module_summary.get('production_verified_label', 'production_verified=false')}",
            f"- Secret scan: {module_readiness.get('secret_scan', {}).get('status', 'unknown')}",
            "",
            "This matrix is the buyer/IT proof that each Pilot module has its own metric contract, visibility rules, export surface, public-data review lane, and live-proof gate. It keeps DAW/FacadePilot enabled for the current demo while showing how WindowPilot, RoofPilot, GardenPilot, PoolPilot, PorchPilot, and DrivewayPilot remain catalog-ready until a tenant is entitled.",
            "",
            "Evidence:",
            f"- Module readiness matrix: {report.get('paths', {}).get('module_readiness_matrix_markdown')}",
            f"- Module readiness CSV: {report.get('paths', {}).get('module_readiness_matrix_csv')}",
            f"- Module metric coverage: {report.get('paths', {}).get('module_metric_coverage')}",
        ]
    else:
        lines.append("- Status: not_generated")
    lines += [
        "",
        "## Live Proof Cockpit",
        "",
    ]
    live_proof_cockpit = report.get("live_proof_cockpit") or build_live_proof_cockpit(report)
    if live_proof_cockpit.get("status") == "not_generated":
        lines.append("- Status: not_generated")
    else:
        cockpit_summary = live_proof_cockpit.get("summary") or {}
        lines += [
            f"- Status: {live_proof_cockpit.get('status')}",
            f"- Acceptance criteria: {cockpit_summary.get('criterion_count', 0)}",
            f"- Passed: {cockpit_summary.get('passed_count', 0)}",
            f"- Blocked: {cockpit_summary.get('blocked_count', 0)}",
            f"- Live-launch blockers: {cockpit_summary.get('live_launch_blockers', 0)}",
            f"- Production blockers: {cockpit_summary.get('production_blockers', 0)}",
            f"- Live launch tasks: {cockpit_summary.get('live_launch_task_count')}",
            f"- {cockpit_summary.get('production_verified_label', 'production_verified=false')}",
            f"- Secret scan: {cockpit_summary.get('secret_scan_status', 'unknown')}",
            "",
            "This cockpit is a review surface only: it writes no live data, stores no secrets, and customer signoff cannot override failed schema, RLS, or customer-access proof.",
            "",
            "Evidence:",
        ]
        for item in live_proof_cockpit.get("evidence") or []:
            lines.append(f"- {item['label']}: {item.get('path')}")
        lines += [
            "",
            "| Key | Stage | Status | Owner | Blocker | Next Action |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for row in live_proof_cockpit.get("blockers") or []:
            blocker = str(row.get("blocker") or "")
            lines.append(
                f"| {row.get('key')} | {row.get('stage')} | {row.get('status')} | {row.get('owner')} | {blocker} | {row.get('next_action')} |"
            )
    lines += [
        "",
        "## Live Credential Handoff",
        "",
    ]
    live_credential_handoff = report.get("live_credential_handoff") or {}
    if live_credential_handoff:
        credential_summary = live_credential_handoff.get("summary") or {}
        lines += [
            f"- Status: {live_credential_handoff.get('status')}",
            f"- Open credential/config tasks: {credential_summary.get('task_count', 0)}",
            f"- Secret-bearing tasks: {credential_summary.get('secret_task_count', 0)}",
            f"- Env var names: {credential_summary.get('env_var_count', 0)}",
            f"- Live inputs ready: {str(credential_summary.get('live_inputs_ready')).lower()}",
            f"- {credential_summary.get('production_verified_label', 'production_verified=false')}",
            f"- Secret scan: {live_credential_handoff.get('secret_scan', {}).get('status', 'unknown')}",
            "",
            "The credential handoff is the customer/IT contract for safe live inputs: env var names, owners, approved secret channels, forbidden channels, validation artifacts, and evidence archive rules.",
            "",
            "Evidence:",
            f"- Live credential handoff: {report.get('paths', {}).get('live_credential_handoff_markdown')}",
            f"- Live credential checklist: {report.get('paths', {}).get('live_credential_handoff_checklist')}",
            f"- Live secret channel contract: {report.get('paths', {}).get('live_secret_channel_contract')}",
        ]
    else:
        lines.append("- Status: not_generated")
    lines += [
        "",
        "## Live Proof Evidence Vault",
        "",
    ]
    live_proof_vault = report.get("live_proof_evidence_vault") or {}
    if live_proof_vault:
        vault_summary = live_proof_vault.get("summary") or {}
        lines += [
            f"- Status: {live_proof_vault.get('status')}",
            f"- Required evidence rows: {vault_summary.get('required_count', 0)}",
            f"- Archived locally: {vault_summary.get('archived_count', 0)}",
            f"- Passed: {vault_summary.get('passed_count', 0)}",
            f"- Blocked: {vault_summary.get('blocked_count', 0)}",
            f"- Live-launch blockers: {vault_summary.get('live_launch_blocked_count', 0)}",
            f"- Production blockers: {vault_summary.get('production_blocked_count', 0)}",
            f"- {vault_summary.get('production_verified_label', 'production_verified=false')}",
            f"- Secret scan: {live_proof_vault.get('secret_scan', {}).get('status', 'unknown')}",
            "",
            "The vault is an evidence archive index: it shows what exists, what must still be proven live, who owns the proof, and which artifacts must stay secret-free.",
            "",
            "Evidence:",
            f"- Live proof evidence vault: {report.get('paths', {}).get('live_proof_evidence_vault_markdown')}",
            f"- Live proof archive index: {report.get('paths', {}).get('live_proof_archive_index')}",
        ]
    else:
        lines.append("- Status: not_generated")
    lines += [
        "",
        "## Outcome Measurement Contract",
        "",
    ]
    outcome_contract = report.get("outcome_measurement_contract") or {}
    if outcome_contract:
        outcome_summary = outcome_contract.get("summary") or {}
        lines += [
            f"- Status: {outcome_contract.get('status')}",
            f"- Outcome event fields: {outcome_summary.get('event_field_count', 0)}",
            f"- Outcome metrics: {outcome_summary.get('metric_count', 0)}",
            f"- Reconciliation gates: {outcome_summary.get('checklist_gate_count', 0)}",
            f"- Blocked gates: {outcome_summary.get('blocked_gate_count', 0)}",
            f"- {outcome_summary.get('production_verified_label', 'production_verified=false')}",
            "",
            "This contract defines how DAW and partner renovators can measure appointment, quote, won/lost, commercial value, and loss-reason outcomes after a campaign while keeping source-system approval, tenant scope, and denominators explicit.",
            "",
            "Evidence:",
            f"- Outcome measurement contract: {report.get('paths', {}).get('outcome_measurement_contract_markdown')}",
            f"- Outcome event schema: {report.get('paths', {}).get('outcome_event_schema')}",
            f"- Outcome sync template: {report.get('paths', {}).get('outcome_sync_template')}",
            f"- Outcome reconciliation checklist: {report.get('paths', {}).get('outcome_reconciliation_checklist')}",
            "",
            "| Metric | Numerator | Denominator | Guardrail |",
            "| --- | --- | --- | --- |",
        ]
        for row in outcome_contract.get("outcome_metrics") or []:
            lines.append(
                f"| {row.get('metric')} | {row.get('numerator')} | {row.get('denominator')} | {row.get('guardrail')} |"
            )
    else:
        lines.append("- Status: not_generated")
    lines += [
        "",
        "## Outcome Import Dry-Run",
        "",
    ]
    outcome_import = report.get("outcome_import_validation") or {}
    if outcome_import:
        import_summary = outcome_import.get("summary") or {}
        lines += [
            f"- Status: {outcome_import.get('status')}",
            f"- Sync decision: {outcome_import.get('sync_decision')}",
            f"- Rows checked: {import_summary.get('row_count', 0)}",
            f"- Valid rows: {import_summary.get('valid_row_count', 0)}",
            f"- Blockers: {import_summary.get('blocker_count', 0)}",
            f"- Warnings: {import_summary.get('warning_count', 0)}",
            f"- {import_summary.get('production_verified_label', 'production_verified=false')}",
            "",
            "This dry-run validates approved CRM/sheet outcome rows before any live sync. It checks tenant/module/partner scope, outcome stages, idempotency, source references, customer approval references, commercial amounts, loss reasons, and raw-contact/secret leakage.",
            "",
            "Evidence:",
            f"- Outcome import validation: {report.get('paths', {}).get('outcome_import_validation_markdown')}",
            f"- Outcome import issues: {report.get('paths', {}).get('outcome_import_issues')}",
            f"- Outcome import review rows: {report.get('paths', {}).get('outcome_import_review_rows')}",
        ]
    else:
        lines.append("- Status: not_generated")
    lines += [
        "",
        "## What This Proves",
        "",
        "- The customer demo, boardroom report, partner cutdowns, access model, governance pack, and release evidence are locally ready for buyer review.",
        "- The release room separates buyer readiness from live launch and production proof.",
        "- The customer rollout plan translates the evidence into RACI ownership, training, workstreams, and 30/60/90-day success criteria.",
        "- The procurement/security review pack turns common enterprise questions into evidence-backed answers, risk owners, and review blockers.",
        "- The customer pilot proposal turns the buyer-room evidence into a first paid pilot scope, milestones, assumptions, and decisions requested.",
        "- The customer training guide translates the evidence room into role-based adoption, training sessions, and visibility guardrails.",
        "- The value realization plan turns campaign data into executive KPIs, decision gates, and 30/60/90-day proof of value.",
        "- The outcome measurement contract explains how appointments, quotes, won/lost projects, project value, and loss reasons can be reconciled after a campaign without raw contact data or cross-tenant leakage.",
        "- The module expansion plan shows how FacadePilot, WindowPilot, RoofPilot, GardenPilot, PoolPilot, PorchPilot, and DrivewayPilot can grow on one tenant-safe platform.",
        "- The module readiness matrix proves every Pilot module has a reviewable metric/access/export contract, while disabled modules remain hidden until tenant entitlement and live proof pass.",
        "- The customer view catalog explains which DAW, partner, module-only, IT/security, and customer-success views can see which metrics, exports, and blocked data lanes.",
        "- The live launch control room turns the remaining production gap into stage gates, owners, env-var-only live inputs, live-proof blockers, and first-wave launch gates.",
        "- The public data source register shows which official/open-data lanes are approved for review, require legal review, or are blocked by default.",
        "- The public data production intake turns those sources into dataset-level approval owners, field allowlists, live-import gates, and production go/no-go evidence.",
        "- The first campaign launch intake turns the DAW/customer handoff into concrete partner, territory, contact-basis, suppression, message, capacity, and first-wave go/no-go inputs.",
        "- The DAW boardroom demo walkthrough turns the evidence room into a meeting-ready agenda, screen sequence, stakeholder Q&A, proof map, and follow-up decision list.",
        "- The Intelligence Lab evidence explains the autoresearched lead priority, partner wave, campaign segment, and message-test review loop without authorizing outreach.",
        "- The DAW first campaign control room turns the buyer demo into an operational cockpit for partner waves, owners, inputs, public-data approvals, live proof, and first-wave go/no-go.",
        "- Missing live inputs are owner-assigned without writing secret values.",
        "",
        "## What This Does Not Prove",
        "",
        "- It does not prove the Supabase schema has been applied to production.",
        "- It does not prove live RLS or customer access with real customer JWTs.",
        "- It does not convert synthetic demo metrics into live customer results.",
        "",
        "## Scorecard",
        "",
        "| Area | Status | Summary | Caveat |",
        "| --- | --- | --- | --- |",
    ]
    for row in report["scorecard"]:
        lines.append(f"| {row['label']} | {row['status']} | {row['summary']} | {row['caveat']} |")
    lines += ["", "## Priority Actions", ""]
    for action in report["actions"]:
        lines.append(f"- P{action['priority']} {action['owner']}: {action['action']}")
    lines += ["", "## Data Room Files", ""]
    for item in report["data_room"]:
        exists = "exists" if item["exists"] else "missing"
        lines.append(f"- {item['label']} ({item['audience']}): {exists} - {item['path']}")
    lines.append("")
    return "\n".join(lines)


def render_data_room_index(report: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Boardroom Data Room Index",
        "",
        "Use this as the customer-facing reading order. Each file is derived from the evidence pack; raw tenant rows and secrets stay out of this index.",
        "",
        "| File | Audience | Why It Matters | Status |",
        "| --- | --- | --- | --- |",
    ]
    for item in _portable_source_items(report):
        status = "exists" if _path_exists(str(item.get("path")) if item.get("path") else None) else "missing"
        lines.append(f"| {item['label']} | {item['audience']} | {item['why_it_matters']} | {status} |")
    lines.append("")
    return "\n".join(lines)


def render_stakeholder_views(report: dict[str, Any]) -> str:
    lines = ["# HomePilot Stakeholder Views", ""]
    for label, view in report["stakeholder_views"].items():
        lines += [
            f"## {label.replace('_', ' ').title()}",
            "",
            view["headline"],
            "",
            f"Decision: {view['decision']}",
            "",
            "Look at:",
        ]
        for item in view["look_at"]:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines)


def _file_href(path: str | None) -> str:
    if not path:
        return "#"
    try:
        return Path(path).resolve().as_uri()
    except ValueError:
        return "#"


def _status_label(status: str) -> str:
    return {
        "pass": "Ready",
        "blocked": "Blocked",
        "market_review_ready": "Market review ready",
        "production_ready": "Production ready",
        "action_required": "Action required",
        "go": "Go",
        "no_go": "No go",
    }.get(status, status.replace("_", " ").title())


def build_live_proof_cockpit(report: dict[str, Any]) -> dict[str, Any]:
    acceptance = report.get("live_proof_acceptance") or {}
    criteria = acceptance.get("criteria") or []
    summary = acceptance.get("summary") or {}
    blocked = [row for row in criteria if row.get("status") != "pass"]
    paths = report.get("paths") or {}
    production_verified = bool(summary.get("production_verified") is True or report.get("summary", {}).get("production_verified") is True)
    evidence = [
        {
            "label": "Live proof acceptance matrix",
            "path": paths.get("live_proof_acceptance_markdown"),
            "source": "live_proof_acceptance",
        },
        {
            "label": "Live proof acceptance CSV",
            "path": paths.get("live_proof_acceptance_csv"),
            "source": "live_proof_acceptance",
        },
        {
            "label": "Live credential handoff",
            "audience": "IT owner, security, customer success, HomePilot operator",
            "why_it_matters": "Secret-safe contract for live Supabase, RLS fixture, and customer-access inputs, safe channels, validation artifacts, and evidence archive rules.",
            "path": paths["live_credential_handoff_markdown"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Live credential checklist",
            "audience": "IT owner, customer success, HomePilot operator",
            "why_it_matters": "Excel-ready owner checklist for every live credential/config input without storing secret values.",
            "path": paths["live_credential_handoff_checklist"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Live secret channel contract",
            "audience": "IT owner, security, HomePilot operator",
            "why_it_matters": "Approved secret channels, forbidden channels, validation commands, and expected proof artifacts for each live input.",
            "path": paths["live_secret_channel_contract"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Live proof execution plan",
            "path": paths.get("live_proof_plan_markdown"),
            "source": "live_proof_plan",
        },
        {
            "label": "Live launch control room",
            "path": paths.get("live_launch_control_room_markdown"),
            "source": "live_launch_control_room",
        },
        {
            "label": "Live credential handoff",
            "path": paths.get("live_credential_handoff_markdown"),
            "source": "live_credential_handoff",
        },
        {
            "label": "Live credential checklist",
            "path": paths.get("live_credential_handoff_checklist"),
            "source": "live_credential_handoff",
        },
        {
            "label": "Live proof evidence vault",
            "path": paths.get("live_proof_evidence_vault_markdown"),
            "source": "live_proof_evidence_vault",
        },
        {
            "label": "Live proof archive index",
            "path": paths.get("live_proof_archive_index"),
            "source": "live_proof_evidence_vault",
        },
    ]
    return {
        "section_type": "homepilot_live_proof_cockpit",
        "status": acceptance.get("status") or "not_generated",
        "release_label": report.get("release_label"),
        "summary": {
            "criterion_count": int(summary.get("criterion_count") or len(criteria)),
            "passed_count": int(summary.get("passed_count") or 0),
            "blocked_count": int(summary.get("blocked_count") or len(blocked)),
            "live_launch_blockers": int(summary.get("live_launch_blockers") or 0),
            "production_blockers": int(summary.get("production_blockers") or 0),
            "live_launch_task_count": summary.get("live_launch_task_count", report.get("summary", {}).get("live_launch_task_count")),
            "production_verified": production_verified,
            "production_verified_label": f"production_verified={str(production_verified).lower()}",
            "secret_scan_status": (acceptance.get("secret_scan") or {}).get("status", "unknown"),
        },
        "blockers": [
            {
                "key": row.get("key"),
                "label": row.get("label"),
                "stage": row.get("stage"),
                "status": row.get("status"),
                "owner": row.get("owner"),
                "blocker": row.get("blocker"),
                "next_action": row.get("next_action"),
                "source_artifacts": row.get("source_artifacts") or [],
            }
            for row in blocked[:6]
        ],
        "evidence": evidence,
        "guardrails": {
            "review_surface_only": True,
            "no_live_writes": True,
            "no_secret_values": True,
            "customer_signoff_cannot_override_technical_proof": True,
        },
    }


def render_html(report: dict[str, Any]) -> str:
    decisions = report["decisions"]
    summary = report["summary"]
    pass_count = len([row for row in report["scorecard"] if row["status"] == "pass"])
    blocked_count = len([row for row in report["scorecard"] if row["status"] != "pass"])
    total_count = len(report["scorecard"])
    ready_pct = int(round((pass_count / total_count) * 100)) if total_count else 0
    score_rows = "\n".join(
        f"""
        <article class="score {escape(row['status'])}">
          <div class="score-top">
            <span>{escape(row['label'])}</span>
            <strong>{escape(_status_label(row['status']))}</strong>
          </div>
          <p>{escape(row['summary'])}</p>
          <small>{escape(row['caveat'])}</small>
        </article>
        """
        for row in report["scorecard"]
    )
    action_rows = "\n".join(
        f"""
        <tr>
          <td data-label="Priority">P{escape(str(action['priority']))}</td>
          <td data-label="Owner">{escape(str(action['owner']))}</td>
          <td data-label="Action">{escape(str(action['action']))}</td>
          <td data-label="Status"><span class="pill muted">{escape(str(action['status']))}</span></td>
        </tr>
        """
        for action in report["actions"]
    )
    data_room_rows = "\n".join(
        f"""
        <tr>
          <td data-label="File"><a href="{escape(_file_href(str(item.get('path')) if item.get('path') else None))}">{escape(str(item['label']))}</a></td>
          <td data-label="Audience">{escape(str(item['audience']))}</td>
          <td data-label="Why it matters">{escape(str(item['why_it_matters']))}</td>
          <td data-label="Status"><span class="pill {'ok' if item['exists'] else 'warn'}">{'exists' if item['exists'] else 'missing'}</span></td>
        </tr>
        """
        for item in report["data_room"]
    )
    stakeholder_blocks = "\n".join(
        f"""
        <article class="stakeholder">
          <h3>{escape(label.replace('_', ' ').title())}</h3>
          <p>{escape(str(view['headline']))}</p>
          <span class="pill {'ok' if view['decision'] == 'go' else 'warn'}">{escape(_status_label(str(view['decision'])))}</span>
        </article>
        """
        for label, view in report["stakeholder_views"].items()
    )
    signoff = report.get("customer_signoff_reconciliation") or {}
    signoff_summary = signoff.get("summary") or {}
    signoff_rows = "\n".join(
        f"""
        <tr>
          <td data-label="Decision">{escape(str(row.get('decision_area', '')))}</td>
          <td data-label="Stage">{escape(str(row.get('required_stage', '')))}</td>
          <td data-label="Signoff"><span class="pill {'ok' if row.get('signoff_status') == 'signed_or_approved' else 'warn'}">{escape(_status_label(str(row.get('signoff_status', 'missing'))))}</span></td>
          <td data-label="Live">{escape('blocks' if row.get('blocks_live_launch') else 'does not block')}</td>
          <td data-label="Production">{escape('blocks' if row.get('blocks_production') else 'does not block')}</td>
          <td data-label="Next action">{escape(str(row.get('next_action', '')))}</td>
        </tr>
        """
        for row in signoff.get("decision_matrix") or []
    )
    decision_board_block = ""
    if signoff:
        decision_board_block = f"""
    <section class="decision-board">
      <div class="section-head">
        <div>
          <h2>Customer Decision Board</h2>
          <p>Customer signoff status, live-launch blockers, production blockers, and next actions in one boardroom view.</p>
        </div>
        <span class="pill warn">{escape(_status_label(str(signoff.get('status', 'blocked'))))}</span>
      </div>
      <div class="decision-metrics">
        <div class="decision-metric"><span>Signed/approved</span><strong>{escape(str(signoff_summary.get('signed_decision_count', 0)))}/{escape(str(signoff_summary.get('decision_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Ready for decision</span><strong>{escape(str(signoff_summary.get('ready_for_review_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Live-launch blockers</span><strong>{escape(str(signoff_summary.get('live_launch_blockers', 0)))}</strong></div>
        <div class="decision-metric"><span>Production blockers</span><strong>{escape(str(signoff_summary.get('production_blockers', 0)))}</strong></div>
        <div class="decision-metric"><span>Evidence rows applied</span><strong>{escape(str(signoff_summary.get('signoff_evidence_rows_applied', 0)))}</strong></div>
      </div>
      <div class="note">Buyer-ready is not customer-approved until signed references are archived; customer signoff CSVs cannot replace live schema, RLS, or customer-access proof.</div>
      <table class="decision-table">
        <thead><tr><th>Decision</th><th>Stage</th><th>Signoff</th><th>Live</th><th>Production</th><th>Next action</th></tr></thead>
        <tbody>{signoff_rows}</tbody>
      </table>
    </section>
        """
    view_catalog = report.get("customer_view_catalog") or {}
    view_catalog_summary = view_catalog.get("summary") or {}
    view_rows = "\n".join(
        f"""
        <tr>
          <td data-label="View">{escape(str(row.get('view_label', '')))}</td>
          <td data-label="Audience">{escape(str(row.get('audience', '')))}</td>
          <td data-label="Role">{escape(str(row.get('default_role', '')))}</td>
          <td data-label="Scope">{escape(str(row.get('access_scope', '')))}</td>
          <td data-label="Module">{escape(str(row.get('module_scope', '')))}</td>
          <td data-label="Live gate">{escape(str(row.get('live_gate', '')))}</td>
        </tr>
        """
        for row in view_catalog.get("views") or []
    )
    view_catalog_block = ""
    if view_catalog:
        view_catalog_block = f"""
    <section class="view-catalog">
      <div class="section-head">
        <div>
          <h2>Customer Access Lenses</h2>
          <p>Who can see which HomePilot metrics, exports, partner scopes, and blocked data lanes.</p>
        </div>
        <span class="pill warn">{escape(_status_label(str(view_catalog.get('status', 'blocked'))))}</span>
      </div>
      <div class="decision-metrics">
        <div class="decision-metric"><span>Views</span><strong>{escape(str(view_catalog_summary.get('view_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Modules</span><strong>{escape(str(view_catalog_summary.get('module_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Live access</span><strong>{escape(str(view_catalog_summary.get('live_access_ready', False)).lower())}</strong></div>
        <div class="decision-metric"><span>Partner access</span><strong>{escape(str(view_catalog_summary.get('partner_access_ready', False)).lower())}</strong></div>
        <div class="decision-metric"><span>Portal runtime</span><strong>{escape(str(view_catalog_summary.get('portal_runtime_status', 'unknown')))}</strong></div>
      </div>
      <div class="note">This catalog is a buyer-review explanation layer. Runtime access still requires tenant_id, module_key, partner_id where applicable, Supabase RLS, and customer JWT proof.</div>
      <table class="decision-table">
        <thead><tr><th>View</th><th>Audience</th><th>Role</th><th>Scope</th><th>Module</th><th>Live gate</th></tr></thead>
        <tbody>{view_rows}</tbody>
      </table>
    </section>
        """
    data_platform = report.get("data_platform_blueprint") or {}
    data_platform_summary = data_platform.get("summary") or {}
    data_platform_scope = data_platform.get("current_customer_scope") or {}
    data_platform_modules = ", ".join(str(item) for item in data_platform_scope.get("module_labels") or [])
    data_platform_links = ""
    if data_platform:
        data_platform_links = "\n".join(
            f"""<a href="{escape(_file_href(str(path) if path else None))}">{escape(label)}</a>"""
            for label, path in (
                ("Data platform blueprint", report.get("paths", {}).get("data_platform_blueprint_markdown")),
                ("Scope matrix", report.get("paths", {}).get("data_platform_scope_matrix")),
            )
        )
    data_platform_block = ""
    if data_platform:
        data_platform_block = f"""
    <section class="data-platform-blueprint">
      <div class="section-head">
        <div>
          <h2>Data Platform Blueprint</h2>
          <p>One shared property spine across pilots, with tenant, module, partner, campaign, export, public-data, and live-proof boundaries made reviewable.</p>
        </div>
        <span class="pill warn">{escape(_status_label(str(data_platform.get('status', 'blocked'))))}</span>
      </div>
      <div class="decision-metrics">
        <div class="decision-metric"><span>Pilot modules</span><strong>{escape(str(data_platform_summary.get('module_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Enabled here</span><strong>{escape(str(data_platform_summary.get('enabled_module_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Data layers</span><strong>{escape(str(data_platform_summary.get('data_layer_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Access lenses</span><strong>{escape(str(data_platform_summary.get('access_lens_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Export surfaces</span><strong>{escape(str(data_platform_summary.get('export_surface_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Production verified</span><strong>{escape(str(data_platform_summary.get('production_verified_label', 'production_verified=false')))}</strong></div>
      </div>
      <p><strong>{escape(str(data_platform.get('architecture_rule', 'tenant -> modules -> campaigns -> properties -> assessments -> interactions')))}</strong></p>
      <p>Current enabled modules: {escape(data_platform_modules or 'none')}</p>
      <div class="note">One database does not mean one shared customer dataset: raw addresses, responses, notes, exports, and campaign learnings remain tenant-, module-, and partner-scoped.</div>
      <div class="evidence-links">{data_platform_links}</div>
    </section>
        """
    module_readiness = report.get("module_readiness_matrix") or {}
    module_readiness_summary = module_readiness.get("summary") or {}
    module_readiness_rows = "\n".join(
        f"""
        <tr>
          <td data-label="Module"><strong>{escape(str(row.get('label', '')))}</strong><br><code>{escape(str(row.get('module_key', '')))}</code></td>
          <td data-label="Enabled">{escape(str(row.get('enabled_in_current_customer_scope', False)).lower())}</td>
          <td data-label="Metrics">{escape(str(row.get('metric_count', 0)))}</td>
          <td data-label="Dashboard">{escape(str(row.get('dashboard_metric_count', 0)))}</td>
          <td data-label="Export">{escape(str(row.get('export_metric_count', 0)))}</td>
          <td data-label="Overall"><span class="pill warn">{escape(_status_label(str(row.get('overall_status', 'blocked'))))}</span></td>
          <td data-label="Live proof">{escape(str(row.get('live_proof_status', 'blocked')))}</td>
        </tr>
        """
        for row in module_readiness.get("modules") or []
    )
    module_readiness_links = ""
    if module_readiness:
        module_readiness_links = "\n".join(
            f"""<a href="{escape(_file_href(str(path) if path else None))}">{escape(label)}</a>"""
            for label, path in (
                ("Module readiness matrix", report.get("paths", {}).get("module_readiness_matrix_markdown")),
                ("Module readiness CSV", report.get("paths", {}).get("module_readiness_matrix_csv")),
                ("Module metric coverage", report.get("paths", {}).get("module_metric_coverage")),
            )
        )
    module_readiness_block = ""
    if module_readiness:
        module_readiness_block = f"""
    <section class="module-readiness">
      <div class="section-head">
        <div>
          <h2>Module Readiness Matrix</h2>
          <p>Per-pilot proof of metric contracts, visibility, exports, public-data lanes, and live-production gates across the shared HomePilot spine.</p>
        </div>
        <span class="pill warn">{escape(_status_label(str(module_readiness.get('status', 'blocked'))))}</span>
      </div>
      <div class="decision-metrics">
        <div class="decision-metric"><span>Modules</span><strong>{escape(str(module_readiness_summary.get('module_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Enabled here</span><strong>{escape(str(module_readiness_summary.get('enabled_module_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Buyer ready</span><strong>{escape(str(module_readiness_summary.get('buyer_ready_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Production ready</span><strong>{escape(str(module_readiness_summary.get('production_ready_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Metric rows</span><strong>{escape(str(module_readiness_summary.get('metric_coverage_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Production verified</span><strong>{escape(str(module_readiness_summary.get('production_verified_label', 'production_verified=false')))}</strong></div>
      </div>
      <div class="note">Buyer-ready means reviewable contracts and safe demo/export surfaces. Production-ready still requires tenant entitlement plus live schema, RLS, and customer-access proof.</div>
      <table class="decision-table">
        <thead><tr><th>Module</th><th>Enabled</th><th>Metrics</th><th>Dashboard</th><th>Export</th><th>Overall</th><th>Live proof</th></tr></thead>
        <tbody>{module_readiness_rows}</tbody>
      </table>
      <div class="evidence-links">{module_readiness_links}</div>
    </section>
        """
    live_proof_cockpit = report.get("live_proof_cockpit") or build_live_proof_cockpit(report)
    live_proof_summary = live_proof_cockpit.get("summary") or {}
    live_proof_rows = "\n".join(
        f"""
        <tr>
          <td data-label="Key"><code>{escape(str(row.get('key', '')))}</code></td>
          <td data-label="Stage">{escape(str(row.get('stage', '')))}</td>
          <td data-label="Status"><span class="pill warn">{escape(_status_label(str(row.get('status', 'blocked'))))}</span></td>
          <td data-label="Owner">{escape(str(row.get('owner', '')))}</td>
          <td data-label="Blocker">{escape(str(row.get('blocker', '')))}</td>
          <td data-label="Next action">{escape(str(row.get('next_action', '')))}</td>
        </tr>
        """
        for row in live_proof_cockpit.get("blockers") or []
    )
    live_proof_links = "\n".join(
        f"""<a href="{escape(_file_href(str(item.get('path')) if item.get('path') else None))}">{escape(str(item.get('label', 'Evidence')))}</a>"""
        for item in live_proof_cockpit.get("evidence") or []
    )
    live_proof_class = "ok" if live_proof_summary.get("production_verified") is True else "warn"
    live_proof_block = ""
    if live_proof_cockpit.get("status") != "not_generated":
        live_proof_block = f"""
    <section class="live-proof-cockpit">
      <div class="section-head">
        <div>
          <h2>Live Proof Cockpit</h2>
          <p>Customer/IT acceptance evidence, live blockers, production proof status, and next actions without storing secrets or writing live data.</p>
        </div>
        <span class="pill {live_proof_class}">{escape(_status_label(str(live_proof_cockpit.get('status', 'blocked'))))}</span>
      </div>
      <div class="decision-metrics">
        <div class="decision-metric"><span>Acceptance criteria</span><strong>{escape(str(live_proof_summary.get('criterion_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Blocked</span><strong>{escape(str(live_proof_summary.get('blocked_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Live blockers</span><strong>{escape(str(live_proof_summary.get('live_launch_blockers', 0)))}</strong></div>
        <div class="decision-metric"><span>Production blockers</span><strong>{escape(str(live_proof_summary.get('production_blockers', 0)))}</strong></div>
        <div class="decision-metric"><span>Live launch tasks</span><strong>{escape(str(live_proof_summary.get('live_launch_task_count')))}</strong></div>
        <div class="decision-metric"><span>Production verified</span><strong>{escape(str(live_proof_summary.get('production_verified_label', 'production_verified=false')))}</strong></div>
      </div>
      <div class="note">Review surface only: no live writes, no secret values, and customer signoff cannot override failed schema, RLS, or customer-access proof.</div>
      <div class="evidence-links">{live_proof_links}</div>
      <table class="decision-table">
        <thead><tr><th>Key</th><th>Stage</th><th>Status</th><th>Owner</th><th>Blocker</th><th>Next action</th></tr></thead>
        <tbody>{live_proof_rows}</tbody>
      </table>
    </section>
        """
    credential_handoff = report.get("live_credential_handoff") or {}
    credential_handoff_block = ""
    if credential_handoff:
        credential_summary = credential_handoff.get("summary") or {}
        credential_rows = "\n".join(
            f"""
        <tr>
          <td data-label="Input">{escape(str(row.get('input_name', '')))}</td>
          <td data-label="Env"><code>{escape(str(row.get('env_var', '')))}</code></td>
          <td data-label="Owner">{escape(str(row.get('owner_label', '')))}</td>
          <td data-label="Channel">{escape(str(row.get('safe_channel', '')))}</td>
          <td data-label="Unlocks">{escape(str(row.get('unlocks_gate', '')))}</td>
        </tr>
            """
            for row in (credential_handoff.get("handoff_rows") or [])[:8]
        )
        credential_links = "\n".join(
            f"""<a href="{escape(_file_href(str(path) if path else None))}">{escape(label)}</a>"""
            for label, path in (
                ("Credential handoff", report.get("paths", {}).get("live_credential_handoff_markdown")),
                ("Credential checklist", report.get("paths", {}).get("live_credential_handoff_checklist")),
                ("Secret channel contract", report.get("paths", {}).get("live_secret_channel_contract")),
            )
        )
        credential_class = "ok" if credential_summary.get("live_inputs_ready") is True else "warn"
        credential_handoff_block = f"""
    <section class="live-credential-handoff">
      <div class="section-head">
        <div>
          <h2>Live Credential Handoff</h2>
          <p>Customer/IT-safe contract for Supabase, RLS fixture, and customer-access inputs, with approved channels and validation artifacts.</p>
        </div>
        <span class="pill {credential_class}">{escape(_status_label(str(credential_handoff.get('status', 'handoff_required'))))}</span>
      </div>
      <div class="decision-metrics">
        <div class="decision-metric"><span>Open tasks</span><strong>{escape(str(credential_summary.get('task_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Secret-bearing</span><strong>{escape(str(credential_summary.get('secret_task_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Env vars</span><strong>{escape(str(credential_summary.get('env_var_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Owners</span><strong>{escape(str(credential_summary.get('owner_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Live inputs ready</span><strong>{escape(str(credential_summary.get('live_inputs_ready', False)).lower())}</strong></div>
        <div class="decision-metric"><span>Production verified</span><strong>{escape(str(credential_summary.get('production_verified_label', 'production_verified=false')))}</strong></div>
      </div>
      <div class="note">Env var names only: secret values stay in the approved secret manager or local live-proof session, never in the data room.</div>
      <div class="evidence-links">{credential_links}</div>
      <table class="decision-table">
        <thead><tr><th>Input</th><th>Env</th><th>Owner</th><th>Channel</th><th>Unlocks</th></tr></thead>
        <tbody>{credential_rows}</tbody>
      </table>
    </section>
        """
    live_proof_vault = report.get("live_proof_evidence_vault") or {}
    vault_block = ""
    if live_proof_vault:
        vault_summary = live_proof_vault.get("summary") or {}
        vault_rows = "\n".join(
            f"""
        <tr>
          <td data-label="Evidence">{escape(str(row.get('label', '')))}</td>
          <td data-label="Stage">{escape(str(row.get('stage', '')))}</td>
          <td data-label="Current"><span class="pill warn">{escape(_status_label(str(row.get('current_status', 'blocked'))))}</span></td>
          <td data-label="Required">{escape(str(row.get('required_status', '')))}</td>
          <td data-label="Blocker">{escape(str(row.get('blocker', '') or 'none'))}</td>
        </tr>
            """
            for row in (live_proof_vault.get("evidence_rows") or [])[:8]
        )
        vault_links = "\n".join(
            f"""<a href="{escape(_file_href(str(path) if path else None))}">{escape(label)}</a>"""
            for label, path in (
                ("Evidence vault", report.get("paths", {}).get("live_proof_evidence_vault_markdown")),
                ("Archive index", report.get("paths", {}).get("live_proof_archive_index")),
            )
        )
        vault_class = "ok" if vault_summary.get("production_verified") is True else "warn"
        vault_block = f"""
    <section class="live-proof-vault">
      <div class="section-head">
        <div>
          <h2>Live Proof Evidence Vault</h2>
          <p>Archive index for schema, RLS, customer access, partner access, public-data, signoff, first-wave, and production proof.</p>
        </div>
        <span class="pill {vault_class}">{escape(_status_label(str(live_proof_vault.get('status', 'blocked'))))}</span>
      </div>
      <div class="decision-metrics">
        <div class="decision-metric"><span>Evidence rows</span><strong>{escape(str(vault_summary.get('required_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Archived</span><strong>{escape(str(vault_summary.get('archived_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Passed</span><strong>{escape(str(vault_summary.get('passed_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Blocked</span><strong>{escape(str(vault_summary.get('blocked_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Production verified</span><strong>{escape(str(vault_summary.get('production_verified_label', 'production_verified=false')))}</strong></div>
      </div>
      <div class="note">Evidence archive only: no live writes, no secret values, no raw contact data, and no production claim without live schema/RLS/customer-access proof.</div>
      <div class="evidence-links">{vault_links}</div>
      <table class="decision-table">
        <thead><tr><th>Evidence</th><th>Stage</th><th>Current</th><th>Required</th><th>Blocker</th></tr></thead>
        <tbody>{vault_rows}</tbody>
      </table>
    </section>
        """
    outcome_contract = report.get("outcome_measurement_contract") or {}
    outcome_block = ""
    if outcome_contract:
        outcome_summary = outcome_contract.get("summary") or {}
        outcome_rows = "\n".join(
            f"""
        <tr>
          <td data-label="Metric">{escape(str(row.get('metric', '')))}</td>
          <td data-label="Numerator">{escape(str(row.get('numerator', '')))}</td>
          <td data-label="Denominator">{escape(str(row.get('denominator', '')))}</td>
          <td data-label="Guardrail">{escape(str(row.get('guardrail', '')))}</td>
        </tr>
            """
            for row in (outcome_contract.get("outcome_metrics") or [])[:6]
        )
        outcome_links = "\n".join(
            f"""<a href="{escape(_file_href(str(path) if path else None))}">{escape(label)}</a>"""
            for label, path in (
                ("Outcome contract", report.get("paths", {}).get("outcome_measurement_contract_markdown")),
                ("Event schema", report.get("paths", {}).get("outcome_event_schema")),
                ("Sync template", report.get("paths", {}).get("outcome_sync_template")),
                ("Reconciliation checklist", report.get("paths", {}).get("outcome_reconciliation_checklist")),
            )
        )
        outcome_class = "ok" if outcome_summary.get("blocked_gate_count", 0) == 0 else "warn"
        outcome_block = f"""
    <section class="outcome-contract">
      <div class="section-head">
        <div>
          <h2>Outcome Measurement Contract</h2>
          <p>Closed-loop measurement for appointments, quotes, won/lost projects, value, and loss reasons after campaign launch.</p>
        </div>
        <span class="pill {outcome_class}">{escape(_status_label(str(outcome_contract.get('status', 'blocked'))))}</span>
      </div>
      <div class="decision-metrics">
        <div class="decision-metric"><span>Event fields</span><strong>{escape(str(outcome_summary.get('event_field_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Outcome metrics</span><strong>{escape(str(outcome_summary.get('metric_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Checklist gates</span><strong>{escape(str(outcome_summary.get('checklist_gate_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Blocked gates</span><strong>{escape(str(outcome_summary.get('blocked_gate_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Production verified</span><strong>{escape(str(outcome_summary.get('production_verified_label', 'production_verified=false')))}</strong></div>
      </div>
      <div class="note">Review contract only: no live CRM writes, no Supabase writes, no raw contact data, and no commercial outcome claim until customer-approved source evidence is reconciled.</div>
      <div class="evidence-links">{outcome_links}</div>
      <table class="decision-table">
        <thead><tr><th>Metric</th><th>Numerator</th><th>Denominator</th><th>Guardrail</th></tr></thead>
        <tbody>{outcome_rows}</tbody>
      </table>
    </section>
        """
    outcome_import = report.get("outcome_import_validation") or {}
    outcome_import_block = ""
    if outcome_import:
        import_summary = outcome_import.get("summary") or {}
        import_links = "\n".join(
            f"""<a href="{escape(_file_href(str(path) if path else None))}">{escape(label)}</a>"""
            for label, path in (
                ("Import validation", report.get("paths", {}).get("outcome_import_validation_markdown")),
                ("Import issues", report.get("paths", {}).get("outcome_import_issues")),
                ("Review rows", report.get("paths", {}).get("outcome_import_review_rows")),
            )
        )
        import_class = "ok" if int(import_summary.get("blocker_count") or 0) == 0 else "warn"
        outcome_import_block = f"""
    <section class="outcome-import">
      <div class="section-head">
        <div>
          <h2>Outcome Import Dry-Run</h2>
          <p>Safe preflight for CRM/sheet outcome rows before any live sync.</p>
        </div>
        <span class="pill {import_class}">{escape(_status_label(str(outcome_import.get('status', 'blocked'))))}</span>
      </div>
      <div class="decision-metrics">
        <div class="decision-metric"><span>Rows checked</span><strong>{escape(str(import_summary.get('row_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Valid rows</span><strong>{escape(str(import_summary.get('valid_row_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Blockers</span><strong>{escape(str(import_summary.get('blocker_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Warnings</span><strong>{escape(str(import_summary.get('warning_count', 0)))}</strong></div>
        <div class="decision-metric"><span>Sync decision</span><strong>{escape(_status_label(str(outcome_import.get('sync_decision', 'blocked'))))}</strong></div>
        <div class="decision-metric"><span>Production verified</span><strong>{escape(str(import_summary.get('production_verified_label', 'production_verified=false')))}</strong></div>
      </div>
      <div class="note">Dry-run only: validates scope, stages, idempotency, source references, approvals, amounts, loss reasons, and data hygiene, but does not write to Supabase or CRMs.</div>
      <div class="evidence-links">{import_links}</div>
    </section>
        """
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HomePilot Market Readiness</title>
  <style>
    :root {{
      color-scheme: light;
      --ink:#17211c;
      --muted:#5f6b64;
      --line:#d9dfd8;
      --paper:#f7f8f5;
      --panel:#ffffff;
      --ok:#1f8f61;
      --ok-bg:#e6f4ed;
      --warn:#b65c1e;
      --warn-bg:#fff0df;
      --dark:#10231b;
      --accent:#2f6f5e;
    }}
    * {{ box-sizing:border-box; }}
    body {{
      margin:0;
      font:14px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color:var(--ink);
      background:var(--paper);
    }}
    main {{ max-width:1220px; margin:0 auto; padding:24px; }}
    header {{
      display:grid;
      grid-template-columns:minmax(0,1.35fr) minmax(300px,.65fr);
      gap:20px;
      align-items:stretch;
      margin-bottom:18px;
    }}
    .headline, .decision-panel, .score, .stakeholder, section {{
      background:var(--panel);
      border:1px solid var(--line);
      border-radius:8px;
      min-width:0;
    }}
    header > *, .kpis > *, .score-grid > *, .stakeholder-grid > * {{ min-width:0; }}
    .headline {{ padding:22px; }}
    .eyebrow {{ color:var(--accent); font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:0; }}
    h1 {{ margin:8px 0 8px; font-size:32px; line-height:1.08; letter-spacing:0; }}
    h2 {{ margin:0 0 14px; font-size:18px; letter-spacing:0; }}
    h3 {{ margin:0 0 8px; font-size:15px; letter-spacing:0; }}
    h1, h2, h3, p, a, .note, .decision strong, .score-top span {{ overflow-wrap:anywhere; }}
    p {{ margin:0; color:var(--muted); }}
    .decision-panel {{ padding:18px; display:grid; gap:12px; }}
    .decision-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }}
    .decision {{ border:1px solid var(--line); border-radius:6px; padding:10px; background:#fbfcfa; }}
    .decision span {{ display:block; color:var(--muted); font-size:12px; }}
    .decision strong {{ display:block; margin-top:4px; font-size:18px; }}
    .meter {{ height:10px; border-radius:999px; background:#e7ebe5; overflow:hidden; }}
    .meter > div {{ height:100%; width:{ready_pct}%; background:linear-gradient(90deg, var(--ok), #7aae5f); }}
    .kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:18px; }}
    .kpi {{ background:var(--dark); color:white; border-radius:8px; padding:16px; min-height:92px; }}
    .kpi span {{ display:block; color:#b9c7bf; font-size:12px; }}
    .kpi strong {{ display:block; margin-top:8px; font-size:26px; line-height:1; }}
    section {{ padding:18px; margin-bottom:18px; overflow-x:auto; }}
    .section-head {{ display:flex; justify-content:space-between; gap:14px; align-items:flex-start; margin-bottom:14px; }}
    .decision-metrics {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(135px,1fr)); gap:10px; margin-bottom:14px; }}
    .decision-metric {{ border:1px solid var(--line); border-radius:6px; padding:12px; background:#fbfcfa; min-height:82px; }}
    .decision-metric span {{ display:block; color:var(--muted); font-size:12px; }}
    .decision-metric strong {{ display:block; margin-top:8px; font-size:24px; line-height:1; }}
    .decision-table {{ margin-top:14px; }}
    .score-grid {{ display:grid; grid-template-columns:repeat(7, minmax(135px,1fr)); gap:10px; }}
    .score {{ padding:12px; min-height:160px; display:flex; flex-direction:column; gap:10px; }}
    .score-top {{ display:flex; justify-content:space-between; gap:10px; align-items:flex-start; }}
    .score-top span {{ font-weight:700; }}
    .score-top strong {{ font-size:12px; border-radius:999px; padding:4px 8px; white-space:nowrap; }}
    .score.pass .score-top strong, .pill.ok {{ color:var(--ok); background:var(--ok-bg); }}
    .score.blocked .score-top strong, .pill.warn {{ color:var(--warn); background:var(--warn-bg); }}
    .score small {{ color:var(--muted); margin-top:auto; }}
    .stakeholder-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }}
    .stakeholder {{ padding:14px; min-height:128px; }}
    .stakeholder p {{ min-height:62px; }}
    table {{ width:100%; min-width:760px; border-collapse:collapse; }}
    th, td {{ border-bottom:1px solid var(--line); padding:10px 8px; text-align:left; vertical-align:top; }}
    th {{ font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:0; }}
    td {{ overflow-wrap:anywhere; }}
    a {{ color:#245c4e; text-decoration:none; font-weight:650; }}
    a:hover {{ text-decoration:underline; }}
    code {{ color:#214e43; background:#eef4f1; border-radius:4px; padding:2px 5px; font-size:12px; }}
    .evidence-links {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }}
    .evidence-links a {{ border:1px solid var(--line); border-radius:999px; padding:7px 10px; background:#fbfcfa; }}
    .pill {{ display:inline-flex; align-items:center; border-radius:999px; padding:4px 8px; font-size:12px; font-weight:700; }}
    .pill.muted {{ color:var(--muted); background:#eef1ec; }}
    .note {{ border-left:4px solid var(--warn); padding:10px 12px; background:#fff8ef; color:#704015; margin-top:14px; border-radius:6px; }}
    @media (max-width:980px) {{
      main {{ padding:14px; }}
      header, .kpis, .score-grid, .stakeholder-grid, .decision-metrics {{ grid-template-columns:1fr; }}
      .section-head {{ display:block; }}
      .section-head .pill {{ margin-top:10px; }}
      .decision-grid {{ grid-template-columns:1fr; }}
      h1 {{ font-size:26px; }}
      table {{ font-size:13px; }}
    }}
    @media (max-width:700px) {{
      section {{ overflow-x:visible; }}
      table {{ min-width:0; }}
      thead {{ display:none; }}
      tbody, tr, td {{ display:block; width:100%; }}
      tr {{ border-bottom:1px solid var(--line); padding:10px 0; }}
      td {{ border-bottom:0; padding:4px 0 4px 124px; position:relative; min-height:24px; }}
      td::before {{ content:attr(data-label); position:absolute; left:0; width:108px; color:var(--muted); font-weight:700; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div class="headline">
        <div class="eyebrow">HomePilot market readiness</div>
        <h1>Buyer-ready property intelligence, with live launch blockers explicit.</h1>
        <p>This view is generated from the evidence pack. It is a reading layer, not a new source of proof.</p>
        <div class="note">Production stays no-go until live Supabase schema verification, live RLS launch, and customer access verification all pass with production_verified=true.</div>
      </div>
      <aside class="decision-panel">
        <h2>Release decisions</h2>
        <div class="decision-grid">
          <div class="decision"><span>Buyer review</span><strong>{escape(_status_label(decisions['buyer_review']))}</strong></div>
          <div class="decision"><span>Live launch</span><strong>{escape(_status_label(decisions['live_launch']))}</strong></div>
          <div class="decision"><span>Production</span><strong>{escape(_status_label(decisions['production']))}</strong></div>
        </div>
        <div>
          <p>{pass_count} of {total_count} areas ready</p>
          <div class="meter" aria-label="Readiness meter"><div></div></div>
        </div>
      </aside>
    </header>

    <div class="kpis">
      <div class="kpi"><span>Readiness gates</span><strong>{escape(str(summary['readiness_gate_count']))}</strong></div>
      <div class="kpi"><span>Live launch tasks</span><strong>{escape(str(summary['live_launch_task_count']))}</strong></div>
      <div class="kpi"><span>Secret values written</span><strong>{escape(str(summary['secrets_written']).lower())}</strong></div>
      <div class="kpi"><span>Blocked areas</span><strong>{blocked_count}</strong></div>
    </div>

    {decision_board_block}

    {view_catalog_block}

    {data_platform_block}

    {module_readiness_block}

    {live_proof_block}

    {credential_handoff_block}

    {vault_block}

    {outcome_block}

    {outcome_import_block}

    <section>
      <h2>Readiness Matrix</h2>
      <div class="score-grid">{score_rows}</div>
    </section>

    <section>
      <h2>Stakeholder Views</h2>
      <div class="stakeholder-grid">{stakeholder_blocks}</div>
    </section>

    <section>
      <h2>Priority Actions</h2>
      <table>
        <thead><tr><th>Priority</th><th>Owner</th><th>Action</th><th>Status</th></tr></thead>
        <tbody>{action_rows}</tbody>
      </table>
    </section>

    <section>
      <h2>Data Room</h2>
      <table>
        <thead><tr><th>File</th><th>Audience</th><th>Why it matters</th><th>Status</th></tr></thead>
        <tbody>{data_room_rows}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "artifact"


def _portable_source_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    paths = report["paths"]
    own_items = [
        {
            "label": "Market readiness scorecard",
            "audience": "Boardroom, security, procurement",
            "why_it_matters": "Plain-language summary of buyer-readiness, live blockers, and priority actions.",
            "path": paths["markdown"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Boardroom data room index",
            "audience": "Boardroom, customer success",
            "why_it_matters": "Reading order for all evidence files in this customer handoff.",
            "path": paths["data_room_index"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Stakeholder views",
            "audience": "Boardroom, IT, customer success, sales",
            "why_it_matters": "Stakeholder-specific interpretation of the same release evidence.",
            "path": paths["stakeholder_views"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Priority actions",
            "audience": "Operator, IT owner, customer success",
            "why_it_matters": "CSV task list for the remaining live-launch and production blockers.",
            "path": paths["actions_csv"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Live launch control room",
            "audience": "Boardroom, IT owner, customer success, HomePilot operator",
            "why_it_matters": "One cockpit for buyer-review, live-input, schema, RLS, customer-access, first-wave, and production go/no-go gates.",
            "path": paths["live_launch_control_room_markdown"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Live launch action board",
            "audience": "IT owner, customer success, HomePilot operator",
            "why_it_matters": "Excel-ready action board with owners, evidence, env var names, live-proof blockers, and first-wave blockers without secret values.",
            "path": paths["live_launch_action_board"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Live proof execution plan",
            "audience": "IT owner, HomePilot operator, customer success, executive sponsor",
            "why_it_matters": "Ordered bridge from buyer-ready evidence to production proof, with live-input tasks, exact proof commands, expected artifacts, pass conditions, and guardrails.",
            "path": paths["live_proof_plan_markdown"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Live proof evidence map",
            "audience": "IT owner, security, customer success",
            "why_it_matters": "CSV map showing each required live proof artifact, required status, current status, path, and the gate it unlocks.",
            "path": paths["live_proof_evidence_map"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Live proof command script",
            "audience": "HomePilot operator, IT owner",
            "why_it_matters": "Review-first shell script with explicit confirmation guard, no secret values, and the commands to rerun live readiness, cutover, release, market pack, and production verification.",
            "path": paths["live_proof_commands"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Live proof acceptance matrix",
            "audience": "DAW executive sponsor, IT owner, security, customer success, HomePilot operator",
            "why_it_matters": "Customer/IT acceptance criteria for moving from buyer-ready evidence to live launch or production, with owners, blockers, current proof, and safe handling rules.",
            "path": paths["live_proof_acceptance_markdown"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Live proof acceptance CSV",
            "audience": "IT owner, security, customer success, HomePilot operator",
            "why_it_matters": "Excel-ready acceptance matrix for schema, RLS, customer access, partner access, public-data, signoff, and production proof gates.",
            "path": paths["live_proof_acceptance_csv"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Live proof evidence vault",
            "audience": "Boardroom, IT owner, security, customer success, HomePilot operator",
            "why_it_matters": "Archive index showing which live proof artifacts exist, which are blocked, who owns each proof, freshness rules, pass conditions, and safe handling rules.",
            "path": paths["live_proof_evidence_vault_markdown"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Live proof archive index",
            "audience": "IT owner, security, customer success, HomePilot operator",
            "why_it_matters": "Excel-ready vault index for schema verification, RLS launch, customer access, production proof, partner access, public-data, signoff, and first-wave evidence.",
            "path": paths["live_proof_archive_index"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Market-ready gap audit",
            "audience": "Boardroom, IT owner, customer success, HomePilot operator",
            "why_it_matters": "Requirement-by-requirement audit that separates buyer-review proof from live-launch and production blockers.",
            "path": paths["market_ready_audit_markdown"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Market-ready requirements CSV",
            "audience": "IT owner, customer success, HomePilot operator",
            "why_it_matters": "Excel-ready requirement tracker with stage, status, owner, evidence, blockers, and next actions.",
            "path": paths["market_ready_requirements"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "DAW boardroom demo walkthrough",
            "audience": "HomePilot operator, DAW leadership, sales, customer success",
            "why_it_matters": "Meeting-ready DAW demo agenda, screen sequence, stakeholder questions, proof map, guardrails, and follow-up decisions.",
            "path": paths["daw_boardroom_demo_walkthrough_markdown"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "DAW demo checklist",
            "audience": "HomePilot operator, customer success",
            "why_it_matters": "CSV checklist for demo screens, success checks, guardrails, and follow-up decision owners.",
            "path": paths["daw_demo_checklist"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "DAW first campaign control room",
            "audience": "DAW network manager, executive sponsor, customer success, IT, legal",
            "why_it_matters": "Operational cockpit that turns the DAW demo into launch lanes, partner waves, owners, proof requirements, and first-wave go/no-go decisions.",
            "path": paths["daw_first_campaign_control_room_markdown"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "DAW first campaign action board",
            "audience": "DAW network manager, customer success, IT, legal, HomePilot operator",
            "why_it_matters": "CSV action board for the remaining first-campaign owners, evidence, statuses, and exit conditions.",
            "path": paths["daw_first_campaign_action_board"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Customer acceptance plan",
            "audience": "Boardroom, IT, legal, customer success",
            "why_it_matters": "Stage-by-stage acceptance criteria and signoff roles for buyer review, live launch, and production.",
            "path": paths["customer_acceptance_plan_markdown"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Acceptance checklist",
            "audience": "Operator, customer success, IT owner",
            "why_it_matters": "CSV checklist of acceptance criteria, owners, evidence, and current status.",
            "path": paths["acceptance_checklist"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Customer rollout plan",
            "audience": "Boardroom, IT, legal, customer success, partner managers",
            "why_it_matters": "Practical RACI, workstream, training, and 30/60/90-day plan for moving from demo to first campaign.",
            "path": paths["customer_rollout_plan_markdown"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Rollout workstreams",
            "audience": "Operator, customer success, IT owner, partner manager",
            "why_it_matters": "Excel-ready workstream tracker with owners, inputs, HomePilot actions, evidence, and stage status.",
            "path": paths["rollout_workstreams"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "First campaign launch intake",
            "audience": "DAW network manager, legal, IT, campaign operations, partner manager",
            "why_it_matters": "Concrete first-campaign intake for partner roster, territories, contact basis, suppression, message approval, channel ops, capacity, and go/no-go.",
            "path": paths["first_campaign_launch_intake_markdown"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "First campaign launch checklist",
            "audience": "Customer success, campaign owner, partner manager, legal, IT",
            "why_it_matters": "Excel-ready checklist of customer inputs and approvals needed before the first live outreach wave.",
            "path": paths["first_campaign_launch_checklist"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Customer input templates",
            "audience": "DAW network manager, partner manager, legal, campaign operations",
            "why_it_matters": "Explains the CSV templates DAW can fill in for partner roster, territories, property source, suppression, message approval, and partner capacity.",
            "path": paths["customer_input_templates_markdown"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Partner roster template",
            "audience": "Partner manager",
            "why_it_matters": "CSV template for partner ids, company names, regions, languages, capacity, service categories, roles, and secure contact references.",
            "path": paths["partner_roster_template"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Territory assignment template",
            "audience": "DAW network manager, analyst",
            "why_it_matters": "CSV template for partner territories, included/excluded postcodes, capacity caps, overlap rules, and fallback owners.",
            "path": paths["territory_assignment_template"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Property source template",
            "audience": "Customer data owner, HomePilot operator",
            "why_it_matters": "CSV template for the tenant-scoped property import source, column mapping, provenance, refresh date, and dedupe rule.",
            "path": paths["property_source_template"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Suppression list template",
            "audience": "Legal, privacy, campaign operations",
            "why_it_matters": "CSV template for opt-outs, do-not-contact rules, exclusions, wrong-address feedback, and retention dates.",
            "path": paths["suppression_list_template"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Message approval template",
            "audience": "DAW marketing, legal, partner manager",
            "why_it_matters": "CSV template for campaign variants, channels, claims, CTAs, opt-out wording, language, owners, and approval status.",
            "path": paths["message_approval_template"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Partner capacity template",
            "audience": "Partner manager, partner renovators",
            "why_it_matters": "CSV template for capacity, appointment slots, follow-up SLA, accepted statuses, rejection reasons, and escalation path.",
            "path": paths["partner_capacity_template"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "First campaign input validation",
            "audience": "Customer success, campaign owner, legal, IT, partner manager",
            "why_it_matters": "Machine-readable validation report that shows whether filled customer CSVs are complete enough for first-wave launch review.",
            "path": paths["first_campaign_input_validation_markdown"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "First campaign input issues",
            "audience": "Customer success, campaign owner, legal, IT, partner manager",
            "why_it_matters": "Excel-ready blocker and warning list for missing files, unapproved inputs, unsafe contact data, and live-proof gaps.",
            "path": paths["first_campaign_input_issues"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "First campaign import plan",
            "audience": "DAW network manager, IT, legal, customer success, HomePilot operator",
            "why_it_matters": "Non-mutating staging manifest that translates validated customer CSVs into tenant, module, partner, campaign, source-run, suppression, and message records for review.",
            "path": paths["first_campaign_import_plan_markdown"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "First campaign staging rows",
            "audience": "IT, campaign operations, customer success",
            "why_it_matters": "Excel-ready staging rows showing proposed target tables, row keys, import gates, evidence, and notes before any live database write.",
            "path": paths["first_campaign_staging_rows"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "First wave launch gate",
            "audience": "DAW executive sponsor, legal, IT, campaign owner, customer success",
            "why_it_matters": "Final non-mutating go/no-go decision surface combining input validation, staging plan, source approvals, public-data approvals, live proof, and explicit customer go/no-go.",
            "path": paths["first_wave_launch_gate_markdown"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "First wave launch gate checklist",
            "audience": "DAW campaign owner, legal, IT, customer success",
            "why_it_matters": "Excel-ready gate checklist that shows which evidence blocks first-wave outreach or partner portal access.",
            "path": paths["first_wave_launch_gate_checklist"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "First wave database handoff",
            "audience": "Customer IT, DAW campaign owner, HomePilot operator",
            "why_it_matters": "Conservative database handoff that turns a validated first-wave plan into review scope and only emits executable SQL after launch_authorized=true.",
            "path": paths["first_wave_database_handoff_markdown"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "First wave database handoff checklist",
            "audience": "Customer IT, customer success, HomePilot operator",
            "why_it_matters": "Excel-ready checklist for launch authorization, SQL review, deferred partner Auth mapping, and post-apply verification.",
            "path": paths["first_wave_database_handoff_checklist"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "First wave database review rows",
            "audience": "Customer IT, HomePilot operator",
            "why_it_matters": "Excel-ready table-by-table review rows for tenant, module, campaign, source-run, audit, and deferred records.",
            "path": paths["first_wave_database_review_rows"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "First wave database review SQL",
            "audience": "Customer IT, HomePilot operator",
            "why_it_matters": "Review SQL for first-wave database setup; blocked launch gates produce comment-only SQL with no executable DML.",
            "path": paths["first_wave_database_review_sql"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Partner Auth mapping",
            "audience": "Customer IT, DAW network manager, customer success",
            "why_it_matters": "Safe bridge from the approved partner roster to real Supabase Auth user IDs before partner-scoped portal access is enabled.",
            "path": paths["partner_auth_mapping_markdown"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Partner Auth mapping template",
            "audience": "Customer IT, partner manager",
            "why_it_matters": "CSV template for mapping each approved partner_id to a real Supabase Auth UUID and secret-channel reference.",
            "path": paths["partner_auth_mapping_template"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Partner Auth mapping issues",
            "audience": "Customer IT, customer success, HomePilot operator",
            "why_it_matters": "Excel-ready blocker and warning list for missing Auth IDs, invalid UUIDs, duplicate mappings, raw contact references, and launch-gate status.",
            "path": paths["partner_auth_mapping_issues"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Partner membership review SQL",
            "audience": "Customer IT, HomePilot operator",
            "why_it_matters": "Comment-only SQL until partner Auth mapping is complete and launch_authorized=true; executable membership SQL is never generated silently.",
            "path": paths["partner_membership_review_sql"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Partner access reconciliation",
            "audience": "Customer IT, DAW network manager, customer success",
            "why_it_matters": "Reconciles partner Auth mappings against account-access membership rows and customer-access verification before partner portal access.",
            "path": paths["partner_access_reconciliation_markdown"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Partner access reconciliation matrix",
            "audience": "Customer IT, customer success, HomePilot operator",
            "why_it_matters": "Excel-ready partner_id matrix showing mapping coverage, account-access membership coverage, customer-access coverage, and blockers.",
            "path": paths["partner_access_reconciliation_matrix"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Partner access reconciliation issues",
            "audience": "Customer IT, customer success, HomePilot operator",
            "why_it_matters": "Excel-ready issue list for partner Auth, membership, and customer-access alignment blockers.",
            "path": paths["partner_access_reconciliation_issues"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Example completed customer inputs",
            "audience": "DAW network manager, partner manager, customer success, legal",
            "why_it_matters": "Synthetic DAW-style happy-path example showing how the six customer CSVs look when correctly completed for 10 partner renovators.",
            "path": paths["example_completed_customer_inputs_markdown"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Example partner roster",
            "audience": "Partner manager",
            "why_it_matters": "Synthetic completed roster with 10 partner renovators, assigned-record-only scope, capacity, regions, and secret-channel contact references.",
            "path": paths["example_completed_partner_roster"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Example territory assignment",
            "audience": "DAW network manager, analyst",
            "why_it_matters": "Synthetic completed territory split with non-overlapping postcode ranges, capacity caps, and fallback owner.",
            "path": paths["example_completed_territory_assignment"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Example property source",
            "audience": "Customer data owner, HomePilot operator",
            "why_it_matters": "Synthetic completed property-source row with approved example contact basis, provenance, dedupe rule, and import-ready status.",
            "path": paths["example_completed_property_source"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Example suppression list",
            "audience": "Legal, privacy, campaign operations",
            "why_it_matters": "Synthetic hash-only suppression example with opt-out workflow and retention metadata, without raw contact data.",
            "path": paths["example_completed_suppression_list"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Example message approval",
            "audience": "DAW marketing, legal, partner manager",
            "why_it_matters": "Synthetic completed NL/FR message approvals with no-homeowner-intent and no-guaranteed-savings checks.",
            "path": paths["example_completed_message_approval"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Example partner capacity",
            "audience": "Partner manager, partner renovators",
            "why_it_matters": "Synthetic completed partner capacity and follow-up rows for all 10 partner renovators.",
            "path": paths["example_completed_partner_capacity"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Example first campaign input validation",
            "audience": "Customer success, campaign owner, legal, IT, partner manager",
            "why_it_matters": "Happy-path validation report showing the synthetic customer inputs pass and only live proof remains before launch.",
            "path": paths["example_first_campaign_input_validation_markdown"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Example first campaign input issues",
            "audience": "Customer success, campaign owner, legal, IT, partner manager",
            "why_it_matters": "Excel-ready happy-path issue list showing live-proof gating without customer input blockers.",
            "path": paths["example_first_campaign_input_issues"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Example first campaign import plan",
            "audience": "DAW network manager, IT, legal, customer success, HomePilot operator",
            "why_it_matters": "Synthetic happy-path staging manifest showing 10 partner campaign records ready for review while live import remains blocked.",
            "path": paths["example_first_campaign_import_plan_markdown"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Example first campaign staging rows",
            "audience": "IT, campaign operations, customer success",
            "why_it_matters": "Excel-ready synthetic staging rows for the DAW-style partner/campaign setup, with import gates still visible.",
            "path": paths["example_first_campaign_staging_rows"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Example first wave launch gate",
            "audience": "DAW executive sponsor, legal, IT, campaign owner, customer success",
            "why_it_matters": "Synthetic happy-path gate showing that 10 partner campaigns can be staged while live proof and explicit customer go/no-go still block launch.",
            "path": paths["example_first_wave_launch_gate_markdown"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Example first wave launch gate checklist",
            "audience": "DAW campaign owner, legal, IT, customer success",
            "why_it_matters": "Excel-ready synthetic launch-gate checklist for explaining exactly what remains before first-wave authorization.",
            "path": paths["example_first_wave_launch_gate_checklist"],
            "source": "market_readiness",
            "required_for": "first_campaign",
        },
        {
            "label": "Procurement security review",
            "audience": "Procurement, IT, security, legal",
            "why_it_matters": "Evidence-backed questionnaire answers and risk register for enterprise vendor review.",
            "path": paths["procurement_review_markdown"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Security questionnaire",
            "audience": "Procurement, IT, security",
            "why_it_matters": "CSV of common security/procurement questions, owners, answers, evidence, and caveats.",
            "path": paths["security_questionnaire"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Procurement risk register",
            "audience": "Procurement, IT, legal, executive sponsor",
            "why_it_matters": "CSV risk register showing severity, owner, mitigation, and remaining production blockers.",
            "path": paths["procurement_risk_register"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Support SLA plan",
            "audience": "Executive sponsor, customer success, procurement, IT",
            "why_it_matters": "Operational support model with priority tiers, response targets, service boundaries, and production caveats.",
            "path": paths["support_sla_plan_markdown"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Support escalation matrix",
            "audience": "Customer success, IT, support owner, partner manager",
            "why_it_matters": "CSV escalation tracker for access incidents, portal/export issues, metric questions, and partner onboarding.",
            "path": paths["support_escalation_matrix"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Incident response playbook",
            "audience": "IT, security, customer success, HomePilot operator",
            "why_it_matters": "Step-by-step response process for classifying, containing, verifying, communicating, remediating, and archiving incidents.",
            "path": paths["incident_response_playbook"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Customer pilot proposal",
            "audience": "Boardroom, procurement, sales, executive sponsor",
            "why_it_matters": "Buyer-review proposal for the first paid pilot with scope, deliverables, milestones, assumptions, and decisions requested.",
            "path": paths["customer_pilot_proposal_markdown"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Pilot scope checklist",
            "audience": "Customer success, sales, executive sponsor",
            "why_it_matters": "CSV checklist of pilot milestones, owners, statuses, and exit conditions.",
            "path": paths["pilot_scope_checklist"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Commercial assumptions",
            "audience": "Procurement, executive sponsor, legal",
            "why_it_matters": "CSV list of pricing, scope, legal, live launch, and support assumptions requiring customer agreement.",
            "path": paths["commercial_assumptions"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Customer training guide",
            "audience": "DAW, partner renovators, customer success, IT, operators",
            "why_it_matters": "Role-based adoption guide showing what each stakeholder can see, must not see, and should do first.",
            "path": paths["customer_training_guide"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Training session plan",
            "audience": "Customer success, DAW network manager, IT, partner manager",
            "why_it_matters": "Excel-ready training agenda with audience, duration, objective, materials, and exit checks.",
            "path": paths["training_session_plan"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Role cheatsheet",
            "audience": "All customer-facing stakeholders",
            "why_it_matters": "CSV cheat sheet for role visibility, blocked visibility, first actions, and guardrails.",
            "path": paths["role_cheatsheet"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Customer view catalog",
            "audience": "Boardroom, DAW network manager, IT/security, partners, customer success",
            "why_it_matters": "Plain-language catalog of which DAW, partner, module-only, IT/security, and customer-success lenses can see which metrics, exports, partner scopes, and blocked data lanes.",
            "path": paths["customer_view_catalog_markdown"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Customer view matrix",
            "audience": "IT/security, customer success, DAW network manager, analyst",
            "why_it_matters": "Excel-ready access-lens matrix with role, scope, module, partner, export, live-gate, evidence, and blocked-visibility columns.",
            "path": paths["customer_view_matrix"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Data platform blueprint",
            "audience": "Boardroom, IT/security, analyst, customer success",
            "why_it_matters": "Explains the one shared HomePilot database spine across pilots, tenants, partners, campaigns, public-data lanes, exports, and live-proof gates.",
            "path": paths["data_platform_blueprint_markdown"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Data platform scope matrix",
            "audience": "IT/security, analyst, customer success",
            "why_it_matters": "Excel-ready matrix of data layers, access lenses, export surfaces, required keys, live gates, and guardrails.",
            "path": paths["data_platform_scope_matrix"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Value realization plan",
            "audience": "Executive sponsor, DAW network manager, customer success",
            "why_it_matters": "Executive plan for proving value with outcome tracks, KPIs, decision gates, and production caveats.",
            "path": paths["value_realization_plan_markdown"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Value realization metrics",
            "audience": "Executive sponsor, analyst, customer success",
            "why_it_matters": "CSV metric catalog for measuring campaign value, response, partner performance, access proof, and evidence freshness.",
            "path": paths["value_realization_metrics"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Executive decision log",
            "audience": "Executive sponsor, IT/security, DAW network manager",
            "why_it_matters": "CSV decision log showing which evidence unlocks buyer review, live launch, first campaign, and scale decisions.",
            "path": paths["executive_decision_log"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Outcome measurement contract",
            "audience": "DAW executive sponsor, CRM owner, analyst, customer success",
            "why_it_matters": "Closed-loop measurement contract for appointments, quotes, won/lost projects, commercial value, and loss reasons after campaign launch.",
            "path": paths["outcome_measurement_contract_markdown"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Outcome event schema",
            "audience": "CRM owner, analyst, IT/security",
            "why_it_matters": "Excel-ready event schema that keeps tenant, module, partner, campaign, property, source-system, and evidence keys explicit.",
            "path": paths["outcome_event_schema"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Outcome sync template",
            "audience": "CRM owner, partner manager, customer success",
            "why_it_matters": "Synthetic template for approved post-campaign outcome rows before any live CRM or Supabase sync is enabled.",
            "path": paths["outcome_sync_template"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Outcome reconciliation checklist",
            "audience": "DAW executive sponsor, CRM owner, legal, customer success",
            "why_it_matters": "Checklist for agreeing source-system approval, live access proof, first-wave authorization, import dry run, and metric definitions.",
            "path": paths["outcome_reconciliation_checklist"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Outcome import dry-run validation",
            "audience": "DAW executive sponsor, CRM owner, analyst, customer success",
            "why_it_matters": "Dry-run validation report for customer-approved CRM/sheet outcome rows before any live Supabase or CRM sync.",
            "path": paths["outcome_import_validation_markdown"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Outcome import issues",
            "audience": "CRM owner, analyst, customer success",
            "why_it_matters": "Excel-ready blocker and warning list for scope mismatches, duplicate outcome ids, invalid stages, missing approvals, unsafe raw contact data, and live-proof gating.",
            "path": paths["outcome_import_issues"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Outcome import review rows",
            "audience": "CRM owner, analyst, customer success",
            "why_it_matters": "Excel-ready redacted row review showing tenant, module, partner, stage, source, amount, reference status, and validation status.",
            "path": paths["outcome_import_review_rows"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Module expansion plan",
            "audience": "Boardroom, sales, product owner, customer success",
            "why_it_matters": "Explains how HomePilot grows from FacadePilot into WindowPilot, RoofPilot, GardenPilot, PoolPilot, PorchPilot, DrivewayPilot, and future modules.",
            "path": paths["module_expansion_plan_markdown"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Module value matrix",
            "audience": "Sales, analyst, customer success, product owner",
            "why_it_matters": "CSV of module catalog, buyer questions, metrics, data candidates, expansion triggers, and access guardrails.",
            "path": paths["module_value_matrix"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Expansion decision tree",
            "audience": "Executive sponsor, DAW network manager, HomePilot operator",
            "why_it_matters": "CSV decision tree for when to add modules, partner waves, territories, or benchmark-safe portfolio learning.",
            "path": paths["expansion_decision_tree"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Public data source register",
            "audience": "Boardroom, legal, IT, customer success",
            "why_it_matters": "Explains which official/open-data sources can be reviewed, which require legal approval, and which lanes are blocked by default.",
            "path": paths["public_data_source_register_markdown"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Public data source matrix",
            "audience": "Analyst, legal, IT, operator",
            "why_it_matters": "Excel-ready source list with publisher, licence, allowed use, suggested fields, attribution, and production gate.",
            "path": paths["public_data_source_matrix"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Blocked data register",
            "audience": "Legal, procurement, security, customer success",
            "why_it_matters": "CSV guardrail showing why owner data, individual EPC labels, scraped contact details, and similar lanes are blocked by default.",
            "path": paths["blocked_data_register"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Attribution requirements",
            "audience": "Legal, analyst, operator, customer success",
            "why_it_matters": "CSV checklist for source-run metadata, separate enrichment tables, dashboard provenance, and licence review before production import.",
            "path": paths["attribution_requirements"],
            "source": "market_readiness",
            "required_for": "buyer_review",
        },
        {
            "label": "Public data production intake",
            "audience": "Legal, IT, data engineering, customer success",
            "why_it_matters": "Customer-ready approval workflow for dataset-level licence checks, field allowlists, live-import gates, and production go/no-go.",
            "path": paths["public_data_production_intake_markdown"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Public data approval checklist",
            "audience": "Legal, analyst, data engineering, operator",
            "why_it_matters": "Excel-ready approval matrix for each public-data lane before production import.",
            "path": paths["public_data_approval_checklist"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Public data reconciliation",
            "audience": "Legal, IT, data engineering, customer success",
            "why_it_matters": "Reconciles source register, dataset approvals, first-wave public-data need, and live-proof status before any production public-data import.",
            "path": paths["public_data_reconciliation_markdown"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Public data reconciliation matrix",
            "audience": "Legal, analyst, data engineering, operator",
            "why_it_matters": "Excel-ready source-by-source matrix showing register status, approval status, import decision, first-wave dependency, and live-proof readiness.",
            "path": paths["public_data_reconciliation_matrix"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Public data reconciliation issues",
            "audience": "Legal, customer success, data engineering, operator",
            "why_it_matters": "Excel-ready blocker list for missing dataset approvals, legal review, import decisions, and live proof.",
            "path": paths["public_data_reconciliation_issues"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Customer signoff reconciliation",
            "audience": "Executive sponsor, procurement, legal, customer success",
            "why_it_matters": "Separates buyer-review material from signed customer decisions, first-wave go/no-go, commercial terms, support acknowledgement, and live proof.",
            "path": paths["customer_signoff_reconciliation_markdown"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Customer signoff reconciliation matrix",
            "audience": "Executive sponsor, customer success, operator",
            "why_it_matters": "Excel-ready decision matrix showing signoff status, evidence, live-launch blockers, production blockers, owners, and next actions.",
            "path": paths["customer_signoff_reconciliation_matrix"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Customer signoff reconciliation issues",
            "audience": "Executive sponsor, procurement, legal, customer success",
            "why_it_matters": "Excel-ready list of missing customer approvals and decision blockers before outreach, partner access, public-data import, or production rollout.",
            "path": paths["customer_signoff_reconciliation_issues"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Customer signoff intake",
            "audience": "Executive sponsor, procurement, legal, customer success",
            "why_it_matters": "Instructions for filling safe customer approval references without storing raw signatures, personal contact details, or secrets.",
            "path": paths["customer_signoff_intake_markdown"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
        {
            "label": "Customer signoff evidence template",
            "audience": "Executive sponsor, procurement, legal, customer success",
            "why_it_matters": "Fillable CSV for controlled customer approval references across buyer-review acceptance, first-wave go/no-go, commercial terms, support acknowledgement, and value metrics.",
            "path": paths["customer_signoff_evidence_template"],
            "source": "market_readiness",
            "required_for": "live_launch",
        },
    ]
    return _dedupe_artifacts_by_label(own_items + list(report["data_room"]))


def render_portable_data_room_html(report: dict[str, Any], manifest: dict[str, Any]) -> str:
    decisions = report["decisions"]
    summary = report["summary"]
    rows = "\n".join(
        f"""
        <tr>
          <td data-label="File"><a href="{escape(str(entry.get('relative_path') or '#'))}">{escape(str(entry['label']))}</a></td>
          <td data-label="Audience">{escape(str(entry['audience']))}</td>
          <td data-label="Why it matters">{escape(str(entry['why_it_matters']))}</td>
          <td data-label="Checksum">{escape(str(entry.get('sha256', 'missing'))[:12])}</td>
        </tr>
        """
        for entry in manifest["entries"]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HomePilot Portable Data Room</title>
  <style>
    :root {{
      color-scheme:light;
      --ink:#17211c;
      --muted:#5f6b64;
      --line:#d9dfd8;
      --paper:#f7f8f5;
      --panel:#ffffff;
      --ok:#1f8f61;
      --warn:#b65c1e;
      --dark:#10231b;
      --accent:#2f6f5e;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font:14px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--ink); background:var(--paper); }}
    main {{ max-width:1120px; margin:0 auto; padding:24px; }}
    header, section {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; min-width:0; }}
    header {{ padding:22px; margin-bottom:18px; }}
    .eyebrow {{ color:var(--accent); font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:0; }}
    h1 {{ margin:8px 0; font-size:30px; line-height:1.08; letter-spacing:0; }}
    h2 {{ margin:0 0 14px; font-size:18px; letter-spacing:0; }}
    h1, h2, p, a, td {{ overflow-wrap:anywhere; }}
    p {{ margin:0; color:var(--muted); }}
    .kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:18px 0; }}
    .kpi {{ background:var(--dark); color:white; border-radius:8px; padding:14px; min-width:0; }}
    .kpi span {{ display:block; color:#b9c7bf; font-size:12px; }}
    .kpi strong {{ display:block; margin-top:6px; font-size:22px; }}
    .note {{ border-left:4px solid var(--warn); padding:10px 12px; background:#fff8ef; color:#704015; margin-top:14px; border-radius:6px; }}
    section {{ padding:18px; }}
    table {{ width:100%; border-collapse:collapse; }}
    th, td {{ border-bottom:1px solid var(--line); padding:10px 8px; text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:0; }}
    a {{ color:#245c4e; font-weight:650; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    @media (max-width:760px) {{
      main {{ padding:14px; }}
      .kpis {{ grid-template-columns:1fr; }}
      h1 {{ font-size:25px; }}
      thead {{ display:none; }}
      tbody, tr, td {{ display:block; width:100%; }}
      tr {{ border-bottom:1px solid var(--line); padding:10px 0; }}
      td {{ border-bottom:0; padding:4px 0 4px 124px; position:relative; min-height:24px; }}
      td::before {{ content:attr(data-label); position:absolute; left:0; width:108px; color:var(--muted); font-weight:700; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div class="eyebrow">HomePilot portable data room</div>
      <h1>Customer-shareable evidence room with relative links.</h1>
      <p>This package is copied from the release evidence pack. It avoids local absolute links and records SHA-256 checksums for every included file.</p>
      <div class="note">Production remains no-go until live Supabase schema verification, live RLS launch, and customer access verification all pass with production_verified=true.</div>
    </header>
    <div class="kpis">
      <div class="kpi"><span>Buyer review</span><strong>{escape(_status_label(decisions['buyer_review']))}</strong></div>
      <div class="kpi"><span>Live launch</span><strong>{escape(_status_label(decisions['live_launch']))}</strong></div>
      <div class="kpi"><span>Production</span><strong>{escape(_status_label(decisions['production']))}</strong></div>
      <div class="kpi"><span>Files copied</span><strong>{escape(str(manifest['copied_file_count']))}</strong></div>
    </div>
    <section>
      <h2>Evidence Files</h2>
      <table>
        <thead><tr><th>File</th><th>Audience</th><th>Why it matters</th><th>Checksum</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    <p style="margin-top:14px;">Readiness gates: {escape(str(summary['readiness_gate_count']))}. Live launch tasks: {escape(str(summary['live_launch_task_count']))}. Secret values written: {escape(str(summary['secrets_written']).lower())}.</p>
  </main>
</body>
</html>
"""


def build_portable_data_room(report: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    package_dir = out_dir / "portable_data_room"
    files_dir = package_dir / "files"
    zip_path = out_dir / "homepilot_boardroom_data_room.zip"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    if zip_path.exists():
        zip_path.unlink()
    files_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    for index, item in enumerate(_portable_source_items(report), start=1):
        source_path = Path(str(item.get("path"))) if item.get("path") else None
        exists = bool(source_path and source_path.exists() and source_path.is_file())
        entry = {
            "label": item["label"],
            "audience": item["audience"],
            "why_it_matters": item["why_it_matters"],
            "source": item.get("source"),
            "required_for": item.get("required_for", "buyer_review"),
            "exists": exists,
            "original_filename": source_path.name if source_path else None,
            "relative_path": None,
            "bytes": None,
            "sha256": None,
            "local_path_redactions": 0,
        }
        if exists and source_path:
            suffix = source_path.suffix or ".txt"
            target = files_dir / f"{index:02d}-{_slugify(str(item['label']))}{suffix}"
            entry["local_path_redactions"] = copy_portable_artifact(source_path, target)
            entry["relative_path"] = target.relative_to(package_dir).as_posix()
            entry["bytes"] = target.stat().st_size
            entry["sha256"] = sha256_file(target)
        entries.append(entry)

    manifest = {
        "manifest_type": "homepilot_portable_boardroom_data_room",
        "created_at": utc_now(),
        "release_label": report["release_label"],
        "status": "pass" if all(entry["exists"] for entry in entries) else "partial",
        "decisions": report["decisions"],
        "copied_file_count": len([entry for entry in entries if entry["exists"]]),
        "missing_file_count": len([entry for entry in entries if not entry["exists"]]),
        "local_path_redaction_count": sum(int(entry["local_path_redactions"] or 0) for entry in entries),
        "link_mode": "relative",
        "absolute_links_written": False,
        "source_paths_written": False,
        "entries": entries,
    }
    write_json(package_dir / "DATA_ROOM_MANIFEST.json", manifest)
    write_text(package_dir / "index.html", render_portable_data_room_html(report, manifest))
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(package_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(package_dir).as_posix())
    return {
        "status": manifest["status"],
        "directory": str(package_dir),
        "html": str(package_dir / "index.html"),
        "manifest": str(package_dir / "DATA_ROOM_MANIFEST.json"),
        "zip": str(zip_path),
        "zip_sha256": sha256_file(zip_path),
        "copied_file_count": manifest["copied_file_count"],
        "missing_file_count": manifest["missing_file_count"],
        "absolute_links_written": False,
    }


def build_market_readiness_pack(
    out_dir: Path,
    readiness_report_path: Path,
    due_diligence_report_path: Path,
    artifact_index_path: Path | None = None,
    production_proof_path: Path | None = None,
    live_readiness_report_path: Path | None = None,
    live_launch_request_path: Path | None = None,
    release_label: str = "local",
) -> dict[str, Any]:
    readiness = load_json(readiness_report_path)
    due_diligence = load_json(due_diligence_report_path)
    artifact_index = load_json(artifact_index_path)
    production_proof = load_json(production_proof_path)
    live_readiness = load_json(live_readiness_report_path)
    live_launch_request = load_json(live_launch_request_path)
    if not readiness:
        raise ValueError(f"Missing readiness report: {readiness_report_path}")
    if not due_diligence:
        raise ValueError(f"Missing due diligence report: {due_diligence_report_path}")

    decisions = _decision_sources(artifact_index, production_proof)
    scorecard = _scorecard(readiness, due_diligence, artifact_index, production_proof, live_readiness, live_launch_request)
    actions = _actions(scorecard, live_launch_request, production_proof)
    data_room = _data_room(
        readiness,
        due_diligence,
        artifact_index,
        production_proof,
        str(live_readiness_report_path) if live_readiness_report_path else None,
        str(live_launch_request_path) if live_launch_request_path else None,
    )
    status = (
        "production_ready" if decisions["production"] == "go"
        else "market_review_ready" if decisions["buyer_review"] == "go" else "action_required"
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "report_type": "homepilot_market_readiness_scorecard",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": status,
        "decisions": decisions,
        "summary": {
            "readiness_status": readiness.get("status"),
            "readiness_gate_count": len(readiness.get("gates", [])),
            "due_diligence_status": due_diligence.get("status"),
            "redaction_status": due_diligence.get("redaction", {}).get("status"),
            "live_readiness_status": live_readiness.get("status") if live_readiness else None,
            "live_launch_task_count": live_launch_request.get("summary", {}).get("task_count") if live_launch_request else None,
            "secrets_written": live_launch_request.get("guardrails", {}).get("secrets_written") if live_launch_request else None,
            "production_verified": production_proof.get("production_gate", {}).get("verified") if production_proof else False,
        },
        "scorecard": scorecard,
        "actions": actions,
        "data_room": data_room,
        "stakeholder_views": {},
        "inputs": {
            "readiness_report": str(readiness_report_path),
            "due_diligence_report": str(due_diligence_report_path),
            "artifact_index": str(artifact_index_path) if artifact_index_path else None,
            "production_proof": str(production_proof_path) if production_proof_path else None,
            "live_readiness_report": str(live_readiness_report_path) if live_readiness_report_path else None,
            "live_launch_request": str(live_launch_request_path) if live_launch_request_path else None,
        },
        "paths": {
            "scorecard": str(out_dir / "market_readiness_scorecard.json"),
            "markdown": str(out_dir / "MARKET_READINESS_SCORECARD.md"),
            "html": str(out_dir / "market-readiness.html"),
            "data_room_index": str(out_dir / "BOARDROOM_DATA_ROOM_INDEX.md"),
            "actions_csv": str(out_dir / "market_readiness_actions.csv"),
            "stakeholder_views": str(out_dir / "STAKEHOLDER_VIEWS.md"),
            "live_launch_control_room": str(out_dir / "live_launch_control_room.json"),
            "live_launch_control_room_markdown": str(out_dir / "LIVE_LAUNCH_CONTROL_ROOM.md"),
            "live_launch_action_board": str(out_dir / "LIVE_LAUNCH_ACTION_BOARD.csv"),
            "live_credential_handoff": str(out_dir / "live_credential_handoff.json"),
            "live_credential_handoff_markdown": str(out_dir / "LIVE_CREDENTIAL_HANDOFF.md"),
            "live_credential_handoff_checklist": str(out_dir / "LIVE_CREDENTIAL_HANDOFF_CHECKLIST.csv"),
            "live_secret_channel_contract": str(out_dir / "LIVE_SECRET_CHANNEL_CONTRACT.csv"),
            "live_proof_plan": str(out_dir / "live_proof_execution_plan.json"),
            "live_proof_plan_markdown": str(out_dir / "LIVE_PROOF_EXECUTION_PLAN.md"),
            "live_proof_evidence_map": str(out_dir / "LIVE_PROOF_EVIDENCE_MAP.csv"),
            "live_proof_commands": str(out_dir / "LIVE_PROOF_COMMANDS.sh"),
            "live_proof_acceptance": str(out_dir / "live_proof_acceptance_matrix.json"),
            "live_proof_acceptance_markdown": str(out_dir / "LIVE_PROOF_ACCEPTANCE_MATRIX.md"),
            "live_proof_acceptance_csv": str(out_dir / "LIVE_PROOF_ACCEPTANCE_MATRIX.csv"),
            "live_proof_evidence_vault": str(out_dir / "live_proof_evidence_vault.json"),
            "live_proof_evidence_vault_markdown": str(out_dir / "LIVE_PROOF_EVIDENCE_VAULT.md"),
            "live_proof_archive_index": str(out_dir / "LIVE_PROOF_ARCHIVE_INDEX.csv"),
            "market_ready_audit": str(out_dir / "market_ready_audit.json"),
            "market_ready_audit_markdown": str(out_dir / "MARKET_READY_GAP_AUDIT.md"),
            "market_ready_requirements": str(out_dir / "MARKET_READY_REQUIREMENTS.csv"),
            "customer_acceptance_plan": str(out_dir / "customer_acceptance_plan.json"),
            "customer_acceptance_plan_markdown": str(out_dir / "CUSTOMER_ACCEPTANCE_PLAN.md"),
            "acceptance_checklist": str(out_dir / "ACCEPTANCE_CHECKLIST.csv"),
            "customer_rollout_plan": str(out_dir / "customer_rollout_plan.json"),
            "customer_rollout_plan_markdown": str(out_dir / "CUSTOMER_ROLLOUT_PLAN.md"),
            "rollout_workstreams": str(out_dir / "ROLLOUT_WORKSTREAMS.csv"),
            "first_campaign_launch_intake": str(out_dir / "first_campaign_launch_intake.json"),
            "first_campaign_launch_intake_markdown": str(out_dir / "FIRST_CAMPAIGN_LAUNCH_INTAKE.md"),
            "first_campaign_launch_checklist": str(out_dir / "FIRST_CAMPAIGN_LAUNCH_CHECKLIST.csv"),
            "customer_input_templates": str(out_dir / "customer_input_templates.json"),
            "customer_input_templates_markdown": str(out_dir / "CUSTOMER_INPUT_TEMPLATES.md"),
            "partner_roster_template": str(out_dir / "PARTNER_ROSTER_TEMPLATE.csv"),
            "territory_assignment_template": str(out_dir / "TERRITORY_ASSIGNMENT_TEMPLATE.csv"),
            "property_source_template": str(out_dir / "PROPERTY_SOURCE_TEMPLATE.csv"),
            "suppression_list_template": str(out_dir / "SUPPRESSION_LIST_TEMPLATE.csv"),
            "message_approval_template": str(out_dir / "MESSAGE_APPROVAL_TEMPLATE.csv"),
            "partner_capacity_template": str(out_dir / "PARTNER_CAPACITY_TEMPLATE.csv"),
            "first_campaign_input_validation": str(out_dir / "first_campaign_input_validation.json"),
            "first_campaign_input_validation_markdown": str(out_dir / "FIRST_CAMPAIGN_INPUT_VALIDATION.md"),
            "first_campaign_input_issues": str(out_dir / "FIRST_CAMPAIGN_INPUT_ISSUES.csv"),
            "first_campaign_import_plan": str(out_dir / "first_campaign_import_plan.json"),
            "first_campaign_import_plan_markdown": str(out_dir / "FIRST_CAMPAIGN_IMPORT_PLAN.md"),
            "first_campaign_staging_rows": str(out_dir / "FIRST_CAMPAIGN_STAGING_ROWS.csv"),
            "first_wave_launch_gate": str(out_dir / "first_wave_launch_gate.json"),
            "first_wave_launch_gate_markdown": str(out_dir / "FIRST_WAVE_LAUNCH_GATE.md"),
            "first_wave_launch_gate_checklist": str(out_dir / "FIRST_WAVE_LAUNCH_GATE_CHECKLIST.csv"),
            "first_wave_database_handoff": str(out_dir / "first_wave_database_handoff.json"),
            "first_wave_database_handoff_markdown": str(out_dir / "FIRST_WAVE_DATABASE_HANDOFF.md"),
            "first_wave_database_handoff_checklist": str(out_dir / "FIRST_WAVE_DATABASE_HANDOFF_CHECKLIST.csv"),
            "first_wave_database_review_rows": str(out_dir / "FIRST_WAVE_DATABASE_REVIEW_ROWS.csv"),
            "first_wave_database_review_sql": str(out_dir / "FIRST_WAVE_DATABASE_REVIEW.sql"),
            "partner_auth_mapping": str(out_dir / "partner_auth_mapping.json"),
            "partner_auth_mapping_markdown": str(out_dir / "PARTNER_AUTH_MAPPING.md"),
            "partner_auth_mapping_template": str(out_dir / "PARTNER_AUTH_MAPPING_TEMPLATE.csv"),
            "partner_auth_mapping_rows": str(out_dir / "PARTNER_AUTH_MAPPING_ROWS.csv"),
            "partner_auth_mapping_issues": str(out_dir / "PARTNER_AUTH_MAPPING_ISSUES.csv"),
            "partner_membership_review_sql": str(out_dir / "PARTNER_MEMBERSHIP_REVIEW.sql"),
            "partner_access_reconciliation": str(out_dir / "partner_access_reconciliation.json"),
            "partner_access_reconciliation_markdown": str(out_dir / "PARTNER_ACCESS_RECONCILIATION.md"),
            "partner_access_reconciliation_matrix": str(out_dir / "PARTNER_ACCESS_RECONCILIATION_MATRIX.csv"),
            "partner_access_reconciliation_issues": str(out_dir / "PARTNER_ACCESS_RECONCILIATION_ISSUES.csv"),
            "example_completed_customer_inputs": str(out_dir / "example_completed_customer_inputs.json"),
            "example_completed_customer_inputs_markdown": str(out_dir / "EXAMPLE_COMPLETED_CUSTOMER_INPUTS.md"),
            "example_completed_partner_roster": str(out_dir / "example_completed_customer_inputs" / "PARTNER_ROSTER_TEMPLATE.csv"),
            "example_completed_territory_assignment": str(out_dir / "example_completed_customer_inputs" / "TERRITORY_ASSIGNMENT_TEMPLATE.csv"),
            "example_completed_property_source": str(out_dir / "example_completed_customer_inputs" / "PROPERTY_SOURCE_TEMPLATE.csv"),
            "example_completed_suppression_list": str(out_dir / "example_completed_customer_inputs" / "SUPPRESSION_LIST_TEMPLATE.csv"),
            "example_completed_message_approval": str(out_dir / "example_completed_customer_inputs" / "MESSAGE_APPROVAL_TEMPLATE.csv"),
            "example_completed_partner_capacity": str(out_dir / "example_completed_customer_inputs" / "PARTNER_CAPACITY_TEMPLATE.csv"),
            "example_first_campaign_input_validation": str(out_dir / "example_completed_customer_inputs" / "first_campaign_input_validation.json"),
            "example_first_campaign_input_validation_markdown": str(out_dir / "example_completed_customer_inputs" / "FIRST_CAMPAIGN_INPUT_VALIDATION.md"),
            "example_first_campaign_input_issues": str(out_dir / "example_completed_customer_inputs" / "FIRST_CAMPAIGN_INPUT_ISSUES.csv"),
            "example_first_campaign_import_plan": str(out_dir / "example_completed_customer_inputs" / "first_campaign_import_plan.json"),
            "example_first_campaign_import_plan_markdown": str(out_dir / "example_completed_customer_inputs" / "FIRST_CAMPAIGN_IMPORT_PLAN.md"),
            "example_first_campaign_staging_rows": str(out_dir / "example_completed_customer_inputs" / "FIRST_CAMPAIGN_STAGING_ROWS.csv"),
            "example_first_wave_launch_gate": str(out_dir / "example_completed_customer_inputs" / "first_wave_launch_gate.json"),
            "example_first_wave_launch_gate_markdown": str(out_dir / "example_completed_customer_inputs" / "FIRST_WAVE_LAUNCH_GATE.md"),
            "example_first_wave_launch_gate_checklist": str(out_dir / "example_completed_customer_inputs" / "FIRST_WAVE_LAUNCH_GATE_CHECKLIST.csv"),
            "daw_boardroom_demo_walkthrough": str(out_dir / "daw_boardroom_demo_walkthrough.json"),
            "daw_boardroom_demo_walkthrough_markdown": str(out_dir / "DAW_BOARDROOM_DEMO_WALKTHROUGH.md"),
            "daw_demo_checklist": str(out_dir / "DAW_DEMO_CHECKLIST.csv"),
            "daw_first_campaign_control_room": str(out_dir / "daw_first_campaign_control_room.json"),
            "daw_first_campaign_control_room_markdown": str(out_dir / "DAW_FIRST_CAMPAIGN_CONTROL_ROOM.md"),
            "daw_first_campaign_action_board": str(out_dir / "DAW_FIRST_CAMPAIGN_ACTION_BOARD.csv"),
            "procurement_review": str(out_dir / "procurement_security_review.json"),
            "procurement_review_markdown": str(out_dir / "PROCUREMENT_SECURITY_REVIEW.md"),
            "security_questionnaire": str(out_dir / "SECURITY_QUESTIONNAIRE.csv"),
            "procurement_risk_register": str(out_dir / "PROCUREMENT_RISK_REGISTER.csv"),
            "support_sla_plan": str(out_dir / "support_sla_plan.json"),
            "support_sla_plan_markdown": str(out_dir / "SUPPORT_SLA_PLAN.md"),
            "support_escalation_matrix": str(out_dir / "SUPPORT_ESCALATION_MATRIX.csv"),
            "incident_response_playbook": str(out_dir / "INCIDENT_RESPONSE_PLAYBOOK.md"),
            "customer_pilot_proposal": str(out_dir / "customer_pilot_proposal.json"),
            "customer_pilot_proposal_markdown": str(out_dir / "CUSTOMER_PILOT_PROPOSAL.md"),
            "pilot_scope_checklist": str(out_dir / "PILOT_SCOPE_CHECKLIST.csv"),
            "commercial_assumptions": str(out_dir / "COMMERCIAL_ASSUMPTIONS.csv"),
            "customer_training_plan": str(out_dir / "customer_training_plan.json"),
            "customer_training_guide": str(out_dir / "CUSTOMER_TRAINING_GUIDE.md"),
            "training_session_plan": str(out_dir / "TRAINING_SESSION_PLAN.csv"),
            "role_cheatsheet": str(out_dir / "ROLE_CHEATSHEET.csv"),
            "value_realization_plan": str(out_dir / "customer_value_realization_plan.json"),
            "value_realization_plan_markdown": str(out_dir / "CUSTOMER_VALUE_REALIZATION_PLAN.md"),
            "value_realization_metrics": str(out_dir / "VALUE_REALIZATION_METRICS.csv"),
            "executive_decision_log": str(out_dir / "EXECUTIVE_DECISION_LOG.csv"),
            "outcome_measurement_contract": str(out_dir / "outcome_measurement_contract.json"),
            "outcome_measurement_contract_markdown": str(out_dir / "OUTCOME_MEASUREMENT_CONTRACT.md"),
            "outcome_event_schema": str(out_dir / "OUTCOME_EVENT_SCHEMA.csv"),
            "outcome_sync_template": str(out_dir / "OUTCOME_SYNC_TEMPLATE.csv"),
            "outcome_reconciliation_checklist": str(out_dir / "OUTCOME_RECONCILIATION_CHECKLIST.csv"),
            "outcome_import_validation": str(out_dir / "outcome_import_validation.json"),
            "outcome_import_validation_markdown": str(out_dir / "OUTCOME_IMPORT_VALIDATION.md"),
            "outcome_import_issues": str(out_dir / "OUTCOME_IMPORT_ISSUES.csv"),
            "outcome_import_review_rows": str(out_dir / "OUTCOME_IMPORT_REVIEW_ROWS.csv"),
            "module_expansion_plan": str(out_dir / "customer_module_expansion_plan.json"),
            "module_expansion_plan_markdown": str(out_dir / "CUSTOMER_MODULE_EXPANSION_PLAN.md"),
            "module_value_matrix": str(out_dir / "MODULE_VALUE_MATRIX.csv"),
            "expansion_decision_tree": str(out_dir / "EXPANSION_DECISION_TREE.csv"),
            "module_readiness_matrix": str(out_dir / "module_readiness_matrix.json"),
            "module_readiness_matrix_markdown": str(out_dir / "MODULE_READINESS_MATRIX.md"),
            "module_readiness_matrix_csv": str(out_dir / "MODULE_READINESS_MATRIX.csv"),
            "module_metric_coverage": str(out_dir / "MODULE_METRIC_COVERAGE.csv"),
            "public_data_source_register": str(out_dir / "customer_public_data_source_register.json"),
            "public_data_source_register_markdown": str(out_dir / "PUBLIC_DATA_SOURCE_REGISTER.md"),
            "public_data_source_matrix": str(out_dir / "PUBLIC_DATA_SOURCE_MATRIX.csv"),
            "blocked_data_register": str(out_dir / "BLOCKED_DATA_REGISTER.csv"),
            "attribution_requirements": str(out_dir / "ATTRIBUTION_REQUIREMENTS.csv"),
            "public_data_production_intake": str(out_dir / "public_data_production_intake.json"),
            "public_data_production_intake_markdown": str(out_dir / "PUBLIC_DATA_PRODUCTION_INTAKE.md"),
            "public_data_approval_checklist": str(out_dir / "PUBLIC_DATA_APPROVAL_CHECKLIST.csv"),
            "public_data_reconciliation": str(out_dir / "public_data_reconciliation.json"),
            "public_data_reconciliation_markdown": str(out_dir / "PUBLIC_DATA_RECONCILIATION.md"),
            "public_data_reconciliation_matrix": str(out_dir / "PUBLIC_DATA_RECONCILIATION_MATRIX.csv"),
            "public_data_reconciliation_issues": str(out_dir / "PUBLIC_DATA_RECONCILIATION_ISSUES.csv"),
            "customer_signoff_reconciliation": str(out_dir / "customer_signoff_reconciliation.json"),
            "customer_signoff_reconciliation_markdown": str(out_dir / "CUSTOMER_SIGNOFF_RECONCILIATION.md"),
            "customer_signoff_reconciliation_matrix": str(out_dir / "CUSTOMER_SIGNOFF_RECONCILIATION_MATRIX.csv"),
            "customer_signoff_reconciliation_issues": str(out_dir / "CUSTOMER_SIGNOFF_RECONCILIATION_ISSUES.csv"),
            "customer_signoff_intake_markdown": str(out_dir / "CUSTOMER_SIGNOFF_INTAKE.md"),
            "customer_signoff_evidence_template": str(out_dir / "CUSTOMER_SIGNOFF_EVIDENCE_TEMPLATE.csv"),
            "customer_view_catalog": str(out_dir / "customer_view_catalog.json"),
            "customer_view_catalog_markdown": str(out_dir / "CUSTOMER_VIEW_CATALOG.md"),
            "customer_view_matrix": str(out_dir / "CUSTOMER_VIEW_MATRIX.csv"),
            "data_platform_blueprint": str(out_dir / "data_platform_blueprint.json"),
            "data_platform_blueprint_markdown": str(out_dir / "DATA_PLATFORM_BLUEPRINT.md"),
            "data_platform_scope_matrix": str(out_dir / "DATA_PLATFORM_SCOPE_MATRIX.csv"),
            "portable_data_room_html": str(out_dir / "portable_data_room" / "index.html"),
            "portable_data_room_manifest": str(out_dir / "portable_data_room" / "DATA_ROOM_MANIFEST.json"),
            "portable_data_room_zip": str(out_dir / "homepilot_boardroom_data_room.zip"),
        },
    }
    report["stakeholder_views"] = _stakeholder_views(report)
    report["customer_acceptance_plan"] = build_acceptance_plan(report)
    report["customer_rollout_plan"] = build_customer_rollout_plan(report)
    report["first_campaign_launch_intake"] = build_first_campaign_launch_intake(report)
    report["customer_input_templates"] = build_customer_input_template_pack(report)
    report["procurement_review"] = build_procurement_review_pack(report)
    report["support_sla_plan"] = build_support_readiness_pack(report)
    report["customer_pilot_proposal"] = build_customer_pilot_proposal(report)
    report["customer_training_plan"] = build_customer_training_plan(report)
    report["value_realization_plan"] = build_value_realization_plan(report)
    report["outcome_measurement_contract"] = build_outcome_measurement_contract_pack(
        out_dir,
        market_readiness=report,
        production_proof=production_proof,
        release_label=release_label,
    )
    report["outcome_import_validation"] = build_outcome_import_validation_pack(
        out_dir,
        input_csv=Path(report["paths"]["outcome_sync_template"]),
        outcome_contract=report["outcome_measurement_contract"],
        expected_tenant_id="daw-belgium",
        expected_module_key="facadepilot",
        require_partner_scope=True,
        production_verified=bool(report["summary"].get("production_verified")),
        release_label=release_label,
    )
    for artifact in (
        _artifact(
            "Outcome import dry-run validation",
            "DAW executive sponsor, CRM owner, analyst, customer success",
            "Dry-run validation report for customer-approved CRM/sheet outcome rows before any live Supabase or CRM sync.",
            report["paths"]["outcome_import_validation_markdown"],
            "market_readiness",
            "buyer_review",
        ),
        _artifact(
            "Outcome import issues",
            "CRM owner, analyst, customer success",
            "Excel-ready blocker and warning list for scope mismatches, duplicate outcome ids, invalid stages, missing approvals, unsafe raw contact data, and live-proof gating.",
            report["paths"]["outcome_import_issues"],
            "market_readiness",
            "buyer_review",
        ),
        _artifact(
            "Outcome import review rows",
            "CRM owner, analyst, customer success",
            "Excel-ready redacted row review showing tenant, module, partner, stage, source, amount, reference status, and validation status.",
            report["paths"]["outcome_import_review_rows"],
            "market_readiness",
            "buyer_review",
        ),
    ):
        existing_index = next(
            (index for index, item in enumerate(report["data_room"]) if item.get("label") == artifact["label"]),
            None,
        )
        if existing_index is None:
            report["data_room"].append(artifact)
        elif not _path_exists(str(report["data_room"][existing_index].get("path")) if report["data_room"][existing_index].get("path") else None):
            report["data_room"][existing_index] = artifact
    report["module_expansion_plan"] = build_module_expansion_plan(report)
    report["module_readiness_matrix"] = build_module_readiness_matrix_pack(
        out_dir,
        due_diligence=due_diligence,
        production_proof=production_proof,
        release_label=release_label,
    )
    for artifact in (
        _artifact(
            "Module readiness matrix",
            "Boardroom, IT/security, analyst, customer success",
            "Audit-grade per-pilot matrix showing catalog, metric visibility, export readiness, public-data lanes, scope filters, and live-production gates.",
            report["paths"]["module_readiness_matrix_markdown"],
            "market_readiness",
            "buyer_review",
        ),
        _artifact(
            "Module readiness CSV",
            "IT/security, analyst, customer success",
            "Excel-ready module-by-module readiness matrix across FacadePilot, WindowPilot, RoofPilot, GardenPilot, PoolPilot, PorchPilot, DrivewayPilot, and future module review.",
            report["paths"]["module_readiness_matrix_csv"],
            "market_readiness",
            "buyer_review",
        ),
        _artifact(
            "Module metric coverage",
            "Analyst, product owner, customer success",
            "Excel-ready metric coverage file showing which module metrics are dashboard-visible, export-visible, benchmark-visible, and primary score fields.",
            report["paths"]["module_metric_coverage"],
            "market_readiness",
            "buyer_review",
        ),
    ):
        existing_index = next(
            (index for index, item in enumerate(report["data_room"]) if item.get("label") == artifact["label"]),
            None,
        )
        if existing_index is None:
            report["data_room"].append(artifact)
        elif not _path_exists(str(report["data_room"][existing_index].get("path")) if report["data_room"][existing_index].get("path") else None):
            report["data_room"][existing_index] = artifact
    report["data_room"] = _dedupe_artifacts_by_label(report["data_room"])
    report["data_platform_blueprint"] = build_data_platform_blueprint_pack(
        out_dir,
        due_diligence=due_diligence,
        readiness=readiness,
        production_proof=production_proof,
        release_label=release_label,
    )
    report["public_data_source_register"] = build_public_data_source_register(report)
    report["public_data_production_intake"] = build_public_data_production_intake(
        report,
        report["public_data_source_register"],
    )
    write_json(out_dir / "market_readiness_scorecard.json", report)
    write_text(out_dir / "MARKET_READINESS_SCORECARD.md", render_scorecard_markdown(report))
    write_text(out_dir / "market-readiness.html", render_html(report))
    write_text(out_dir / "BOARDROOM_DATA_ROOM_INDEX.md", render_data_room_index(report))
    _write_actions_csv(out_dir / "market_readiness_actions.csv", actions)
    write_text(out_dir / "STAKEHOLDER_VIEWS.md", render_stakeholder_views(report))
    write_json(out_dir / "customer_acceptance_plan.json", report["customer_acceptance_plan"])
    write_text(out_dir / "CUSTOMER_ACCEPTANCE_PLAN.md", render_acceptance_plan_markdown(report["customer_acceptance_plan"]))
    _write_acceptance_csv(out_dir / "ACCEPTANCE_CHECKLIST.csv", report["customer_acceptance_plan"]["criteria"])
    write_json(out_dir / "customer_rollout_plan.json", report["customer_rollout_plan"])
    write_text(out_dir / "CUSTOMER_ROLLOUT_PLAN.md", render_customer_rollout_plan_markdown(report["customer_rollout_plan"]))
    _write_rollout_csv(out_dir / "ROLLOUT_WORKSTREAMS.csv", report["customer_rollout_plan"]["workstreams"])
    write_json(out_dir / "first_campaign_launch_intake.json", report["first_campaign_launch_intake"])
    write_text(
        out_dir / "FIRST_CAMPAIGN_LAUNCH_INTAKE.md",
        render_first_campaign_launch_intake_markdown(report["first_campaign_launch_intake"]),
    )
    _write_first_campaign_checklist_csv(
        out_dir / "FIRST_CAMPAIGN_LAUNCH_CHECKLIST.csv",
        report["first_campaign_launch_intake"]["input_requirements"],
    )
    write_json(out_dir / "customer_input_templates.json", report["customer_input_templates"])
    write_text(
        out_dir / "CUSTOMER_INPUT_TEMPLATES.md",
        render_customer_input_templates_markdown(report["customer_input_templates"]),
    )
    for template in report["customer_input_templates"]["templates"]:
        _write_customer_template_csv(out_dir / template["file_name"], template)
    report["first_campaign_input_validation"] = build_first_campaign_input_validation(
        out_dir=out_dir,
        template_pack=report["customer_input_templates"],
        input_dir=out_dir,
        release_label=release_label,
        expected_partner_count=report["first_campaign_launch_intake"]["scenario"]["expected_partner_renovators"],
        live_proof_ready=False,
    )
    report["first_campaign_import_plan"] = build_first_campaign_import_plan(
        out_dir=out_dir,
        template_pack=report["customer_input_templates"],
        input_dir=out_dir,
        release_label=release_label,
        expected_partner_count=report["first_campaign_launch_intake"]["scenario"]["expected_partner_renovators"],
        live_proof_ready=False,
        validation_report=report["first_campaign_input_validation"],
    )
    report["first_wave_launch_gate"] = build_first_wave_launch_gate(
        out_dir=out_dir,
        input_validation=report["first_campaign_input_validation"],
        import_plan=report["first_campaign_import_plan"],
        public_data_intake=report["public_data_production_intake"],
        live_readiness=live_readiness,
        release_label=release_label,
        customer_go_no_go_ready=False,
    )
    report["public_data_reconciliation"] = build_public_data_reconciliation_pack(
        out_dir=out_dir,
        public_register=report["public_data_source_register"],
        public_data_intake=report["public_data_production_intake"],
        first_campaign_import_plan=report["first_campaign_import_plan"],
        first_wave_launch_gate=report["first_wave_launch_gate"],
        release_label=release_label,
    )
    report["first_wave_database_handoff"] = build_first_wave_database_handoff(
        out_dir=out_dir,
        input_validation=report["first_campaign_input_validation"],
        import_plan=report["first_campaign_import_plan"],
        launch_gate=report["first_wave_launch_gate"],
        release_label=release_label,
    )
    report["partner_auth_mapping"] = build_partner_auth_mapping_pack(
        out_dir=out_dir,
        import_plan=report["first_campaign_import_plan"],
        launch_gate=report["first_wave_launch_gate"],
        release_label=release_label,
        expected_partner_count=report["first_campaign_launch_intake"]["scenario"]["expected_partner_renovators"],
    )
    report["partner_access_reconciliation"] = build_partner_access_reconciliation_pack(
        out_dir=out_dir,
        partner_auth_mapping=report["partner_auth_mapping"],
        account_access_plan=_json_from_readiness(readiness, "account_access_smoke", "account_access_plan.json"),
        customer_access_verification=_json_from_readiness(
            readiness,
            "customer_access_verification_smoke",
            "customer_access_verification.json",
        ),
        release_label=release_label,
    )
    report["customer_signoff_reconciliation"] = build_customer_signoff_reconciliation_pack(
        out_dir=out_dir,
        customer_acceptance_plan=report["customer_acceptance_plan"],
        first_campaign_input_validation=report["first_campaign_input_validation"],
        first_campaign_import_plan=report["first_campaign_import_plan"],
        first_wave_launch_gate=report["first_wave_launch_gate"],
        customer_pilot_proposal=report["customer_pilot_proposal"],
        support_sla_plan=report["support_sla_plan"],
        value_realization_plan=report["value_realization_plan"],
        partner_access_reconciliation=report["partner_access_reconciliation"],
        public_data_reconciliation=report["public_data_reconciliation"],
        production_proof=production_proof,
        release_label=release_label,
    )
    report["customer_view_catalog"] = build_customer_view_catalog_pack(
        out_dir=out_dir,
        due_diligence=due_diligence,
        readiness=readiness,
        account_access_plan=_json_from_readiness(readiness, "account_access_smoke", "account_access_plan.json"),
        portal_manifest=_json_from_readiness(readiness, "customer_portal_smoke", "portal_manifest.json"),
        partner_access_reconciliation=report["partner_access_reconciliation"],
        customer_signoff_reconciliation=report["customer_signoff_reconciliation"],
        production_proof=production_proof,
        release_label=release_label,
    )
    report["live_launch_control_room"] = build_launch_control_room_pack(
        out_dir=out_dir,
        market_readiness=report,
        live_readiness=live_readiness,
        live_launch_request=live_launch_request,
        production_proof=production_proof,
        first_wave_launch_gate=report["first_wave_launch_gate"],
        partner_auth_mapping=report["partner_auth_mapping"],
        partner_access_reconciliation=report["partner_access_reconciliation"],
        public_data_reconciliation=report["public_data_reconciliation"],
        customer_signoff_reconciliation=report["customer_signoff_reconciliation"],
        release_label=release_label,
    )
    generated = artifact_index.get("generated_evidence", {}) if artifact_index else {}
    account_access_plan_path = _path_from_readiness(readiness, "account_access_smoke", "account_access_plan.json")
    report["live_proof_plan"] = build_live_proof_plan_pack(
        out_dir=out_dir,
        readiness_report_path=readiness_report_path,
        due_diligence_report_path=due_diligence_report_path,
        live_readiness_report_path=live_readiness_report_path,
        live_launch_request_path=live_launch_request_path,
        production_cutover_report_path=Path(generated["production_cutover_report"]) if generated.get("production_cutover_report") else None,
        production_proof_path=production_proof_path,
        artifact_index_path=artifact_index_path,
        account_access_plan_path=Path(account_access_plan_path) if account_access_plan_path else None,
        release_label=release_label,
    )
    report["live_credential_handoff"] = build_live_credential_handoff_pack(
        out_dir=out_dir,
        live_readiness=live_readiness,
        live_launch_request=live_launch_request,
        live_proof_plan=report.get("live_proof_plan"),
        production_proof=production_proof,
        release_label=release_label,
    )
    report["live_proof_acceptance"] = build_live_proof_acceptance_pack(
        out_dir=out_dir,
        live_readiness=live_readiness,
        live_launch_request=live_launch_request,
        live_proof_plan=report["live_proof_plan"],
        production_proof=production_proof,
        launch_control_room=report.get("live_launch_control_room"),
        partner_auth_mapping=report.get("partner_auth_mapping"),
        partner_access_reconciliation=report.get("partner_access_reconciliation"),
        public_data_reconciliation=report.get("public_data_reconciliation"),
        customer_signoff_reconciliation=report.get("customer_signoff_reconciliation"),
        customer_view_catalog=report.get("customer_view_catalog"),
        release_label=release_label,
    )
    artifact_inputs = artifact_index.get("inputs", {}) if artifact_index else {}
    report["live_proof_evidence_vault"] = build_live_proof_evidence_vault_pack(
        out_dir=out_dir,
        artifact_paths={
            "schema_verification_report": artifact_inputs.get("schema_verification_report"),
            "launch_report": artifact_inputs.get("launch_report"),
            "customer_access_report": artifact_inputs.get("customer_access_report"),
            "production_proof": str(production_proof_path) if production_proof_path else None,
            "live_readiness_report": str(live_readiness_report_path) if live_readiness_report_path else None,
            "live_launch_request": str(live_launch_request_path) if live_launch_request_path else None,
            "live_proof_plan": report["paths"]["live_proof_plan_markdown"],
            "live_proof_acceptance": report["paths"]["live_proof_acceptance_markdown"],
            "live_launch_control_room": report["paths"]["live_launch_control_room_markdown"],
            "partner_auth_mapping": report["paths"]["partner_auth_mapping_markdown"],
            "partner_access_reconciliation": report["paths"]["partner_access_reconciliation_markdown"],
            "public_data_reconciliation": report["paths"]["public_data_reconciliation_markdown"],
            "customer_signoff_reconciliation": report["paths"]["customer_signoff_reconciliation_markdown"],
            "first_wave_launch_gate": report["paths"]["first_wave_launch_gate_markdown"],
        },
        live_readiness=live_readiness,
        live_launch_request=live_launch_request,
        live_proof_plan=report.get("live_proof_plan"),
        live_proof_acceptance=report.get("live_proof_acceptance"),
        production_proof=production_proof,
        launch_control_room=report.get("live_launch_control_room"),
        partner_auth_mapping=report.get("partner_auth_mapping"),
        partner_access_reconciliation=report.get("partner_access_reconciliation"),
        public_data_reconciliation=report.get("public_data_reconciliation"),
        customer_signoff_reconciliation=report.get("customer_signoff_reconciliation"),
        first_wave_launch_gate=report.get("first_wave_launch_gate"),
        release_label=release_label,
    )
    report["live_proof_cockpit"] = build_live_proof_cockpit(report)
    report["example_completed_customer_inputs"] = build_example_completed_customer_inputs(report["customer_input_templates"])
    example_input_dir = out_dir / "example_completed_customer_inputs"
    write_example_completed_customer_inputs(example_input_dir, report["example_completed_customer_inputs"])
    report["example_first_campaign_input_validation"] = build_first_campaign_input_validation(
        out_dir=example_input_dir,
        template_pack=report["customer_input_templates"],
        input_dir=example_input_dir,
        release_label=release_label,
        expected_partner_count=report["first_campaign_launch_intake"]["scenario"]["expected_partner_renovators"],
        live_proof_ready=False,
    )
    report["example_first_campaign_import_plan"] = build_first_campaign_import_plan(
        out_dir=example_input_dir,
        template_pack=report["customer_input_templates"],
        input_dir=example_input_dir,
        release_label=release_label,
        expected_partner_count=report["first_campaign_launch_intake"]["scenario"]["expected_partner_renovators"],
        live_proof_ready=False,
        validation_report=report["example_first_campaign_input_validation"],
    )
    report["example_first_wave_launch_gate"] = build_first_wave_launch_gate(
        out_dir=example_input_dir,
        input_validation=report["example_first_campaign_input_validation"],
        import_plan=report["example_first_campaign_import_plan"],
        public_data_intake=report["public_data_production_intake"],
        live_readiness=live_readiness,
        release_label=release_label,
        customer_go_no_go_ready=False,
    )
    write_json(out_dir / "example_completed_customer_inputs.json", report["example_completed_customer_inputs"])
    write_text(
        out_dir / "EXAMPLE_COMPLETED_CUSTOMER_INPUTS.md",
        render_example_completed_customer_inputs_markdown(
            report["example_completed_customer_inputs"],
            report["example_first_campaign_input_validation"],
        ),
    )
    report["daw_boardroom_demo_walkthrough"] = build_daw_boardroom_demo_walkthrough(report)
    write_json(out_dir / "daw_boardroom_demo_walkthrough.json", report["daw_boardroom_demo_walkthrough"])
    write_text(
        out_dir / "DAW_BOARDROOM_DEMO_WALKTHROUGH.md",
        render_daw_boardroom_demo_walkthrough_markdown(report["daw_boardroom_demo_walkthrough"]),
    )
    _write_daw_demo_checklist_csv(out_dir / "DAW_DEMO_CHECKLIST.csv", report["daw_boardroom_demo_walkthrough"])
    report["daw_first_campaign_control_room"] = build_daw_first_campaign_control_room(report)
    write_json(out_dir / "daw_first_campaign_control_room.json", report["daw_first_campaign_control_room"])
    write_text(
        out_dir / "DAW_FIRST_CAMPAIGN_CONTROL_ROOM.md",
        render_daw_first_campaign_control_room_markdown(report["daw_first_campaign_control_room"]),
    )
    _write_daw_first_campaign_action_board_csv(
        out_dir / "DAW_FIRST_CAMPAIGN_ACTION_BOARD.csv",
        report["daw_first_campaign_control_room"],
    )
    write_json(out_dir / "procurement_security_review.json", report["procurement_review"])
    write_text(out_dir / "PROCUREMENT_SECURITY_REVIEW.md", render_procurement_review_markdown(report["procurement_review"]))
    _write_security_questionnaire_csv(out_dir / "SECURITY_QUESTIONNAIRE.csv", report["procurement_review"]["questionnaire"])
    _write_procurement_risk_csv(out_dir / "PROCUREMENT_RISK_REGISTER.csv", report["procurement_review"]["risk_register"])
    write_json(out_dir / "support_sla_plan.json", report["support_sla_plan"])
    write_text(out_dir / "SUPPORT_SLA_PLAN.md", render_support_sla_markdown(report["support_sla_plan"]))
    _write_support_escalation_csv(out_dir / "SUPPORT_ESCALATION_MATRIX.csv", report["support_sla_plan"]["escalation_matrix"])
    write_text(out_dir / "INCIDENT_RESPONSE_PLAYBOOK.md", render_incident_playbook_markdown(report["support_sla_plan"]))
    write_json(out_dir / "customer_pilot_proposal.json", report["customer_pilot_proposal"])
    write_text(out_dir / "CUSTOMER_PILOT_PROPOSAL.md", render_customer_pilot_proposal_markdown(report["customer_pilot_proposal"]))
    _write_pilot_scope_csv(out_dir / "PILOT_SCOPE_CHECKLIST.csv", report["customer_pilot_proposal"])
    _write_commercial_assumptions_csv(out_dir / "COMMERCIAL_ASSUMPTIONS.csv", report["customer_pilot_proposal"])
    write_json(out_dir / "customer_training_plan.json", report["customer_training_plan"])
    write_text(out_dir / "CUSTOMER_TRAINING_GUIDE.md", render_customer_training_guide_markdown(report["customer_training_plan"]))
    _write_training_session_csv(out_dir / "TRAINING_SESSION_PLAN.csv", report["customer_training_plan"]["sessions"])
    _write_role_cheatsheet_csv(out_dir / "ROLE_CHEATSHEET.csv", report["customer_training_plan"]["roles"])
    write_json(out_dir / "customer_value_realization_plan.json", report["value_realization_plan"])
    write_text(out_dir / "CUSTOMER_VALUE_REALIZATION_PLAN.md", render_value_realization_markdown(report["value_realization_plan"]))
    _write_value_metrics_csv(out_dir / "VALUE_REALIZATION_METRICS.csv", report["value_realization_plan"]["metrics"])
    _write_decision_log_csv(out_dir / "EXECUTIVE_DECISION_LOG.csv", report["value_realization_plan"]["decision_log"])
    write_json(out_dir / "customer_module_expansion_plan.json", report["module_expansion_plan"])
    write_text(out_dir / "CUSTOMER_MODULE_EXPANSION_PLAN.md", render_module_expansion_markdown(report["module_expansion_plan"]))
    _write_module_value_matrix_csv(out_dir / "MODULE_VALUE_MATRIX.csv", report["module_expansion_plan"]["modules"])
    _write_expansion_decision_tree_csv(out_dir / "EXPANSION_DECISION_TREE.csv", report["module_expansion_plan"]["decision_tree"])
    write_json(out_dir / "customer_public_data_source_register.json", report["public_data_source_register"])
    write_text(out_dir / "PUBLIC_DATA_SOURCE_REGISTER.md", render_public_data_register_markdown(report["public_data_source_register"]))
    _write_public_source_matrix_csv(out_dir / "PUBLIC_DATA_SOURCE_MATRIX.csv", report["public_data_source_register"]["sources"])
    _write_blocked_data_csv(out_dir / "BLOCKED_DATA_REGISTER.csv", report["public_data_source_register"]["blocked_or_high_risk"])
    _write_attribution_requirements_csv(
        out_dir / "ATTRIBUTION_REQUIREMENTS.csv",
        report["public_data_source_register"]["attribution_requirements"],
    )
    write_json(out_dir / "public_data_production_intake.json", report["public_data_production_intake"])
    write_text(
        out_dir / "PUBLIC_DATA_PRODUCTION_INTAKE.md",
        render_public_data_production_intake_markdown(report["public_data_production_intake"]),
    )
    _write_public_data_approval_csv(
        out_dir / "PUBLIC_DATA_APPROVAL_CHECKLIST.csv",
        report["public_data_production_intake"]["dataset_approvals"],
    )
    write_text(out_dir / "MARKET_READINESS_SCORECARD.md", render_scorecard_markdown(report))
    write_text(out_dir / "market-readiness.html", render_html(report))
    write_text(out_dir / "BOARDROOM_DATA_ROOM_INDEX.md", render_data_room_index(report))
    write_text(out_dir / "STAKEHOLDER_VIEWS.md", render_stakeholder_views(report))
    report["portable_data_room"] = build_portable_data_room(report, out_dir)
    portable_manifest = load_json(Path(report["paths"]["portable_data_room_manifest"]))
    report["market_ready_audit"] = build_market_ready_audit_pack(
        out_dir,
        market_readiness=report,
        launch_control_room=report.get("live_launch_control_room"),
        live_proof_plan=report.get("live_proof_plan"),
        live_proof_acceptance=report.get("live_proof_acceptance"),
        live_credential_handoff=report.get("live_credential_handoff"),
        live_proof_evidence_vault=report.get("live_proof_evidence_vault"),
        outcome_measurement_contract=report.get("outcome_measurement_contract"),
        outcome_import_validation=report.get("outcome_import_validation"),
        module_readiness_matrix=report.get("module_readiness_matrix"),
        production_proof=production_proof,
        portable_manifest=portable_manifest,
        release_label=release_label,
    )
    report["live_proof_cockpit"] = build_live_proof_cockpit(report)
    write_text(out_dir / "MARKET_READINESS_SCORECARD.md", render_scorecard_markdown(report))
    write_text(out_dir / "market-readiness.html", render_html(report))
    write_text(out_dir / "BOARDROOM_DATA_ROOM_INDEX.md", render_data_room_index(report))
    write_text(out_dir / "STAKEHOLDER_VIEWS.md", render_stakeholder_views(report))
    report["portable_data_room"] = build_portable_data_room(report, out_dir)
    write_json(out_dir / "market_readiness_scorecard.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot market-readiness scorecard")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--readiness-report", required=True, type=Path)
    parser.add_argument("--due-diligence-report", required=True, type=Path)
    parser.add_argument("--artifact-index", type=Path)
    parser.add_argument("--production-proof", type=Path)
    parser.add_argument("--live-readiness-report", type=Path)
    parser.add_argument("--live-launch-request", type=Path)
    parser.add_argument("--release-label", default="local")
    args = parser.parse_args()

    report = build_market_readiness_pack(
        out_dir=args.out_dir,
        readiness_report_path=args.readiness_report,
        due_diligence_report_path=args.due_diligence_report,
        artifact_index_path=args.artifact_index,
        production_proof_path=args.production_proof,
        live_readiness_report_path=args.live_readiness_report,
        live_launch_request_path=args.live_launch_request,
        release_label=args.release_label,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": report["status"],
        "decisions": report["decisions"],
        "scorecard": report["paths"]["scorecard"],
        "markdown": report["paths"]["markdown"],
        "html": report["paths"]["html"],
        "data_room_index": report["paths"]["data_room_index"],
        "actions_csv": report["paths"]["actions_csv"],
        "stakeholder_views": report["paths"]["stakeholder_views"],
        "live_launch_control_room": report["paths"]["live_launch_control_room"],
        "live_launch_control_room_markdown": report["paths"]["live_launch_control_room_markdown"],
        "live_launch_action_board": report["paths"]["live_launch_action_board"],
        "live_credential_handoff": report["paths"]["live_credential_handoff"],
        "live_credential_handoff_markdown": report["paths"]["live_credential_handoff_markdown"],
        "live_credential_handoff_checklist": report["paths"]["live_credential_handoff_checklist"],
        "live_secret_channel_contract": report["paths"]["live_secret_channel_contract"],
        "live_proof_plan": report["paths"]["live_proof_plan"],
        "live_proof_plan_markdown": report["paths"]["live_proof_plan_markdown"],
        "live_proof_evidence_map": report["paths"]["live_proof_evidence_map"],
        "live_proof_commands": report["paths"]["live_proof_commands"],
        "live_proof_acceptance": report["paths"]["live_proof_acceptance"],
        "live_proof_acceptance_markdown": report["paths"]["live_proof_acceptance_markdown"],
        "live_proof_acceptance_csv": report["paths"]["live_proof_acceptance_csv"],
        "live_proof_evidence_vault": report["paths"]["live_proof_evidence_vault"],
        "live_proof_evidence_vault_markdown": report["paths"]["live_proof_evidence_vault_markdown"],
        "live_proof_archive_index": report["paths"]["live_proof_archive_index"],
        "market_ready_audit": report["paths"]["market_ready_audit"],
        "market_ready_audit_markdown": report["paths"]["market_ready_audit_markdown"],
        "market_ready_requirements": report["paths"]["market_ready_requirements"],
        "customer_acceptance_plan": report["paths"]["customer_acceptance_plan"],
        "customer_acceptance_plan_markdown": report["paths"]["customer_acceptance_plan_markdown"],
        "acceptance_checklist": report["paths"]["acceptance_checklist"],
        "customer_rollout_plan": report["paths"]["customer_rollout_plan"],
        "customer_rollout_plan_markdown": report["paths"]["customer_rollout_plan_markdown"],
        "rollout_workstreams": report["paths"]["rollout_workstreams"],
        "first_campaign_launch_intake": report["paths"]["first_campaign_launch_intake"],
        "first_campaign_launch_intake_markdown": report["paths"]["first_campaign_launch_intake_markdown"],
        "first_campaign_launch_checklist": report["paths"]["first_campaign_launch_checklist"],
        "customer_input_templates": report["paths"]["customer_input_templates"],
        "customer_input_templates_markdown": report["paths"]["customer_input_templates_markdown"],
        "partner_roster_template": report["paths"]["partner_roster_template"],
        "territory_assignment_template": report["paths"]["territory_assignment_template"],
        "property_source_template": report["paths"]["property_source_template"],
        "suppression_list_template": report["paths"]["suppression_list_template"],
        "message_approval_template": report["paths"]["message_approval_template"],
        "partner_capacity_template": report["paths"]["partner_capacity_template"],
        "first_campaign_input_validation": report["paths"]["first_campaign_input_validation"],
        "first_campaign_input_validation_markdown": report["paths"]["first_campaign_input_validation_markdown"],
        "first_campaign_input_issues": report["paths"]["first_campaign_input_issues"],
        "first_campaign_import_plan": report["paths"]["first_campaign_import_plan"],
        "first_campaign_import_plan_markdown": report["paths"]["first_campaign_import_plan_markdown"],
        "first_campaign_staging_rows": report["paths"]["first_campaign_staging_rows"],
        "first_wave_launch_gate": report["paths"]["first_wave_launch_gate"],
        "first_wave_launch_gate_markdown": report["paths"]["first_wave_launch_gate_markdown"],
        "first_wave_launch_gate_checklist": report["paths"]["first_wave_launch_gate_checklist"],
        "first_wave_database_handoff": report["paths"]["first_wave_database_handoff"],
        "first_wave_database_handoff_markdown": report["paths"]["first_wave_database_handoff_markdown"],
        "first_wave_database_handoff_checklist": report["paths"]["first_wave_database_handoff_checklist"],
        "first_wave_database_review_rows": report["paths"]["first_wave_database_review_rows"],
        "first_wave_database_review_sql": report["paths"]["first_wave_database_review_sql"],
        "partner_auth_mapping": report["paths"]["partner_auth_mapping"],
        "partner_auth_mapping_markdown": report["paths"]["partner_auth_mapping_markdown"],
        "partner_auth_mapping_template": report["paths"]["partner_auth_mapping_template"],
        "partner_auth_mapping_rows": report["paths"]["partner_auth_mapping_rows"],
        "partner_auth_mapping_issues": report["paths"]["partner_auth_mapping_issues"],
        "partner_membership_review_sql": report["paths"]["partner_membership_review_sql"],
        "partner_access_reconciliation": report["paths"]["partner_access_reconciliation"],
        "partner_access_reconciliation_markdown": report["paths"]["partner_access_reconciliation_markdown"],
        "partner_access_reconciliation_matrix": report["paths"]["partner_access_reconciliation_matrix"],
        "partner_access_reconciliation_issues": report["paths"]["partner_access_reconciliation_issues"],
        "example_completed_customer_inputs": report["paths"]["example_completed_customer_inputs"],
        "example_completed_customer_inputs_markdown": report["paths"]["example_completed_customer_inputs_markdown"],
        "example_completed_partner_roster": report["paths"]["example_completed_partner_roster"],
        "example_completed_territory_assignment": report["paths"]["example_completed_territory_assignment"],
        "example_completed_property_source": report["paths"]["example_completed_property_source"],
        "example_completed_suppression_list": report["paths"]["example_completed_suppression_list"],
        "example_completed_message_approval": report["paths"]["example_completed_message_approval"],
        "example_completed_partner_capacity": report["paths"]["example_completed_partner_capacity"],
        "example_first_campaign_input_validation": report["paths"]["example_first_campaign_input_validation"],
        "example_first_campaign_input_validation_markdown": report["paths"]["example_first_campaign_input_validation_markdown"],
        "example_first_campaign_input_issues": report["paths"]["example_first_campaign_input_issues"],
        "example_first_campaign_import_plan": report["paths"]["example_first_campaign_import_plan"],
        "example_first_campaign_import_plan_markdown": report["paths"]["example_first_campaign_import_plan_markdown"],
        "example_first_campaign_staging_rows": report["paths"]["example_first_campaign_staging_rows"],
        "example_first_wave_launch_gate": report["paths"]["example_first_wave_launch_gate"],
        "example_first_wave_launch_gate_markdown": report["paths"]["example_first_wave_launch_gate_markdown"],
        "example_first_wave_launch_gate_checklist": report["paths"]["example_first_wave_launch_gate_checklist"],
        "daw_boardroom_demo_walkthrough": report["paths"]["daw_boardroom_demo_walkthrough"],
        "daw_boardroom_demo_walkthrough_markdown": report["paths"]["daw_boardroom_demo_walkthrough_markdown"],
        "daw_demo_checklist": report["paths"]["daw_demo_checklist"],
        "daw_first_campaign_control_room": report["paths"]["daw_first_campaign_control_room"],
        "daw_first_campaign_control_room_markdown": report["paths"]["daw_first_campaign_control_room_markdown"],
        "daw_first_campaign_action_board": report["paths"]["daw_first_campaign_action_board"],
        "procurement_review": report["paths"]["procurement_review"],
        "procurement_review_markdown": report["paths"]["procurement_review_markdown"],
        "security_questionnaire": report["paths"]["security_questionnaire"],
        "procurement_risk_register": report["paths"]["procurement_risk_register"],
        "support_sla_plan": report["paths"]["support_sla_plan"],
        "support_sla_plan_markdown": report["paths"]["support_sla_plan_markdown"],
        "support_escalation_matrix": report["paths"]["support_escalation_matrix"],
        "incident_response_playbook": report["paths"]["incident_response_playbook"],
        "customer_pilot_proposal": report["paths"]["customer_pilot_proposal"],
        "customer_pilot_proposal_markdown": report["paths"]["customer_pilot_proposal_markdown"],
        "pilot_scope_checklist": report["paths"]["pilot_scope_checklist"],
        "commercial_assumptions": report["paths"]["commercial_assumptions"],
        "customer_training_guide": report["paths"]["customer_training_guide"],
        "training_session_plan": report["paths"]["training_session_plan"],
        "role_cheatsheet": report["paths"]["role_cheatsheet"],
        "value_realization_plan_markdown": report["paths"]["value_realization_plan_markdown"],
        "value_realization_metrics": report["paths"]["value_realization_metrics"],
        "executive_decision_log": report["paths"]["executive_decision_log"],
        "outcome_measurement_contract": report["paths"]["outcome_measurement_contract"],
        "outcome_measurement_contract_markdown": report["paths"]["outcome_measurement_contract_markdown"],
        "outcome_event_schema": report["paths"]["outcome_event_schema"],
        "outcome_sync_template": report["paths"]["outcome_sync_template"],
        "outcome_reconciliation_checklist": report["paths"]["outcome_reconciliation_checklist"],
        "outcome_import_validation": report["paths"]["outcome_import_validation"],
        "outcome_import_validation_markdown": report["paths"]["outcome_import_validation_markdown"],
        "outcome_import_issues": report["paths"]["outcome_import_issues"],
        "outcome_import_review_rows": report["paths"]["outcome_import_review_rows"],
        "module_expansion_plan_markdown": report["paths"]["module_expansion_plan_markdown"],
        "module_value_matrix": report["paths"]["module_value_matrix"],
        "expansion_decision_tree": report["paths"]["expansion_decision_tree"],
        "module_readiness_matrix": report["paths"]["module_readiness_matrix"],
        "module_readiness_matrix_markdown": report["paths"]["module_readiness_matrix_markdown"],
        "module_readiness_matrix_csv": report["paths"]["module_readiness_matrix_csv"],
        "module_metric_coverage": report["paths"]["module_metric_coverage"],
        "public_data_source_register_markdown": report["paths"]["public_data_source_register_markdown"],
        "public_data_source_matrix": report["paths"]["public_data_source_matrix"],
        "blocked_data_register": report["paths"]["blocked_data_register"],
        "attribution_requirements": report["paths"]["attribution_requirements"],
        "public_data_production_intake": report["paths"]["public_data_production_intake"],
        "public_data_production_intake_markdown": report["paths"]["public_data_production_intake_markdown"],
        "public_data_approval_checklist": report["paths"]["public_data_approval_checklist"],
        "public_data_reconciliation": report["paths"]["public_data_reconciliation"],
        "public_data_reconciliation_markdown": report["paths"]["public_data_reconciliation_markdown"],
        "public_data_reconciliation_matrix": report["paths"]["public_data_reconciliation_matrix"],
        "public_data_reconciliation_issues": report["paths"]["public_data_reconciliation_issues"],
        "customer_signoff_reconciliation": report["paths"]["customer_signoff_reconciliation"],
        "customer_signoff_reconciliation_markdown": report["paths"]["customer_signoff_reconciliation_markdown"],
        "customer_signoff_reconciliation_matrix": report["paths"]["customer_signoff_reconciliation_matrix"],
        "customer_signoff_reconciliation_issues": report["paths"]["customer_signoff_reconciliation_issues"],
        "customer_signoff_intake_markdown": report["paths"]["customer_signoff_intake_markdown"],
        "customer_signoff_evidence_template": report["paths"]["customer_signoff_evidence_template"],
        "customer_view_catalog": report["paths"]["customer_view_catalog"],
        "customer_view_catalog_markdown": report["paths"]["customer_view_catalog_markdown"],
        "customer_view_matrix": report["paths"]["customer_view_matrix"],
        "portable_data_room_html": report["paths"]["portable_data_room_html"],
        "portable_data_room_zip": report["paths"]["portable_data_room_zip"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
