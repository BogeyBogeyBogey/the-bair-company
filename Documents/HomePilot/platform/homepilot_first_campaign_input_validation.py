#!/usr/bin/env python3
"""
Validate HomePilot first-campaign customer input templates.

The customer input templates are useful only if HomePilot can also prove what
is complete, what is still blocked, and whether a first outreach wave is safe
to start. This validator checks the filled CSVs without exposing raw contact
details or secrets in the generated report.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TEMPLATE_KEYS = (
    "partner_roster_template",
    "territory_assignment_template",
    "property_source_template",
    "suppression_list_template",
    "message_approval_template",
    "partner_capacity_template",
)

GATES = (
    {
        "key": "customer_inputs_complete",
        "label": "Customer inputs complete",
        "description": "All six first-campaign CSVs exist, have the expected headers, and contain reviewable rows.",
    },
    {
        "key": "partner_scope_ready",
        "label": "Partner scope ready",
        "description": "Partner ids, territories, secure contact references, and assigned-record-only scope are reviewable.",
    },
    {
        "key": "contact_basis_and_suppression",
        "label": "Contact basis and suppression",
        "description": "Property source, contact basis reference, opt-out/suppression handling, and retention metadata are present.",
    },
    {
        "key": "message_and_claim_approval",
        "label": "Message and claim approval",
        "description": "Campaign variants are approved and avoid homeowner-intent or guaranteed-savings claims.",
    },
    {
        "key": "partner_capacity_confirmed",
        "label": "Partner capacity confirmed",
        "description": "Partner capacity, appointment slots, response SLA, accepted statuses, and rejection taxonomy are confirmed.",
    },
    {
        "key": "live_access_proof",
        "label": "Live access proof",
        "description": "Live schema, RLS, customer access, and partner-scoped proof have been archived.",
    },
)

APPROVED_STATUSES = {
    "active",
    "approved",
    "approved_for_import",
    "approved_for_launch",
    "confirmed",
    "ready",
    "ready_for_access",
    "ready_for_import",
}

SECRET_REF_RE = re.compile(r"^(secret|vault|1password|op|secure_channel|customer_system)://", re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+?\d[\s().-]*){8,}")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_lower(value: Any) -> str:
    return _norm(value).lower()


def _is_approved(value: Any) -> bool:
    return _norm_lower(value) in APPROVED_STATUSES


def _is_positive_int(value: Any) -> bool:
    try:
        return int(_norm(value)) > 0
    except ValueError:
        return False


def _safe_excerpt(value: Any) -> str:
    text = _norm(value)
    if not text:
        return ""
    if SECRET_REF_RE.search(text):
        return "[secret-reference]"
    if EMAIL_RE.search(text):
        return "[raw-email-redacted]"
    if PHONE_RE.fullmatch(text):
        return "[raw-phone-redacted]"
    if len(text) > 80:
        return f"{text[:77]}..."
    return text


def _raw_contact_detected(value: Any) -> bool:
    text = _norm(value)
    if not text or SECRET_REF_RE.search(text):
        return False
    return bool(EMAIL_RE.search(text) or PHONE_RE.search(text))


def _add_issue(
    issues: list[dict[str, Any]],
    gate: str,
    severity: str,
    code: str,
    message: str,
    file_name: str = "",
    row_number: int | None = None,
    field: str = "",
    value: Any = "",
) -> None:
    issues.append({
        "gate": gate,
        "severity": severity,
        "code": code,
        "message": message,
        "file": file_name,
        "row": row_number,
        "field": field,
        "value_excerpt": _safe_excerpt(value),
    })


def _template_map(template_pack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {template["key"]: template for template in template_pack.get("templates", [])}


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        rows = [{key: _norm(value) for key, value in row.items()} for row in reader]
    return headers, rows


def _load_template_inputs(
    input_dir: Path,
    templates: dict[str, dict[str, Any]],
    issues: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for key in TEMPLATE_KEYS:
        template = templates.get(key)
        if not template:
            _add_issue(
                issues,
                "customer_inputs_complete",
                "blocker",
                "missing_template_contract",
                f"Template contract is missing {key}.",
            )
            continue
        file_name = template["file_name"]
        path = input_dir / file_name
        if not path.exists():
            _add_issue(
                issues,
                "customer_inputs_complete",
                "blocker",
                "missing_required_file",
                f"Required first-campaign input file {file_name} is missing.",
                file_name=file_name,
            )
            loaded[key] = {"template": template, "path": str(path), "exists": False, "headers": [], "rows": []}
            continue
        headers, rows = _read_csv(path)
        missing_fields = [field for field in template["fields"] if field not in headers]
        for field in missing_fields:
            _add_issue(
                issues,
                "customer_inputs_complete",
                "blocker",
                "missing_required_column",
                f"{file_name} is missing required column {field}.",
                file_name=file_name,
                field=field,
            )
        if not rows and key != "suppression_list_template":
            _add_issue(
                issues,
                "customer_inputs_complete",
                "blocker",
                "empty_required_file",
                f"{file_name} has no reviewable rows.",
                file_name=file_name,
            )
        loaded[key] = {
            "template": template,
            "path": str(path),
            "exists": True,
            "headers": headers,
            "rows": rows,
            "row_count": len(rows),
        }
    return loaded


def _validate_partner_roster(
    loaded: dict[str, dict[str, Any]],
    issues: list[dict[str, Any]],
    expected_partner_count: int,
) -> dict[str, dict[str, str]]:
    file_name = "PARTNER_ROSTER_TEMPLATE.csv"
    rows = loaded.get("partner_roster_template", {}).get("rows", [])
    partners: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows, start=2):
        partner_id = _norm_lower(row.get("partner_id"))
        if not partner_id:
            _add_issue(issues, "partner_scope_ready", "blocker", "missing_partner_id", "Partner id is required.", file_name, index, "partner_id")
            continue
        if partner_id in partners:
            _add_issue(issues, "partner_scope_ready", "blocker", "duplicate_partner_id", "Partner id must be unique.", file_name, index, "partner_id", partner_id)
        partners[partner_id] = row
        if not _norm(row.get("partner_name")):
            _add_issue(issues, "partner_scope_ready", "blocker", "missing_partner_name", "Partner name is required.", file_name, index, "partner_name")
        if not _is_positive_int(row.get("capacity_per_month")):
            _add_issue(issues, "partner_capacity_confirmed", "blocker", "invalid_partner_capacity", "Partner monthly capacity must be a positive integer.", file_name, index, "capacity_per_month", row.get("capacity_per_month"))
        contact_ref = row.get("primary_contact_email_or_secret_channel_ref")
        if _raw_contact_detected(contact_ref):
            _add_issue(issues, "partner_scope_ready", "blocker", "raw_personal_contact_data", "Use a secret-channel reference instead of raw personal contact data.", file_name, index, "primary_contact_email_or_secret_channel_ref", contact_ref)
        elif not SECRET_REF_RE.search(_norm(contact_ref)):
            _add_issue(issues, "partner_scope_ready", "blocker", "missing_secure_contact_reference", "Secure partner contact reference is required.", file_name, index, "primary_contact_email_or_secret_channel_ref", contact_ref)
        if _norm_lower(row.get("portal_role")) != "partner_renovator":
            _add_issue(issues, "partner_scope_ready", "warning", "unexpected_partner_role", "Partner portal role should be partner_renovator.", file_name, index, "portal_role", row.get("portal_role"))
        if "assigned_records_only" not in _norm_lower(row.get("partner_scope_notes")):
            _add_issue(issues, "partner_scope_ready", "blocker", "partner_scope_not_confirmed", "Partner scope notes must confirm assigned_records_only.", file_name, index, "partner_scope_notes", row.get("partner_scope_notes"))
        if not _is_approved(row.get("status")):
            _add_issue(issues, "partner_scope_ready", "blocker", "partner_not_confirmed", "Partner roster row must be approved or confirmed before access setup.", file_name, index, "status", row.get("status"))
    if expected_partner_count and len(partners) < expected_partner_count:
        _add_issue(
            issues,
            "partner_scope_ready",
            "blocker",
            "expected_partner_count_missing",
            f"Expected at least {expected_partner_count} partner renovators for the DAW first wave; found {len(partners)}.",
            file_name=file_name,
        )
    return partners


def _validate_territories(
    loaded: dict[str, dict[str, Any]],
    issues: list[dict[str, Any]],
    partners: dict[str, dict[str, str]],
) -> None:
    file_name = "TERRITORY_ASSIGNMENT_TEMPLATE.csv"
    rows = loaded.get("territory_assignment_template", {}).get("rows", [])
    assigned_partners: set[str] = set()
    territory_keys: dict[str, str] = {}
    for index, row in enumerate(rows, start=2):
        partner_id = _norm_lower(row.get("partner_id"))
        assigned_partners.add(partner_id)
        if partner_id not in partners:
            _add_issue(issues, "partner_scope_ready", "blocker", "unknown_territory_partner", "Territory assignment references an unknown partner_id.", file_name, index, "partner_id", partner_id)
        if not _norm(row.get("cities_or_postcodes")) and not _norm(row.get("included_postcodes")):
            _add_issue(issues, "partner_scope_ready", "blocker", "missing_territory_scope", "Territory assignment needs cities_or_postcodes or included_postcodes.", file_name, index)
        if not _is_positive_int(row.get("capacity_cap")):
            _add_issue(issues, "partner_capacity_confirmed", "blocker", "invalid_territory_capacity_cap", "Territory capacity cap must be a positive integer.", file_name, index, "capacity_cap", row.get("capacity_cap"))
        territory_key = _norm_lower(row.get("included_postcodes") or row.get("cities_or_postcodes"))
        if territory_key:
            previous = territory_keys.get(territory_key)
            if previous and previous != partner_id:
                _add_issue(issues, "partner_scope_ready", "warning", "overlapping_territory", "The same territory appears assigned to more than one partner.", file_name, index, "included_postcodes", territory_key)
            territory_keys[territory_key] = partner_id
        if not _norm(row.get("overlap_rule")):
            _add_issue(issues, "partner_scope_ready", "blocker", "missing_overlap_rule", "Territory overlap rule is required.", file_name, index, "overlap_rule")
        if not _is_approved(row.get("status")):
            _add_issue(issues, "partner_scope_ready", "blocker", "territory_not_confirmed", "Territory assignment row must be approved or confirmed.", file_name, index, "status", row.get("status"))
    missing = sorted(set(partners) - assigned_partners)
    for partner_id in missing:
        _add_issue(issues, "partner_scope_ready", "blocker", "partner_missing_territory", "Every partner needs a territory assignment.", file_name, field="partner_id", value=partner_id)


def _validate_property_source(loaded: dict[str, dict[str, Any]], issues: list[dict[str, Any]]) -> None:
    file_name = "PROPERTY_SOURCE_TEMPLATE.csv"
    rows = loaded.get("property_source_template", {}).get("rows", [])
    for index, row in enumerate(rows, start=2):
        tenant_id = _norm(row.get("tenant_id"))
        module_key = _norm(row.get("module_key"))
        allowed_modules = {module.strip() for module in _norm(row.get("allowed_modules")).split(";") if module.strip()}
        if not tenant_id:
            _add_issue(issues, "contact_basis_and_suppression", "blocker", "missing_tenant_id", "Property source must name the tenant_id.", file_name, index, "tenant_id")
        if not module_key:
            _add_issue(issues, "contact_basis_and_suppression", "blocker", "missing_module_key", "Property source must name the module_key.", file_name, index, "module_key")
        elif allowed_modules and module_key not in allowed_modules:
            _add_issue(issues, "contact_basis_and_suppression", "blocker", "module_not_allowed", "module_key must be included in allowed_modules.", file_name, index, "allowed_modules", row.get("allowed_modules"))
        for field in ("address_column", "postcode_column", "city_column", "source_provenance", "dedupe_rule"):
            if not _norm(row.get(field)):
                _add_issue(issues, "contact_basis_and_suppression", "blocker", f"missing_{field}", f"Property source is missing {field}.", file_name, index, field)
        contact_basis = _norm_lower(row.get("contact_basis_source"))
        if not any(fragment in contact_basis for fragment in ("approved", "lawful", "legitimate", "customer-approved")):
            _add_issue(issues, "contact_basis_and_suppression", "blocker", "contact_basis_not_approved", "Contact basis source must reference an approved/lawful customer review.", file_name, index, "contact_basis_source", row.get("contact_basis_source"))
        public_data_used = _norm_lower(row.get("public_data_used"))
        if public_data_used and public_data_used not in {"none", "none_until_approved", "approved", "approved_public_sources"} and "approved" not in public_data_used:
            _add_issue(issues, "contact_basis_and_suppression", "blocker", "public_data_not_approved", "Public-data use must be none or explicitly approved.", file_name, index, "public_data_used", row.get("public_data_used"))
        if not _is_approved(row.get("import_status")):
            _add_issue(issues, "contact_basis_and_suppression", "blocker", "property_source_not_approved", "Property source import_status must be approved or ready_for_import.", file_name, index, "import_status", row.get("import_status"))


def _validate_suppression(loaded: dict[str, dict[str, Any]], issues: list[dict[str, Any]]) -> None:
    file_name = "SUPPRESSION_LIST_TEMPLATE.csv"
    rows = loaded.get("suppression_list_template", {}).get("rows", [])
    if not rows:
        _add_issue(
            issues,
            "contact_basis_and_suppression",
            "blocker",
            "suppression_confirmation_missing",
            "Suppression file has no rows; add explicit zero-suppression confirmation outside raw contact data.",
            file_name=file_name,
        )
        return
    for index, row in enumerate(rows, start=2):
        if not _norm(row.get("suppression_id")):
            _add_issue(issues, "contact_basis_and_suppression", "blocker", "missing_suppression_id", "Suppression row needs a suppression_id.", file_name, index, "suppression_id")
        if not _norm(row.get("property_or_hash_reference")):
            _add_issue(issues, "contact_basis_and_suppression", "blocker", "missing_suppression_reference", "Suppression row needs a property/hash reference.", file_name, index, "property_or_hash_reference")
        if not _norm(row.get("reason")):
            _add_issue(issues, "contact_basis_and_suppression", "blocker", "missing_suppression_reason", "Suppression row needs a reason.", file_name, index, "reason")
        if not _norm(row.get("opt_out_method")):
            _add_issue(issues, "contact_basis_and_suppression", "blocker", "missing_opt_out_method", "Suppression row needs an opt-out method.", file_name, index, "opt_out_method")
        if not _norm(row.get("delete_after")):
            _add_issue(issues, "contact_basis_and_suppression", "blocker", "missing_retention_delete_after", "Suppression row needs delete_after retention metadata.", file_name, index, "delete_after")
        for field in ("property_or_hash_reference", "notes"):
            if _raw_contact_detected(row.get(field)):
                _add_issue(issues, "contact_basis_and_suppression", "blocker", "raw_personal_contact_data", "Suppression data must use property/hash references, not raw contact data.", file_name, index, field, row.get(field))


def _validate_messages(loaded: dict[str, dict[str, Any]], issues: list[dict[str, Any]]) -> None:
    file_name = "MESSAGE_APPROVAL_TEMPLATE.csv"
    rows = loaded.get("message_approval_template", {}).get("rows", [])
    for index, row in enumerate(rows, start=2):
        if not _is_approved(row.get("approval_status")):
            _add_issue(issues, "message_and_claim_approval", "blocker", "message_not_approved", "Message variant must be approved before use.", file_name, index, "approval_status", row.get("approval_status"))
        if not _norm(row.get("approved_at")):
            _add_issue(issues, "message_and_claim_approval", "blocker", "message_approval_timestamp_missing", "Message approval needs approved_at evidence.", file_name, index, "approved_at")
        if not _norm(row.get("opt_out_wording")):
            _add_issue(issues, "message_and_claim_approval", "blocker", "opt_out_wording_missing", "Message variant needs customer-approved opt-out wording.", file_name, index, "opt_out_wording")
        prohibited_checked = _norm_lower(row.get("prohibited_claims_checked"))
        if "no homeowner intent" not in prohibited_checked:
            _add_issue(issues, "message_and_claim_approval", "blocker", "homeowner_intent_language_not_checked", "Prohibited-claims check must confirm no homeowner intent language.", file_name, index, "prohibited_claims_checked", row.get("prohibited_claims_checked"))
        if "guaranteed" in _norm_lower(row.get("claim_summary")):
            _add_issue(issues, "message_and_claim_approval", "blocker", "guaranteed_claim_detected", "Claim summary must not promise guaranteed savings/results.", file_name, index, "claim_summary", row.get("claim_summary"))


def _validate_partner_capacity(
    loaded: dict[str, dict[str, Any]],
    issues: list[dict[str, Any]],
    partners: dict[str, dict[str, str]],
) -> None:
    file_name = "PARTNER_CAPACITY_TEMPLATE.csv"
    rows = loaded.get("partner_capacity_template", {}).get("rows", [])
    capacity_partners: set[str] = set()
    for index, row in enumerate(rows, start=2):
        partner_id = _norm_lower(row.get("partner_id"))
        capacity_partners.add(partner_id)
        if partner_id not in partners:
            _add_issue(issues, "partner_capacity_confirmed", "blocker", "unknown_capacity_partner", "Capacity row references an unknown partner_id.", file_name, index, "partner_id", partner_id)
        for field in ("capacity_per_month", "appointment_slots_per_week", "response_sla_hours"):
            if not _is_positive_int(row.get(field)):
                _add_issue(issues, "partner_capacity_confirmed", "blocker", f"invalid_{field}", f"{field} must be a positive integer.", file_name, index, field, row.get(field))
        try:
            if int(_norm(row.get("response_sla_hours"))) > 48:
                _add_issue(issues, "partner_capacity_confirmed", "warning", "slow_response_sla", "Response SLA is above 48 hours; review first-wave expectations.", file_name, index, "response_sla_hours", row.get("response_sla_hours"))
        except ValueError:
            pass
        if not _norm(row.get("accepted_statuses")):
            _add_issue(issues, "partner_capacity_confirmed", "blocker", "accepted_statuses_missing", "Accepted statuses are required.", file_name, index, "accepted_statuses")
        if not _norm(row.get("rejection_reasons_allowed")):
            _add_issue(issues, "partner_capacity_confirmed", "blocker", "rejection_taxonomy_missing", "Rejected-reason taxonomy is required.", file_name, index, "rejection_reasons_allowed")
        if not _is_approved(row.get("capacity_status")):
            _add_issue(issues, "partner_capacity_confirmed", "blocker", "capacity_not_confirmed", "Capacity status must be approved or confirmed.", file_name, index, "capacity_status", row.get("capacity_status"))
    missing = sorted(set(partners) - capacity_partners)
    for partner_id in missing:
        _add_issue(issues, "partner_capacity_confirmed", "blocker", "partner_missing_capacity", "Every partner needs a capacity/follow-up row.", file_name, field="partner_id", value=partner_id)


def _gate_summaries(issues: list[dict[str, Any]], live_proof_ready: bool) -> list[dict[str, Any]]:
    gate_rows: list[dict[str, Any]] = []
    for gate in GATES:
        gate_issues = [issue for issue in issues if issue["gate"] == gate["key"]]
        blockers = [issue for issue in gate_issues if issue["severity"] == "blocker"]
        warnings = [issue for issue in gate_issues if issue["severity"] == "warning"]
        status = "pass" if not blockers else "blocked"
        if gate["key"] == "live_access_proof" and not live_proof_ready:
            status = "blocked"
        gate_rows.append({
            "key": gate["key"],
            "label": gate["label"],
            "status": status,
            "description": gate["description"],
            "blockers": len(blockers),
            "warnings": len(warnings),
        })
    return gate_rows


def render_validation_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# HomePilot First Campaign Input Validation",
        "",
        f"Release: {report['release_label']}",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        f"First-wave decision: {report['first_wave_decision']}",
        f"Input directory: {report['input_dir']}",
        "",
        "This report checks the filled first-campaign CSV templates before HomePilot allows a controlled campaign wave.",
        "It is validation evidence, not a legal signoff or live RLS proof.",
        "",
        "## Summary",
        "",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- {key}: {value}")
    lines += [
        "",
        "## Gates",
        "",
        "| Gate | Status | Blockers | Warnings |",
        "| --- | --- | --- | --- |",
    ]
    for gate in report["gates"]:
        lines.append(f"| {gate['label']} | {gate['status']} | {gate['blockers']} | {gate['warnings']} |")
    lines += [
        "",
        "## Issues",
        "",
    ]
    if not report["issues"]:
        lines.append("- No validation issues found.")
    else:
        lines += [
            "| Severity | Gate | Code | File | Row | Field | Message |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for issue in report["issues"]:
            row = "" if issue["row"] is None else issue["row"]
            lines.append(
                f"| {issue['severity']} | {issue['gate']} | {issue['code']} | "
                f"{issue['file']} | {row} | {issue['field']} | {issue['message']} |"
            )
    lines += [
        "",
        "## Guardrails",
        "",
        "- This report redacts raw email/phone values and secret references.",
        "- Customer input completion does not replace legal approval, suppression proof, or live access proof.",
        "- First-wave launch requires explicit go/no-go after live schema, RLS, and customer-access verification.",
        "",
    ]
    return "\n".join(lines)


def _write_issues_csv(path: Path, issues: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["severity", "gate", "code", "file", "row", "field", "message", "value_excerpt"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for issue in issues:
            writer.writerow({field: issue.get(field, "") for field in fields})


def build_first_campaign_input_validation(
    out_dir: Path,
    template_pack: dict[str, Any],
    input_dir: Path,
    release_label: str = "local",
    expected_partner_count: int = 10,
    live_proof_ready: bool = False,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    issues: list[dict[str, Any]] = []
    templates = _template_map(template_pack)
    loaded = _load_template_inputs(input_dir, templates, issues)
    partners = _validate_partner_roster(loaded, issues, expected_partner_count)
    _validate_territories(loaded, issues, partners)
    _validate_property_source(loaded, issues)
    _validate_suppression(loaded, issues)
    _validate_messages(loaded, issues)
    _validate_partner_capacity(loaded, issues, partners)
    if not live_proof_ready:
        _add_issue(
            issues,
            "live_access_proof",
            "blocker",
            "live_proof_missing",
            "Live schema, RLS, customer access, and partner-scoped proof are required before first-wave launch.",
        )

    gates = _gate_summaries(issues, live_proof_ready)
    blocker_count = sum(1 for issue in issues if issue["severity"] == "blocker")
    warning_count = sum(1 for issue in issues if issue["severity"] == "warning")
    input_blockers = [
        issue for issue in issues
        if issue["severity"] == "blocker" and issue["gate"] != "live_access_proof"
    ]
    if blocker_count == 0:
        status = "ready_for_first_wave"
        first_wave_decision = "ready_for_first_wave"
    elif not input_blockers:
        status = "customer_inputs_ready"
        first_wave_decision = "blocked_until_live_proof"
    else:
        status = "action_required"
        first_wave_decision = "blocked_until_customer_input_fixes"

    loaded_files = [item["template"]["file_name"] for item in loaded.values() if item.get("exists")]
    report = {
        "report_type": "homepilot_first_campaign_input_validation",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": status,
        "first_wave_decision": first_wave_decision,
        "input_dir": str(input_dir),
        "expected_partner_count": expected_partner_count,
        "live_proof_ready": live_proof_ready,
        "summary": {
            "required_files": len(TEMPLATE_KEYS),
            "loaded_files": len(loaded_files),
            "partner_count": len(partners),
            "blockers": blocker_count,
            "warnings": warning_count,
            "issues": len(issues),
        },
        "loaded_files": loaded_files,
        "row_counts": {
            key: len(value.get("rows", []))
            for key, value in loaded.items()
        },
        "gates": gates,
        "issues": issues,
        "guardrails": {
            "templates_are_not_customer_approval": True,
            "raw_contact_values_redacted": True,
            "secret_values_written": False,
            "contact_basis_required_before_outreach": True,
            "live_proof_required_before_launch": True,
        },
        "paths": {
            "validation_report": str(out_dir / "first_campaign_input_validation.json"),
            "validation_markdown": str(out_dir / "FIRST_CAMPAIGN_INPUT_VALIDATION.md"),
            "issues_csv": str(out_dir / "FIRST_CAMPAIGN_INPUT_ISSUES.csv"),
        },
    }
    write_json(out_dir / "first_campaign_input_validation.json", report)
    write_text(out_dir / "FIRST_CAMPAIGN_INPUT_VALIDATION.md", render_validation_markdown(report))
    _write_issues_csv(out_dir / "FIRST_CAMPAIGN_INPUT_ISSUES.csv", issues)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate HomePilot first-campaign customer input CSVs")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--template-pack", required=True, type=Path)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--release-label", default="local")
    parser.add_argument("--expected-partners", type=int, default=10)
    parser.add_argument("--live-proof-ready", action="store_true")
    args = parser.parse_args()

    template_pack = json.loads(args.template_pack.read_text(encoding="utf-8"))
    report = build_first_campaign_input_validation(
        out_dir=args.out_dir,
        template_pack=template_pack,
        input_dir=args.input_dir,
        release_label=args.release_label,
        expected_partner_count=args.expected_partners,
        live_proof_ready=args.live_proof_ready,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": report["status"],
        "first_wave_decision": report["first_wave_decision"],
        "validation_report": report["paths"]["validation_report"],
        "validation_markdown": report["paths"]["validation_markdown"],
        "issues_csv": report["paths"]["issues_csv"],
    }, indent=2))


if __name__ == "__main__":
    main()
