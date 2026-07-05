#!/usr/bin/env python3
"""
Reconcile customer decisions, commercial signoff, and launch proof.

This pack is intentionally non-mutating. It does not approve a campaign, write
Supabase rows, create users, send outreach, or turn buyer-review material into
customer approval. It answers one narrow question: which customer decisions are
review-ready, which are actually signed/approved, and which blockers remain
before first-wave launch or production rollout?
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
    re.compile(r"service[-_ ]?role", re.IGNORECASE),
    re.compile(r"authorization:\s*bearer", re.IGNORECASE),
    re.compile(r"secret-token", re.IGNORECASE),
    re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE),
)

SIGNED_STATUSES = {
    "accepted",
    "approved",
    "customer_accepted",
    "customer_approved",
    "customer_signed_off",
    "signed",
    "pass",
}
READY_STATUSES = {
    "buyer_review_ready",
    "buyer_review_support_ready",
    "buyer_review_proposal_ready",
    "buyer_review_value_ready",
    "ready_for_customer_review",
    "ready_for_review",
    "ready_for_live_import_review",
}
MANUAL_SIGNOFF_DECISIONS = {
    "buyer_review_acceptance",
    "first_wave_go_no_go",
    "commercial_pilot_terms",
    "support_sla_ack",
    "value_metric_baseline",
}
SIGNOFF_TEMPLATE_FIELDS = [
    "decision_key",
    "decision_area",
    "required_stage",
    "owner",
    "requested_signoff_status",
    "signoff_reference",
    "signer_role",
    "signed_at",
    "evidence_channel_ref",
    "notes",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_signoff_evidence(path: Path | None) -> list[dict[str, Any]] | None:
    if path is None or not path.exists():
        return None
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        rows = data.get("signoff_rows") if isinstance(data, dict) else None
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return _text(value).lower().replace("-", "_").replace(" ", "_")


def _has_reference(value: Any) -> bool:
    text = _text(value)
    return bool(text) and "customer_to_confirm" not in text.lower() and text.lower() not in {"none", "n/a", "todo"}


def _signed_status(value: Any) -> bool:
    return _norm(value) in SIGNED_STATUSES


def _status_value(source: dict[str, Any] | None) -> str:
    return _norm((source or {}).get("status"))


def _signed(source: dict[str, Any] | None, *, extra_statuses: set[str] | None = None) -> bool:
    if not source:
        return False
    statuses = set(SIGNED_STATUSES)
    if extra_statuses:
        statuses.update(extra_statuses)
    if _status_value(source) in statuses:
        return True
    for key in ("signoff_reference", "approval_reference", "customer_approval_reference", "signed_reference"):
        if _has_reference(source.get(key)):
            return True
    return False


def _ready_for_review(source: dict[str, Any] | None, *, extra_statuses: set[str] | None = None) -> bool:
    if not source:
        return False
    statuses = set(READY_STATUSES)
    if extra_statuses:
        statuses.update(extra_statuses)
    return _status_value(source) in statuses


def _validation_ready(input_validation: dict[str, Any] | None) -> bool:
    summary = (input_validation or {}).get("summary") or {}
    return (
        _status_value(input_validation) in {"pass", "ready", "ready_for_first_wave_review"}
        and int(summary.get("blockers") or 0) == 0
    )


def _import_ready(import_plan: dict[str, Any] | None) -> bool:
    summary = (import_plan or {}).get("summary") or {}
    return (
        _status_value(import_plan) in {"ready_for_live_import_review", "ready_for_first_wave_review", "pass", "ready"}
        and int(summary.get("campaign_records") or 0) > 0
        and not summary.get("raw_contact_values_written")
        and not summary.get("secret_values_written")
    )


def _first_wave_authorized(first_wave_launch_gate: dict[str, Any] | None) -> bool:
    return bool((first_wave_launch_gate or {}).get("launch_authorized"))


def _customer_go_no_go_ready(first_wave_launch_gate: dict[str, Any] | None) -> bool:
    summary = (first_wave_launch_gate or {}).get("summary")
    if isinstance(summary, dict):
        return bool(summary.get("customer_go_no_go_ready"))
    gates = (first_wave_launch_gate or {}).get("gates")
    if isinstance(gates, list):
        return any(
            isinstance(gate, dict)
            and gate.get("key") == "customer_go_no_go"
            and _norm(gate.get("status")) == "pass"
            for gate in gates
        )
    return False


def _live_proof_ready(first_wave_launch_gate: dict[str, Any] | None, production_proof: dict[str, Any] | None) -> bool:
    summary = (first_wave_launch_gate or {}).get("summary")
    if isinstance(summary, dict) and summary.get("live_proof_ready") is True:
        return True
    return _production_verified(production_proof)


def _production_verified(production_proof: dict[str, Any] | None) -> bool:
    if not production_proof:
        return False
    if production_proof.get("production_verified") is True:
        return True
    return bool((production_proof.get("production_gate") or {}).get("verified"))


def _partner_access_ready(partner_access_reconciliation: dict[str, Any] | None) -> bool:
    summary = (partner_access_reconciliation or {}).get("summary") or {}
    return (
        (partner_access_reconciliation or {}).get("status") == "partner_access_reconciled"
        and (partner_access_reconciliation or {}).get("production_ready") is True
        and int(summary.get("blockers") or 0) == 0
    )


def _public_data_ready(public_data_reconciliation: dict[str, Any] | None) -> bool:
    summary = (public_data_reconciliation or {}).get("summary") or {}
    return (
        (public_data_reconciliation or {}).get("status") == "public_data_reconciled_for_production_import"
        and (public_data_reconciliation or {}).get("production_import_ready") is True
        and int(summary.get("blockers") or 0) == 0
    )


def _public_data_blocks_live(public_data_reconciliation: dict[str, Any] | None) -> bool:
    if not public_data_reconciliation or _public_data_ready(public_data_reconciliation):
        return False
    summary = public_data_reconciliation.get("summary") or {}
    return bool(summary.get("first_wave_public_data_required") and int(summary.get("first_wave_blocks") or 0) > 0)


def _add_issue(
    issues: list[dict[str, Any]],
    severity: str,
    issue_key: str,
    decision_key: str,
    evidence: str,
    detail: str,
    next_action: str,
    *,
    blocks_live_launch: bool,
    blocks_production: bool,
) -> None:
    issues.append({
        "severity": severity,
        "issue_key": issue_key,
        "decision_key": decision_key,
        "evidence": evidence,
        "detail": detail,
        "next_action": next_action,
        "blocks_live_launch": blocks_live_launch,
        "blocks_production": blocks_production,
    })


def _decision_row(
    rows: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    *,
    decision_key: str,
    decision_area: str,
    required_stage: str,
    owner: str,
    evidence: str,
    source_status: str,
    signed: bool,
    ready: bool,
    blocks_live_launch: bool,
    blocks_production: bool,
    issue_key: str,
    detail: str,
    next_action: str,
) -> None:
    if signed:
        signoff_status = "signed_or_approved"
        current_status = "pass"
    elif ready:
        signoff_status = "ready_for_customer_decision"
        current_status = "ready_for_review_not_signed"
    else:
        signoff_status = "missing_or_blocked"
        current_status = source_status or "missing"

    rows.append({
        "decision_key": decision_key,
        "decision_area": decision_area,
        "required_stage": required_stage,
        "owner": owner,
        "current_status": current_status,
        "source_status": source_status,
        "signoff_status": signoff_status,
        "evidence": evidence,
        "blocks_live_launch": blocks_live_launch,
        "blocks_production": blocks_production,
        "next_action": "Archive the signed approval reference." if signed else next_action,
    })

    if not signed and (blocks_live_launch or blocks_production):
        _add_issue(
            issues,
            "blocker",
            issue_key,
            decision_key,
            evidence,
            detail,
            next_action,
            blocks_live_launch=blocks_live_launch,
            blocks_production=blocks_production,
        )


def _matrix_and_issues(
    *,
    customer_acceptance_plan: dict[str, Any] | None,
    first_campaign_input_validation: dict[str, Any] | None,
    first_campaign_import_plan: dict[str, Any] | None,
    first_wave_launch_gate: dict[str, Any] | None,
    customer_pilot_proposal: dict[str, Any] | None,
    support_sla_plan: dict[str, Any] | None,
    value_realization_plan: dict[str, Any] | None,
    partner_access_reconciliation: dict[str, Any] | None,
    public_data_reconciliation: dict[str, Any] | None,
    production_proof: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    validation_ready = _validation_ready(first_campaign_input_validation)
    import_ready = _import_ready(first_campaign_import_plan)
    first_wave_authorized = _first_wave_authorized(first_wave_launch_gate)
    customer_go_ready = _customer_go_no_go_ready(first_wave_launch_gate)
    live_proof_ready = _live_proof_ready(first_wave_launch_gate, production_proof)
    partner_access_ready = _partner_access_ready(partner_access_reconciliation)
    public_data_ready = _public_data_ready(public_data_reconciliation)
    public_data_blocks_live = _public_data_blocks_live(public_data_reconciliation)

    _decision_row(
        rows,
        issues,
        decision_key="buyer_review_acceptance",
        decision_area="Buyer-review evidence accepted",
        required_stage="buyer_review",
        owner="Executive sponsor + customer success",
        evidence="CUSTOMER_ACCEPTANCE_PLAN.md; ACCEPTANCE_CHECKLIST.csv",
        source_status=(customer_acceptance_plan or {}).get("status") or "missing",
        signed=_signed(customer_acceptance_plan),
        ready=_ready_for_review(customer_acceptance_plan),
        blocks_live_launch=False,
        blocks_production=not _signed(customer_acceptance_plan),
        issue_key="buyer_review_acceptance_not_signed",
        detail="Buyer-review evidence is reviewable, but no customer acceptance/signature is archived.",
        next_action="Ask the executive sponsor to approve the buyer-review package or archive a signed acceptance reference.",
    )
    _decision_row(
        rows,
        issues,
        decision_key="customer_inputs_approved",
        decision_area="Customer first-campaign inputs complete",
        required_stage="first_wave_launch",
        owner="DAW campaign owner + legal/privacy owner",
        evidence="FIRST_CAMPAIGN_INPUT_VALIDATION.md; FIRST_CAMPAIGN_INPUT_ISSUES.csv",
        source_status=(first_campaign_input_validation or {}).get("status") or "missing",
        signed=validation_ready,
        ready=validation_ready,
        blocks_live_launch=not validation_ready,
        blocks_production=not validation_ready,
        issue_key="customer_inputs_not_ready",
        detail="Customer input validation has blockers or is missing.",
        next_action="Complete partner roster, territory, source, suppression, message approval, and capacity files before first-wave approval.",
    )
    _decision_row(
        rows,
        issues,
        decision_key="staging_import_review",
        decision_area="First-campaign staging/import review",
        required_stage="first_wave_launch",
        owner="Customer IT + HomePilot operator",
        evidence="FIRST_CAMPAIGN_IMPORT_PLAN.md; FIRST_CAMPAIGN_STAGING_ROWS.csv",
        source_status=(first_campaign_import_plan or {}).get("status") or "missing",
        signed=import_ready,
        ready=import_ready,
        blocks_live_launch=not import_ready,
        blocks_production=not import_ready,
        issue_key="staging_import_review_not_ready",
        detail="First-campaign import plan is not ready for live import review.",
        next_action="Fix customer-input blockers, review staging rows, and rerun the import plan.",
    )
    _decision_row(
        rows,
        issues,
        decision_key="first_wave_go_no_go",
        decision_area="Explicit first-wave go/no-go",
        required_stage="first_wave_launch",
        owner="Executive sponsor + campaign owner",
        evidence="FIRST_WAVE_LAUNCH_GATE.md; FIRST_WAVE_LAUNCH_GATE_CHECKLIST.csv",
        source_status=(first_wave_launch_gate or {}).get("launch_decision") or (first_wave_launch_gate or {}).get("status") or "missing",
        signed=first_wave_authorized,
        ready=customer_go_ready,
        blocks_live_launch=not first_wave_authorized,
        blocks_production=not first_wave_authorized,
        issue_key="first_wave_go_no_go_missing",
        detail="First-wave launch is not authorized.",
        next_action="Resolve gate blockers and archive explicit customer go/no-go before outreach or partner access.",
    )
    _decision_row(
        rows,
        issues,
        decision_key="live_proof_archived",
        decision_area="Live schema/RLS/customer-access proof archived",
        required_stage="live_launch",
        owner="Customer IT + HomePilot operator",
        evidence="schema_verification.json; launch_report.json; customer_access_verification.json; PRODUCTION_PROOF.md",
        source_status="production_verified" if _production_verified(production_proof) else "live_proof_missing",
        signed=live_proof_ready,
        ready=live_proof_ready,
        blocks_live_launch=not live_proof_ready,
        blocks_production=not live_proof_ready,
        issue_key="live_proof_missing",
        detail="Live schema, RLS, and customer-access proof is not archived with production_verified=true.",
        next_action="Run live schema verification, live RLS launch probe, and customer-access verification; archive production proof.",
    )
    _decision_row(
        rows,
        issues,
        decision_key="partner_access_signoff",
        decision_area="Partner Auth and assigned-record access reconciled",
        required_stage="production_rollout",
        owner="Customer IT + customer success",
        evidence="PARTNER_ACCESS_RECONCILIATION.md; PARTNER_ACCESS_RECONCILIATION_MATRIX.csv",
        source_status=(partner_access_reconciliation or {}).get("status") or "missing",
        signed=partner_access_ready,
        ready=partner_access_ready,
        blocks_live_launch=False,
        blocks_production=not partner_access_ready,
        issue_key="partner_access_not_reconciled",
        detail="Partner Auth, membership rows, and customer-access verification are not fully reconciled.",
        next_action="Map every approved partner Auth user and prove assigned-record-only access before partner portal rollout.",
    )
    _decision_row(
        rows,
        issues,
        decision_key="public_data_import_signoff",
        decision_area="Public-data import approvals reconciled",
        required_stage="production_rollout",
        owner="Legal/privacy owner + data engineering owner",
        evidence="PUBLIC_DATA_RECONCILIATION.md; PUBLIC_DATA_RECONCILIATION_MATRIX.csv",
        source_status=(public_data_reconciliation or {}).get("status") or "missing",
        signed=public_data_ready,
        ready=public_data_ready,
        blocks_live_launch=public_data_blocks_live,
        blocks_production=not public_data_ready,
        issue_key="public_data_import_not_reconciled",
        detail="Public-data dataset approvals, field allowlists, attribution, or live proof are not fully reconciled.",
        next_action="Approve exact public datasets and archive live proof before production public-data import.",
    )
    _decision_row(
        rows,
        issues,
        decision_key="commercial_pilot_terms",
        decision_area="Commercial pilot scope and assumptions signed",
        required_stage="pilot_kickoff",
        owner="Executive sponsor + procurement + sales",
        evidence="CUSTOMER_PILOT_PROPOSAL.md; PILOT_SCOPE_CHECKLIST.csv; COMMERCIAL_ASSUMPTIONS.csv",
        source_status=(customer_pilot_proposal or {}).get("status") or "missing",
        signed=_signed(customer_pilot_proposal, extra_statuses={"pilot_terms_signed", "commercial_terms_signed"}),
        ready=_ready_for_review(customer_pilot_proposal),
        blocks_live_launch=False,
        blocks_production=not _signed(customer_pilot_proposal, extra_statuses={"pilot_terms_signed", "commercial_terms_signed"}),
        issue_key="commercial_pilot_terms_not_signed",
        detail="Pilot scope, pricing assumptions, and commercial terms are not signed.",
        next_action="Convert the buyer-review pilot proposal into agreed commercial terms or archive customer approval.",
    )
    _decision_row(
        rows,
        issues,
        decision_key="support_sla_ack",
        decision_area="Support/SLA operating model acknowledged",
        required_stage="pilot_kickoff",
        owner="Customer success + support owner + procurement",
        evidence="SUPPORT_SLA_PLAN.md; SUPPORT_ESCALATION_MATRIX.csv; INCIDENT_RESPONSE_PLAYBOOK.md",
        source_status=(support_sla_plan or {}).get("status") or "missing",
        signed=_signed(support_sla_plan, extra_statuses={"support_sla_signed", "customer_acknowledged"}),
        ready=_ready_for_review(support_sla_plan),
        blocks_live_launch=False,
        blocks_production=not _signed(support_sla_plan, extra_statuses={"support_sla_signed", "customer_acknowledged"}),
        issue_key="support_sla_not_acknowledged",
        detail="Support model, escalation owners, and incident response expectations are not customer-acknowledged.",
        next_action="Review the support SLA pack with the customer and archive acknowledgement.",
    )
    _decision_row(
        rows,
        issues,
        decision_key="value_metric_baseline",
        decision_area="Value metric baseline and denominators accepted",
        required_stage="pilot_kickoff",
        owner="Executive sponsor + analyst + customer success",
        evidence="CUSTOMER_VALUE_REALIZATION_PLAN.md; VALUE_REALIZATION_METRICS.csv; EXECUTIVE_DECISION_LOG.csv",
        source_status=(value_realization_plan or {}).get("status") or "missing",
        signed=_signed(value_realization_plan, extra_statuses={"value_baseline_accepted", "metrics_accepted"}),
        ready=_ready_for_review(value_realization_plan),
        blocks_live_launch=False,
        blocks_production=not _signed(value_realization_plan, extra_statuses={"value_baseline_accepted", "metrics_accepted"}),
        issue_key="value_metric_baseline_not_accepted",
        detail="The customer has not accepted KPI denominators, tenant-private value metrics, and scale decision gates.",
        next_action="Agree metric denominators and customer-private value assumptions before production scale decisions.",
    )
    return rows, issues


def _evidence_rows(customer_signoff_evidence: list[dict[str, Any]] | dict[str, Any] | None) -> list[dict[str, Any]]:
    if not customer_signoff_evidence:
        return []
    if isinstance(customer_signoff_evidence, list):
        return [row for row in customer_signoff_evidence if isinstance(row, dict)]
    rows = customer_signoff_evidence.get("signoff_rows") if isinstance(customer_signoff_evidence, dict) else None
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _apply_customer_signoff_evidence(
    matrix: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    customer_signoff_evidence: list[dict[str, Any]] | dict[str, Any] | None,
) -> list[dict[str, Any]]:
    decision_rows = {row["decision_key"]: row for row in matrix}
    evidence_report: list[dict[str, Any]] = []
    for raw_row in _evidence_rows(customer_signoff_evidence):
        decision_key = _norm(raw_row.get("decision_key"))
        signoff_status = _norm(raw_row.get("signoff_status") or raw_row.get("approval_status") or raw_row.get("requested_signoff_status"))
        signoff_reference = _text(raw_row.get("signoff_reference") or raw_row.get("approval_reference") or raw_row.get("signed_reference"))
        signer_role = _text(raw_row.get("signer_role") or raw_row.get("owner") or "customer_to_confirm")
        signed_at = _text(raw_row.get("signed_at"))
        evidence_channel_ref = _text(raw_row.get("evidence_channel_ref"))
        applied = False
        issue_key = ""
        detail = ""

        if decision_key not in decision_rows:
            issue_key = "signoff_evidence_unknown_decision"
            detail = "Signoff evidence references a decision_key that is not part of the reconciliation matrix."
            _add_issue(
                issues,
                "warning",
                issue_key,
                decision_key,
                "CUSTOMER_SIGNOFF_EVIDENCE_TEMPLATE.csv",
                detail,
                "Remove the unknown decision_key or add it to the controlled signoff decision catalog.",
                blocks_live_launch=False,
                blocks_production=False,
            )
        elif decision_key not in MANUAL_SIGNOFF_DECISIONS:
            issue_key = "technical_proof_cannot_be_overridden_by_signoff"
            detail = "This decision requires source-proof reconciliation and cannot be satisfied by customer signoff evidence alone."
            _add_issue(
                issues,
                "warning",
                issue_key,
                decision_key,
                decision_rows[decision_key]["evidence"],
                detail,
                "Provide the underlying technical/source proof artifact instead of trying to override it with customer signoff evidence.",
                blocks_live_launch=False,
                blocks_production=False,
            )
        elif not _signed_status(signoff_status):
            issue_key = "signoff_status_not_approved"
            detail = f"Signoff status is {signoff_status or 'missing'}, not approved/signed."
        elif not _has_reference(signoff_reference):
            issue_key = "signoff_reference_missing"
            detail = "Signoff evidence is marked approved/signed but has no safe approval reference."
            target = decision_rows[decision_key]
            _add_issue(
                issues,
                "blocker",
                issue_key,
                decision_key,
                target["evidence"],
                detail,
                "Add a non-secret signed approval reference such as signed://customer/decision-id before treating this decision as approved.",
                blocks_live_launch=bool(target.get("blocks_live_launch")),
                blocks_production=bool(target.get("blocks_production")),
            )
        else:
            target = decision_rows[decision_key]
            target["current_status"] = "pass"
            target["source_status"] = f"customer_signoff_evidence:{signoff_status}"
            target["signoff_status"] = "signed_or_approved"
            target["customer_signoff_reference"] = signoff_reference
            target["customer_signoff_role"] = signer_role
            target["customer_signoff_signed_at"] = signed_at
            target["customer_signoff_evidence_channel_ref"] = evidence_channel_ref
            target["blocks_live_launch"] = False
            target["blocks_production"] = False
            target["next_action"] = "Keep the signed approval reference with launch evidence."
            issues[:] = [issue for issue in issues if issue.get("decision_key") != decision_key]
            applied = True

        evidence_report.append({
            "decision_key": decision_key,
            "signoff_status": signoff_status,
            "signoff_reference": signoff_reference,
            "signer_role": signer_role,
            "signed_at": signed_at,
            "evidence_channel_ref": evidence_channel_ref,
            "applied": applied,
            "issue_key": issue_key,
            "detail": detail,
        })
    return evidence_report


def _summary(
    matrix: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    first_wave_launch_gate: dict[str, Any] | None,
    production_proof: dict[str, Any] | None,
    signoff_evidence_report: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    blockers = [issue for issue in issues if issue.get("severity") == "blocker"]
    signed_count = len([row for row in matrix if row["signoff_status"] == "signed_or_approved"])
    ready_for_review = len([row for row in matrix if row["signoff_status"] == "ready_for_customer_decision"])
    live_blockers = len([issue for issue in blockers if issue.get("blocks_live_launch")])
    production_blockers = len([issue for issue in blockers if issue.get("blocks_production")])
    signoff_evidence_report = signoff_evidence_report or []
    return {
        "decision_count": len(matrix),
        "signed_decision_count": signed_count,
        "ready_for_review_count": ready_for_review,
        "missing_or_blocked_count": len(matrix) - signed_count - ready_for_review,
        "blockers": len(blockers),
        "live_launch_blockers": live_blockers,
        "production_blockers": production_blockers,
        "first_wave_launch_authorized": _first_wave_authorized(first_wave_launch_gate),
        "customer_go_no_go_ready": _customer_go_no_go_ready(first_wave_launch_gate),
        "live_proof_ready": _live_proof_ready(first_wave_launch_gate, production_proof),
        "production_verified": _production_verified(production_proof),
        "all_decisions_signed": signed_count == len(matrix) and bool(matrix),
        "signoff_evidence_rows_loaded": len(signoff_evidence_report),
        "signoff_evidence_rows_applied": len([row for row in signoff_evidence_report if row.get("applied")]),
        "signoff_evidence_rows_rejected": len([row for row in signoff_evidence_report if row.get("issue_key")]),
    }


def _status(summary: dict[str, Any]) -> str:
    if summary["all_decisions_signed"] and summary["blockers"] == 0:
        return "customer_signoff_reconciled"
    if summary["live_launch_blockers"] > 0:
        return "blocked_until_customer_signoff_and_live_proof"
    if summary["production_blockers"] > 0:
        return "blocked_until_customer_signoff"
    return "blocked_until_customer_signoff_reconciliation"


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# HomePilot Customer Signoff Reconciliation",
        "",
        f"Release: {report['release_label']}",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        f"Live launch ready: {str(report['live_launch_ready']).lower()}",
        f"Production signoff ready: {str(report['production_signoff_ready']).lower()}",
        "",
        "This pack separates buyer-review material from actual customer decisions. It is non-mutating: it does not write to Supabase, authorize outreach, create partner access, or approve commercial terms.",
        "",
        "## Summary",
        "",
        f"- Decisions tracked: {summary['decision_count']}",
        f"- Signed/approved: {summary['signed_decision_count']}",
        f"- Ready for customer decision: {summary['ready_for_review_count']}",
        f"- Missing or blocked: {summary['missing_or_blocked_count']}",
        f"- Live-launch blockers: {summary['live_launch_blockers']}",
        f"- Production blockers: {summary['production_blockers']}",
        f"- First-wave launch authorized: {str(summary['first_wave_launch_authorized']).lower()}",
        f"- Live proof ready: {str(summary['live_proof_ready']).lower()}",
        f"- Signoff evidence rows loaded: {summary['signoff_evidence_rows_loaded']}",
        f"- Signoff evidence rows applied: {summary['signoff_evidence_rows_applied']}",
        "",
        "## Decision Matrix",
        "",
        "| Decision | Stage | Signoff | Blocks live | Blocks production | Evidence |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["decision_matrix"]:
        lines.append(
            f"| {row['decision_area']} | {row['required_stage']} | {row['signoff_status']} | {str(row['blocks_live_launch']).lower()} | {str(row['blocks_production']).lower()} | {row['evidence']} |"
        )
    lines += ["", "## Issues", ""]
    if report["issues"]:
        for issue in report["issues"]:
            lines.append(f"- {issue['severity']}: {issue['issue_key']} ({issue['decision_key']}) - {issue['next_action']}")
    else:
        lines.append("- No customer signoff reconciliation issues detected.")
    lines += ["", "## Guardrails", ""]
    for key, value in report["guardrails"].items():
        value = "yes" if value is True else "no" if value is False else value
        lines.append(f"- {key}: {value}")
    lines.append("")
    return "\n".join(lines)


def _signoff_template_rows(matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in matrix:
        decision_key = row["decision_key"]
        rows.append({
            "decision_key": decision_key,
            "decision_area": row["decision_area"],
            "required_stage": row["required_stage"],
            "owner": row["owner"],
            "requested_signoff_status": "customer_to_confirm" if decision_key in MANUAL_SIGNOFF_DECISIONS else "technical_proof_required",
            "signoff_reference": "customer_to_confirm",
            "signer_role": row["owner"],
            "signed_at": "customer_to_confirm",
            "evidence_channel_ref": "customer_to_confirm",
            "notes": "Do not add secret values, personal contact details, or raw signatures to this file.",
        })
    return rows


def render_intake_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Customer Signoff Intake",
        "",
        f"Release: {report['release_label']}",
        "",
        "Use `CUSTOMER_SIGNOFF_EVIDENCE_TEMPLATE.csv` to record safe approval references for the controlled decision keys. This intake file is evidence metadata only: keep raw signatures, emails, personal contact data, and secret values in the approved customer system or secure channel.",
        "",
        "## How To Fill",
        "",
        "- Keep `decision_key` unchanged.",
        "- Use `approved`, `signed`, or `accepted` only when the customer decision is actually approved.",
        "- Put a safe reference in `signoff_reference`, for example `signed://daw/first-wave-go-no-go` or a customer document ID.",
        "- Do not use this template to override technical proof. Live schema/RLS/customer-access proof, partner-access reconciliation, and public-data reconciliation must pass through their own evidence reports.",
        "",
        "## Controlled Decisions",
        "",
        "| Decision | Stage | Manual signoff allowed |",
        "| --- | --- | --- |",
    ]
    for row in report["decision_matrix"]:
        lines.append(
            f"| {row['decision_key']} | {row['required_stage']} | {str(row['decision_key'] in MANUAL_SIGNOFF_DECISIONS).lower()} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _secret_scan(report: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(report, ensure_ascii=False)
    findings = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(body)]
    return {
        "status": "pass" if not findings else "fail",
        "issue_count": len(findings),
        "patterns": findings,
    }


def build_customer_signoff_reconciliation_pack(
    out_dir: Path,
    *,
    customer_acceptance_plan: dict[str, Any] | None,
    first_campaign_input_validation: dict[str, Any] | None,
    first_campaign_import_plan: dict[str, Any] | None,
    first_wave_launch_gate: dict[str, Any] | None,
    customer_pilot_proposal: dict[str, Any] | None,
    support_sla_plan: dict[str, Any] | None,
    value_realization_plan: dict[str, Any] | None = None,
    partner_access_reconciliation: dict[str, Any] | None = None,
    public_data_reconciliation: dict[str, Any] | None = None,
    production_proof: dict[str, Any] | None = None,
    customer_signoff_evidence: list[dict[str, Any]] | dict[str, Any] | None = None,
    release_label: str = "local",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    matrix, issues = _matrix_and_issues(
        customer_acceptance_plan=customer_acceptance_plan,
        first_campaign_input_validation=first_campaign_input_validation,
        first_campaign_import_plan=first_campaign_import_plan,
        first_wave_launch_gate=first_wave_launch_gate,
        customer_pilot_proposal=customer_pilot_proposal,
        support_sla_plan=support_sla_plan,
        value_realization_plan=value_realization_plan,
        partner_access_reconciliation=partner_access_reconciliation,
        public_data_reconciliation=public_data_reconciliation,
        production_proof=production_proof,
    )
    signoff_evidence_report = _apply_customer_signoff_evidence(matrix, issues, customer_signoff_evidence)
    summary = _summary(matrix, issues, first_wave_launch_gate, production_proof, signoff_evidence_report)
    status = _status(summary)
    report = {
        "reconciliation_type": "homepilot_customer_signoff_reconciliation",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": status,
        "live_launch_ready": summary["live_launch_blockers"] == 0,
        "production_signoff_ready": status == "customer_signoff_reconciled",
        "summary": summary,
        "decision_matrix": matrix,
        "signoff_evidence": signoff_evidence_report,
        "issues": issues,
        "source_contract": {
            "customer_acceptance_plan": "buyer-review acceptance criteria and optional signoff reference",
            "first_campaign_input_validation": "customer input completeness and blockers",
            "first_campaign_import_plan": "non-mutating import/staging review readiness",
            "first_wave_launch_gate": "explicit customer go/no-go plus live proof gates",
            "customer_pilot_proposal": "pilot scope and commercial assumptions",
            "support_sla_plan": "support tiers, escalation, and incident-response acknowledgement",
            "partner_access_reconciliation": "producer-network partner access proof",
            "public_data_reconciliation": "public-data approval/import proof",
            "customer_signoff_evidence": "optional CSV/JSON rows with safe customer approval references for controlled manual decision keys",
        },
        "guardrails": {
            "non_mutating_pack": True,
            "no_database_writes": True,
            "no_supabase_writes": True,
            "no_outreach_authorized": not summary["first_wave_launch_authorized"],
            "no_partner_portal_access_authorized": not summary["production_verified"],
            "no_public_data_import_authorized": True,
            "no_secret_values_written": True,
            "no_raw_contact_values_written": True,
            "buyer_review_material_is_not_customer_approval": True,
            "synthetic_examples_are_not_customer_approval": True,
            "technical_proof_cannot_be_overridden_by_customer_signoff": True,
            "production_requires_live_proof": True,
        },
        "paths": {
            "customer_signoff_reconciliation": str(out_dir / "customer_signoff_reconciliation.json"),
            "customer_signoff_reconciliation_markdown": str(out_dir / "CUSTOMER_SIGNOFF_RECONCILIATION.md"),
            "customer_signoff_reconciliation_matrix": str(out_dir / "CUSTOMER_SIGNOFF_RECONCILIATION_MATRIX.csv"),
            "customer_signoff_reconciliation_issues": str(out_dir / "CUSTOMER_SIGNOFF_RECONCILIATION_ISSUES.csv"),
            "customer_signoff_intake_markdown": str(out_dir / "CUSTOMER_SIGNOFF_INTAKE.md"),
            "customer_signoff_evidence_template": str(out_dir / "CUSTOMER_SIGNOFF_EVIDENCE_TEMPLATE.csv"),
        },
    }
    report["secret_scan"] = _secret_scan(report)
    if report["secret_scan"]["status"] != "pass":
        report["status"] = "fail_secret_scan"
        report["live_launch_ready"] = False
        report["production_signoff_ready"] = False
    write_json(out_dir / "customer_signoff_reconciliation.json", report)
    write_text(out_dir / "CUSTOMER_SIGNOFF_RECONCILIATION.md", render_markdown(report))
    write_text(out_dir / "CUSTOMER_SIGNOFF_INTAKE.md", render_intake_markdown(report))
    write_csv(out_dir / "CUSTOMER_SIGNOFF_RECONCILIATION_MATRIX.csv", matrix, [
        "decision_key",
        "decision_area",
        "required_stage",
        "owner",
        "current_status",
        "source_status",
        "signoff_status",
        "evidence",
        "blocks_live_launch",
        "blocks_production",
        "next_action",
        "customer_signoff_reference",
        "customer_signoff_role",
        "customer_signoff_signed_at",
        "customer_signoff_evidence_channel_ref",
    ])
    write_csv(out_dir / "CUSTOMER_SIGNOFF_RECONCILIATION_ISSUES.csv", issues, [
        "severity",
        "issue_key",
        "decision_key",
        "evidence",
        "detail",
        "next_action",
        "blocks_live_launch",
        "blocks_production",
    ])
    write_csv(out_dir / "CUSTOMER_SIGNOFF_EVIDENCE_TEMPLATE.csv", _signoff_template_rows(matrix), SIGNOFF_TEMPLATE_FIELDS)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HomePilot customer signoff reconciliation evidence")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--customer-acceptance-plan", type=Path)
    parser.add_argument("--first-campaign-input-validation", type=Path)
    parser.add_argument("--first-campaign-import-plan", type=Path)
    parser.add_argument("--first-wave-launch-gate", type=Path)
    parser.add_argument("--customer-pilot-proposal", type=Path)
    parser.add_argument("--support-sla-plan", type=Path)
    parser.add_argument("--value-realization-plan", type=Path)
    parser.add_argument("--partner-access-reconciliation", type=Path)
    parser.add_argument("--public-data-reconciliation", type=Path)
    parser.add_argument("--production-proof", type=Path)
    parser.add_argument("--customer-signoff-evidence", type=Path)
    parser.add_argument("--release-label", default="local")
    args = parser.parse_args()
    report = build_customer_signoff_reconciliation_pack(
        args.out_dir,
        customer_acceptance_plan=load_json(args.customer_acceptance_plan),
        first_campaign_input_validation=load_json(args.first_campaign_input_validation),
        first_campaign_import_plan=load_json(args.first_campaign_import_plan),
        first_wave_launch_gate=load_json(args.first_wave_launch_gate),
        customer_pilot_proposal=load_json(args.customer_pilot_proposal),
        support_sla_plan=load_json(args.support_sla_plan),
        value_realization_plan=load_json(args.value_realization_plan),
        partner_access_reconciliation=load_json(args.partner_access_reconciliation),
        public_data_reconciliation=load_json(args.public_data_reconciliation),
        production_proof=load_json(args.production_proof),
        customer_signoff_evidence=load_signoff_evidence(args.customer_signoff_evidence),
        release_label=args.release_label,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": report["status"],
        "live_launch_ready": report["live_launch_ready"],
        "production_signoff_ready": report["production_signoff_ready"],
        "decisions": report["summary"]["decision_count"],
        "signed_decisions": report["summary"]["signed_decision_count"],
        "signoff_evidence_rows_loaded": report["summary"]["signoff_evidence_rows_loaded"],
        "signoff_evidence_rows_applied": report["summary"]["signoff_evidence_rows_applied"],
        "live_launch_blockers": report["summary"]["live_launch_blockers"],
        "production_blockers": report["summary"]["production_blockers"],
        "paths": report["paths"],
    }, indent=2, ensure_ascii=False))
    if report["secret_scan"]["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
