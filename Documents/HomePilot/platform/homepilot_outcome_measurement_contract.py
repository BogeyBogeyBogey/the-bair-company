#!/usr/bin/env python3
"""
Build the HomePilot outcome measurement contract.

This is the closed-loop measurement layer for enterprise campaigns. It defines
which post-campaign outcomes may be imported or synced back from customer-
approved systems, how denominators stay explicit, and which live gates remain
blocked before any production outcome sync. It never writes to Supabase, CRMs,
mail systems, or partner portals.
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
    re.compile(r"(?:api[_-]?key|service[_-]?role|password|token|secret)\s*[:=]\s*['\"][^'\"\n]{12,}['\"]", re.IGNORECASE),
)


EVENT_SCHEMA_FIELDS = [
    "field",
    "required",
    "type",
    "grain",
    "allowed_values",
    "description",
    "safe_handling",
]

OUTCOME_TEMPLATE_FIELDS = [
    "tenant_id",
    "module_key",
    "partner_id",
    "campaign_id",
    "property_id",
    "outcome_event_id",
    "outcome_stage",
    "event_at",
    "source_system",
    "source_record_ref",
    "amount_ex_vat",
    "currency",
    "loss_reason",
    "evidence_reference",
    "customer_approval_reference",
]

CHECKLIST_FIELDS = [
    "gate",
    "owner",
    "status",
    "required_evidence",
    "pass_condition",
    "blocker",
    "safe_handling",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _production_verified(production_proof: dict[str, Any] | None, market_readiness: dict[str, Any] | None) -> bool:
    gate = (production_proof or {}).get("production_gate") or {}
    summary = (market_readiness or {}).get("summary") or {}
    return bool(gate.get("verified") or summary.get("production_verified") is True)


def _decisions(market_readiness: dict[str, Any] | None) -> dict[str, Any]:
    return (market_readiness or {}).get("decisions") or {}


def _value_plan_status(market_readiness: dict[str, Any] | None) -> str:
    value_plan = (market_readiness or {}).get("value_realization_plan") or {}
    return str(value_plan.get("status") or "missing")


def _schema_rows() -> list[dict[str, Any]]:
    return [
        {
            "field": "tenant_id",
            "required": "yes",
            "type": "text/uuid",
            "grain": "all outcome events",
            "allowed_values": "active tenant only",
            "description": "Customer account boundary for the outcome event.",
            "safe_handling": "Required on every row; never mix tenants in one import.",
        },
        {
            "field": "module_key",
            "required": "yes",
            "type": "text",
            "grain": "all outcome events",
            "allowed_values": "facadepilot; windowpilot; roofpilot; gardenpilot; poolpilot; porchpilot; drivewaypilot",
            "description": "Pilot module that generated the opportunity or campaign target.",
            "safe_handling": "Must match tenant entitlements before import.",
        },
        {
            "field": "partner_id",
            "required": "conditional",
            "type": "text",
            "grain": "producer-network outcome events",
            "allowed_values": "approved partner ids",
            "description": "Renovator scope for DAW-style producer networks.",
            "safe_handling": "Partner views may only receive assigned partner rows.",
        },
        {
            "field": "campaign_id",
            "required": "yes",
            "type": "text/uuid",
            "grain": "campaign outcome event",
            "allowed_values": "approved campaign ids",
            "description": "Campaign or wave that created the measurable outcome.",
            "safe_handling": "Use campaign id rather than free-form campaign names.",
        },
        {
            "field": "property_id",
            "required": "yes",
            "type": "text/uuid",
            "grain": "property outcome event",
            "allowed_values": "tenant-scoped HomePilot property ids",
            "description": "Property spine key used to reconcile outcomes to campaign targets.",
            "safe_handling": "Do not include raw contact details in outcome rows.",
        },
        {
            "field": "outcome_event_id",
            "required": "yes",
            "type": "text",
            "grain": "one outcome event",
            "allowed_values": "stable source-system idempotency key",
            "description": "Idempotency key for importing or syncing outcome events.",
            "safe_handling": "Upsert by this key; never duplicate outcome events.",
        },
        {
            "field": "outcome_stage",
            "required": "yes",
            "type": "enum",
            "grain": "one outcome event",
            "allowed_values": "appointment_booked; appointment_completed; no_show; quote_requested; quote_sent; quote_accepted; won_project; lost_project; not_qualified",
            "description": "Commercial outcome stage from a customer-approved system.",
            "safe_handling": "Only explicit customer/partner evidence may move an opportunity into outcome stages.",
        },
        {
            "field": "event_at",
            "required": "yes",
            "type": "timestamp",
            "grain": "one outcome event",
            "allowed_values": "ISO 8601 UTC timestamp",
            "description": "Time of the outcome event.",
            "safe_handling": "Store UTC; present in tenant locale.",
        },
        {
            "field": "source_system",
            "required": "yes",
            "type": "text",
            "grain": "one outcome event",
            "allowed_values": "customer_crm; partner_crm; approved_sheet; manual_customer_signoff",
            "description": "Approved source that supplied the outcome.",
            "safe_handling": "Source must be approved before production sync.",
        },
        {
            "field": "source_record_ref",
            "required": "yes",
            "type": "text",
            "grain": "one outcome event",
            "allowed_values": "redacted external record reference",
            "description": "Reference to the source-system record without exposing private notes.",
            "safe_handling": "Reference only; no free-form private notes or contact details.",
        },
        {
            "field": "amount_ex_vat",
            "required": "conditional",
            "type": "decimal",
            "grain": "quote or won-project outcome",
            "allowed_values": "non-negative amount",
            "description": "Quote or won project value when customer-approved.",
            "safe_handling": "Tenant-private commercial metric; not benchmark-visible by default.",
        },
        {
            "field": "currency",
            "required": "conditional",
            "type": "text",
            "grain": "quote or won-project outcome",
            "allowed_values": "EUR",
            "description": "Currency for the commercial amount.",
            "safe_handling": "Do not mix currencies in one executive metric without conversion rules.",
        },
        {
            "field": "loss_reason",
            "required": "conditional",
            "type": "enum/text",
            "grain": "lost_project or not_qualified outcome",
            "allowed_values": "price; timing; not_owner; already_renovated; partner_capacity; no_budget; other_reviewed",
            "description": "Reviewed reason for lost or disqualified outcomes.",
            "safe_handling": "No insulting or sensitive free-form notes.",
        },
        {
            "field": "evidence_reference",
            "required": "yes",
            "type": "text",
            "grain": "one outcome event",
            "allowed_values": "signed://, crm://, sheet://, ticket:// reference",
            "description": "Pointer to customer-approved evidence.",
            "safe_handling": "Pointer only; store underlying documents in customer-approved systems.",
        },
        {
            "field": "customer_approval_reference",
            "required": "yes",
            "type": "text",
            "grain": "batch or event",
            "allowed_values": "signed decision or approved sync reference",
            "description": "Customer approval that permits outcome import or sync.",
            "safe_handling": "Approval reference cannot override failed RLS/customer-access proof.",
        },
    ]


def _template_rows() -> list[dict[str, Any]]:
    return [
        {
            "tenant_id": "daw-belgium",
            "module_key": "facadepilot",
            "partner_id": "daw-partner-01",
            "campaign_id": "campaign-placeholder",
            "property_id": "property-placeholder",
            "outcome_event_id": "outcome-placeholder-001",
            "outcome_stage": "appointment_booked",
            "event_at": "2026-07-15T10:00:00Z",
            "source_system": "customer_crm",
            "source_record_ref": "crm://redacted/opportunity/001",
            "amount_ex_vat": "",
            "currency": "EUR",
            "loss_reason": "",
            "evidence_reference": "crm://redacted/appointment/001",
            "customer_approval_reference": "signed://customer/outcome-sync-approval",
        },
        {
            "tenant_id": "daw-belgium",
            "module_key": "facadepilot",
            "partner_id": "daw-partner-01",
            "campaign_id": "campaign-placeholder",
            "property_id": "property-placeholder",
            "outcome_event_id": "outcome-placeholder-002",
            "outcome_stage": "quote_sent",
            "event_at": "2026-07-22T14:30:00Z",
            "source_system": "partner_crm",
            "source_record_ref": "crm://redacted/quote/002",
            "amount_ex_vat": "8500",
            "currency": "EUR",
            "loss_reason": "",
            "evidence_reference": "crm://redacted/quote/002",
            "customer_approval_reference": "signed://customer/outcome-sync-approval",
        },
    ]


def _checklist_rows(production_verified: bool, live_launch_go: bool) -> list[dict[str, Any]]:
    live_status = "pass" if production_verified else "blocked"
    launch_status = "pass" if live_launch_go else "blocked"
    return [
        {
            "gate": "metric_definitions_approved",
            "owner": "Executive sponsor + analyst",
            "status": "review_ready",
            "required_evidence": "VALUE_REALIZATION_METRICS.csv; OUTCOME_EVENT_SCHEMA.csv",
            "pass_condition": "Customer accepts contacted denominator, appointment definition, quote/won/lost definitions, and tenant-private value handling.",
            "blocker": "",
            "safe_handling": "Metric definitions are review evidence, not live outcome proof.",
        },
        {
            "gate": "source_system_approved",
            "owner": "DAW/partner CRM owner + security owner",
            "status": "blocked",
            "required_evidence": "approved CRM/sheet source; customer_approval_reference",
            "pass_condition": "Every source_system is approved and has a field owner.",
            "blocker": "Customer-approved outcome source is not yet supplied.",
            "safe_handling": "No API keys, raw contact details, or private notes in HomePilot artifacts.",
        },
        {
            "gate": "live_access_proven",
            "owner": "IT owner + HomePilot operator",
            "status": live_status,
            "required_evidence": "PRODUCTION_PROOF.md; schema_verification.json; customer_access_verification.json",
            "pass_condition": "production_verified=true for live schema, RLS, and customer access.",
            "blocker": "" if production_verified else "Live schema/RLS/customer-access proof is still missing.",
            "safe_handling": "Outcome sync cannot start before live proof passes.",
        },
        {
            "gate": "first_wave_authorized",
            "owner": "DAW executive sponsor + campaign owner",
            "status": launch_status,
            "required_evidence": "FIRST_WAVE_LAUNCH_GATE.md; customer go/no-go reference",
            "pass_condition": "launch_authorized=true after source, suppression, message, capacity, live proof, and customer signoff pass.",
            "blocker": "" if live_launch_go else "First wave is not authorized.",
            "safe_handling": "No outreach or partner access can be inferred from this contract.",
        },
        {
            "gate": "outcome_import_dry_run",
            "owner": "HomePilot operator + analyst",
            "status": "review_ready",
            "required_evidence": "OUTCOME_SYNC_TEMPLATE.csv; outcome validation report",
            "pass_condition": "Template rows validate for tenant/module/partner keys, outcome stages, idempotency, and no raw contact leakage.",
            "blocker": "",
            "safe_handling": "Dry-run only until source approval and live proof pass.",
        },
    ]


def _metric_rows() -> list[dict[str, Any]]:
    return [
        {
            "metric": "Appointment completion rate",
            "denominator": "appointment_booked_count",
            "numerator": "appointment_completed_count",
            "grain": "campaign/module/partner",
            "source": "outcome events from customer-approved system",
            "guardrail": "Booked appointment and completed appointment are separate outcomes.",
        },
        {
            "metric": "Quote rate",
            "denominator": "appointment_completed_count or response_count, as agreed",
            "numerator": "quote_sent_count",
            "grain": "campaign/module/partner",
            "source": "outcome events",
            "guardrail": "State the denominator beside every rate.",
        },
        {
            "metric": "Win rate",
            "denominator": "quote_sent_count",
            "numerator": "won_project_count",
            "grain": "campaign/module/partner",
            "source": "customer/partner CRM outcome events",
            "guardrail": "Won status requires customer-approved evidence.",
        },
        {
            "metric": "Won project value",
            "denominator": "not applicable",
            "numerator": "sum amount_ex_vat for won_project",
            "grain": "tenant/module/campaign or partner",
            "source": "customer-approved commercial outcome events",
            "guardrail": "Tenant-private; not benchmark-visible by default.",
        },
        {
            "metric": "Loss reason mix",
            "denominator": "lost_project_count + not_qualified_count",
            "numerator": "count by loss_reason",
            "grain": "campaign/module/partner",
            "source": "reviewed outcome events",
            "guardrail": "No sensitive free-form private notes.",
        },
    ]


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


def build_outcome_measurement_contract(
    *,
    market_readiness: dict[str, Any] | None = None,
    production_proof: dict[str, Any] | None = None,
    release_label: str = "local",
) -> dict[str, Any]:
    decisions = _decisions(market_readiness)
    production_verified = _production_verified(production_proof, market_readiness)
    live_launch_go = decisions.get("live_launch") == "go"
    event_schema = _schema_rows()
    outcome_metrics = _metric_rows()
    checklist = _checklist_rows(production_verified=production_verified, live_launch_go=live_launch_go)
    blocked_count = len([row for row in checklist if row["status"] == "blocked"])
    allowed_outcome_stages = [
        "appointment_booked",
        "appointment_completed",
        "no_show",
        "quote_requested",
        "quote_sent",
        "quote_accepted",
        "won_project",
        "lost_project",
        "not_qualified",
    ]
    return {
        "contract_type": "homepilot_outcome_measurement_contract",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": "ready_for_live_outcome_sync" if not blocked_count else "buyer_review_ready_live_outcome_sync_blocked",
        "decisions": decisions,
        "summary": {
            "event_field_count": len(event_schema),
            "metric_count": len(outcome_metrics),
            "checklist_gate_count": len(checklist),
            "blocked_gate_count": blocked_count,
            "production_verified": production_verified,
            "production_verified_label": f"production_verified={str(production_verified).lower()}",
            "value_realization_status": _value_plan_status(market_readiness),
            "allowed_outcome_stages": allowed_outcome_stages,
        },
        "allowed_outcome_stages": allowed_outcome_stages,
        "event_schema": event_schema,
        "outcome_metrics": outcome_metrics,
        "reconciliation_checklist": checklist,
        "templates": {
            "outcome_sync_template_description": "Customer-fillable sample rows for reviewed outcome import. Replace placeholders with customer-approved source references before use.",
        },
        "guardrails": {
            "derived_review_surface": True,
            "non_mutating": True,
            "no_supabase_writes": True,
            "no_crm_writes": True,
            "no_outreach_authorized": True,
            "no_secret_values": True,
            "no_raw_contact_data": True,
            "no_freeform_private_notes": True,
            "tenant_module_partner_scope_required": True,
            "response_rate_denominator_required": True,
            "commercial_values_tenant_private": True,
            "production_requires_live_proof": True,
        },
    }


def render_markdown(contract: dict[str, Any]) -> str:
    summary = contract["summary"]
    lines = [
        "# HomePilot Outcome Measurement Contract",
        "",
        f"Release: {contract['release_label']}",
        f"Created: {contract['created_at']}",
        f"Status: {contract['status']}",
        "",
        "This contract defines the safe closed-loop outcome data that may come back from DAW, partner renovators, CRMs, or approved sheets after a campaign. It is a review artifact: it does not write to Supabase or CRMs and does not authorize outreach.",
        "",
        "## Summary",
        "",
        f"- Event fields: {summary['event_field_count']}",
        f"- Outcome metrics: {summary['metric_count']}",
        f"- Checklist gates: {summary['checklist_gate_count']}",
        f"- Blocked gates: {summary['blocked_gate_count']}",
        f"- Value realization status: {summary['value_realization_status']}",
        f"- {summary['production_verified_label']}",
        "",
        "## Outcome Metrics",
        "",
        "| Metric | Numerator | Denominator | Grain | Guardrail |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in contract["outcome_metrics"]:
        lines.append(
            f"| {row['metric']} | {row['numerator']} | {row['denominator']} | {row['grain']} | {row['guardrail']} |"
        )
    lines += [
        "",
        "## Reconciliation Gates",
        "",
        "| Gate | Status | Owner | Pass condition | Blocker |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in contract["reconciliation_checklist"]:
        lines.append(
            f"| {row['gate']} | {row['status']} | {row['owner']} | {row['pass_condition']} | {row['blocker'] or 'none'} |"
        )
    lines += [
        "",
        "## Guardrails",
        "",
    ]
    for key, value in contract["guardrails"].items():
        lines.append(f"- {key}: {str(value).lower()}")
    lines.append("")
    return "\n".join(lines)


def build_outcome_measurement_contract_pack(
    out_dir: Path,
    *,
    market_readiness: dict[str, Any] | None = None,
    production_proof: dict[str, Any] | None = None,
    release_label: str = "local",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "outcome_measurement_contract": str(out_dir / "outcome_measurement_contract.json"),
        "outcome_measurement_contract_markdown": str(out_dir / "OUTCOME_MEASUREMENT_CONTRACT.md"),
        "outcome_event_schema": str(out_dir / "OUTCOME_EVENT_SCHEMA.csv"),
        "outcome_sync_template": str(out_dir / "OUTCOME_SYNC_TEMPLATE.csv"),
        "outcome_reconciliation_checklist": str(out_dir / "OUTCOME_RECONCILIATION_CHECKLIST.csv"),
    }
    contract = build_outcome_measurement_contract(
        market_readiness=market_readiness,
        production_proof=production_proof,
        release_label=release_label,
    )
    contract["paths"] = paths
    contract["secret_scan"] = {"status": "not_run", "issue_count": 0, "findings": []}
    write_json(Path(paths["outcome_measurement_contract"]), contract)
    write_text(Path(paths["outcome_measurement_contract_markdown"]), render_markdown(contract))
    write_csv(Path(paths["outcome_event_schema"]), contract["event_schema"], EVENT_SCHEMA_FIELDS)
    write_csv(Path(paths["outcome_sync_template"]), _template_rows(), OUTCOME_TEMPLATE_FIELDS)
    write_csv(Path(paths["outcome_reconciliation_checklist"]), contract["reconciliation_checklist"], CHECKLIST_FIELDS)
    scan = _secret_scan(Path(path) for path in paths.values())
    contract["secret_scan"] = scan
    if scan["status"] != "pass":
        contract["status"] = "failed_secret_scan"
    write_json(Path(paths["outcome_measurement_contract"]), contract)
    write_text(Path(paths["outcome_measurement_contract_markdown"]), render_markdown(contract))
    return contract


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HomePilot outcome measurement contract")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--market-readiness", type=Path)
    parser.add_argument("--production-proof", type=Path)
    parser.add_argument("--release-label", default="local")
    args = parser.parse_args()
    contract = build_outcome_measurement_contract_pack(
        args.out_dir,
        market_readiness=load_json(args.market_readiness),
        production_proof=load_json(args.production_proof),
        release_label=args.release_label,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": contract["status"],
        "event_fields": contract["summary"]["event_field_count"],
        "blocked_gates": contract["summary"]["blocked_gate_count"],
        "markdown": contract["paths"]["outcome_measurement_contract_markdown"],
        "template": contract["paths"]["outcome_sync_template"],
    }, indent=2, ensure_ascii=False))
    if contract["secret_scan"]["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
