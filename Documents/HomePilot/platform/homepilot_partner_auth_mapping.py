#!/usr/bin/env python3
"""
Build a guarded HomePilot partner Auth mapping pack.

This pack bridges the gap between a first-wave partner roster and real
Supabase Auth users. It is non-mutating by default: it validates mappings and
emits review SQL only when the first-wave launch gate is authorized and every
partner has a valid Auth user id.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECRET_REF_RE = re.compile(r"^(secret|vault|1password|op|secure_channel|customer_system)://", re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+?\d[\s().-]*){8,}")


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


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_lower(value: Any) -> str:
    return _norm(value).lower()


def _valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (TypeError, ValueError):
        return False
    return True


def _raw_phone_detected(value: Any) -> bool:
    text = _norm(value)
    digits = re.sub(r"\D", "", text)
    return len(digits) >= 9 and bool(PHONE_RE.fullmatch(text))


def _raw_contact_detected(value: Any) -> bool:
    text = _norm(value)
    if not text or SECRET_REF_RE.search(text):
        return False
    return bool(EMAIL_RE.search(text) or _raw_phone_detected(text))


def _secret_ref_status(value: Any) -> str:
    text = _norm(value)
    if not text:
        return "missing"
    if SECRET_REF_RE.search(text):
        return "secret_reference_present"
    if _raw_contact_detected(text):
        return "raw_contact_blocked"
    return "non_secret_reference_needs_review"


def _safe_free_text(value: Any) -> str:
    text = _norm(value)
    if not text:
        return ""
    if SECRET_REF_RE.search(text):
        return "[secret-reference]"
    if _raw_contact_detected(text):
        return "[raw-contact-redacted]"
    if len(text) > 160:
        return f"{text[:157]}..."
    return text


def _read_csv(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [{key: _norm(value) for key, value in row.items()} for row in reader]


def _sql_literal(value: Any) -> str:
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def _scenario(import_plan: dict[str, Any]) -> dict[str, Any]:
    scenario = import_plan.get("scenario", {})
    return {
        "tenant_slug": scenario.get("tenant_slug", "tenant"),
        "tenant_id_candidate": scenario.get("tenant_id_candidate", ""),
        "module_key": scenario.get("module_key", "facadepilot"),
        "expected_partner_count": int(scenario.get("expected_partner_count") or 0),
        "network_shape": scenario.get("network_shape", "producer tenant with partner-scoped campaign records"),
    }


def expected_partner_rows(import_plan: dict[str, Any], expected_partner_count: int = 10) -> list[dict[str, str]]:
    partners = []
    for row in import_plan.get("partner_scope_records", []):
        partners.append({
            "partner_id": _norm_lower(row.get("partner_id")),
            "partner_name": _norm(row.get("partner_name")),
            "role": _norm(row.get("portal_role")) or "partner_renovator",
            "source": "first_campaign_import_plan",
        })
    count = max(int(expected_partner_count or 0), 1)
    if partners and len(partners) >= count:
        return partners
    existing = {_norm_lower(row.get("partner_id")) for row in partners}
    placeholders = [
        {
            "partner_id": f"customer_to_confirm_{index:02d}",
            "partner_name": "customer_to_confirm",
            "role": "partner_renovator",
            "source": "customer_input_required",
        }
        for index in range(1, count + 1)
        if f"customer_to_confirm_{index:02d}" not in existing
    ]
    return (partners + placeholders)[:count]


def build_mapping_rows(
    expected_partners: list[dict[str, str]],
    supplied_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    supplied_by_partner = {_norm_lower(row.get("partner_id")): row for row in supplied_rows if _norm(row.get("partner_id"))}
    rows: list[dict[str, str]] = []
    for partner in expected_partners:
        partner_id = _norm_lower(partner.get("partner_id"))
        supplied = supplied_by_partner.get(partner_id, {})
        user_id = _norm(supplied.get("supabase_user_id"))
        raw_secret_ref = _norm(
            supplied.get("auth_email_ref")
            or supplied.get("secret_channel_ref")
            or supplied.get("auth_email_or_secret_channel_ref")
        )
        contact_reference_status = _secret_ref_status(raw_secret_ref)
        safe_secret_ref = "[raw-contact-redacted]" if contact_reference_status == "raw_contact_blocked" else raw_secret_ref
        rows.append({
            "partner_id": partner_id,
            "partner_name": _norm(supplied.get("partner_name") or partner.get("partner_name")),
            "role": _norm(supplied.get("role") or partner.get("role") or "partner_renovator"),
            "supabase_user_id": user_id,
            "auth_email_ref": safe_secret_ref,
            "mapping_status": _norm(supplied.get("mapping_status") or "pending_customer_it"),
            "source": _norm(partner.get("source")),
            "uuid_status": "valid" if user_id and _valid_uuid(user_id) else "missing" if not user_id else "invalid",
            "contact_reference_status": contact_reference_status,
            "notes": _safe_free_text(supplied.get("notes")),
        })
    known_ids = {_norm_lower(row.get("partner_id")) for row in expected_partners}
    for row in supplied_rows:
        partner_id = _norm_lower(row.get("partner_id"))
        if partner_id and partner_id not in known_ids:
            raw_secret_ref = _norm(row.get("auth_email_ref") or row.get("secret_channel_ref") or row.get("auth_email_or_secret_channel_ref"))
            contact_reference_status = _secret_ref_status(raw_secret_ref)
            safe_secret_ref = "[raw-contact-redacted]" if contact_reference_status == "raw_contact_blocked" else raw_secret_ref
            user_id = _norm(row.get("supabase_user_id"))
            rows.append({
                "partner_id": partner_id,
                "partner_name": _norm(row.get("partner_name")),
                "role": _norm(row.get("role") or "partner_renovator"),
                "supabase_user_id": user_id,
                "auth_email_ref": safe_secret_ref,
                "mapping_status": _norm(row.get("mapping_status") or "unexpected_partner"),
                "source": "mapping_file_only",
                "uuid_status": "valid" if user_id and _valid_uuid(user_id) else "missing" if not user_id else "invalid",
                "contact_reference_status": contact_reference_status,
                "notes": _safe_free_text(row.get("notes")),
            })
    return rows


def build_issues(
    rows: list[dict[str, str]],
    expected_partners: list[dict[str, str]],
    launch_gate: dict[str, Any],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    expected_ids = {_norm_lower(row.get("partner_id")) for row in expected_partners}
    user_counts: dict[str, int] = {}
    partner_counts: dict[str, int] = {}
    for row in rows:
        partner_id = _norm_lower(row.get("partner_id"))
        user_id = _norm_lower(row.get("supabase_user_id"))
        partner_counts[partner_id] = partner_counts.get(partner_id, 0) + 1
        if user_id:
            user_counts[user_id] = user_counts.get(user_id, 0) + 1

    if not launch_gate.get("launch_authorized"):
        issues.append({
            "severity": "blocker",
            "issue_key": "first_wave_launch_not_authorized",
            "partner_id": "",
            "field": "launch_authorized",
            "detail": "Partner membership SQL stays comment-only until FIRST_WAVE_LAUNCH_GATE has launch_authorized=true.",
            "next_action": "Resolve first-wave launch gate blockers and archive explicit customer go/no-go.",
        })

    for row in rows:
        partner_id = _norm_lower(row.get("partner_id"))
        if partner_id.startswith("customer_to_confirm"):
            issues.append({
                "severity": "blocker",
                "issue_key": "partner_roster_missing",
                "partner_id": partner_id,
                "field": "partner_id",
                "detail": "Customer-approved partner roster is not available yet.",
                "next_action": "Fill PARTNER_ROSTER_TEMPLATE.csv and rerun first-campaign input validation.",
            })
        if partner_id not in expected_ids:
            issues.append({
                "severity": "blocker",
                "issue_key": "unexpected_partner_id",
                "partner_id": partner_id,
                "field": "partner_id",
                "detail": "Mapping row is not present in the approved partner scope records.",
                "next_action": "Correct the partner_id or update the approved partner roster before membership review.",
            })
        if partner_counts.get(partner_id, 0) > 1:
            issues.append({
                "severity": "blocker",
                "issue_key": "duplicate_partner_id",
                "partner_id": partner_id,
                "field": "partner_id",
                "detail": "Partner appears more than once in the mapping output.",
                "next_action": "Keep one reviewed mapping row per partner.",
            })
        if not row.get("supabase_user_id"):
            issues.append({
                "severity": "blocker",
                "issue_key": "supabase_user_id_missing",
                "partner_id": partner_id,
                "field": "supabase_user_id",
                "detail": "Real Supabase Auth user id is missing.",
                "next_action": "Create/invite the user in Supabase Auth, then paste only the user UUID here.",
            })
        elif row.get("uuid_status") != "valid":
            issues.append({
                "severity": "blocker",
                "issue_key": "supabase_user_id_invalid",
                "partner_id": partner_id,
                "field": "supabase_user_id",
                "detail": "Supabase user id is not a valid UUID.",
                "next_action": "Replace with the exact Supabase Auth user UUID.",
            })
        if row.get("supabase_user_id") and user_counts.get(_norm_lower(row.get("supabase_user_id")), 0) > 1:
            issues.append({
                "severity": "blocker",
                "issue_key": "duplicate_supabase_user_id",
                "partner_id": partner_id,
                "field": "supabase_user_id",
                "detail": "Same Supabase Auth user id is mapped to multiple partners.",
                "next_action": "Use one Auth user per partner-scoped membership unless customer IT explicitly approves otherwise.",
            })
        if row.get("contact_reference_status") == "raw_contact_blocked":
            issues.append({
                "severity": "blocker",
                "issue_key": "raw_contact_reference",
                "partner_id": partner_id,
                "field": "auth_email_ref",
                "detail": "Raw email or phone-like value was found in the mapping reference.",
                "next_action": "Move personal contact details to the approved customer system or secret channel and keep only a secret:// reference here.",
            })
        elif row.get("contact_reference_status") in {"missing", "non_secret_reference_needs_review"}:
            issues.append({
                "severity": "warning",
                "issue_key": "secret_channel_reference_missing",
                "partner_id": partner_id,
                "field": "auth_email_ref",
                "detail": "A secret-channel reference is recommended so raw personal contact data stays out of the data room.",
                "next_action": "Add secret://, vault://, op://, or customer_system:// reference for customer IT.",
            })
    return issues


def _statement_count(sql: str) -> int:
    statements = []
    for raw in sql.split(";"):
        lines = [line for line in raw.splitlines() if not line.strip().startswith("--")]
        if "\n".join(lines).strip():
            statements.append(raw)
    return len(statements)


def render_sql(report: dict[str, Any], rows: list[dict[str, str]]) -> str:
    scenario = report["scenario"]
    if report["sql_mode"] != "membership_review_sql_generated_not_applied":
        lines = [
            "-- HomePilot partner Auth mapping review.",
            f"-- Release: {report['release_label']}",
            f"-- Generated: {report['created_at']}",
            f"-- Status: {report['status']}",
            f"-- Launch authorized: {str(report['launch_authorized']).lower()}",
            "--",
            "-- No executable membership SQL is generated.",
            "-- Requirements before SQL can be generated:",
            "-- 1. FIRST_WAVE_LAUNCH_GATE has launch_authorized=true.",
            "-- 2. Every approved partner has one valid Supabase Auth user UUID.",
            "-- 3. No duplicate partner/user ids and no raw contact references.",
            "-- 4. Customer IT reviews PARTNER_AUTH_MAPPING.md and PARTNER_AUTH_MAPPING_ISSUES.csv.",
            "",
        ]
        for issue in report["issues"][:20]:
            lines.append(f"-- {issue['severity']}: {issue['issue_key']} {issue['partner_id']} - {issue['detail']}")
        lines.append("")
        return "\n".join(lines)

    lines = [
        "-- HomePilot partner membership review SQL.",
        f"-- Release: {report['release_label']}",
        f"-- Generated: {report['created_at']}",
        "-- Review with customer IT; do not run before live schema/RLS/customer-access proof is archived.",
        "",
        "begin;",
        "",
    ]
    for row in rows:
        if row.get("uuid_status") != "valid":
            continue
        lines += [
            "insert into public.homepilot_memberships (tenant_id, user_id, role, partner_id)",
            "values (",
            f"  {_sql_literal(scenario['tenant_id_candidate'])}::uuid,",
            f"  {_sql_literal(row['supabase_user_id'])}::uuid,",
            f"  {_sql_literal(row['role'] or 'partner_renovator')},",
            f"  {_sql_literal(row['partner_id'])}",
            ")",
            "on conflict (tenant_id, user_id) do update set",
            "  role = excluded.role,",
            "  partner_id = excluded.partner_id,",
            "  updated_at = now();",
            "",
        ]
    lines += [
        "commit;",
        "",
    ]
    return "\n".join(lines)


def render_markdown(report: dict[str, Any]) -> str:
    scenario = report["scenario"]
    lines = [
        "# HomePilot Partner Auth Mapping",
        "",
        f"Release: {report['release_label']}",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        f"SQL mode: {report['sql_mode']}",
        f"Launch authorized: {str(report['launch_authorized']).lower()}",
        "",
        "This pack tells DAW, customer IT, and HomePilot how each partner renovator will be linked to a real Supabase Auth user before portal access is enabled.",
        "It is intentionally separate from the database handoff so partner access cannot quietly become live without Auth IDs, launch authorization, and review.",
        "",
        "## Scenario",
        "",
        f"- Tenant: {scenario['tenant_slug']}",
        f"- Tenant id candidate: {scenario['tenant_id_candidate']}",
        f"- Module: {scenario['module_key']}",
        f"- Expected partners: {report['summary']['expected_partner_count']}",
        f"- Mapped partners: {report['summary']['mapped_partner_count']}",
        f"- Blockers: {report['summary']['blockers']}",
        "",
        "## What Customer IT Must Fill",
        "",
        "- `partner_id` from the approved partner roster.",
        "- `partner_name` for human review.",
        "- `role`, normally `partner_renovator`.",
        "- `supabase_user_id`, the real Supabase Auth UUID.",
        "- `auth_email_ref`, a secret-channel reference such as `secret://...`, not a raw email address.",
        "",
        "## Guardrails",
        "",
    ]
    lines.extend(f"- {key.replace('_', ' ')}: {str(value).lower()}" for key, value in report["guardrails"].items())
    lines += [
        "",
        "## Issues",
        "",
    ]
    if not report["issues"]:
        lines.append("- No issues detected; review SQL may be generated when launch is authorized.")
    else:
        for issue in report["issues"][:25]:
            partner = f" for `{issue['partner_id']}`" if issue.get("partner_id") else ""
            lines.append(f"- {issue['severity']}: {issue['issue_key']}{partner} - {issue['next_action']}")
    lines += [
        "",
        "## Next Review",
        "",
        "- DAW/network manager confirms the partner roster.",
        "- Customer IT creates or invites Supabase Auth users through the approved process.",
        "- HomePilot reruns this pack and customer-access probes.",
        "- Partner portal access remains blocked until live RLS/customer-access verification passes.",
        "",
    ]
    return "\n".join(lines)


def write_template_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "partner_id",
        "partner_name",
        "role",
        "supabase_user_id",
        "auth_email_ref",
        "mapping_status",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "partner_id": row.get("partner_id", ""),
                "partner_name": row.get("partner_name", ""),
                "role": row.get("role", "partner_renovator"),
                "supabase_user_id": "",
                "auth_email_ref": "",
                "mapping_status": "pending_customer_it",
                "notes": "Fill only after Supabase Auth user exists; use secret-channel reference, not raw email.",
            })


def write_mapping_rows_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "partner_id",
        "partner_name",
        "role",
        "supabase_user_id",
        "auth_email_ref",
        "mapping_status",
        "source",
        "uuid_status",
        "contact_reference_status",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_issues_csv(path: Path, issues: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["severity", "issue_key", "partner_id", "field", "detail", "next_action"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in issues:
            writer.writerow({field: row.get(field, "") for field in fields})


def build_partner_auth_mapping_pack(
    out_dir: Path,
    import_plan: dict[str, Any],
    launch_gate: dict[str, Any],
    mapping_csv_path: Path | None = None,
    release_label: str = "local",
    expected_partner_count: int = 10,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    scenario = _scenario(import_plan)
    expected_count = scenario["expected_partner_count"] or expected_partner_count
    expected_partners = expected_partner_rows(import_plan, expected_count)
    supplied_rows = _read_csv(mapping_csv_path)
    rows = build_mapping_rows(expected_partners, supplied_rows)
    issues = build_issues(rows, expected_partners, launch_gate)
    blockers = sum(1 for issue in issues if issue["severity"] == "blocker")
    warnings = sum(1 for issue in issues if issue["severity"] == "warning")
    valid_rows = [row for row in rows if row["uuid_status"] == "valid" and _norm_lower(row.get("partner_id")) in {_norm_lower(p.get("partner_id")) for p in expected_partners}]
    launch_authorized = bool(launch_gate.get("launch_authorized"))
    ready_for_sql = launch_authorized and blockers == 0 and len(valid_rows) == len(expected_partners)
    raw_contact_input_detected = any(row.get("contact_reference_status") == "raw_contact_blocked" for row in rows)
    status = (
        "ready_for_membership_sql_review"
        if ready_for_sql
        else "blocked_until_partner_auth_mapping"
        if supplied_rows
        else "mapping_required"
    )
    report = {
        "mapping_type": "homepilot_partner_auth_mapping",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": status,
        "sql_mode": "membership_review_sql_generated_not_applied" if ready_for_sql else "comment_only_mapping_required",
        "launch_authorized": launch_authorized,
        "launch_decision": launch_gate.get("launch_decision", "unknown"),
        "scenario": scenario,
        "summary": {
            "expected_partner_count": len(expected_partners),
            "supplied_mapping_rows": len(supplied_rows),
            "mapped_partner_count": len(valid_rows),
            "missing_auth_user_ids": sum(1 for row in rows if not row.get("supabase_user_id")),
            "invalid_auth_user_ids": sum(1 for row in rows if row.get("supabase_user_id") and row.get("uuid_status") != "valid"),
            "blockers": blockers,
            "warnings": warnings,
            "executable_statement_count": 0,
            "raw_contact_input_detected": raw_contact_input_detected,
            "raw_contact_values_written": False,
            "secret_values_written": False,
        },
        "database_contract": {
            "target_table": "homepilot_memberships",
            "grain": "one membership row per tenant/Auth user, with partner_id filled for partner-scoped renovator access",
            "join_keys": ["tenant_id", "user_id", "role", "partner_id"],
            "deferred_until": [
                "customer-approved partner roster",
                "real Supabase Auth user UUIDs",
                "first-wave launch authorization",
                "customer IT SQL review",
                "live schema/RLS/customer-access proof",
            ],
        },
        "expected_partners": expected_partners,
        "mapping_rows": rows,
        "issues": issues,
        "guardrails": {
            "non_mutating_pack": True,
            "no_database_writes": True,
            "comment_only_sql_until_mapping_complete": True,
            "launch_authorized_required_before_membership_sql": True,
            "customer_it_review_required_before_apply": True,
            "live_rls_customer_access_required_before_partner_access": True,
            "partner_id_limits_partner_visibility": True,
            "no_cross_partner_raw_data": True,
            "no_secret_values_written": True,
            "raw_contact_input_detected": raw_contact_input_detected,
            "raw_contact_values_written": False,
        },
        "paths": {
            "partner_auth_mapping": str(out_dir / "partner_auth_mapping.json"),
            "partner_auth_mapping_markdown": str(out_dir / "PARTNER_AUTH_MAPPING.md"),
            "partner_auth_mapping_template": str(out_dir / "PARTNER_AUTH_MAPPING_TEMPLATE.csv"),
            "partner_auth_mapping_rows": str(out_dir / "PARTNER_AUTH_MAPPING_ROWS.csv"),
            "partner_auth_mapping_issues": str(out_dir / "PARTNER_AUTH_MAPPING_ISSUES.csv"),
            "partner_membership_review_sql": str(out_dir / "PARTNER_MEMBERSHIP_REVIEW.sql"),
        },
    }
    sql = render_sql(report, rows)
    report["summary"]["executable_statement_count"] = _statement_count(sql) if ready_for_sql else 0
    write_json(out_dir / "partner_auth_mapping.json", report)
    write_text(out_dir / "PARTNER_AUTH_MAPPING.md", render_markdown(report))
    write_template_csv(out_dir / "PARTNER_AUTH_MAPPING_TEMPLATE.csv", expected_partners)
    write_mapping_rows_csv(out_dir / "PARTNER_AUTH_MAPPING_ROWS.csv", rows)
    write_issues_csv(out_dir / "PARTNER_AUTH_MAPPING_ISSUES.csv", issues)
    write_text(out_dir / "PARTNER_MEMBERSHIP_REVIEW.sql", sql)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a guarded HomePilot partner Auth mapping pack")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--import-plan", required=True, type=Path)
    parser.add_argument("--launch-gate", required=True, type=Path)
    parser.add_argument("--mapping-csv", type=Path)
    parser.add_argument("--release-label", default="local")
    parser.add_argument("--expected-partner-count", type=int, default=10)
    args = parser.parse_args()

    report = build_partner_auth_mapping_pack(
        out_dir=args.out_dir,
        import_plan=load_json(args.import_plan) or {},
        launch_gate=load_json(args.launch_gate) or {},
        mapping_csv_path=args.mapping_csv,
        release_label=args.release_label,
        expected_partner_count=args.expected_partner_count,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": report["status"],
        "sql_mode": report["sql_mode"],
        "mapped_partner_count": report["summary"]["mapped_partner_count"],
        "partner_auth_mapping": report["paths"]["partner_auth_mapping"],
        "partner_membership_review_sql": report["paths"]["partner_membership_review_sql"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
