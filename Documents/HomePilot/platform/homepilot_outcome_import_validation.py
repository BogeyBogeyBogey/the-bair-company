#!/usr/bin/env python3
"""
Validate HomePilot outcome import CSVs in dry-run mode.

This validator is the safety layer between customer-approved CRM/sheet outcome
exports and any future live HomePilot sync. It checks scope, required fields,
allowed outcome stages, idempotency, source references, commercial values, and
privacy guardrails without writing to Supabase, CRMs, mail systems, or portals.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_outcome_measurement_contract import OUTCOME_TEMPLATE_FIELDS
from homepilot_platform import PILOT_MODULES


ALLOWED_OUTCOME_STAGES = {
    "appointment_booked",
    "appointment_completed",
    "no_show",
    "quote_requested",
    "quote_sent",
    "quote_accepted",
    "won_project",
    "lost_project",
    "not_qualified",
}
ALLOWED_SOURCE_SYSTEMS = {
    "customer_crm",
    "partner_crm",
    "approved_sheet",
    "manual_customer_signoff",
}
COMMERCIAL_AMOUNT_REQUIRED_STAGES = {
    "quote_sent",
    "quote_accepted",
    "won_project",
}
LOSS_REASON_REQUIRED_STAGES = {
    "lost_project",
    "not_qualified",
}
ALLOWED_LOSS_REASONS = {
    "price",
    "timing",
    "not_owner",
    "already_renovated",
    "partner_capacity",
    "no_budget",
    "other_reviewed",
}
REQUIRED_VALUE_FIELDS = [
    "tenant_id",
    "module_key",
    "campaign_id",
    "property_id",
    "outcome_event_id",
    "outcome_stage",
    "event_at",
    "source_system",
    "source_record_ref",
    "evidence_reference",
    "customer_approval_reference",
]
SAFE_REFERENCE_PREFIXES = (
    "crm://",
    "sheet://",
    "signed://",
    "ticket://",
    "manual://",
    "customer_system://",
    "secure_channel://",
    "vault://",
)
ISSUE_FIELDS = [
    "severity",
    "row_number",
    "field",
    "code",
    "message",
    "value_excerpt",
    "next_action",
    "blocks_live_sync",
]
REVIEW_ROW_FIELDS = [
    "row_number",
    "validation_status",
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

SECRET_PATTERNS = (
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"postgres(?:ql)?://[^:\s]+:[^@\s]{8,}@", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?:api[_-]?key|service[_-]?role|password|token|secret)\s*[:=]\s*['\"][^'\"\n]{12,}['\"]", re.IGNORECASE),
)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
BELGIAN_PHONE_RE = re.compile(r"(?:\+32|0032|0[1-9])[\s().-]*(?:\d[\s().-]*){7,}")
HOMEOWNER_INTENT_RE = re.compile(
    r"\b(?:buying intent|purchase intent|homeowner intent|wants to buy|wil kopen|koopintentie|wil renoveren)\b",
    re.IGNORECASE,
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


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_lower(value: Any) -> str:
    return _norm(value).lower()


def _default_rows() -> list[dict[str, Any]]:
    return [
        {
            "tenant_id": "daw-belgium",
            "module_key": "facadepilot",
            "partner_id": "daw-partner-01",
            "campaign_id": "campaign-placeholder",
            "property_id": "property-placeholder-001",
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
            "property_id": "property-placeholder-002",
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
        {
            "tenant_id": "daw-belgium",
            "module_key": "facadepilot",
            "partner_id": "daw-partner-02",
            "campaign_id": "campaign-placeholder",
            "property_id": "property-placeholder-003",
            "outcome_event_id": "outcome-placeholder-003",
            "outcome_stage": "won_project",
            "event_at": "2026-08-04T09:15:00Z",
            "source_system": "customer_crm",
            "source_record_ref": "crm://redacted/project/003",
            "amount_ex_vat": "12750",
            "currency": "EUR",
            "loss_reason": "",
            "evidence_reference": "crm://redacted/project/003",
            "customer_approval_reference": "signed://customer/outcome-sync-approval",
        },
    ]


def _safe_excerpt(value: Any) -> str:
    text = _norm(value)
    if not text:
        return ""
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        return "[secret-redacted]"
    if EMAIL_RE.search(text):
        return "[raw-email-redacted]"
    if BELGIAN_PHONE_RE.search(text):
        return "[raw-phone-redacted]"
    if len(text) > 80:
        return f"{text[:77]}..."
    return text


def _raw_contact_detected(value: Any) -> bool:
    text = _norm(value)
    return bool(text and (EMAIL_RE.search(text) or BELGIAN_PHONE_RE.search(text)))


def _secret_detected(value: Any) -> bool:
    text = _norm(value)
    return bool(text and any(pattern.search(text) for pattern in SECRET_PATTERNS))


def _add_issue(
    issues: list[dict[str, Any]],
    severity: str,
    code: str,
    message: str,
    *,
    row_number: int | None = None,
    field: str = "",
    value: Any = "",
    next_action: str = "",
    blocks_live_sync: bool | None = None,
) -> None:
    if blocks_live_sync is None:
        blocks_live_sync = severity == "blocker"
    issues.append({
        "severity": severity,
        "row_number": row_number,
        "field": field,
        "code": code,
        "message": message,
        "value_excerpt": _safe_excerpt(value),
        "next_action": next_action,
        "blocks_live_sync": blocks_live_sync,
    })


def _read_input_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        rows = [
            {key: _norm(value) for key, value in row.items()}
            for row in reader
        ]
    return headers, rows


def _allowed_stages(outcome_contract: dict[str, Any] | None) -> set[str]:
    if not outcome_contract:
        return set(ALLOWED_OUTCOME_STAGES)
    stages = outcome_contract.get("allowed_outcome_stages")
    if not stages:
        stages = (outcome_contract.get("summary") or {}).get("allowed_outcome_stages")
    return {str(stage).strip() for stage in stages or ALLOWED_OUTCOME_STAGES if str(stage).strip()}


def _production_verified(outcome_contract: dict[str, Any] | None, override: bool | None) -> bool:
    if override is not None:
        return bool(override)
    summary = (outcome_contract or {}).get("summary") or {}
    return bool(summary.get("production_verified"))


def _iso_timestamp_ok(value: str) -> bool:
    text = _norm(value)
    if not text:
        return False
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _decimal_amount(value: str) -> float | None:
    text = _norm(value)
    if not text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _safe_reference(value: Any) -> bool:
    text = _norm_lower(value)
    return bool(text and text.startswith(SAFE_REFERENCE_PREFIXES))


def _validate_headers(headers: list[str], issues: list[dict[str, Any]]) -> None:
    missing = [field for field in OUTCOME_TEMPLATE_FIELDS if field not in headers]
    extras = [field for field in headers if field not in OUTCOME_TEMPLATE_FIELDS]
    for field in missing:
        _add_issue(
            issues,
            "blocker",
            "missing_required_column",
            f"Outcome import CSV is missing required column {field}.",
            row_number=1,
            field=field,
            next_action="Use OUTCOME_SYNC_TEMPLATE.csv as the import schema.",
        )
    for field in extras:
        _add_issue(
            issues,
            "warning",
            "unexpected_extra_column",
            f"Extra column {field} is not part of the outcome import contract.",
            row_number=1,
            field=field,
            next_action="Remove extra fields or add them through a reviewed schema change.",
            blocks_live_sync=False,
        )


def _validate_row(
    row: dict[str, Any],
    *,
    row_number: int,
    issues: list[dict[str, Any]],
    seen_event_ids: set[str],
    allowed_stages: set[str],
    expected_tenant_id: str | None,
    expected_module_key: str | None,
    require_partner_scope: bool,
) -> float:
    for field in REQUIRED_VALUE_FIELDS:
        if not _norm(row.get(field)):
            _add_issue(
                issues,
                "blocker",
                f"missing_{field}",
                f"{field} is required for every outcome event.",
                row_number=row_number,
                field=field,
                next_action=f"Add {field} from the customer-approved source export.",
            )

    for field, value in row.items():
        if _secret_detected(value):
            _add_issue(
                issues,
                "blocker",
                "secret_value_detected",
                "Outcome import rows must not contain API keys, tokens, passwords, private keys, or database URLs.",
                row_number=row_number,
                field=field,
                value=value,
                next_action="Replace the value with a reviewed source reference and keep secrets in the approved secret channel.",
            )
        if _raw_contact_detected(value):
            _add_issue(
                issues,
                "blocker",
                "raw_contact_data_detected",
                "Outcome import rows must not contain raw email addresses or phone numbers.",
                row_number=row_number,
                field=field,
                value=value,
                next_action="Use a redacted CRM/sheet/ticket reference instead of raw personal contact data.",
            )
        if HOMEOWNER_INTENT_RE.search(_norm(value)):
            _add_issue(
                issues,
                "blocker",
                "homeowner_intent_claim_detected",
                "Outcome rows may record explicit events, but must not add homeowner-intent claims.",
                row_number=row_number,
                field=field,
                value=value,
                next_action="Replace intent language with the explicit outcome_stage and evidence reference.",
            )

    tenant_id = _norm(row.get("tenant_id"))
    module_key = _norm_lower(row.get("module_key"))
    partner_id = _norm(row.get("partner_id"))
    event_id = _norm(row.get("outcome_event_id"))
    stage = _norm_lower(row.get("outcome_stage"))
    source_system = _norm_lower(row.get("source_system"))

    if expected_tenant_id and tenant_id and tenant_id != expected_tenant_id:
        _add_issue(
            issues,
            "blocker",
            "unexpected_tenant_id",
            "Outcome import row does not match the expected tenant scope.",
            row_number=row_number,
            field="tenant_id",
            value=tenant_id,
            next_action=f"Split imports by tenant and rerun for {expected_tenant_id}.",
        )
    if expected_module_key and module_key and module_key != expected_module_key:
        _add_issue(
            issues,
            "blocker",
            "unexpected_module_key",
            "Outcome import row does not match the expected module scope.",
            row_number=row_number,
            field="module_key",
            value=module_key,
            next_action=f"Split imports by module and rerun for {expected_module_key}.",
        )
    if module_key and module_key not in PILOT_MODULES:
        _add_issue(
            issues,
            "blocker",
            "unknown_module_key",
            "module_key must be a known HomePilot module.",
            row_number=row_number,
            field="module_key",
            value=module_key,
            next_action="Use one of the tenant-entitled HomePilot module keys.",
        )
    if require_partner_scope and not partner_id:
        _add_issue(
            issues,
            "blocker",
            "missing_partner_scope",
            "Producer-network outcome rows require partner_id for assigned-record-only reconciliation.",
            row_number=row_number,
            field="partner_id",
            next_action="Add the approved partner renovator id or rerun with partner scope disabled for a non-network import.",
        )
    if event_id:
        if event_id in seen_event_ids:
            _add_issue(
                issues,
                "blocker",
                "duplicate_outcome_event_id",
                "outcome_event_id must be unique for idempotent imports.",
                row_number=row_number,
                field="outcome_event_id",
                value=event_id,
                next_action="Deduplicate the source export or assign a stable unique event id.",
            )
        seen_event_ids.add(event_id)
    for field in ("campaign_id", "property_id", "outcome_event_id"):
        value = _norm_lower(row.get(field))
        if "placeholder" in value:
            _add_issue(
                issues,
                "warning",
                "placeholder_reference",
                f"{field} still contains a synthetic/demo placeholder.",
                row_number=row_number,
                field=field,
                value=row.get(field),
                next_action=f"Replace {field} with the customer-approved HomePilot/source-system reference before live sync.",
                blocks_live_sync=False,
            )
    if stage and stage not in allowed_stages:
        _add_issue(
            issues,
            "blocker",
            "unknown_outcome_stage",
            "outcome_stage is not allowed by the outcome measurement contract.",
            row_number=row_number,
            field="outcome_stage",
            value=stage,
            next_action="Map the source status to an approved outcome stage before import.",
        )
    if _norm(row.get("event_at")) and not _iso_timestamp_ok(_norm(row.get("event_at"))):
        _add_issue(
            issues,
            "blocker",
            "invalid_event_at",
            "event_at must be an ISO 8601 timestamp.",
            row_number=row_number,
            field="event_at",
            value=row.get("event_at"),
            next_action="Export event_at as an ISO 8601 UTC timestamp.",
        )
    if source_system and source_system not in ALLOWED_SOURCE_SYSTEMS:
        _add_issue(
            issues,
            "blocker",
            "invalid_source_system",
            "source_system is not in the approved outcome source list.",
            row_number=row_number,
            field="source_system",
            value=source_system,
            next_action="Use customer_crm, partner_crm, approved_sheet, or manual_customer_signoff after customer approval.",
        )

    for field in ("source_record_ref", "evidence_reference", "customer_approval_reference"):
        value = row.get(field)
        if _norm(value) and not _safe_reference(value):
            _add_issue(
                issues,
                "warning",
                "reference_prefix_not_reviewed",
                f"{field} should use a reviewed reference prefix.",
                row_number=row_number,
                field=field,
                value=value,
                next_action="Use crm://, sheet://, signed://, ticket://, manual://, customer_system://, secure_channel://, or vault://.",
                blocks_live_sync=False,
            )

    amount = _decimal_amount(_norm(row.get("amount_ex_vat")))
    if stage in COMMERCIAL_AMOUNT_REQUIRED_STAGES and amount is None:
        _add_issue(
            issues,
            "blocker",
            "missing_amount_ex_vat",
            "Commercial outcome stages require amount_ex_vat.",
            row_number=row_number,
            field="amount_ex_vat",
            value=row.get("amount_ex_vat"),
            next_action="Add the customer-approved quote/project amount or remap the stage.",
        )
    if amount is not None and amount < 0:
        _add_issue(
            issues,
            "blocker",
            "negative_amount",
            "amount_ex_vat must be non-negative.",
            row_number=row_number,
            field="amount_ex_vat",
            value=row.get("amount_ex_vat"),
            next_action="Correct negative commercial values before import.",
        )
    if amount is not None and _norm(row.get("currency")) != "EUR":
        _add_issue(
            issues,
            "blocker",
            "invalid_currency",
            "Commercial outcome amounts currently require currency EUR.",
            row_number=row_number,
            field="currency",
            value=row.get("currency"),
            next_action="Convert to EUR or add reviewed currency-conversion rules.",
        )

    loss_reason = _norm_lower(row.get("loss_reason"))
    if stage in LOSS_REASON_REQUIRED_STAGES and not loss_reason:
        _add_issue(
            issues,
            "blocker",
            "loss_reason_required",
            "lost_project and not_qualified outcomes require a reviewed loss_reason.",
            row_number=row_number,
            field="loss_reason",
            next_action="Add a reviewed loss reason without private free-form notes.",
        )
    if loss_reason and loss_reason not in ALLOWED_LOSS_REASONS:
        _add_issue(
            issues,
            "warning",
            "loss_reason_not_standardized",
            "loss_reason is not in the standard reviewed taxonomy.",
            row_number=row_number,
            field="loss_reason",
            value=loss_reason,
            next_action="Use price, timing, not_owner, already_renovated, partner_capacity, no_budget, or other_reviewed.",
            blocks_live_sync=False,
        )
    return amount or 0.0


def _review_rows(rows: list[dict[str, Any]], row_blockers: set[int], row_warnings: set[int]) -> list[dict[str, Any]]:
    review: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=2):
        if index in row_blockers:
            validation_status = "blocked"
        elif index in row_warnings:
            validation_status = "review_ready_with_warnings"
        else:
            validation_status = "review_ready"
        review_row = {
            "row_number": index,
            "validation_status": validation_status,
        }
        for field in REVIEW_ROW_FIELDS:
            if field in {"row_number", "validation_status"}:
                continue
            review_row[field] = _safe_excerpt(row.get(field))
        review.append(review_row)
    return review


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


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# HomePilot Outcome Import Dry-Run Validation",
        "",
        f"Release: {report['release_label']}",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        f"Input: {report['input_label']}",
        "",
        "This report validates customer-approved outcome rows before any live CRM or Supabase sync. It is dry-run evidence only: it does not write data, authorize outreach, or prove production access.",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    lines += [
        "",
        "## Scope",
        "",
        f"- Expected tenant: {report['scope'].get('expected_tenant_id') or 'not_set'}",
        f"- Expected module: {report['scope'].get('expected_module_key') or 'not_set'}",
        f"- Partner scope required: {str(report['scope'].get('require_partner_scope')).lower()}",
        "",
        "## Issues",
        "",
    ]
    if not report["issues"]:
        lines.append("- No validation issues found.")
    else:
        lines += [
            "| Severity | Row | Field | Code | Message | Next action |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for issue in report["issues"]:
            row_number = "" if issue["row_number"] is None else issue["row_number"]
            lines.append(
                f"| {issue['severity']} | {row_number} | {issue['field']} | {issue['code']} | "
                f"{issue['message']} | {issue['next_action']} |"
            )
    lines += [
        "",
        "## Allowed Outcome Stages",
        "",
    ]
    for stage in report["allowed_outcome_stages"]:
        lines.append(f"- {stage}")
    lines += [
        "",
        "## Guardrails",
        "",
    ]
    for key, value in report["guardrails"].items():
        lines.append(f"- {key}: {str(value).lower()}")
    lines.append("")
    return "\n".join(lines)


def build_outcome_import_validation_pack(
    out_dir: Path,
    *,
    input_csv: Path | None = None,
    outcome_contract: dict[str, Any] | None = None,
    expected_tenant_id: str | None = None,
    expected_module_key: str | None = None,
    release_label: str = "local",
    require_partner_scope: bool = True,
    production_verified: bool | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    issues: list[dict[str, Any]] = []
    if input_csv:
        headers, rows = _read_input_csv(input_csv)
        synthetic_fixture = input_csv.name == "OUTCOME_SYNC_TEMPLATE.csv"
        input_label = "synthetic_outcome_sync_template" if synthetic_fixture else str(input_csv)
    else:
        rows = _default_rows()
        headers = list(OUTCOME_TEMPLATE_FIELDS)
        synthetic_fixture = True
        input_label = "synthetic_default_outcome_fixture"

    _validate_headers(headers, issues)
    allowed_stages = _allowed_stages(outcome_contract)
    production_ok = _production_verified(outcome_contract, production_verified)
    seen_event_ids: set[str] = set()
    amount_total = 0.0
    for index, row in enumerate(rows, start=2):
        amount_total += _validate_row(
            row,
            row_number=index,
            issues=issues,
            seen_event_ids=seen_event_ids,
            allowed_stages=allowed_stages,
            expected_tenant_id=expected_tenant_id,
            expected_module_key=expected_module_key,
            require_partner_scope=require_partner_scope,
        )

    tenant_ids = {_norm(row.get("tenant_id")) for row in rows if _norm(row.get("tenant_id"))}
    module_keys = {_norm_lower(row.get("module_key")) for row in rows if _norm(row.get("module_key"))}
    partner_ids = {_norm(row.get("partner_id")) for row in rows if _norm(row.get("partner_id"))}
    if len(tenant_ids) > 1:
        _add_issue(
            issues,
            "blocker",
            "mixed_tenant_batch",
            "Outcome imports must not mix tenants in one validation/import batch.",
            next_action="Split the source export by tenant and rerun validation.",
        )
    if expected_module_key and len(module_keys) > 1:
        _add_issue(
            issues,
            "blocker",
            "mixed_module_batch",
            "This outcome validation expects one module scope.",
            next_action=f"Split the source export by module and rerun for {expected_module_key}.",
        )
    elif not expected_module_key and len(module_keys) > 1:
        _add_issue(
            issues,
            "warning",
            "mixed_module_batch",
            "Outcome import contains multiple module keys; verify each module entitlement before production sync.",
            next_action="Prefer one module per import batch unless the customer has approved a multi-module sync.",
            blocks_live_sync=False,
        )

    blockers = [issue for issue in issues if issue["severity"] == "blocker"]
    warnings = [issue for issue in issues if issue["severity"] == "warning"]
    row_blockers = {
        int(issue["row_number"])
        for issue in blockers
        if issue.get("row_number") not in (None, "")
    }
    row_warnings = {
        int(issue["row_number"])
        for issue in warnings
        if issue.get("row_number") not in (None, "")
    }
    header_blocked = any(issue["code"] == "missing_required_column" for issue in blockers)
    valid_row_count = 0 if header_blocked else max(0, len(rows) - len(row_blockers))
    stage_counts: dict[str, int] = {}
    for row in rows:
        stage = _norm_lower(row.get("outcome_stage"))
        if stage:
            stage_counts[stage] = stage_counts.get(stage, 0) + 1

    if blockers:
        status = "blocked_until_outcome_input_fixes"
        live_sync_decision = "blocked_until_input_fixes"
    elif production_ok:
        status = "ready_for_live_outcome_sync"
        live_sync_decision = "ready_for_live_sync"
    else:
        status = "ready_for_customer_review_live_sync_blocked"
        live_sync_decision = "blocked_until_live_proof"

    paths = {
        "outcome_import_validation": str(out_dir / "outcome_import_validation.json"),
        "outcome_import_validation_markdown": str(out_dir / "OUTCOME_IMPORT_VALIDATION.md"),
        "outcome_import_issues": str(out_dir / "OUTCOME_IMPORT_ISSUES.csv"),
        "outcome_import_review_rows": str(out_dir / "OUTCOME_IMPORT_REVIEW_ROWS.csv"),
    }
    report = {
        "report_type": "homepilot_outcome_import_validation",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": status,
        "sync_decision": live_sync_decision,
        "live_sync_decision": live_sync_decision,
        "input_label": input_label,
        "synthetic_fixture": synthetic_fixture,
        "scope": {
            "expected_tenant_id": expected_tenant_id,
            "expected_module_key": expected_module_key,
            "require_partner_scope": require_partner_scope,
        },
        "summary": {
            "row_count": len(rows),
            "valid_row_count": valid_row_count,
            "blocker_count": len(blockers),
            "warning_count": len(warnings),
            "tenant_count": len(tenant_ids),
            "module_count": len(module_keys),
            "partner_count": len(partner_ids),
            "stage_count": len(stage_counts),
            "amount_total_ex_vat": round(amount_total, 2),
            "production_verified": production_ok,
            "production_verified_label": f"production_verified={str(production_ok).lower()}",
            "secret_scan_status": "not_run",
        },
        "stage_counts": stage_counts,
        "allowed_outcome_stages": sorted(allowed_stages),
        "issues": issues,
        "review_rows": _review_rows(rows, row_blockers, row_warnings),
        "guardrails": {
            "dry_run_only": True,
            "derived_review_surface": True,
            "non_mutating": True,
            "no_supabase_writes": True,
            "no_crm_writes": True,
            "no_outreach_authorized": True,
            "no_raw_contact_data": True,
            "raw_contact_values_redacted": True,
            "tenant_module_partner_scope_required": True,
            "synthetic_fixture_labelled": synthetic_fixture,
            "production_requires_live_proof": True,
        },
        "paths": paths,
        "secret_scan": {"status": "not_run", "issue_count": 0, "findings": []},
    }
    write_json(Path(paths["outcome_import_validation"]), report)
    write_text(Path(paths["outcome_import_validation_markdown"]), render_markdown(report))
    write_csv(Path(paths["outcome_import_issues"]), issues, ISSUE_FIELDS)
    write_csv(Path(paths["outcome_import_review_rows"]), report["review_rows"], REVIEW_ROW_FIELDS)
    scan = _secret_scan([Path(path) for path in paths.values()])
    report["secret_scan"] = scan
    report["summary"]["secret_scan_status"] = scan["status"]
    if scan["status"] != "pass":
        report["status"] = "failed_secret_scan"
        report["live_sync_decision"] = "blocked_until_secret_scan_passes"
    write_json(Path(paths["outcome_import_validation"]), report)
    write_text(Path(paths["outcome_import_validation_markdown"]), render_markdown(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate HomePilot outcome import CSV in dry-run mode")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--input-csv", type=Path)
    parser.add_argument("--outcome-contract", type=Path)
    parser.add_argument("--expected-tenant")
    parser.add_argument("--expected-module")
    parser.add_argument("--release-label", default="local")
    parser.add_argument("--no-require-partner-scope", action="store_true")
    parser.add_argument("--production-verified", action="store_true")
    args = parser.parse_args()
    report = build_outcome_import_validation_pack(
        args.out_dir,
        input_csv=args.input_csv,
        outcome_contract=load_json(args.outcome_contract),
        expected_tenant_id=args.expected_tenant,
        expected_module_key=args.expected_module,
        release_label=args.release_label,
        require_partner_scope=not args.no_require_partner_scope,
        production_verified=True if args.production_verified else None,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": report["status"],
        "live_sync_decision": report["live_sync_decision"],
        "rows": report["summary"]["row_count"],
        "blockers": report["summary"]["blocker_count"],
        "warnings": report["summary"]["warning_count"],
        "markdown": report["paths"]["outcome_import_validation_markdown"],
        "issues_csv": report["paths"]["outcome_import_issues"],
        "review_rows_csv": report["paths"]["outcome_import_review_rows"],
    }, indent=2, ensure_ascii=False))
    if report["secret_scan"]["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
