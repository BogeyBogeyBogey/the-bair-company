#!/usr/bin/env python3
"""
Build a HomePilot release evidence bundle.

The release audit answers go/no-go. This pack turns the evidence into an
operator/customer-review room: release audit, preflight, deployment manifest,
artifact index, release notes, and handoff checklist in one directory.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_deployment import build_deployment_pack
from homepilot_market_readiness import build_market_readiness_pack
from homepilot_ops_status import build_ops_status, write_ops_status_pack
from homepilot_preflight import build_preflight_report
from homepilot_production_cutover import build_production_cutover
from homepilot_production_proof import build_production_proof_pack
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


def _copy_evidence(source: Path | None, target_dir: Path, target_name: str) -> str | None:
    if source is None:
        return None
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / target_name
    shutil.copy2(source, target)
    return str(target)


def _path_exists(path: str | None) -> bool:
    return bool(path and Path(path).exists())


def _due_path(due_diligence: dict[str, Any] | None, key: str) -> str | None:
    if not due_diligence:
        return None
    paths = due_diligence.get("paths") if isinstance(due_diligence.get("paths"), dict) else {}
    value = paths.get(key)
    return str(value) if value else None


def _readiness_gate_statuses(readiness: dict[str, Any] | None) -> dict[str, str]:
    if not readiness:
        return {}
    return {
        str(gate.get("name")): str(gate.get("status"))
        for gate in readiness.get("gates", [])
    }


def _readiness_path(readiness: dict[str, Any] | None, key: str) -> str | None:
    if not readiness:
        return None
    paths = readiness.get("paths") if isinstance(readiness.get("paths"), dict) else {}
    value = paths.get(key)
    return str(value) if value else None


def _build_artifact_index(
    release_label: str,
    stage: str,
    readiness_path: Path,
    due_diligence_path: Path,
    live_readiness_path: Path | None,
    launch_path: Path | None,
    customer_access_path: Path | None,
    schema_verification_path: Path | None,
    copied: dict[str, str | None],
    generated: dict[str, str],
    readiness: dict[str, Any] | None,
    due_diligence: dict[str, Any] | None,
    live_readiness: dict[str, Any] | None,
    schema_verification: dict[str, Any] | None,
    release_audit: dict[str, Any],
    preflight: dict[str, Any],
    deployment_pack: dict[str, Any],
) -> dict[str, Any]:
    data_dictionary = _due_path(due_diligence, "data_dictionary")
    data_dictionary_markdown = _due_path(due_diligence, "data_dictionary_markdown")
    api_contract = _due_path(due_diligence, "api_contract")
    api_contract_markdown = _due_path(due_diligence, "api_contract_markdown")
    processing_register = _due_path(due_diligence, "processing_register")
    processing_register_markdown = _due_path(due_diligence, "processing_register_markdown")
    portal_dir = _readiness_path(readiness, "customer_portal_smoke")
    portal_manifest = str(Path(portal_dir) / "portal_manifest.json") if portal_dir else None
    portal_readme = str(Path(portal_dir) / "PORTAL_README.md") if portal_dir else None
    portal_live_config = str(Path(portal_dir) / "public" / "live-config.js") if portal_dir else None
    portal_live_loader = str(Path(portal_dir) / "public" / "live-data.js") if portal_dir else None
    hosting_dir = _readiness_path(readiness, "portal_hosting_smoke")
    hosting_manifest = str(Path(hosting_dir) / "hosting_manifest.json") if hosting_dir else None
    hosting_runbook = str(Path(hosting_dir) / "HOSTING_RUNBOOK.md") if hosting_dir else None
    hosting_asset_manifest = str(Path(hosting_dir) / "asset_manifest.json") if hosting_dir else None
    hosting_cache_policy = str(Path(hosting_dir) / "cache_policy.json") if hosting_dir else None
    hosting_deployment_checklist = str(Path(hosting_dir) / "deployment_checklist.csv") if hosting_dir else None
    hosting_rollback_manifest = str(Path(hosting_dir) / "rollback_manifest.json") if hosting_dir else None
    integration_dir = _readiness_path(readiness, "sales_integration_smoke")
    integration_manifest = str(Path(integration_dir) / "integration_manifest.json") if integration_dir else None
    integration_runbook = str(Path(integration_dir) / "INTEGRATION_RUNBOOK.md") if integration_dir else None
    integration_sync_dir = _readiness_path(readiness, "sales_integration_sync_smoke")
    integration_sync_report = str(Path(integration_sync_dir) / "sync_report.json") if integration_sync_dir else None
    integration_sync_runbook = str(Path(integration_sync_dir) / "SYNC_RUNBOOK.md") if integration_sync_dir else None
    enrichment_dir = _readiness_path(readiness, "data_vendor_enrichment_smoke")
    enrichment_plan = str(Path(enrichment_dir) / "data_vendor_plan.json") if enrichment_dir else None
    enrichment_markdown = str(Path(enrichment_dir) / "DATA_VENDOR_PLAN.md") if enrichment_dir else None
    enrichment_refresh_dir = _readiness_path(readiness, "data_vendor_refresh_smoke")
    enrichment_refresh_report = str(Path(enrichment_refresh_dir) / "enrichment_refresh_report.json") if enrichment_refresh_dir else None
    enrichment_refresh_runbook = str(Path(enrichment_refresh_dir) / "ENRICHMENT_REFRESH_RUNBOOK.md") if enrichment_refresh_dir else None
    enrichment_refresh_jobs = str(Path(enrichment_refresh_dir) / "refresh_jobs.csv") if enrichment_refresh_dir else None
    enrichment_refresh_dead_letter = str(Path(enrichment_refresh_dir) / "dead_letter.jsonl") if enrichment_refresh_dir else None
    demo_dir = _readiness_path(readiness, "enterprise_demo_room_smoke")
    demo_manifest = str(Path(demo_dir) / "manifest.json") if demo_dir else None
    demo_readme = str(Path(demo_dir) / "README.md") if demo_dir else None
    demo_dashboard = str(Path(demo_dir) / "customer_package" / "dashboard" / "index.html") if demo_dir else None
    demo_open_intelligence = str(Path(demo_dir) / "customer_package" / "data" / "open_intelligence" / "open_intelligence.json") if demo_dir else None
    demo_open_intelligence_markdown = str(Path(demo_dir) / "customer_package" / "data" / "open_intelligence" / "OPEN_INTELLIGENCE.md") if demo_dir else None
    demo_open_intelligence_boardroom_brief = str(Path(demo_dir) / "customer_package" / "data" / "open_intelligence" / "OPEN_INTELLIGENCE_BOARDROOM_BRIEF.md") if demo_dir else None
    demo_open_intelligence_decision_matrix = str(Path(demo_dir) / "customer_package" / "data" / "open_intelligence" / "OPEN_INTELLIGENCE_DECISION_MATRIX.csv") if demo_dir else None
    demo_marketing_impact_planner = str(Path(demo_dir) / "customer_package" / "data" / "open_intelligence" / "MARKETING_IMPACT_PLANNER.csv") if demo_dir else None
    demo_measurement_loop = str(Path(demo_dir) / "customer_package" / "data" / "open_intelligence" / "MEASUREMENT_LOOP.csv") if demo_dir else None
    visual_dir = _readiness_path(readiness, "visual_intelligence_smoke")
    visual_intelligence = str(Path(visual_dir) / "visual_intelligence.json") if visual_dir else None
    visual_runbook = str(Path(visual_dir) / "VISUAL_INTELLIGENCE.md") if visual_dir else None
    visual_map_clusters = str(Path(visual_dir) / "map_clusters.csv") if visual_dir else None
    monitoring_dir = _readiness_path(readiness, "monitoring_smoke")
    monitoring_plan = str(Path(monitoring_dir) / "monitoring_plan.json") if monitoring_dir else None
    monitoring_runbook = str(Path(monitoring_dir) / "MONITORING_RUNBOOK.md") if monitoring_dir else None
    monitoring_alert_matrix = str(Path(monitoring_dir) / "alert_matrix.csv") if monitoring_dir else None
    live_launch_request_dir = _readiness_path(readiness, "live_launch_request_smoke")
    live_launch_request = str(Path(live_launch_request_dir) / "live_launch_request.json") if live_launch_request_dir else None
    live_launch_request_markdown = str(Path(live_launch_request_dir) / "LIVE_LAUNCH_REQUEST.md") if live_launch_request_dir else None
    live_launch_checklist = str(Path(live_launch_request_dir) / "LIVE_LAUNCH_CHECKLIST.csv") if live_launch_request_dir else None
    live_launch_env_template = str(Path(live_launch_request_dir) / "live_launch.env.template") if live_launch_request_dir else None
    live_launch_request_email = str(Path(live_launch_request_dir) / "LIVE_LAUNCH_REQUEST_EMAIL.txt") if live_launch_request_dir else None
    return {
        "index_type": "homepilot_release_evidence_index",
        "created_at": utc_now(),
        "release_label": release_label,
        "requested_stage": stage,
        "status": preflight["status"],
        "stage_status": preflight["stage_status"],
        "decisions": preflight["decisions"],
        "blockers": preflight["blockers"],
        "inputs": {
            "readiness_report": str(readiness_path),
            "due_diligence_report": str(due_diligence_path),
            "live_readiness_report": str(live_readiness_path) if live_readiness_path else None,
            "schema_verification_report": str(schema_verification_path) if schema_verification_path else None,
            "launch_report": str(launch_path) if launch_path else None,
            "customer_access_report": str(customer_access_path) if customer_access_path else None,
        },
        "copied_evidence": copied,
        "generated_evidence": generated,
        "referenced_artifacts": {
            "data_dictionary": data_dictionary,
            "data_dictionary_exists": _path_exists(data_dictionary),
            "data_dictionary_markdown": data_dictionary_markdown,
            "data_dictionary_markdown_exists": _path_exists(data_dictionary_markdown),
            "api_contract": api_contract,
            "api_contract_exists": _path_exists(api_contract),
            "api_contract_markdown": api_contract_markdown,
            "api_contract_markdown_exists": _path_exists(api_contract_markdown),
            "processing_register": processing_register,
            "processing_register_exists": _path_exists(processing_register),
            "processing_register_markdown": processing_register_markdown,
            "processing_register_markdown_exists": _path_exists(processing_register_markdown),
            "customer_portal_manifest": portal_manifest,
            "customer_portal_manifest_exists": _path_exists(portal_manifest),
            "customer_portal_readme": portal_readme,
            "customer_portal_readme_exists": _path_exists(portal_readme),
            "customer_portal_live_config": portal_live_config,
            "customer_portal_live_config_exists": _path_exists(portal_live_config),
            "customer_portal_live_loader": portal_live_loader,
            "customer_portal_live_loader_exists": _path_exists(portal_live_loader),
            "customer_portal_hosting_manifest": hosting_manifest,
            "customer_portal_hosting_manifest_exists": _path_exists(hosting_manifest),
            "customer_portal_hosting_runbook": hosting_runbook,
            "customer_portal_hosting_runbook_exists": _path_exists(hosting_runbook),
            "customer_portal_hosting_asset_manifest": hosting_asset_manifest,
            "customer_portal_hosting_asset_manifest_exists": _path_exists(hosting_asset_manifest),
            "customer_portal_hosting_cache_policy": hosting_cache_policy,
            "customer_portal_hosting_cache_policy_exists": _path_exists(hosting_cache_policy),
            "customer_portal_hosting_deployment_checklist": hosting_deployment_checklist,
            "customer_portal_hosting_deployment_checklist_exists": _path_exists(hosting_deployment_checklist),
            "customer_portal_hosting_rollback_manifest": hosting_rollback_manifest,
            "customer_portal_hosting_rollback_manifest_exists": _path_exists(hosting_rollback_manifest),
            "sales_integration_manifest": integration_manifest,
            "sales_integration_manifest_exists": _path_exists(integration_manifest),
            "sales_integration_runbook": integration_runbook,
            "sales_integration_runbook_exists": _path_exists(integration_runbook),
            "sales_integration_sync_report": integration_sync_report,
            "sales_integration_sync_report_exists": _path_exists(integration_sync_report),
            "sales_integration_sync_runbook": integration_sync_runbook,
            "sales_integration_sync_runbook_exists": _path_exists(integration_sync_runbook),
            "data_vendor_plan": enrichment_plan,
            "data_vendor_plan_exists": _path_exists(enrichment_plan),
            "data_vendor_plan_markdown": enrichment_markdown,
            "data_vendor_plan_markdown_exists": _path_exists(enrichment_markdown),
            "data_vendor_refresh_report": enrichment_refresh_report,
            "data_vendor_refresh_report_exists": _path_exists(enrichment_refresh_report),
            "data_vendor_refresh_runbook": enrichment_refresh_runbook,
            "data_vendor_refresh_runbook_exists": _path_exists(enrichment_refresh_runbook),
            "data_vendor_refresh_jobs": enrichment_refresh_jobs,
            "data_vendor_refresh_jobs_exists": _path_exists(enrichment_refresh_jobs),
            "data_vendor_refresh_dead_letter": enrichment_refresh_dead_letter,
            "data_vendor_refresh_dead_letter_exists": _path_exists(enrichment_refresh_dead_letter),
            "enterprise_demo_room_manifest": demo_manifest,
            "enterprise_demo_room_manifest_exists": _path_exists(demo_manifest),
            "enterprise_demo_room_readme": demo_readme,
            "enterprise_demo_room_readme_exists": _path_exists(demo_readme),
            "enterprise_demo_room_dashboard": demo_dashboard,
            "enterprise_demo_room_dashboard_exists": _path_exists(demo_dashboard),
            "enterprise_demo_room_open_intelligence": demo_open_intelligence,
            "enterprise_demo_room_open_intelligence_exists": _path_exists(demo_open_intelligence),
            "enterprise_demo_room_open_intelligence_markdown": demo_open_intelligence_markdown,
            "enterprise_demo_room_open_intelligence_markdown_exists": _path_exists(demo_open_intelligence_markdown),
            "enterprise_demo_room_open_intelligence_boardroom_brief": demo_open_intelligence_boardroom_brief,
            "enterprise_demo_room_open_intelligence_boardroom_brief_exists": _path_exists(demo_open_intelligence_boardroom_brief),
            "enterprise_demo_room_open_intelligence_decision_matrix": demo_open_intelligence_decision_matrix,
            "enterprise_demo_room_open_intelligence_decision_matrix_exists": _path_exists(demo_open_intelligence_decision_matrix),
            "enterprise_demo_room_marketing_impact_planner": demo_marketing_impact_planner,
            "enterprise_demo_room_marketing_impact_planner_exists": _path_exists(demo_marketing_impact_planner),
            "enterprise_demo_room_measurement_loop": demo_measurement_loop,
            "enterprise_demo_room_measurement_loop_exists": _path_exists(demo_measurement_loop),
            "visual_intelligence": visual_intelligence,
            "visual_intelligence_exists": _path_exists(visual_intelligence),
            "visual_intelligence_runbook": visual_runbook,
            "visual_intelligence_runbook_exists": _path_exists(visual_runbook),
            "visual_intelligence_map_clusters": visual_map_clusters,
            "visual_intelligence_map_clusters_exists": _path_exists(visual_map_clusters),
            "monitoring_plan": monitoring_plan,
            "monitoring_plan_exists": _path_exists(monitoring_plan),
            "monitoring_runbook": monitoring_runbook,
            "monitoring_runbook_exists": _path_exists(monitoring_runbook),
            "monitoring_alert_matrix": monitoring_alert_matrix,
            "monitoring_alert_matrix_exists": _path_exists(monitoring_alert_matrix),
            "live_launch_request": live_launch_request,
            "live_launch_request_exists": _path_exists(live_launch_request),
            "live_launch_request_markdown": live_launch_request_markdown,
            "live_launch_request_markdown_exists": _path_exists(live_launch_request_markdown),
            "live_launch_checklist": live_launch_checklist,
            "live_launch_checklist_exists": _path_exists(live_launch_checklist),
            "live_launch_env_template": live_launch_env_template,
            "live_launch_env_template_exists": _path_exists(live_launch_env_template),
            "live_launch_request_email": live_launch_request_email,
            "live_launch_request_email_exists": _path_exists(live_launch_request_email),
            "deployment_manifest": deployment_pack["paths"]["deployment_manifest"],
            "deployment_runbook": deployment_pack["paths"]["deployment_runbook"],
        },
        "summary": {
            "readiness_status": readiness.get("status") if readiness else None,
            "readiness_production_verified": readiness.get("production_verified") if readiness else None,
            "readiness_gates": _readiness_gate_statuses(readiness),
            "due_diligence_status": due_diligence.get("status") if due_diligence else None,
            "due_diligence_redaction": due_diligence.get("redaction", {}) if due_diligence else {},
            "release_status": release_audit["status"],
            "schema_deployment_status": deployment_pack["status"],
            "live_readiness_status": live_readiness.get("status") if live_readiness else None,
            "live_readiness_ready_to_run_live_cutover": live_readiness.get("ready_to_run_live_cutover") if live_readiness else None,
            "schema_verification_status": schema_verification.get("status") if schema_verification else None,
            "schema_verification_production_verified": schema_verification.get("production_verified") if schema_verification else None,
        },
    }


def render_release_notes(index: dict[str, Any], release_audit: dict[str, Any]) -> str:
    decisions = index["decisions"]
    lines = [
        "# HomePilot Release Evidence",
        "",
        f"Release: {index['release_label']}",
        f"Created: {index['created_at']}",
        f"Requested stage: {index['requested_stage']}",
        f"Status: {index['status']}",
        "",
        "## Decisions",
        "",
        f"- Buyer review: {decisions['buyer_review']}",
        f"- Live launch: {decisions['live_launch']}",
        f"- Production: {decisions['production']}",
        "",
        "## Production Blockers",
        "",
    ]
    production_blockers = release_audit["blockers"]["production"]
    if production_blockers:
        lines.extend(f"- {blocker}" for blocker in production_blockers)
    else:
        lines.append("- None.")
    lines += [
        "",
        "## Evidence Files",
        "",
    ]
    for label, path in index["generated_evidence"].items():
        lines.append(f"- {label}: {path}")
    for label, path in index["copied_evidence"].items():
        if path:
            lines.append(f"- {label}: {path}")
    lines += [
        "",
        "## Referenced Artifacts",
        "",
    ]
    for label, path in index["referenced_artifacts"].items():
        if label.endswith("_exists") or not path:
            continue
        lines.append(f"- {label}: {path}")
    lines += [
        "",
        "## Required For Production",
        "",
    ]
    for item in release_audit["required_for_production"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def render_handoff_checklist(index: dict[str, Any]) -> str:
    decisions = index["decisions"]
    lines = [
        "# HomePilot Handoff Checklist",
        "",
        "## Buyer Review",
        "",
        f"- Status: {decisions['buyer_review']}",
        (
            "- Share homepilot_boardroom_data_room.zip first; it contains portable_data_room/index.html with relative evidence links, local-path redaction, and checksums. "
            "Keep DAW_BOARDROOM_DEMO_WALKTHROUGH.md, DAW_DEMO_CHECKLIST.csv, DAW_FIRST_CAMPAIGN_CONTROL_ROOM.md, and DAW_FIRST_CAMPAIGN_ACTION_BOARD.csv ready for the live meeting and first-campaign operating flow. "
            "Keep CUSTOMER_ACCEPTANCE_PLAN.md, ACCEPTANCE_CHECKLIST.csv, CUSTOMER_ROLLOUT_PLAN.md, ROLLOUT_WORKSTREAMS.csv, FIRST_CAMPAIGN_LAUNCH_INTAKE.md, FIRST_CAMPAIGN_LAUNCH_CHECKLIST.csv, CUSTOMER_INPUT_TEMPLATES.md, PARTNER_ROSTER_TEMPLATE.csv, TERRITORY_ASSIGNMENT_TEMPLATE.csv, PROPERTY_SOURCE_TEMPLATE.csv, SUPPRESSION_LIST_TEMPLATE.csv, MESSAGE_APPROVAL_TEMPLATE.csv, PARTNER_CAPACITY_TEMPLATE.csv, FIRST_CAMPAIGN_INPUT_VALIDATION.md, FIRST_CAMPAIGN_INPUT_ISSUES.csv, FIRST_CAMPAIGN_IMPORT_PLAN.md, FIRST_CAMPAIGN_STAGING_ROWS.csv, FIRST_WAVE_LAUNCH_GATE.md, FIRST_WAVE_LAUNCH_GATE_CHECKLIST.csv, PARTNER_AUTH_MAPPING.md, PARTNER_MEMBERSHIP_REVIEW.sql, PARTNER_ACCESS_RECONCILIATION.md, PARTNER_ACCESS_RECONCILIATION_MATRIX.csv, PARTNER_ACCESS_RECONCILIATION_ISSUES.csv, EXAMPLE_COMPLETED_CUSTOMER_INPUTS.md, example_completed_customer_inputs/*.csv, example_completed_customer_inputs/FIRST_CAMPAIGN_INPUT_VALIDATION.md, example_completed_customer_inputs/FIRST_CAMPAIGN_IMPORT_PLAN.md, example_completed_customer_inputs/FIRST_CAMPAIGN_STAGING_ROWS.csv, example_completed_customer_inputs/FIRST_WAVE_LAUNCH_GATE.md, example_completed_customer_inputs/FIRST_WAVE_LAUNCH_GATE_CHECKLIST.csv, PROCUREMENT_SECURITY_REVIEW.md, SECURITY_QUESTIONNAIRE.csv, PROCUREMENT_RISK_REGISTER.csv, SUPPORT_SLA_PLAN.md, SUPPORT_ESCALATION_MATRIX.csv, INCIDENT_RESPONSE_PLAYBOOK.md, CUSTOMER_PILOT_PROPOSAL.md, PILOT_SCOPE_CHECKLIST.csv, COMMERCIAL_ASSUMPTIONS.csv, CUSTOMER_TRAINING_GUIDE.md, TRAINING_SESSION_PLAN.csv, ROLE_CHEATSHEET.csv, CUSTOMER_VALUE_REALIZATION_PLAN.md, VALUE_REALIZATION_METRICS.csv, EXECUTIVE_DECISION_LOG.csv, OUTCOME_MEASUREMENT_CONTRACT.md, OUTCOME_EVENT_SCHEMA.csv, OUTCOME_SYNC_TEMPLATE.csv, OUTCOME_RECONCILIATION_CHECKLIST.csv, OUTCOME_IMPORT_VALIDATION.md, OUTCOME_IMPORT_ISSUES.csv, OUTCOME_IMPORT_REVIEW_ROWS.csv, CUSTOMER_MODULE_EXPANSION_PLAN.md, MODULE_VALUE_MATRIX.csv, EXPANSION_DECISION_TREE.csv, MODULE_READINESS_MATRIX.md, MODULE_READINESS_MATRIX.csv, MODULE_METRIC_COVERAGE.csv, PUBLIC_DATA_SOURCE_REGISTER.md, PUBLIC_DATA_SOURCE_MATRIX.csv, BLOCKED_DATA_REGISTER.csv, ATTRIBUTION_REQUIREMENTS.csv, PUBLIC_DATA_PRODUCTION_INTAKE.md, PUBLIC_DATA_APPROVAL_CHECKLIST.csv, PUBLIC_DATA_RECONCILIATION.md, PUBLIC_DATA_RECONCILIATION_MATRIX.csv, PUBLIC_DATA_RECONCILIATION_ISSUES.csv, CUSTOMER_SIGNOFF_RECONCILIATION.md, CUSTOMER_SIGNOFF_RECONCILIATION_MATRIX.csv, CUSTOMER_SIGNOFF_RECONCILIATION_ISSUES.csv, CUSTOMER_SIGNOFF_INTAKE.md, CUSTOMER_SIGNOFF_EVIDENCE_TEMPLATE.csv, LIVE_CREDENTIAL_HANDOFF.md, LIVE_CREDENTIAL_HANDOFF_CHECKLIST.csv, LIVE_SECRET_CHANNEL_CONTRACT.csv, LIVE_PROOF_EVIDENCE_VAULT.md, LIVE_PROOF_ARCHIVE_INDEX.csv, market-readiness.html, MARKET_READINESS_SCORECARD.md, BOARDROOM_DATA_ROOM_INDEX.md, STAKEHOLDER_VIEWS.md, production_proof.json, PRODUCTION_PROOF.md, release_audit.json, preflight_report.json, due_diligence_report.json, readiness_report.json, SQL_APPLY_PLAN.md, apply.sql, post_apply_verification.sql, LIVE_READINESS.md, LIVE_LAUNCH_REQUEST.md, LIVE_LAUNCH_CHECKLIST.csv, LIVE_LAUNCH_REQUEST_EMAIL.txt, live_cutover.env.template, live_launch.env.template, ACCOUNT_ACCESS_PLAN.md, CUSTOMER_ACCESS_VERIFICATION.md, PORTAL_README.md, HOSTING_RUNBOOK.md, deployment_checklist.csv, INTEGRATION_RUNBOOK.md, SYNC_RUNBOOK.md, VISUAL_INTELLIGENCE.md, map_clusters.csv, MONITORING_RUNBOOK.md, alert_matrix.csv, DATA_VENDOR_PLAN.md, ENRICHMENT_REFRESH_RUNBOOK.md, refresh_jobs.csv, DATA_DICTIONARY.md, API_CONTRACT.md, PROCESSING_REGISTER.md, the enterprise demo room README/dashboard, and the package CUSTOMER_BRIEF.md, CAMPAIGN_LEARNING.md, TERRITORY_PLAN.md, ROI_FORECAST.md, OPPORTUNITY_DOSSIER.md, and SOURCE_LEDGER.md available for deeper review."
        ),
        "- Confirm customer modules and metric visibility match the signed scope.",
        "- Confirm generated exports are scoped to one tenant and enabled modules only.",
        "",
        "## Live Launch",
        "",
        f"- Status: {decisions['live_launch']}",
        "- Review SQL_APPLY_PLAN.md and apply.sql with the customer/operator IT owner before running live schema verification.",
        "- Run homepilot_live_readiness.py and archive live_readiness.json before mutating live seed/import/probe steps.",
        "- Use LIVE_LAUNCH_REQUEST.md and LIVE_LAUNCH_CHECKLIST.csv to assign missing Supabase, fixture, and customer-access inputs without emailing secret values.",
        "- Use LIVE_PROOF_EXECUTION_PLAN.md, LIVE_PROOF_EVIDENCE_MAP.csv, and LIVE_PROOF_COMMANDS.sh as the guarded operator route after inputs are assigned; the command script requires HOMEPILOT_LIVE_PROOF_CONFIRM=run-live-proof and secret-manager/environment values, and it must not be treated as buyer-review evidence by itself.",
        "- Use LIVE_PROOF_EVIDENCE_VAULT.md and LIVE_PROOF_ARCHIVE_INDEX.csv as the archive map for schema verification, RLS launch, customer access, partner access, public-data, customer signoff, first-wave, and production proof.",
        "- Configure Supabase URL, service-role key, anon key, and customer test users.",
        "- Run homepilot_live_schema_verification.py --live and archive schema_verification.json.",
        "- Run live healthcheck and homepilot_launch.py rls-fixture.",
        "- Run homepilot_customer_access_verification.py with planned customer invitees and env-based credentials.",
        "- Run homepilot_partner_access_reconciliation.py for producer-network partner access and archive the reconciliation report.",
        "- Run homepilot_public_data_reconciliation.py before any production public-data import and archive the reconciliation report.",
        "- Run homepilot_customer_signoff_reconciliation.py before customer go/no-go and archive the signoff matrix plus issue list.",
        "- Use OUTCOME_MEASUREMENT_CONTRACT.md, OUTCOME_EVENT_SCHEMA.csv, OUTCOME_SYNC_TEMPLATE.csv, OUTCOME_RECONCILIATION_CHECKLIST.csv, OUTCOME_IMPORT_VALIDATION.md, OUTCOME_IMPORT_ISSUES.csv, and OUTCOME_IMPORT_REVIEW_ROWS.csv to agree and dry-run closed-loop CRM/sheet outcome sync before importing appointments, quotes, won/lost projects, or value metrics.",
        "- Archive schema_verification.json, launch_report.json, rls_probe_report.json, customer_access_verification.json, partner_access_reconciliation.json, public_data_reconciliation.json, customer_signoff_reconciliation.json, cleanup_plan.json, and cleanup_plan.sql.",
        "",
        "## Production Rollout",
        "",
        f"- Status: {decisions['production']}",
        "- Production is go only after live readiness is ready and schema verification, launch, and customer access reports all have production_verified=true, with RLS probes passing for real customer JWTs; producer-network partner access also requires partner-access reconciliation, and public-data imports require public-data reconciliation.",
        "- Archive PRODUCTION_PROOF.md and production_proof.json with the release pack so artifact hashes, freshness, and secret-scan status are reviewable.",
        "- Review fixture cleanup SQL after evidence is archived.",
        "- Run release audit with --require-production before customer access is enabled.",
        "",
    ]
    return "\n".join(lines)


def build_release_evidence_bundle(
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
    out_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = out_dir / "evidence"

    readiness = load_json(readiness_report_path)
    due_diligence = load_json(due_diligence_report_path)
    launch = load_json(launch_report_path)
    customer_access = load_json(customer_access_report_path)
    schema_verification = load_json(schema_verification_report_path)
    live_readiness = load_json(live_readiness_report_path)

    copied = {
        "readiness_report": _copy_evidence(readiness_report_path, evidence_dir, "readiness_report.json"),
        "due_diligence_report": _copy_evidence(due_diligence_report_path, evidence_dir, "due_diligence_report.json"),
        "live_readiness_report": _copy_evidence(live_readiness_report_path, evidence_dir, "live_readiness.json"),
        "schema_verification_report": _copy_evidence(schema_verification_report_path, evidence_dir, "schema_verification.json"),
        "launch_report": _copy_evidence(launch_report_path, evidence_dir, "launch_report.json"),
        "customer_access_report": _copy_evidence(customer_access_report_path, evidence_dir, "customer_access_verification.json"),
    }
    deployment_pack = build_deployment_pack(out_dir / "deployment", release_label=release_label)
    release_audit = build_release_audit(
        readiness=readiness,
        due_diligence=due_diligence,
        live_readiness=live_readiness,
        launch=launch,
        customer_access=customer_access,
        schema_verification=schema_verification,
    )
    preflight = build_preflight_report(
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

    release_audit_path = out_dir / "release_audit.json"
    preflight_path = out_dir / "preflight_report.json"
    ops_dir = out_dir / "ops"
    generated = {
        "release_audit": str(release_audit_path),
        "preflight_report": str(preflight_path),
        "ops_status": str(ops_dir / "ops_status.json"),
        "status_page": str(ops_dir / "STATUS_PAGE.md"),
        "ops_runbook": str(ops_dir / "OPS_RUNBOOK.md"),
        "production_proof": str(out_dir / "production_proof.json"),
        "production_proof_markdown": str(out_dir / "PRODUCTION_PROOF.md"),
        "production_cutover_report": str(out_dir / "production_cutover" / "cutover_report.json"),
        "production_cutover_runbook": str(out_dir / "production_cutover" / "CUTOVER_RUNBOOK.md"),
        "deployment_manifest": deployment_pack["paths"]["deployment_manifest"],
        "deployment_runbook": deployment_pack["paths"]["deployment_runbook"],
        "sql_apply_plan": deployment_pack["paths"]["sql_apply_plan"],
        "sql_apply_runbook": deployment_pack["paths"]["sql_apply_runbook"],
        "apply_sql": deployment_pack["paths"]["apply_sql"],
        "post_apply_verification_sql": deployment_pack["paths"]["post_apply_verification_sql"],
        "market_readiness_scorecard": str(out_dir / "market_readiness" / "market_readiness_scorecard.json"),
        "market_readiness_markdown": str(out_dir / "market_readiness" / "MARKET_READINESS_SCORECARD.md"),
        "market_readiness_html": str(out_dir / "market_readiness" / "market-readiness.html"),
        "boardroom_data_room_index": str(out_dir / "market_readiness" / "BOARDROOM_DATA_ROOM_INDEX.md"),
        "market_readiness_actions": str(out_dir / "market_readiness" / "market_readiness_actions.csv"),
        "stakeholder_views": str(out_dir / "market_readiness" / "STAKEHOLDER_VIEWS.md"),
        "live_launch_control_room": str(out_dir / "market_readiness" / "live_launch_control_room.json"),
        "live_launch_control_room_markdown": str(out_dir / "market_readiness" / "LIVE_LAUNCH_CONTROL_ROOM.md"),
        "live_launch_action_board": str(out_dir / "market_readiness" / "LIVE_LAUNCH_ACTION_BOARD.csv"),
        "live_credential_handoff": str(out_dir / "market_readiness" / "live_credential_handoff.json"),
        "live_credential_handoff_markdown": str(out_dir / "market_readiness" / "LIVE_CREDENTIAL_HANDOFF.md"),
        "live_credential_handoff_checklist": str(out_dir / "market_readiness" / "LIVE_CREDENTIAL_HANDOFF_CHECKLIST.csv"),
        "live_secret_channel_contract": str(out_dir / "market_readiness" / "LIVE_SECRET_CHANNEL_CONTRACT.csv"),
        "live_proof_plan": str(out_dir / "market_readiness" / "live_proof_execution_plan.json"),
        "live_proof_plan_markdown": str(out_dir / "market_readiness" / "LIVE_PROOF_EXECUTION_PLAN.md"),
        "live_proof_evidence_map": str(out_dir / "market_readiness" / "LIVE_PROOF_EVIDENCE_MAP.csv"),
        "live_proof_commands": str(out_dir / "market_readiness" / "LIVE_PROOF_COMMANDS.sh"),
        "live_proof_acceptance": str(out_dir / "market_readiness" / "live_proof_acceptance_matrix.json"),
        "live_proof_acceptance_markdown": str(out_dir / "market_readiness" / "LIVE_PROOF_ACCEPTANCE_MATRIX.md"),
        "live_proof_acceptance_csv": str(out_dir / "market_readiness" / "LIVE_PROOF_ACCEPTANCE_MATRIX.csv"),
        "live_proof_evidence_vault": str(out_dir / "market_readiness" / "live_proof_evidence_vault.json"),
        "live_proof_evidence_vault_markdown": str(out_dir / "market_readiness" / "LIVE_PROOF_EVIDENCE_VAULT.md"),
        "live_proof_archive_index": str(out_dir / "market_readiness" / "LIVE_PROOF_ARCHIVE_INDEX.csv"),
        "market_ready_audit": str(out_dir / "market_readiness" / "market_ready_audit.json"),
        "market_ready_audit_markdown": str(out_dir / "market_readiness" / "MARKET_READY_GAP_AUDIT.md"),
        "market_ready_requirements": str(out_dir / "market_readiness" / "MARKET_READY_REQUIREMENTS.csv"),
        "daw_boardroom_demo_walkthrough": str(out_dir / "market_readiness" / "daw_boardroom_demo_walkthrough.json"),
        "daw_boardroom_demo_walkthrough_markdown": str(out_dir / "market_readiness" / "DAW_BOARDROOM_DEMO_WALKTHROUGH.md"),
        "daw_demo_checklist": str(out_dir / "market_readiness" / "DAW_DEMO_CHECKLIST.csv"),
        "daw_first_campaign_control_room": str(out_dir / "market_readiness" / "daw_first_campaign_control_room.json"),
        "daw_first_campaign_control_room_markdown": str(out_dir / "market_readiness" / "DAW_FIRST_CAMPAIGN_CONTROL_ROOM.md"),
        "daw_first_campaign_action_board": str(out_dir / "market_readiness" / "DAW_FIRST_CAMPAIGN_ACTION_BOARD.csv"),
        "customer_acceptance_plan": str(out_dir / "market_readiness" / "customer_acceptance_plan.json"),
        "customer_acceptance_plan_markdown": str(out_dir / "market_readiness" / "CUSTOMER_ACCEPTANCE_PLAN.md"),
        "acceptance_checklist": str(out_dir / "market_readiness" / "ACCEPTANCE_CHECKLIST.csv"),
        "customer_rollout_plan": str(out_dir / "market_readiness" / "customer_rollout_plan.json"),
        "customer_rollout_plan_markdown": str(out_dir / "market_readiness" / "CUSTOMER_ROLLOUT_PLAN.md"),
        "rollout_workstreams": str(out_dir / "market_readiness" / "ROLLOUT_WORKSTREAMS.csv"),
        "first_campaign_launch_intake": str(out_dir / "market_readiness" / "first_campaign_launch_intake.json"),
        "first_campaign_launch_intake_markdown": str(out_dir / "market_readiness" / "FIRST_CAMPAIGN_LAUNCH_INTAKE.md"),
        "first_campaign_launch_checklist": str(out_dir / "market_readiness" / "FIRST_CAMPAIGN_LAUNCH_CHECKLIST.csv"),
        "customer_input_templates": str(out_dir / "market_readiness" / "customer_input_templates.json"),
        "customer_input_templates_markdown": str(out_dir / "market_readiness" / "CUSTOMER_INPUT_TEMPLATES.md"),
        "partner_roster_template": str(out_dir / "market_readiness" / "PARTNER_ROSTER_TEMPLATE.csv"),
        "territory_assignment_template": str(out_dir / "market_readiness" / "TERRITORY_ASSIGNMENT_TEMPLATE.csv"),
        "property_source_template": str(out_dir / "market_readiness" / "PROPERTY_SOURCE_TEMPLATE.csv"),
        "suppression_list_template": str(out_dir / "market_readiness" / "SUPPRESSION_LIST_TEMPLATE.csv"),
        "message_approval_template": str(out_dir / "market_readiness" / "MESSAGE_APPROVAL_TEMPLATE.csv"),
        "partner_capacity_template": str(out_dir / "market_readiness" / "PARTNER_CAPACITY_TEMPLATE.csv"),
        "first_campaign_input_validation": str(out_dir / "market_readiness" / "first_campaign_input_validation.json"),
        "first_campaign_input_validation_markdown": str(out_dir / "market_readiness" / "FIRST_CAMPAIGN_INPUT_VALIDATION.md"),
        "first_campaign_input_issues": str(out_dir / "market_readiness" / "FIRST_CAMPAIGN_INPUT_ISSUES.csv"),
        "first_campaign_import_plan": str(out_dir / "market_readiness" / "first_campaign_import_plan.json"),
        "first_campaign_import_plan_markdown": str(out_dir / "market_readiness" / "FIRST_CAMPAIGN_IMPORT_PLAN.md"),
        "first_campaign_staging_rows": str(out_dir / "market_readiness" / "FIRST_CAMPAIGN_STAGING_ROWS.csv"),
        "first_wave_launch_gate": str(out_dir / "market_readiness" / "first_wave_launch_gate.json"),
        "first_wave_launch_gate_markdown": str(out_dir / "market_readiness" / "FIRST_WAVE_LAUNCH_GATE.md"),
        "first_wave_launch_gate_checklist": str(out_dir / "market_readiness" / "FIRST_WAVE_LAUNCH_GATE_CHECKLIST.csv"),
        "first_wave_database_handoff": str(out_dir / "market_readiness" / "first_wave_database_handoff.json"),
        "first_wave_database_handoff_markdown": str(out_dir / "market_readiness" / "FIRST_WAVE_DATABASE_HANDOFF.md"),
        "first_wave_database_handoff_checklist": str(out_dir / "market_readiness" / "FIRST_WAVE_DATABASE_HANDOFF_CHECKLIST.csv"),
        "first_wave_database_review_rows": str(out_dir / "market_readiness" / "FIRST_WAVE_DATABASE_REVIEW_ROWS.csv"),
        "first_wave_database_review_sql": str(out_dir / "market_readiness" / "FIRST_WAVE_DATABASE_REVIEW.sql"),
        "partner_auth_mapping": str(out_dir / "market_readiness" / "partner_auth_mapping.json"),
        "partner_auth_mapping_markdown": str(out_dir / "market_readiness" / "PARTNER_AUTH_MAPPING.md"),
        "partner_auth_mapping_template": str(out_dir / "market_readiness" / "PARTNER_AUTH_MAPPING_TEMPLATE.csv"),
        "partner_auth_mapping_rows": str(out_dir / "market_readiness" / "PARTNER_AUTH_MAPPING_ROWS.csv"),
        "partner_auth_mapping_issues": str(out_dir / "market_readiness" / "PARTNER_AUTH_MAPPING_ISSUES.csv"),
        "partner_membership_review_sql": str(out_dir / "market_readiness" / "PARTNER_MEMBERSHIP_REVIEW.sql"),
        "partner_access_reconciliation": str(out_dir / "market_readiness" / "partner_access_reconciliation.json"),
        "partner_access_reconciliation_markdown": str(out_dir / "market_readiness" / "PARTNER_ACCESS_RECONCILIATION.md"),
        "partner_access_reconciliation_matrix": str(out_dir / "market_readiness" / "PARTNER_ACCESS_RECONCILIATION_MATRIX.csv"),
        "partner_access_reconciliation_issues": str(out_dir / "market_readiness" / "PARTNER_ACCESS_RECONCILIATION_ISSUES.csv"),
        "example_completed_customer_inputs": str(out_dir / "market_readiness" / "example_completed_customer_inputs.json"),
        "example_completed_customer_inputs_markdown": str(out_dir / "market_readiness" / "EXAMPLE_COMPLETED_CUSTOMER_INPUTS.md"),
        "example_completed_partner_roster": str(out_dir / "market_readiness" / "example_completed_customer_inputs" / "PARTNER_ROSTER_TEMPLATE.csv"),
        "example_completed_territory_assignment": str(out_dir / "market_readiness" / "example_completed_customer_inputs" / "TERRITORY_ASSIGNMENT_TEMPLATE.csv"),
        "example_completed_property_source": str(out_dir / "market_readiness" / "example_completed_customer_inputs" / "PROPERTY_SOURCE_TEMPLATE.csv"),
        "example_completed_suppression_list": str(out_dir / "market_readiness" / "example_completed_customer_inputs" / "SUPPRESSION_LIST_TEMPLATE.csv"),
        "example_completed_message_approval": str(out_dir / "market_readiness" / "example_completed_customer_inputs" / "MESSAGE_APPROVAL_TEMPLATE.csv"),
        "example_completed_partner_capacity": str(out_dir / "market_readiness" / "example_completed_customer_inputs" / "PARTNER_CAPACITY_TEMPLATE.csv"),
        "example_first_campaign_input_validation": str(out_dir / "market_readiness" / "example_completed_customer_inputs" / "first_campaign_input_validation.json"),
        "example_first_campaign_input_validation_markdown": str(out_dir / "market_readiness" / "example_completed_customer_inputs" / "FIRST_CAMPAIGN_INPUT_VALIDATION.md"),
        "example_first_campaign_input_issues": str(out_dir / "market_readiness" / "example_completed_customer_inputs" / "FIRST_CAMPAIGN_INPUT_ISSUES.csv"),
        "example_first_campaign_import_plan": str(out_dir / "market_readiness" / "example_completed_customer_inputs" / "first_campaign_import_plan.json"),
        "example_first_campaign_import_plan_markdown": str(out_dir / "market_readiness" / "example_completed_customer_inputs" / "FIRST_CAMPAIGN_IMPORT_PLAN.md"),
        "example_first_campaign_staging_rows": str(out_dir / "market_readiness" / "example_completed_customer_inputs" / "FIRST_CAMPAIGN_STAGING_ROWS.csv"),
        "example_first_wave_launch_gate": str(out_dir / "market_readiness" / "example_completed_customer_inputs" / "first_wave_launch_gate.json"),
        "example_first_wave_launch_gate_markdown": str(out_dir / "market_readiness" / "example_completed_customer_inputs" / "FIRST_WAVE_LAUNCH_GATE.md"),
        "example_first_wave_launch_gate_checklist": str(out_dir / "market_readiness" / "example_completed_customer_inputs" / "FIRST_WAVE_LAUNCH_GATE_CHECKLIST.csv"),
        "procurement_review": str(out_dir / "market_readiness" / "procurement_security_review.json"),
        "procurement_review_markdown": str(out_dir / "market_readiness" / "PROCUREMENT_SECURITY_REVIEW.md"),
        "security_questionnaire": str(out_dir / "market_readiness" / "SECURITY_QUESTIONNAIRE.csv"),
        "procurement_risk_register": str(out_dir / "market_readiness" / "PROCUREMENT_RISK_REGISTER.csv"),
        "support_sla_plan": str(out_dir / "market_readiness" / "support_sla_plan.json"),
        "support_sla_plan_markdown": str(out_dir / "market_readiness" / "SUPPORT_SLA_PLAN.md"),
        "support_escalation_matrix": str(out_dir / "market_readiness" / "SUPPORT_ESCALATION_MATRIX.csv"),
        "incident_response_playbook": str(out_dir / "market_readiness" / "INCIDENT_RESPONSE_PLAYBOOK.md"),
        "customer_pilot_proposal": str(out_dir / "market_readiness" / "customer_pilot_proposal.json"),
        "customer_pilot_proposal_markdown": str(out_dir / "market_readiness" / "CUSTOMER_PILOT_PROPOSAL.md"),
        "pilot_scope_checklist": str(out_dir / "market_readiness" / "PILOT_SCOPE_CHECKLIST.csv"),
        "commercial_assumptions": str(out_dir / "market_readiness" / "COMMERCIAL_ASSUMPTIONS.csv"),
        "customer_training_plan": str(out_dir / "market_readiness" / "customer_training_plan.json"),
        "customer_training_guide": str(out_dir / "market_readiness" / "CUSTOMER_TRAINING_GUIDE.md"),
        "training_session_plan": str(out_dir / "market_readiness" / "TRAINING_SESSION_PLAN.csv"),
        "role_cheatsheet": str(out_dir / "market_readiness" / "ROLE_CHEATSHEET.csv"),
        "value_realization_plan": str(out_dir / "market_readiness" / "customer_value_realization_plan.json"),
        "value_realization_plan_markdown": str(out_dir / "market_readiness" / "CUSTOMER_VALUE_REALIZATION_PLAN.md"),
        "value_realization_metrics": str(out_dir / "market_readiness" / "VALUE_REALIZATION_METRICS.csv"),
        "executive_decision_log": str(out_dir / "market_readiness" / "EXECUTIVE_DECISION_LOG.csv"),
        "outcome_measurement_contract": str(out_dir / "market_readiness" / "outcome_measurement_contract.json"),
        "outcome_measurement_contract_markdown": str(out_dir / "market_readiness" / "OUTCOME_MEASUREMENT_CONTRACT.md"),
        "outcome_event_schema": str(out_dir / "market_readiness" / "OUTCOME_EVENT_SCHEMA.csv"),
        "outcome_sync_template": str(out_dir / "market_readiness" / "OUTCOME_SYNC_TEMPLATE.csv"),
        "outcome_reconciliation_checklist": str(out_dir / "market_readiness" / "OUTCOME_RECONCILIATION_CHECKLIST.csv"),
        "outcome_import_validation": str(out_dir / "market_readiness" / "outcome_import_validation.json"),
        "outcome_import_validation_markdown": str(out_dir / "market_readiness" / "OUTCOME_IMPORT_VALIDATION.md"),
        "outcome_import_issues": str(out_dir / "market_readiness" / "OUTCOME_IMPORT_ISSUES.csv"),
        "outcome_import_review_rows": str(out_dir / "market_readiness" / "OUTCOME_IMPORT_REVIEW_ROWS.csv"),
        "module_expansion_plan": str(out_dir / "market_readiness" / "customer_module_expansion_plan.json"),
        "module_expansion_plan_markdown": str(out_dir / "market_readiness" / "CUSTOMER_MODULE_EXPANSION_PLAN.md"),
        "module_value_matrix": str(out_dir / "market_readiness" / "MODULE_VALUE_MATRIX.csv"),
        "expansion_decision_tree": str(out_dir / "market_readiness" / "EXPANSION_DECISION_TREE.csv"),
        "module_readiness_matrix": str(out_dir / "market_readiness" / "module_readiness_matrix.json"),
        "module_readiness_matrix_markdown": str(out_dir / "market_readiness" / "MODULE_READINESS_MATRIX.md"),
        "module_readiness_matrix_csv": str(out_dir / "market_readiness" / "MODULE_READINESS_MATRIX.csv"),
        "module_metric_coverage": str(out_dir / "market_readiness" / "MODULE_METRIC_COVERAGE.csv"),
        "public_data_source_register": str(out_dir / "market_readiness" / "customer_public_data_source_register.json"),
        "public_data_source_register_markdown": str(out_dir / "market_readiness" / "PUBLIC_DATA_SOURCE_REGISTER.md"),
        "public_data_source_matrix": str(out_dir / "market_readiness" / "PUBLIC_DATA_SOURCE_MATRIX.csv"),
        "blocked_data_register": str(out_dir / "market_readiness" / "BLOCKED_DATA_REGISTER.csv"),
        "attribution_requirements": str(out_dir / "market_readiness" / "ATTRIBUTION_REQUIREMENTS.csv"),
        "public_data_production_intake": str(out_dir / "market_readiness" / "public_data_production_intake.json"),
        "public_data_production_intake_markdown": str(out_dir / "market_readiness" / "PUBLIC_DATA_PRODUCTION_INTAKE.md"),
        "public_data_approval_checklist": str(out_dir / "market_readiness" / "PUBLIC_DATA_APPROVAL_CHECKLIST.csv"),
        "public_data_reconciliation": str(out_dir / "market_readiness" / "public_data_reconciliation.json"),
        "public_data_reconciliation_markdown": str(out_dir / "market_readiness" / "PUBLIC_DATA_RECONCILIATION.md"),
        "public_data_reconciliation_matrix": str(out_dir / "market_readiness" / "PUBLIC_DATA_RECONCILIATION_MATRIX.csv"),
        "public_data_reconciliation_issues": str(out_dir / "market_readiness" / "PUBLIC_DATA_RECONCILIATION_ISSUES.csv"),
        "customer_signoff_reconciliation": str(out_dir / "market_readiness" / "customer_signoff_reconciliation.json"),
        "customer_signoff_reconciliation_markdown": str(out_dir / "market_readiness" / "CUSTOMER_SIGNOFF_RECONCILIATION.md"),
        "customer_signoff_reconciliation_matrix": str(out_dir / "market_readiness" / "CUSTOMER_SIGNOFF_RECONCILIATION_MATRIX.csv"),
        "customer_signoff_reconciliation_issues": str(out_dir / "market_readiness" / "CUSTOMER_SIGNOFF_RECONCILIATION_ISSUES.csv"),
        "customer_signoff_intake_markdown": str(out_dir / "market_readiness" / "CUSTOMER_SIGNOFF_INTAKE.md"),
        "customer_signoff_evidence_template": str(out_dir / "market_readiness" / "CUSTOMER_SIGNOFF_EVIDENCE_TEMPLATE.csv"),
        "customer_view_catalog": str(out_dir / "market_readiness" / "customer_view_catalog.json"),
        "customer_view_catalog_markdown": str(out_dir / "market_readiness" / "CUSTOMER_VIEW_CATALOG.md"),
        "customer_view_matrix": str(out_dir / "market_readiness" / "CUSTOMER_VIEW_MATRIX.csv"),
        "data_platform_blueprint": str(out_dir / "market_readiness" / "data_platform_blueprint.json"),
        "data_platform_blueprint_markdown": str(out_dir / "market_readiness" / "DATA_PLATFORM_BLUEPRINT.md"),
        "data_platform_scope_matrix": str(out_dir / "market_readiness" / "DATA_PLATFORM_SCOPE_MATRIX.csv"),
        "portable_data_room_html": str(out_dir / "market_readiness" / "portable_data_room" / "index.html"),
        "portable_data_room_manifest": str(out_dir / "market_readiness" / "portable_data_room" / "DATA_ROOM_MANIFEST.json"),
        "portable_data_room_zip": str(out_dir / "market_readiness" / "homepilot_boardroom_data_room.zip"),
        "artifact_index": str(out_dir / "artifact_index.json"),
        "release_notes": str(out_dir / "RELEASE_NOTES.md"),
        "handoff_checklist": str(out_dir / "HANDOFF_CHECKLIST.md"),
    }
    write_json(release_audit_path, release_audit)
    write_json(preflight_path, preflight)
    ops_status = build_ops_status(
        readiness=readiness,
        due_diligence=due_diligence,
        launch=launch,
        customer_access=customer_access,
        schema_verification=schema_verification,
        live_readiness=live_readiness,
        stage=stage,
        live=live,
        env=env,
        release_label=release_label,
        preflight_report=preflight,
        release_audit_report=release_audit,
    )
    write_ops_status_pack(ops_dir, ops_status)
    production_cutover = build_production_cutover(
        out_dir / "production_cutover",
        readiness_report_path=readiness_report_path,
        due_diligence_report_path=due_diligence_report_path,
        release_label=release_label,
        live=False,
        env=env,
    )

    artifact_index = _build_artifact_index(
        release_label=release_label,
        stage=stage,
        readiness_path=readiness_report_path,
        due_diligence_path=due_diligence_report_path,
        live_readiness_path=live_readiness_report_path,
        launch_path=launch_report_path,
        customer_access_path=customer_access_report_path,
        schema_verification_path=schema_verification_report_path,
        copied=copied,
        generated=generated,
        readiness=readiness,
        due_diligence=due_diligence,
        live_readiness=live_readiness,
        schema_verification=schema_verification,
        release_audit=release_audit,
        preflight=preflight,
        deployment_pack=deployment_pack,
    )
    write_json(out_dir / "artifact_index.json", artifact_index)
    write_text(out_dir / "RELEASE_NOTES.md", render_release_notes(artifact_index, release_audit))
    write_text(out_dir / "HANDOFF_CHECKLIST.md", render_handoff_checklist(artifact_index))
    production_proof = build_production_proof_pack(
        out_dir,
        readiness_report_path=readiness_report_path,
        due_diligence_report_path=due_diligence_report_path,
        live_readiness_report_path=live_readiness_report_path,
        schema_verification_report_path=schema_verification_report_path,
        launch_report_path=launch_report_path,
        customer_access_report_path=customer_access_report_path,
        release_audit_report_path=release_audit_path,
        preflight_report_path=preflight_path,
        ops_status_report_path=ops_dir / "ops_status.json",
        artifact_index_path=out_dir / "artifact_index.json",
        release_label=release_label,
    )
    live_launch_request_path = (
        Path(readiness["paths"]["live_launch_request_smoke"]) / "live_launch_request.json"
        if readiness and readiness.get("paths", {}).get("live_launch_request_smoke")
        else None
    )
    market_readiness = build_market_readiness_pack(
        out_dir / "market_readiness",
        readiness_report_path=readiness_report_path,
        due_diligence_report_path=due_diligence_report_path,
        artifact_index_path=out_dir / "artifact_index.json",
        production_proof_path=Path(production_proof["paths"]["production_proof"]),
        live_readiness_report_path=live_readiness_report_path,
        live_launch_request_path=live_launch_request_path,
        release_label=release_label,
    )

    return {
        "pack_type": "homepilot_release_evidence_bundle",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": artifact_index["status"],
        "stage_status": artifact_index["stage_status"],
        "decisions": artifact_index["decisions"],
        "blockers": artifact_index["blockers"],
        "paths": {
            "artifact_index": generated["artifact_index"],
            "release_audit": generated["release_audit"],
            "preflight_report": generated["preflight_report"],
            "ops_status": generated["ops_status"],
            "status_page": generated["status_page"],
            "ops_runbook": generated["ops_runbook"],
            "production_proof": production_proof["paths"]["production_proof"],
            "production_proof_markdown": production_proof["paths"]["production_proof_markdown"],
            "production_cutover_report": production_cutover["paths"]["cutover_report"],
            "production_cutover_runbook": production_cutover["paths"]["runbook"],
            "release_notes": generated["release_notes"],
            "handoff_checklist": generated["handoff_checklist"],
            "deployment_manifest": generated["deployment_manifest"],
            "deployment_runbook": generated["deployment_runbook"],
            "sql_apply_plan": generated["sql_apply_plan"],
            "sql_apply_runbook": generated["sql_apply_runbook"],
            "apply_sql": generated["apply_sql"],
            "post_apply_verification_sql": generated["post_apply_verification_sql"],
            "market_readiness_scorecard": market_readiness["paths"]["scorecard"],
            "market_readiness_markdown": market_readiness["paths"]["markdown"],
            "market_readiness_html": market_readiness["paths"]["html"],
            "boardroom_data_room_index": market_readiness["paths"]["data_room_index"],
            "market_readiness_actions": market_readiness["paths"]["actions_csv"],
            "stakeholder_views": market_readiness["paths"]["stakeholder_views"],
            "live_launch_control_room": market_readiness["paths"]["live_launch_control_room"],
            "live_launch_control_room_markdown": market_readiness["paths"]["live_launch_control_room_markdown"],
            "live_launch_action_board": market_readiness["paths"]["live_launch_action_board"],
            "live_credential_handoff": market_readiness["paths"]["live_credential_handoff"],
            "live_credential_handoff_markdown": market_readiness["paths"]["live_credential_handoff_markdown"],
            "live_credential_handoff_checklist": market_readiness["paths"]["live_credential_handoff_checklist"],
            "live_secret_channel_contract": market_readiness["paths"]["live_secret_channel_contract"],
            "live_proof_plan": market_readiness["paths"]["live_proof_plan"],
            "live_proof_plan_markdown": market_readiness["paths"]["live_proof_plan_markdown"],
            "live_proof_evidence_map": market_readiness["paths"]["live_proof_evidence_map"],
            "live_proof_commands": market_readiness["paths"]["live_proof_commands"],
            "live_proof_acceptance": market_readiness["paths"]["live_proof_acceptance"],
            "live_proof_acceptance_markdown": market_readiness["paths"]["live_proof_acceptance_markdown"],
            "live_proof_acceptance_csv": market_readiness["paths"]["live_proof_acceptance_csv"],
            "live_proof_evidence_vault": market_readiness["paths"]["live_proof_evidence_vault"],
            "live_proof_evidence_vault_markdown": market_readiness["paths"]["live_proof_evidence_vault_markdown"],
            "live_proof_archive_index": market_readiness["paths"]["live_proof_archive_index"],
            "market_ready_audit": market_readiness["paths"]["market_ready_audit"],
            "market_ready_audit_markdown": market_readiness["paths"]["market_ready_audit_markdown"],
            "market_ready_requirements": market_readiness["paths"]["market_ready_requirements"],
            "daw_boardroom_demo_walkthrough": market_readiness["paths"]["daw_boardroom_demo_walkthrough"],
            "daw_boardroom_demo_walkthrough_markdown": market_readiness["paths"]["daw_boardroom_demo_walkthrough_markdown"],
            "daw_demo_checklist": market_readiness["paths"]["daw_demo_checklist"],
            "daw_first_campaign_control_room": market_readiness["paths"]["daw_first_campaign_control_room"],
            "daw_first_campaign_control_room_markdown": market_readiness["paths"]["daw_first_campaign_control_room_markdown"],
            "daw_first_campaign_action_board": market_readiness["paths"]["daw_first_campaign_action_board"],
            "customer_acceptance_plan": market_readiness["paths"]["customer_acceptance_plan"],
            "customer_acceptance_plan_markdown": market_readiness["paths"]["customer_acceptance_plan_markdown"],
            "acceptance_checklist": market_readiness["paths"]["acceptance_checklist"],
            "customer_rollout_plan": market_readiness["paths"]["customer_rollout_plan"],
            "customer_rollout_plan_markdown": market_readiness["paths"]["customer_rollout_plan_markdown"],
            "rollout_workstreams": market_readiness["paths"]["rollout_workstreams"],
            "first_campaign_launch_intake": market_readiness["paths"]["first_campaign_launch_intake"],
            "first_campaign_launch_intake_markdown": market_readiness["paths"]["first_campaign_launch_intake_markdown"],
            "first_campaign_launch_checklist": market_readiness["paths"]["first_campaign_launch_checklist"],
            "customer_input_templates": market_readiness["paths"]["customer_input_templates"],
            "customer_input_templates_markdown": market_readiness["paths"]["customer_input_templates_markdown"],
            "partner_roster_template": market_readiness["paths"]["partner_roster_template"],
            "territory_assignment_template": market_readiness["paths"]["territory_assignment_template"],
            "property_source_template": market_readiness["paths"]["property_source_template"],
            "suppression_list_template": market_readiness["paths"]["suppression_list_template"],
            "message_approval_template": market_readiness["paths"]["message_approval_template"],
            "partner_capacity_template": market_readiness["paths"]["partner_capacity_template"],
            "first_campaign_input_validation": market_readiness["paths"]["first_campaign_input_validation"],
            "first_campaign_input_validation_markdown": market_readiness["paths"]["first_campaign_input_validation_markdown"],
            "first_campaign_input_issues": market_readiness["paths"]["first_campaign_input_issues"],
            "first_campaign_import_plan": market_readiness["paths"]["first_campaign_import_plan"],
            "first_campaign_import_plan_markdown": market_readiness["paths"]["first_campaign_import_plan_markdown"],
            "first_campaign_staging_rows": market_readiness["paths"]["first_campaign_staging_rows"],
            "first_wave_launch_gate": market_readiness["paths"]["first_wave_launch_gate"],
            "first_wave_launch_gate_markdown": market_readiness["paths"]["first_wave_launch_gate_markdown"],
            "first_wave_launch_gate_checklist": market_readiness["paths"]["first_wave_launch_gate_checklist"],
            "first_wave_database_handoff": market_readiness["paths"]["first_wave_database_handoff"],
            "first_wave_database_handoff_markdown": market_readiness["paths"]["first_wave_database_handoff_markdown"],
            "first_wave_database_handoff_checklist": market_readiness["paths"]["first_wave_database_handoff_checklist"],
            "first_wave_database_review_rows": market_readiness["paths"]["first_wave_database_review_rows"],
            "first_wave_database_review_sql": market_readiness["paths"]["first_wave_database_review_sql"],
            "partner_auth_mapping": market_readiness["paths"]["partner_auth_mapping"],
            "partner_auth_mapping_markdown": market_readiness["paths"]["partner_auth_mapping_markdown"],
            "partner_auth_mapping_template": market_readiness["paths"]["partner_auth_mapping_template"],
            "partner_auth_mapping_rows": market_readiness["paths"]["partner_auth_mapping_rows"],
            "partner_auth_mapping_issues": market_readiness["paths"]["partner_auth_mapping_issues"],
            "partner_membership_review_sql": market_readiness["paths"]["partner_membership_review_sql"],
            "partner_access_reconciliation": market_readiness["paths"]["partner_access_reconciliation"],
            "partner_access_reconciliation_markdown": market_readiness["paths"]["partner_access_reconciliation_markdown"],
            "partner_access_reconciliation_matrix": market_readiness["paths"]["partner_access_reconciliation_matrix"],
            "partner_access_reconciliation_issues": market_readiness["paths"]["partner_access_reconciliation_issues"],
            "example_completed_customer_inputs": market_readiness["paths"]["example_completed_customer_inputs"],
            "example_completed_customer_inputs_markdown": market_readiness["paths"]["example_completed_customer_inputs_markdown"],
            "example_completed_partner_roster": market_readiness["paths"]["example_completed_partner_roster"],
            "example_completed_territory_assignment": market_readiness["paths"]["example_completed_territory_assignment"],
            "example_completed_property_source": market_readiness["paths"]["example_completed_property_source"],
            "example_completed_suppression_list": market_readiness["paths"]["example_completed_suppression_list"],
            "example_completed_message_approval": market_readiness["paths"]["example_completed_message_approval"],
            "example_completed_partner_capacity": market_readiness["paths"]["example_completed_partner_capacity"],
            "example_first_campaign_input_validation": market_readiness["paths"]["example_first_campaign_input_validation"],
            "example_first_campaign_input_validation_markdown": market_readiness["paths"]["example_first_campaign_input_validation_markdown"],
            "example_first_campaign_input_issues": market_readiness["paths"]["example_first_campaign_input_issues"],
            "example_first_campaign_import_plan": market_readiness["paths"]["example_first_campaign_import_plan"],
            "example_first_campaign_import_plan_markdown": market_readiness["paths"]["example_first_campaign_import_plan_markdown"],
            "example_first_campaign_staging_rows": market_readiness["paths"]["example_first_campaign_staging_rows"],
            "example_first_wave_launch_gate": market_readiness["paths"]["example_first_wave_launch_gate"],
            "example_first_wave_launch_gate_markdown": market_readiness["paths"]["example_first_wave_launch_gate_markdown"],
            "example_first_wave_launch_gate_checklist": market_readiness["paths"]["example_first_wave_launch_gate_checklist"],
            "procurement_review": market_readiness["paths"]["procurement_review"],
            "procurement_review_markdown": market_readiness["paths"]["procurement_review_markdown"],
            "security_questionnaire": market_readiness["paths"]["security_questionnaire"],
            "procurement_risk_register": market_readiness["paths"]["procurement_risk_register"],
            "support_sla_plan": market_readiness["paths"]["support_sla_plan"],
            "support_sla_plan_markdown": market_readiness["paths"]["support_sla_plan_markdown"],
            "support_escalation_matrix": market_readiness["paths"]["support_escalation_matrix"],
            "incident_response_playbook": market_readiness["paths"]["incident_response_playbook"],
            "customer_pilot_proposal": market_readiness["paths"]["customer_pilot_proposal"],
            "customer_pilot_proposal_markdown": market_readiness["paths"]["customer_pilot_proposal_markdown"],
            "pilot_scope_checklist": market_readiness["paths"]["pilot_scope_checklist"],
            "commercial_assumptions": market_readiness["paths"]["commercial_assumptions"],
            "customer_training_plan": market_readiness["paths"]["customer_training_plan"],
            "customer_training_guide": market_readiness["paths"]["customer_training_guide"],
            "training_session_plan": market_readiness["paths"]["training_session_plan"],
            "role_cheatsheet": market_readiness["paths"]["role_cheatsheet"],
            "value_realization_plan": market_readiness["paths"]["value_realization_plan"],
            "value_realization_plan_markdown": market_readiness["paths"]["value_realization_plan_markdown"],
            "value_realization_metrics": market_readiness["paths"]["value_realization_metrics"],
            "executive_decision_log": market_readiness["paths"]["executive_decision_log"],
            "outcome_measurement_contract": market_readiness["paths"]["outcome_measurement_contract"],
            "outcome_measurement_contract_markdown": market_readiness["paths"]["outcome_measurement_contract_markdown"],
            "outcome_event_schema": market_readiness["paths"]["outcome_event_schema"],
            "outcome_sync_template": market_readiness["paths"]["outcome_sync_template"],
            "outcome_reconciliation_checklist": market_readiness["paths"]["outcome_reconciliation_checklist"],
            "outcome_import_validation": market_readiness["paths"]["outcome_import_validation"],
            "outcome_import_validation_markdown": market_readiness["paths"]["outcome_import_validation_markdown"],
            "outcome_import_issues": market_readiness["paths"]["outcome_import_issues"],
            "outcome_import_review_rows": market_readiness["paths"]["outcome_import_review_rows"],
            "module_expansion_plan": market_readiness["paths"]["module_expansion_plan"],
            "module_expansion_plan_markdown": market_readiness["paths"]["module_expansion_plan_markdown"],
            "module_value_matrix": market_readiness["paths"]["module_value_matrix"],
            "expansion_decision_tree": market_readiness["paths"]["expansion_decision_tree"],
            "module_readiness_matrix": market_readiness["paths"]["module_readiness_matrix"],
            "module_readiness_matrix_markdown": market_readiness["paths"]["module_readiness_matrix_markdown"],
            "module_readiness_matrix_csv": market_readiness["paths"]["module_readiness_matrix_csv"],
            "module_metric_coverage": market_readiness["paths"]["module_metric_coverage"],
            "public_data_source_register": market_readiness["paths"]["public_data_source_register"],
            "public_data_source_register_markdown": market_readiness["paths"]["public_data_source_register_markdown"],
            "public_data_source_matrix": market_readiness["paths"]["public_data_source_matrix"],
            "blocked_data_register": market_readiness["paths"]["blocked_data_register"],
            "attribution_requirements": market_readiness["paths"]["attribution_requirements"],
            "public_data_production_intake": market_readiness["paths"]["public_data_production_intake"],
            "public_data_production_intake_markdown": market_readiness["paths"]["public_data_production_intake_markdown"],
            "public_data_approval_checklist": market_readiness["paths"]["public_data_approval_checklist"],
            "public_data_reconciliation": market_readiness["paths"]["public_data_reconciliation"],
            "public_data_reconciliation_markdown": market_readiness["paths"]["public_data_reconciliation_markdown"],
            "public_data_reconciliation_matrix": market_readiness["paths"]["public_data_reconciliation_matrix"],
            "public_data_reconciliation_issues": market_readiness["paths"]["public_data_reconciliation_issues"],
            "customer_signoff_reconciliation": market_readiness["paths"]["customer_signoff_reconciliation"],
            "customer_signoff_reconciliation_markdown": market_readiness["paths"]["customer_signoff_reconciliation_markdown"],
            "customer_signoff_reconciliation_matrix": market_readiness["paths"]["customer_signoff_reconciliation_matrix"],
            "customer_signoff_reconciliation_issues": market_readiness["paths"]["customer_signoff_reconciliation_issues"],
            "customer_signoff_intake_markdown": market_readiness["paths"]["customer_signoff_intake_markdown"],
            "customer_signoff_evidence_template": market_readiness["paths"]["customer_signoff_evidence_template"],
            "customer_view_catalog": market_readiness["paths"]["customer_view_catalog"],
            "customer_view_catalog_markdown": market_readiness["paths"]["customer_view_catalog_markdown"],
            "customer_view_matrix": market_readiness["paths"]["customer_view_matrix"],
            "data_platform_blueprint": market_readiness["paths"]["data_platform_blueprint"],
            "data_platform_blueprint_markdown": market_readiness["paths"]["data_platform_blueprint_markdown"],
            "data_platform_scope_matrix": market_readiness["paths"]["data_platform_scope_matrix"],
            "portable_data_room_html": market_readiness["paths"]["portable_data_room_html"],
            "portable_data_room_manifest": market_readiness["paths"]["portable_data_room_manifest"],
            "portable_data_room_zip": market_readiness["paths"]["portable_data_room_zip"],
        },
        "artifact_index": artifact_index,
        "production_proof": production_proof,
        "production_cutover": production_cutover,
        "market_readiness": market_readiness,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot release evidence bundle")
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

    pack = build_release_evidence_bundle(
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
        "stage_status": pack["stage_status"],
        "decisions": pack["decisions"],
        "artifact_index": pack["paths"]["artifact_index"],
        "production_proof": pack["paths"]["production_proof"],
        "production_proof_markdown": pack["paths"]["production_proof_markdown"],
        "production_cutover_report": pack["paths"]["production_cutover_report"],
        "production_cutover_runbook": pack["paths"]["production_cutover_runbook"],
        "release_notes": pack["paths"]["release_notes"],
        "handoff_checklist": pack["paths"]["handoff_checklist"],
        "market_readiness_scorecard": pack["paths"]["market_readiness_scorecard"],
        "market_readiness_html": pack["paths"]["market_readiness_html"],
        "boardroom_data_room_index": pack["paths"]["boardroom_data_room_index"],
        "live_launch_control_room": pack["paths"]["live_launch_control_room"],
        "live_launch_control_room_markdown": pack["paths"]["live_launch_control_room_markdown"],
        "live_launch_action_board": pack["paths"]["live_launch_action_board"],
        "live_credential_handoff": pack["paths"]["live_credential_handoff"],
        "live_credential_handoff_markdown": pack["paths"]["live_credential_handoff_markdown"],
        "live_credential_handoff_checklist": pack["paths"]["live_credential_handoff_checklist"],
        "live_secret_channel_contract": pack["paths"]["live_secret_channel_contract"],
        "live_proof_plan": pack["paths"]["live_proof_plan"],
        "live_proof_plan_markdown": pack["paths"]["live_proof_plan_markdown"],
        "live_proof_evidence_map": pack["paths"]["live_proof_evidence_map"],
        "live_proof_commands": pack["paths"]["live_proof_commands"],
        "live_proof_evidence_vault": pack["paths"]["live_proof_evidence_vault"],
        "live_proof_evidence_vault_markdown": pack["paths"]["live_proof_evidence_vault_markdown"],
        "live_proof_archive_index": pack["paths"]["live_proof_archive_index"],
        "market_ready_audit": pack["paths"]["market_ready_audit"],
        "market_ready_audit_markdown": pack["paths"]["market_ready_audit_markdown"],
        "market_ready_requirements": pack["paths"]["market_ready_requirements"],
        "daw_boardroom_demo_walkthrough": pack["paths"]["daw_boardroom_demo_walkthrough"],
        "daw_boardroom_demo_walkthrough_markdown": pack["paths"]["daw_boardroom_demo_walkthrough_markdown"],
        "daw_demo_checklist": pack["paths"]["daw_demo_checklist"],
        "daw_first_campaign_control_room": pack["paths"]["daw_first_campaign_control_room"],
        "daw_first_campaign_control_room_markdown": pack["paths"]["daw_first_campaign_control_room_markdown"],
        "daw_first_campaign_action_board": pack["paths"]["daw_first_campaign_action_board"],
        "customer_acceptance_plan_markdown": pack["paths"]["customer_acceptance_plan_markdown"],
        "acceptance_checklist": pack["paths"]["acceptance_checklist"],
        "customer_rollout_plan_markdown": pack["paths"]["customer_rollout_plan_markdown"],
        "rollout_workstreams": pack["paths"]["rollout_workstreams"],
        "first_campaign_launch_intake": pack["paths"]["first_campaign_launch_intake"],
        "first_campaign_launch_intake_markdown": pack["paths"]["first_campaign_launch_intake_markdown"],
        "first_campaign_launch_checklist": pack["paths"]["first_campaign_launch_checklist"],
        "customer_input_templates": pack["paths"]["customer_input_templates"],
        "customer_input_templates_markdown": pack["paths"]["customer_input_templates_markdown"],
        "partner_roster_template": pack["paths"]["partner_roster_template"],
        "territory_assignment_template": pack["paths"]["territory_assignment_template"],
        "property_source_template": pack["paths"]["property_source_template"],
        "suppression_list_template": pack["paths"]["suppression_list_template"],
        "message_approval_template": pack["paths"]["message_approval_template"],
        "partner_capacity_template": pack["paths"]["partner_capacity_template"],
        "first_campaign_input_validation": pack["paths"]["first_campaign_input_validation"],
        "first_campaign_input_validation_markdown": pack["paths"]["first_campaign_input_validation_markdown"],
        "first_campaign_input_issues": pack["paths"]["first_campaign_input_issues"],
        "first_campaign_import_plan": pack["paths"]["first_campaign_import_plan"],
        "first_campaign_import_plan_markdown": pack["paths"]["first_campaign_import_plan_markdown"],
        "first_campaign_staging_rows": pack["paths"]["first_campaign_staging_rows"],
        "first_wave_launch_gate": pack["paths"]["first_wave_launch_gate"],
        "first_wave_launch_gate_markdown": pack["paths"]["first_wave_launch_gate_markdown"],
        "first_wave_launch_gate_checklist": pack["paths"]["first_wave_launch_gate_checklist"],
        "first_wave_database_handoff": pack["paths"]["first_wave_database_handoff"],
        "first_wave_database_handoff_markdown": pack["paths"]["first_wave_database_handoff_markdown"],
        "first_wave_database_handoff_checklist": pack["paths"]["first_wave_database_handoff_checklist"],
        "first_wave_database_review_rows": pack["paths"]["first_wave_database_review_rows"],
        "first_wave_database_review_sql": pack["paths"]["first_wave_database_review_sql"],
        "partner_auth_mapping": pack["paths"]["partner_auth_mapping"],
        "partner_auth_mapping_markdown": pack["paths"]["partner_auth_mapping_markdown"],
        "partner_auth_mapping_template": pack["paths"]["partner_auth_mapping_template"],
        "partner_auth_mapping_rows": pack["paths"]["partner_auth_mapping_rows"],
        "partner_auth_mapping_issues": pack["paths"]["partner_auth_mapping_issues"],
        "partner_membership_review_sql": pack["paths"]["partner_membership_review_sql"],
        "partner_access_reconciliation": pack["paths"]["partner_access_reconciliation"],
        "partner_access_reconciliation_markdown": pack["paths"]["partner_access_reconciliation_markdown"],
        "partner_access_reconciliation_matrix": pack["paths"]["partner_access_reconciliation_matrix"],
        "partner_access_reconciliation_issues": pack["paths"]["partner_access_reconciliation_issues"],
        "example_completed_customer_inputs": pack["paths"]["example_completed_customer_inputs"],
        "example_completed_customer_inputs_markdown": pack["paths"]["example_completed_customer_inputs_markdown"],
        "example_completed_partner_roster": pack["paths"]["example_completed_partner_roster"],
        "example_completed_territory_assignment": pack["paths"]["example_completed_territory_assignment"],
        "example_completed_property_source": pack["paths"]["example_completed_property_source"],
        "example_completed_suppression_list": pack["paths"]["example_completed_suppression_list"],
        "example_completed_message_approval": pack["paths"]["example_completed_message_approval"],
        "example_completed_partner_capacity": pack["paths"]["example_completed_partner_capacity"],
        "example_first_campaign_input_validation": pack["paths"]["example_first_campaign_input_validation"],
        "example_first_campaign_input_validation_markdown": pack["paths"]["example_first_campaign_input_validation_markdown"],
        "example_first_campaign_input_issues": pack["paths"]["example_first_campaign_input_issues"],
        "example_first_campaign_import_plan": pack["paths"]["example_first_campaign_import_plan"],
        "example_first_campaign_import_plan_markdown": pack["paths"]["example_first_campaign_import_plan_markdown"],
        "example_first_campaign_staging_rows": pack["paths"]["example_first_campaign_staging_rows"],
        "example_first_wave_launch_gate": pack["paths"]["example_first_wave_launch_gate"],
        "example_first_wave_launch_gate_markdown": pack["paths"]["example_first_wave_launch_gate_markdown"],
        "example_first_wave_launch_gate_checklist": pack["paths"]["example_first_wave_launch_gate_checklist"],
        "procurement_review_markdown": pack["paths"]["procurement_review_markdown"],
        "security_questionnaire": pack["paths"]["security_questionnaire"],
        "procurement_risk_register": pack["paths"]["procurement_risk_register"],
        "support_sla_plan_markdown": pack["paths"]["support_sla_plan_markdown"],
        "support_escalation_matrix": pack["paths"]["support_escalation_matrix"],
        "incident_response_playbook": pack["paths"]["incident_response_playbook"],
        "customer_pilot_proposal_markdown": pack["paths"]["customer_pilot_proposal_markdown"],
        "pilot_scope_checklist": pack["paths"]["pilot_scope_checklist"],
        "commercial_assumptions": pack["paths"]["commercial_assumptions"],
        "customer_training_guide": pack["paths"]["customer_training_guide"],
        "training_session_plan": pack["paths"]["training_session_plan"],
        "role_cheatsheet": pack["paths"]["role_cheatsheet"],
        "value_realization_plan_markdown": pack["paths"]["value_realization_plan_markdown"],
        "value_realization_metrics": pack["paths"]["value_realization_metrics"],
        "executive_decision_log": pack["paths"]["executive_decision_log"],
        "outcome_measurement_contract": pack["paths"]["outcome_measurement_contract"],
        "outcome_measurement_contract_markdown": pack["paths"]["outcome_measurement_contract_markdown"],
        "outcome_event_schema": pack["paths"]["outcome_event_schema"],
        "outcome_sync_template": pack["paths"]["outcome_sync_template"],
        "outcome_reconciliation_checklist": pack["paths"]["outcome_reconciliation_checklist"],
        "outcome_import_validation": pack["paths"]["outcome_import_validation"],
        "outcome_import_validation_markdown": pack["paths"]["outcome_import_validation_markdown"],
        "outcome_import_issues": pack["paths"]["outcome_import_issues"],
        "outcome_import_review_rows": pack["paths"]["outcome_import_review_rows"],
        "module_expansion_plan_markdown": pack["paths"]["module_expansion_plan_markdown"],
        "module_value_matrix": pack["paths"]["module_value_matrix"],
        "expansion_decision_tree": pack["paths"]["expansion_decision_tree"],
        "module_readiness_matrix": pack["paths"]["module_readiness_matrix"],
        "module_readiness_matrix_markdown": pack["paths"]["module_readiness_matrix_markdown"],
        "module_readiness_matrix_csv": pack["paths"]["module_readiness_matrix_csv"],
        "module_metric_coverage": pack["paths"]["module_metric_coverage"],
        "public_data_source_register_markdown": pack["paths"]["public_data_source_register_markdown"],
        "public_data_source_matrix": pack["paths"]["public_data_source_matrix"],
        "blocked_data_register": pack["paths"]["blocked_data_register"],
        "attribution_requirements": pack["paths"]["attribution_requirements"],
        "public_data_production_intake": pack["paths"]["public_data_production_intake"],
        "public_data_production_intake_markdown": pack["paths"]["public_data_production_intake_markdown"],
        "public_data_approval_checklist": pack["paths"]["public_data_approval_checklist"],
        "public_data_reconciliation": pack["paths"]["public_data_reconciliation"],
        "public_data_reconciliation_markdown": pack["paths"]["public_data_reconciliation_markdown"],
        "public_data_reconciliation_matrix": pack["paths"]["public_data_reconciliation_matrix"],
        "public_data_reconciliation_issues": pack["paths"]["public_data_reconciliation_issues"],
        "customer_signoff_reconciliation": pack["paths"]["customer_signoff_reconciliation"],
        "customer_signoff_reconciliation_markdown": pack["paths"]["customer_signoff_reconciliation_markdown"],
        "customer_signoff_reconciliation_matrix": pack["paths"]["customer_signoff_reconciliation_matrix"],
        "customer_signoff_reconciliation_issues": pack["paths"]["customer_signoff_reconciliation_issues"],
        "customer_signoff_intake_markdown": pack["paths"]["customer_signoff_intake_markdown"],
        "customer_signoff_evidence_template": pack["paths"]["customer_signoff_evidence_template"],
        "portable_data_room_html": pack["paths"]["portable_data_room_html"],
        "portable_data_room_zip": pack["paths"]["portable_data_room_zip"],
    }, indent=2, ensure_ascii=False))
    if pack["stage_status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
