#!/usr/bin/env python3
"""
Build a non-mutating HomePilot first-campaign import/staging plan.

The input validator proves whether customer CSVs are complete. This module
turns those validated rows into a reviewable tenant/module/partner/campaign
staging manifest without touching Supabase, exposing secrets, or authorizing
outreach.
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

from homepilot_first_campaign_input_validation import build_first_campaign_input_validation


NAMESPACE = uuid.UUID("8f66a0fd-4a0e-51c1-a6c0-8b684479fb37")
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


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "homepilot"


def _stable_uuid(*parts: Any) -> str:
    return str(uuid.uuid5(NAMESPACE, ":".join(_norm(part).lower() for part in parts)))


def _safe_excerpt(value: Any) -> str:
    text = _norm(value)
    if not text:
        return ""
    if SECRET_REF_RE.search(text):
        return "[secret-reference]"
    if EMAIL_RE.search(text):
        return "[raw-email-redacted]"
    if _raw_phone_detected(text):
        return "[raw-phone-redacted]"
    if len(text) > 120:
        return f"{text[:117]}..."
    return text


def _raw_contact_detected(value: Any) -> bool:
    text = _norm(value)
    if not text or SECRET_REF_RE.search(text):
        return False
    return bool(EMAIL_RE.search(text) or _raw_phone_detected(text))


def _raw_phone_detected(value: Any) -> bool:
    text = _norm(value)
    digits = re.sub(r"\D", "", text)
    return len(digits) >= 9 and bool(PHONE_RE.fullmatch(text))


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [{key: _norm(value) for key, value in row.items()} for row in reader]


def _template_file(template_pack: dict[str, Any], key: str) -> str | None:
    for template in template_pack.get("templates", []):
        if template.get("key") == key:
            return str(template.get("file_name") or "")
    return None


def _template_rows(template_pack: dict[str, Any], input_dir: Path, key: str) -> list[dict[str, str]]:
    file_name = _template_file(template_pack, key)
    if not file_name:
        return []
    return _read_csv(input_dir / file_name)


def _first(rows: list[dict[str, str]]) -> dict[str, str]:
    return rows[0] if rows else {}


def _effective_validation(
    out_dir: Path,
    template_pack: dict[str, Any],
    input_dir: Path,
    release_label: str,
    expected_partner_count: int,
    live_proof_ready: bool,
    validation_report: dict[str, Any] | None,
) -> dict[str, Any]:
    if validation_report and bool(validation_report.get("live_proof_ready")) == bool(live_proof_ready):
        return validation_report
    return build_first_campaign_input_validation(
        out_dir=out_dir,
        template_pack=template_pack,
        input_dir=input_dir,
        release_label=release_label,
        expected_partner_count=expected_partner_count,
        live_proof_ready=live_proof_ready,
    )


def _campaign_name(module_key: str, partner_name: str, wave: str) -> str:
    module_label = module_key.replace("pilot", "Pilot").replace("_", " ").title()
    return f"DAW {module_label} {wave.title()} - {partner_name}"


def _partner_records(
    partners: list[dict[str, str]],
    territories: list[dict[str, str]],
    capacities: list[dict[str, str]],
) -> list[dict[str, Any]]:
    territory_by_partner = {_norm_lower(row.get("partner_id")): row for row in territories}
    capacity_by_partner = {_norm_lower(row.get("partner_id")): row for row in capacities}
    records: list[dict[str, Any]] = []
    for row in partners:
        partner_id = _norm_lower(row.get("partner_id"))
        territory = territory_by_partner.get(partner_id, {})
        capacity = capacity_by_partner.get(partner_id, {})
        contact_value = row.get("primary_contact_email_or_secret_channel_ref")
        records.append({
            "partner_id": partner_id,
            "partner_name": _safe_excerpt(row.get("partner_name")),
            "legal_company_name": _safe_excerpt(row.get("legal_company_name")),
            "region": _safe_excerpt(row.get("region") or territory.get("region")),
            "language": _safe_excerpt(row.get("language")),
            "portal_role": _safe_excerpt(row.get("portal_role")),
            "scope": "assigned_records_only" if "assigned_records_only" in _norm_lower(row.get("partner_scope_notes")) else "needs_scope_review",
            "territory": {
                "cities_or_postcodes": _safe_excerpt(territory.get("cities_or_postcodes") or row.get("cities_or_postcodes")),
                "included_postcodes": _safe_excerpt(territory.get("included_postcodes")),
                "excluded_postcodes": _safe_excerpt(territory.get("excluded_postcodes")),
                "overlap_rule": _safe_excerpt(territory.get("overlap_rule")),
                "capacity_cap": _safe_excerpt(territory.get("capacity_cap")),
            },
            "capacity": {
                "monthly": _safe_excerpt(capacity.get("capacity_per_month") or row.get("capacity_per_month")),
                "appointment_slots_per_week": _safe_excerpt(capacity.get("appointment_slots_per_week")),
                "response_sla_hours": _safe_excerpt(capacity.get("response_sla_hours")),
                "accepted_statuses": _safe_excerpt(capacity.get("accepted_statuses")),
                "rejection_reasons_allowed": _safe_excerpt(capacity.get("rejection_reasons_allowed")),
                "feedback_cadence": _safe_excerpt(capacity.get("feedback_cadence")),
            },
            "contact_reference_status": (
                "secret_reference_present" if SECRET_REF_RE.search(_norm(contact_value))
                else "raw_contact_blocked" if _raw_contact_detected(contact_value)
                else "missing_or_needs_secure_reference"
            ),
            "source_status": _safe_excerpt(row.get("status")),
        })
    return records


def _source_runs(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    source_runs: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        tenant_slug = _slugify(row.get("tenant_id") or "tenant")
        module_key = _norm_lower(row.get("module_key") or "facadepilot")
        source_runs.append({
            "source_key": f"property_source_{index:02d}",
            "source_file_name": _safe_excerpt(row.get("source_file_name")),
            "source_owner": _safe_excerpt(row.get("source_owner")),
            "tenant_slug": tenant_slug,
            "tenant_id_candidate": _stable_uuid("tenant", tenant_slug),
            "module_key": module_key,
            "allowed_modules": _safe_excerpt(row.get("allowed_modules")),
            "address_mapping": {
                "address_column": _safe_excerpt(row.get("address_column")),
                "postcode_column": _safe_excerpt(row.get("postcode_column")),
                "city_column": _safe_excerpt(row.get("city_column")),
            },
            "source_provenance": _safe_excerpt(row.get("source_provenance")),
            "refresh_date": _safe_excerpt(row.get("refresh_date")),
            "dedupe_rule": _safe_excerpt(row.get("dedupe_rule")),
            "public_data_used": _safe_excerpt(row.get("public_data_used")),
            "contact_basis_source": _safe_excerpt(row.get("contact_basis_source")),
            "import_status": _safe_excerpt(row.get("import_status")),
        })
    return source_runs


def _message_variants(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    for row in rows:
        variant = _slugify(row.get("message_variant") or "message")
        variants.append({
            "message_variant": variant,
            "language": _safe_excerpt(row.get("language")),
            "module_key": _norm_lower(row.get("module_key") or "facadepilot"),
            "channel": _safe_excerpt(row.get("channel")),
            "claim_summary": _safe_excerpt(row.get("claim_summary")),
            "prohibited_claims_checked": _safe_excerpt(row.get("prohibited_claims_checked")),
            "cta": _safe_excerpt(row.get("cta")),
            "opt_out_wording_status": "present" if _norm(row.get("opt_out_wording")) else "missing",
            "marketing_owner": _safe_excerpt(row.get("marketing_owner")),
            "legal_owner": _safe_excerpt(row.get("legal_owner")),
            "approval_status": _safe_excerpt(row.get("approval_status")),
            "approved_at": _safe_excerpt(row.get("approved_at")),
        })
    return variants


def _suppression_controls(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    for row in rows:
        controls.append({
            "suppression_id": _safe_excerpt(row.get("suppression_id")),
            "match_type": _safe_excerpt(row.get("match_type")),
            "property_or_hash_reference": _safe_excerpt(row.get("property_or_hash_reference")),
            "module_key": _norm_lower(row.get("module_key") or "facadepilot"),
            "reason": _safe_excerpt(row.get("reason")),
            "opt_out_method": _safe_excerpt(row.get("opt_out_method")),
            "effective_from": _safe_excerpt(row.get("effective_from")),
            "delete_after": _safe_excerpt(row.get("delete_after")),
            "raw_contact_detected": any(_raw_contact_detected(row.get(field)) for field in ("property_or_hash_reference", "notes")),
        })
    return controls


def _staging_rows(plan: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    scenario = plan["scenario"]
    tenant_slug = scenario["tenant_slug"]
    tenant_id = scenario["tenant_id_candidate"]
    module_key = scenario["module_key"]
    gate = plan["import_decision"]
    rows.append({
        "staging_area": "tenant_module",
        "target_table": "homepilot_tenant_modules",
        "operation": "upsert_review",
        "row_key": f"{tenant_slug}:{module_key}",
        "tenant_slug": tenant_slug,
        "tenant_id_candidate": tenant_id,
        "module_key": module_key,
        "partner_id": "",
        "partner_name": "",
        "campaign_key": "",
        "status": "planned",
        "import_gate": gate,
        "evidence": "PROPERTY_SOURCE_TEMPLATE.csv",
        "notes": "Enable module only after signed scope and live RLS proof.",
    })
    for partner in plan["partner_scope_records"]:
        partner_id = partner["partner_id"]
        rows.append({
            "staging_area": "partner_scope",
            "target_table": "homepilot_memberships",
            "operation": "invite_or_scope_review",
            "row_key": f"{tenant_slug}:{partner_id}",
            "tenant_slug": tenant_slug,
            "tenant_id_candidate": tenant_id,
            "module_key": module_key,
            "partner_id": partner_id,
            "partner_name": partner["partner_name"],
            "campaign_key": "",
            "status": partner["scope"],
            "import_gate": gate,
            "evidence": "PARTNER_ROSTER_TEMPLATE.csv; TERRITORY_ASSIGNMENT_TEMPLATE.csv",
            "notes": f"Portal role {partner['portal_role']}; contact {partner['contact_reference_status']}.",
        })
    for campaign in plan["campaign_records"]:
        rows.append({
            "staging_area": "campaign",
            "target_table": "homepilot_campaigns",
            "operation": "insert_review",
            "row_key": campaign["campaign_key"],
            "tenant_slug": tenant_slug,
            "tenant_id_candidate": tenant_id,
            "module_key": module_key,
            "partner_id": campaign["partner_id"],
            "partner_name": campaign["partner_name"],
            "campaign_key": campaign["campaign_key"],
            "status": campaign["status"],
            "import_gate": gate,
            "evidence": "PARTNER_ROSTER_TEMPLATE.csv; MESSAGE_APPROVAL_TEMPLATE.csv; PARTNER_CAPACITY_TEMPLATE.csv",
            "notes": campaign["name"],
        })
    for source_run in plan["property_source_runs"]:
        rows.append({
            "staging_area": "property_source_run",
            "target_table": "homepilot_source_runs",
            "operation": "insert_review",
            "row_key": source_run["source_key"],
            "tenant_slug": source_run["tenant_slug"],
            "tenant_id_candidate": source_run["tenant_id_candidate"],
            "module_key": source_run["module_key"],
            "partner_id": "",
            "partner_name": "",
            "campaign_key": "",
            "status": source_run["import_status"],
            "import_gate": gate,
            "evidence": "PROPERTY_SOURCE_TEMPLATE.csv",
            "notes": f"Source {source_run['source_file_name']} with {source_run['dedupe_rule']} dedupe.",
        })
    for control in plan["suppression_controls"]:
        rows.append({
            "staging_area": "suppression_control",
            "target_table": "homepilot_audit_events",
            "operation": "archive_review",
            "row_key": control["suppression_id"] or "suppression-confirmation",
            "tenant_slug": tenant_slug,
            "tenant_id_candidate": tenant_id,
            "module_key": control["module_key"],
            "partner_id": "",
            "partner_name": "",
            "campaign_key": "",
            "status": "reviewed" if not control["raw_contact_detected"] else "blocked_raw_contact",
            "import_gate": gate,
            "evidence": "SUPPRESSION_LIST_TEMPLATE.csv",
            "notes": f"Suppression reason {control['reason']}; delete after {control['delete_after']}.",
        })
    return rows


def render_import_plan_markdown(plan: dict[str, Any]) -> str:
    scenario = plan["scenario"]
    lines = [
        "# HomePilot First Campaign Import Plan",
        "",
        f"Release: {plan['release_label']}",
        f"Created: {plan['created_at']}",
        f"Status: {plan['status']}",
        f"Import decision: {plan['import_decision']}",
        f"First-wave decision: {plan['first_wave_decision']}",
        "",
        "This is a non-mutating staging plan. It explains which tenant, module, partner, campaign, source-run, suppression, and message records should be reviewed before any live import.",
        "",
        "## Scenario",
        "",
        f"- Tenant slug: {scenario['tenant_slug']}",
        f"- Tenant id candidate: {scenario['tenant_id_candidate']}",
        f"- Module: {scenario['module_key']}",
        f"- Expected partners: {scenario['expected_partner_count']}",
        f"- Partner records staged: {plan['summary']['partner_scope_records']}",
        f"- Campaign records staged: {plan['summary']['campaign_records']}",
        f"- Staging rows: {plan['summary']['staging_rows']}",
        "",
        "## Import Gates",
        "",
    ]
    for gate in plan["gates"]:
        lines.append(f"- {gate['gate']}: {gate['status']} - {gate['evidence']}")
    lines += [
        "",
        "## Partner Campaign Seeds",
        "",
        "| Partner | Campaign | Territory | Capacity | Status |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for campaign in plan["campaign_records"]:
        lines.append(
            f"| {campaign['partner_name']} | `{campaign['campaign_key']}` | "
            f"{campaign['territory']} | {campaign['capacity_per_month']} | {campaign['status']} |"
        )
    lines += [
        "",
        "## Blocked Until",
        "",
    ]
    if plan["blocked_steps"]:
        lines.extend(f"- {item}" for item in plan["blocked_steps"])
    else:
        lines.append("- Operator review and explicit customer go/no-go.")
    lines += [
        "",
        "## Guardrails",
        "",
        "- This plan does not write to Supabase.",
        "- This plan does not authorize outreach or partner portal access.",
        "- Raw email, phone, and secret-reference values are redacted from the generated artifacts.",
        "- Actual property target rows are created only after the approved property source is parsed, deduped, and live RLS/customer-access proof is archived.",
        "",
    ]
    return "\n".join(lines)


def _write_staging_rows_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "staging_area",
        "target_table",
        "operation",
        "row_key",
        "tenant_slug",
        "tenant_id_candidate",
        "module_key",
        "partner_id",
        "partner_name",
        "campaign_key",
        "status",
        "import_gate",
        "evidence",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def build_first_campaign_import_plan(
    out_dir: Path,
    template_pack: dict[str, Any],
    input_dir: Path,
    release_label: str = "local",
    expected_partner_count: int = 10,
    live_proof_ready: bool = False,
    validation_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    validation = _effective_validation(
        out_dir=out_dir,
        template_pack=template_pack,
        input_dir=input_dir,
        release_label=release_label,
        expected_partner_count=expected_partner_count,
        live_proof_ready=live_proof_ready,
        validation_report=validation_report,
    )
    partner_rows = _template_rows(template_pack, input_dir, "partner_roster_template")
    territory_rows = _template_rows(template_pack, input_dir, "territory_assignment_template")
    property_source_rows = _template_rows(template_pack, input_dir, "property_source_template")
    suppression_rows = _template_rows(template_pack, input_dir, "suppression_list_template")
    message_rows = _template_rows(template_pack, input_dir, "message_approval_template")
    capacity_rows = _template_rows(template_pack, input_dir, "partner_capacity_template")

    source_runs = _source_runs(property_source_rows)
    first_source = source_runs[0] if source_runs else {}
    tenant_slug = first_source.get("tenant_slug") or _slugify(_first(property_source_rows).get("tenant_id") or "tenant")
    tenant_id_candidate = first_source.get("tenant_id_candidate") or _stable_uuid("tenant", tenant_slug)
    module_key = first_source.get("module_key") or _norm_lower(_first(property_source_rows).get("module_key") or "facadepilot")
    partner_records = _partner_records(partner_rows, territory_rows, capacity_rows)
    messages = _message_variants(message_rows)
    suppressions = _suppression_controls(suppression_rows)
    message_keys = [message["message_variant"] for message in messages]

    customer_inputs_ready = validation.get("status") in {"customer_inputs_ready", "ready_for_first_wave"}
    if not customer_inputs_ready:
        status = "blocked_until_customer_input_fixes"
        import_decision = "do_not_import_customer_inputs_incomplete"
        first_wave_decision = "blocked_until_customer_input_fixes"
    elif not live_proof_ready:
        status = "staging_plan_ready_import_blocked"
        import_decision = "blocked_until_live_proof"
        first_wave_decision = "blocked_until_live_proof"
    else:
        status = "ready_for_live_import_review"
        import_decision = "ready_for_live_import_review"
        first_wave_decision = "ready_for_first_wave_review"

    campaign_records: list[dict[str, Any]] = []
    for index, partner in enumerate(partner_records, start=1):
        campaign_key = f"{tenant_slug}-{module_key}-wave-1-{_slugify(partner['partner_id'])}"
        campaign_records.append({
            "campaign_key": campaign_key,
            "campaign_id_candidate": _stable_uuid("campaign", tenant_slug, module_key, partner["partner_id"], "wave_1"),
            "tenant_id_candidate": tenant_id_candidate,
            "tenant_slug": tenant_slug,
            "module_key": module_key,
            "partner_id": partner["partner_id"],
            "partner_name": partner["partner_name"],
            "name": _campaign_name(module_key, partner["partner_name"], "wave 1"),
            "status": "planned_review" if customer_inputs_ready else "blocked_until_input_fixes",
            "wave": "wave_1",
            "territory": partner["territory"]["included_postcodes"] or partner["territory"]["cities_or_postcodes"],
            "capacity_per_month": partner["capacity"]["monthly"],
            "message_variants": message_keys,
            "metadata": {
                "partner_scope": partner["scope"],
                "response_sla_hours": partner["capacity"]["response_sla_hours"],
                "contact_reference_status": partner["contact_reference_status"],
                "source_status": partner["source_status"],
                "staging_order": index,
            },
        })

    gates = [
        {
            "gate": "customer_inputs",
            "status": "pass" if customer_inputs_ready else "blocked",
            "evidence": "FIRST_CAMPAIGN_INPUT_VALIDATION.md",
        },
        {
            "gate": "live_schema_rls_customer_access",
            "status": "pass" if live_proof_ready else "blocked",
            "evidence": "schema_verification.json, launch_report.json, customer_access_verification.json",
        },
        {
            "gate": "explicit_customer_go_no_go",
            "status": "blocked",
            "evidence": "Customer-approved go/no-go decision after staging review",
        },
        {
            "gate": "approved_property_target_parse",
            "status": "blocked",
            "evidence": "Approved source import run with dedupe and suppression applied",
        },
    ]
    blocked_steps = []
    if not customer_inputs_ready:
        blocked_steps.append("Fix customer CSV blockers from FIRST_CAMPAIGN_INPUT_ISSUES.csv.")
    if not live_proof_ready:
        blocked_steps.append("Archive live schema, RLS, partner-scope, and customer-access proof.")
    blocked_steps.extend([
        "Record explicit customer go/no-go before outreach.",
        "Parse the approved property source into tenant-scoped property/target rows after source and suppression review.",
    ])

    plan = {
        "plan_type": "homepilot_first_campaign_import_plan",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": status,
        "import_decision": import_decision,
        "first_wave_decision": first_wave_decision,
        "scenario": {
            "tenant_slug": tenant_slug,
            "tenant_id_candidate": tenant_id_candidate,
            "module_key": module_key,
            "expected_partner_count": expected_partner_count,
            "network_shape": "producer tenant with partner-scoped campaign records",
        },
        "validation": {
            "status": validation.get("status"),
            "first_wave_decision": validation.get("first_wave_decision"),
            "blockers": validation.get("summary", {}).get("blockers"),
            "warnings": validation.get("summary", {}).get("warnings"),
            "partner_count": validation.get("summary", {}).get("partner_count"),
        },
        "database_contract": {
            "planned_tables": [
                "homepilot_tenant_modules",
                "homepilot_memberships",
                "homepilot_campaigns",
                "homepilot_source_runs",
                "homepilot_audit_events",
            ],
            "deferred_until_property_file_parse": [
                "homepilot_properties",
                "homepilot_assessments",
                "homepilot_campaign_targets",
                "homepilot_interactions",
            ],
            "join_keys": ["tenant_id", "module_key", "partner_id", "campaign_id", "property_id"],
        },
        "partner_scope_records": partner_records,
        "campaign_records": campaign_records,
        "property_source_runs": source_runs,
        "suppression_controls": suppressions,
        "message_variants": messages,
        "gates": gates,
        "blocked_steps": blocked_steps,
        "guardrails": {
            "non_mutating_plan": True,
            "no_database_writes": True,
            "raw_contact_values_written": False,
            "secret_values_written": False,
            "customer_go_no_go_required_before_outreach": True,
            "live_rls_required_before_partner_access": True,
            "schema_apply_required_before_import": True,
        },
        "paths": {
            "import_plan": str(out_dir / "first_campaign_import_plan.json"),
            "import_plan_markdown": str(out_dir / "FIRST_CAMPAIGN_IMPORT_PLAN.md"),
            "staging_rows": str(out_dir / "FIRST_CAMPAIGN_STAGING_ROWS.csv"),
        },
    }
    staging_rows = _staging_rows(plan)
    plan["staging_rows"] = staging_rows
    plan["summary"] = {
        "partner_scope_records": len(partner_records),
        "campaign_records": len(campaign_records),
        "property_source_runs": len(source_runs),
        "suppression_controls": len(suppressions),
        "message_variants": len(messages),
        "staging_rows": len(staging_rows),
        "raw_contact_values_written": False,
        "secret_values_written": False,
    }
    write_json(out_dir / "first_campaign_import_plan.json", plan)
    write_text(out_dir / "FIRST_CAMPAIGN_IMPORT_PLAN.md", render_import_plan_markdown(plan))
    _write_staging_rows_csv(out_dir / "FIRST_CAMPAIGN_STAGING_ROWS.csv", staging_rows)
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a non-mutating HomePilot first-campaign import plan")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--template-pack", required=True, type=Path)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--release-label", default="local")
    parser.add_argument("--expected-partners", type=int, default=10)
    parser.add_argument("--live-proof-ready", action="store_true")
    args = parser.parse_args()

    template_pack = json.loads(args.template_pack.read_text(encoding="utf-8"))
    plan = build_first_campaign_import_plan(
        out_dir=args.out_dir,
        template_pack=template_pack,
        input_dir=args.input_dir,
        release_label=args.release_label,
        expected_partner_count=args.expected_partners,
        live_proof_ready=args.live_proof_ready,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": plan["status"],
        "import_decision": plan["import_decision"],
        "first_wave_decision": plan["first_wave_decision"],
        "import_plan": plan["paths"]["import_plan"],
        "import_plan_markdown": plan["paths"]["import_plan_markdown"],
        "staging_rows": plan["paths"]["staging_rows"],
    }, indent=2))


if __name__ == "__main__":
    main()
