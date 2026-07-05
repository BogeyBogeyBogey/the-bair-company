#!/usr/bin/env python3
"""
Build a guarded HomePilot first-wave database handoff pack.

The launch gate is the source of truth for whether a first wave may touch the
database. This module turns the validated staging plan into a reviewable
database handoff, but it emits executable SQL only when the launch gate says
`launch_authorized=true`.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def _sql_literal(value: Any) -> str:
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def _sql_jsonb(value: Any) -> str:
    return f"{_sql_literal(json.dumps(value or {}, ensure_ascii=False, sort_keys=True))}::jsonb"


def _campaign_status(value: Any) -> str:
    status = _norm(value).lower()
    if status in {"draft", "running", "paused", "completed", "archived"}:
        return status
    return "draft"


def _source_run_status(value: Any) -> str:
    status = _norm(value).lower()
    if status in {"planned", "running", "imported", "failed", "retired"}:
        return status
    return "planned"


def _statement_count(sql: str) -> int:
    statements = []
    for raw in sql.split(";"):
        lines = [line for line in raw.splitlines() if not line.strip().startswith("--")]
        if "\n".join(lines).strip():
            statements.append(raw)
    return len(statements)


def _scenario(import_plan: dict[str, Any]) -> dict[str, Any]:
    scenario = import_plan.get("scenario", {})
    return {
        "tenant_slug": scenario.get("tenant_slug", "tenant"),
        "tenant_id_candidate": scenario.get("tenant_id_candidate", ""),
        "module_key": scenario.get("module_key", "facadepilot"),
        "expected_partner_count": scenario.get("expected_partner_count", 0),
        "network_shape": scenario.get("network_shape", "producer tenant with partner-scoped campaign records"),
    }


def _row(
    staging_area: str,
    target_table: str,
    operation: str,
    row_key: str,
    status: str,
    evidence: str,
    notes: str,
    tenant_slug: str,
    tenant_id: str,
    module_key: str,
    partner_id: str = "",
    partner_name: str = "",
    campaign_key: str = "",
) -> dict[str, str]:
    return {
        "staging_area": staging_area,
        "target_table": target_table,
        "operation": operation,
        "row_key": row_key,
        "tenant_slug": tenant_slug,
        "tenant_id_candidate": tenant_id,
        "module_key": module_key,
        "partner_id": partner_id,
        "partner_name": partner_name,
        "campaign_key": campaign_key,
        "status": status,
        "evidence": evidence,
        "notes": notes,
    }


def build_review_rows(import_plan: dict[str, Any], launch_gate: dict[str, Any]) -> list[dict[str, str]]:
    scenario = _scenario(import_plan)
    tenant_slug = scenario["tenant_slug"]
    tenant_id = scenario["tenant_id_candidate"]
    module_key = scenario["module_key"]
    authorized = bool(launch_gate.get("launch_authorized"))
    write_status = "ready_for_review_sql" if authorized else "blocked_until_launch_authorized"
    rows = [
        _row(
            "tenant",
            "homepilot_tenants",
            "upsert_review_sql" if authorized else "blocked_review_only",
            tenant_slug,
            write_status,
            "FIRST_WAVE_LAUNCH_GATE.md",
            "Create or confirm the DAW/HomePilot tenant before module and campaign rows are applied.",
            tenant_slug,
            tenant_id,
            module_key,
        ),
        _row(
            "tenant_module",
            "homepilot_tenant_modules",
            "upsert_review_sql" if authorized else "blocked_review_only",
            f"{tenant_slug}:{module_key}",
            write_status,
            "FIRST_CAMPAIGN_IMPORT_PLAN.md",
            "Enable the module only after first-wave launch authorization and live RLS proof.",
            tenant_slug,
            tenant_id,
            module_key,
        ),
    ]
    for partner in import_plan.get("partner_scope_records", []):
        rows.append(_row(
            "partner_scope",
            "homepilot_memberships",
            "deferred_until_auth_user_ids",
            f"{tenant_slug}:{partner.get('partner_id', '')}",
            "deferred",
            "PARTNER_ROSTER_TEMPLATE.csv",
            "Partner portal scope requires real Supabase Auth user IDs; no membership SQL is generated here.",
            tenant_slug,
            tenant_id,
            module_key,
            partner_id=_norm(partner.get("partner_id")),
            partner_name=_norm(partner.get("partner_name")),
        ))
    for campaign in import_plan.get("campaign_records", []):
        rows.append(_row(
            "campaign",
            "homepilot_campaigns",
            "insert_review_sql" if authorized else "blocked_review_only",
            _norm(campaign.get("campaign_key")),
            write_status,
            "FIRST_CAMPAIGN_STAGING_ROWS.csv",
            _norm(campaign.get("name")) or "Partner campaign seed.",
            tenant_slug,
            tenant_id,
            module_key,
            partner_id=_norm(campaign.get("partner_id")),
            partner_name=_norm(campaign.get("partner_name")),
            campaign_key=_norm(campaign.get("campaign_key")),
        ))
    for source_run in import_plan.get("property_source_runs", []):
        rows.append(_row(
            "property_source_run",
            "homepilot_source_runs",
            "insert_review_sql" if authorized else "blocked_review_only",
            _norm(source_run.get("source_key")),
            write_status,
            "PROPERTY_SOURCE_TEMPLATE.csv",
            f"Source {_norm(source_run.get('source_file_name'))} remains provenance-only until the approved property file is parsed.",
            tenant_slug,
            tenant_id,
            module_key,
        ))
    for control in import_plan.get("suppression_controls", []):
        rows.append(_row(
            "suppression_control",
            "homepilot_audit_events",
            "archive_review_sql" if authorized else "blocked_review_only",
            _norm(control.get("suppression_id")) or "suppression-confirmation",
            "ready_for_audit" if authorized else "blocked_until_launch_authorized",
            "SUPPRESSION_LIST_TEMPLATE.csv",
            "Archive suppression evidence without writing raw personal contact values.",
            tenant_slug,
            tenant_id,
            module_key,
        ))
    rows.append(_row(
        "message_approval",
        "homepilot_audit_events",
        "archive_review_sql" if authorized else "blocked_review_only",
        f"{tenant_slug}:{module_key}:message-approval",
        "ready_for_audit" if authorized else "blocked_until_launch_authorized",
        "MESSAGE_APPROVAL_TEMPLATE.csv",
        "Archive approved claims, opt-out wording, and no-homeowner-intent language.",
        tenant_slug,
        tenant_id,
        module_key,
    ))
    rows.append(_row(
        "launch_gate",
        "homepilot_audit_events",
        "archive_review_sql" if authorized else "blocked_review_only",
        f"{tenant_slug}:{module_key}:first-wave-launch-gate",
        "ready_for_audit" if authorized else "blocked_until_launch_authorized",
        "FIRST_WAVE_LAUNCH_GATE.md",
        f"Launch decision: {launch_gate.get('launch_decision', 'unknown')}.",
        tenant_slug,
        tenant_id,
        module_key,
    ))
    rows.append(_row(
        "property_target_parse",
        "homepilot_properties; homepilot_campaign_targets; homepilot_interactions",
        "deferred_until_approved_property_file_parse",
        f"{tenant_slug}:{module_key}:property-targets",
        "deferred",
        "Approved source import run with dedupe and suppression applied",
        "Actual target/property rows are deliberately outside this first database handoff.",
        tenant_slug,
        tenant_id,
        module_key,
    ))
    return rows


def _blocked_sql(handoff: dict[str, Any]) -> str:
    blockers = [
        f"-- {gate.get('label', gate.get('key'))}: {gate.get('status')} - {gate.get('next_action')}"
        for gate in handoff.get("launch_gate", {}).get("gates", [])
        if gate.get("blocks_launch")
    ]
    if not blockers:
        blockers = ["-- Launch gate is not authorized; keep this as a review-only handoff."]
    lines = [
        "-- HomePilot first-wave database review.",
        f"-- Release: {handoff['release_label']}",
        f"-- Generated: {handoff['created_at']}",
        f"-- Status: {handoff['status']}",
        f"-- Launch decision: {handoff['launch_decision']}",
        "--",
        "-- No executable DML is generated because the first-wave launch gate is not authorized.",
        "-- Review FIRST_WAVE_DATABASE_HANDOFF.md and FIRST_WAVE_DATABASE_HANDOFF_CHECKLIST.csv first.",
        "--",
        "-- Blocking gates:",
        *blockers,
        "",
    ]
    return "\n".join(lines)


def _authorized_sql(handoff: dict[str, Any], import_plan: dict[str, Any]) -> str:
    scenario = handoff["scenario"]
    tenant_id = scenario["tenant_id_candidate"]
    tenant_slug = scenario["tenant_slug"]
    module_key = scenario["module_key"]
    tenant_name = tenant_slug.replace("-", " ").title()
    lines = [
        "-- HomePilot first-wave database review SQL.",
        f"-- Release: {handoff['release_label']}",
        f"-- Generated: {handoff['created_at']}",
        "-- Review with customer IT, then apply with psql --set ON_ERROR_STOP=1 only after final operator confirmation.",
        "",
        "begin;",
        "",
        "insert into public.homepilot_tenants (id, name, slug, subscription_tier, settings)",
        f"values ({_sql_literal(tenant_id)}::uuid, {_sql_literal(tenant_name)}, {_sql_literal(tenant_slug)}, 'enterprise', {_sql_jsonb({'source': 'first_wave_database_handoff'})})",
        "on conflict (id) do update set",
        "  name = excluded.name,",
        "  settings = public.homepilot_tenants.settings || excluded.settings,",
        "  updated_at = now();",
        "",
        "insert into public.homepilot_tenant_modules (tenant_id, module_key, enabled, settings)",
        f"values ({_sql_literal(tenant_id)}::uuid, {_sql_literal(module_key)}, true, {_sql_jsonb({'source': 'first_wave_database_handoff'})})",
        "on conflict (tenant_id, module_key) do update set",
        "  enabled = excluded.enabled,",
        "  settings = public.homepilot_tenant_modules.settings || excluded.settings;",
        "",
        "-- Partner memberships are intentionally deferred until real Supabase Auth user IDs exist.",
        "",
    ]
    for campaign in import_plan.get("campaign_records", []):
        metadata = dict(campaign.get("metadata") or {})
        metadata.update({
            "source": "first_wave_database_handoff",
            "campaign_key": campaign.get("campaign_key"),
            "original_staging_status": campaign.get("status"),
            "capacity_per_month": campaign.get("capacity_per_month"),
        })
        territory = {
            "label": campaign.get("territory"),
            "wave": campaign.get("wave"),
        }
        message_variants = campaign.get("message_variants") or []
        lines += [
            "insert into public.homepilot_campaigns (id, tenant_id, module_key, name, channel, status, territory, message_variant, partner_id, partner_name, metadata)",
            "values (",
            f"  {_sql_literal(campaign.get('campaign_id_candidate'))}::uuid,",
            f"  {_sql_literal(tenant_id)}::uuid,",
            f"  {_sql_literal(module_key)},",
            f"  {_sql_literal(campaign.get('name'))},",
            "  'direct_mail',",
            f"  {_sql_literal(_campaign_status(campaign.get('status')))},",
            f"  {_sql_jsonb(territory)},",
            f"  {_sql_literal(message_variants[0] if message_variants else '')},",
            f"  {_sql_literal(campaign.get('partner_id'))},",
            f"  {_sql_literal(campaign.get('partner_name'))},",
            f"  {_sql_jsonb(metadata)}",
            ")",
            "on conflict (id) do update set",
            "  name = excluded.name,",
            "  status = excluded.status,",
            "  territory = excluded.territory,",
            "  message_variant = excluded.message_variant,",
            "  partner_id = excluded.partner_id,",
            "  partner_name = excluded.partner_name,",
            "  metadata = public.homepilot_campaigns.metadata || excluded.metadata,",
            "  updated_at = now();",
            "",
        ]
    for source_run in import_plan.get("property_source_runs", []):
        source_key = _norm(source_run.get("source_key"))
        source_file = _norm(source_run.get("source_file_name")) or source_key
        source_url = _norm(source_run.get("source_provenance")) or f"customer://approved-property-source/{source_key}"
        metadata = {
            "source_key": source_key,
            "source_file_name": source_file,
            "dedupe_rule": source_run.get("dedupe_rule"),
            "contact_basis_source": source_run.get("contact_basis_source"),
            "address_mapping": source_run.get("address_mapping"),
            "public_data_used": source_run.get("public_data_used"),
        }
        lines += [
            "insert into public.homepilot_source_runs (id, tenant_id, module_key, source_name, publisher, source_url, licence, allowed_use, attribution, retrieval_started_at, update_frequency, transform_version, operator, status, metadata)",
            "values (",
            f"  {_sql_literal(source_key)},",
            f"  {_sql_literal(tenant_id)}::uuid,",
            f"  {_sql_literal(source_run.get('module_key') or module_key)},",
            f"  {_sql_literal(source_file)},",
            "  'customer-approved source',",
            f"  {_sql_literal(source_url)},",
            "  'customer-approved first-wave source',",
            "  'first-wave campaign import after launch authorization',",
            "  'Retain customer/source attribution in the launch evidence room',",
            "  now(),",
            f"  {_sql_literal(source_run.get('refresh_date') or 'customer-controlled')},",
            f"  {_sql_literal(handoff['release_label'])},",
            "  'HomePilot operator',",
            f"  {_sql_literal(_source_run_status(source_run.get('import_status')))},",
            f"  {_sql_jsonb(metadata)}",
            ")",
            "on conflict (id) do update set",
            "  status = excluded.status,",
            "  metadata = public.homepilot_source_runs.metadata || excluded.metadata;",
            "",
        ]
    audit_payloads = [
        {
            "subject_type": "first_wave_database_handoff",
            "subject_id": handoff["handoff_id"],
            "severity": "info",
            "details": {
                "launch_decision": handoff["launch_decision"],
                "launch_authorized": handoff["launch_authorized"],
                "review_rows": handoff["summary"]["review_rows"],
                "campaign_records": handoff["summary"]["campaign_records"],
            },
        },
        {
            "subject_type": "first_wave_launch_gate",
            "subject_id": handoff["launch_decision"],
            "severity": "info",
            "details": {
                "gate_count": handoff["launch_gate"].get("summary", {}).get("gates"),
                "passed_gates": handoff["launch_gate"].get("summary", {}).get("passed_gates"),
                "customer_go_no_go_ready": handoff["launch_gate"].get("summary", {}).get("customer_go_no_go_ready"),
            },
        },
    ]
    for payload in audit_payloads:
        lines += [
            "insert into public.homepilot_audit_events (tenant_id, module_key, event_type, subject_type, subject_id, severity, details)",
            "values (",
            f"  {_sql_literal(tenant_id)}::uuid,",
            f"  {_sql_literal(module_key)},",
            "  'preflight_run',",
            f"  {_sql_literal(payload['subject_type'])},",
            f"  {_sql_literal(payload['subject_id'])},",
            f"  {_sql_literal(payload['severity'])},",
            f"  {_sql_jsonb(payload['details'])}",
            ");",
            "",
        ]
    lines += [
        "-- Property rows, campaign targets, interactions, and partner memberships are deferred to the approved property-file import.",
        "commit;",
        "",
    ]
    return "\n".join(lines)


def render_sql(handoff: dict[str, Any], import_plan: dict[str, Any]) -> str:
    if not handoff["launch_authorized"]:
        return _blocked_sql(handoff)
    return _authorized_sql(handoff, import_plan)


def render_markdown(handoff: dict[str, Any]) -> str:
    scenario = handoff["scenario"]
    lines = [
        "# HomePilot First Wave Database Handoff",
        "",
        f"Release: {handoff['release_label']}",
        f"Created: {handoff['created_at']}",
        f"Status: {handoff['status']}",
        f"Launch decision: {handoff['launch_decision']}",
        f"Launch authorized: {str(handoff['launch_authorized']).lower()}",
        f"SQL mode: {handoff['sql_mode']}",
        "",
        "This handoff explains what may be reviewed for Supabase after the first-wave launch gate. It is intentionally conservative: blocked gates produce a comment-only SQL file.",
        "",
        "## Scenario",
        "",
        f"- Tenant: {scenario['tenant_slug']}",
        f"- Tenant id candidate: {scenario['tenant_id_candidate']}",
        f"- Module: {scenario['module_key']}",
        f"- Partner campaigns: {handoff['summary']['campaign_records']}",
        f"- Review rows: {handoff['summary']['review_rows']}",
        "",
        "## Database Scope",
        "",
        "| Table | Treatment |",
        "| --- | --- |",
    ]
    for table in handoff["database_contract"]["review_tables"]:
        lines.append(f"| `{table['table']}` | {table['treatment']} |")
    lines += [
        "",
        "## Guardrails",
        "",
    ]
    lines.extend(f"- {label.replace('_', ' ')}: {str(value).lower()}" for label, value in handoff["guardrails"].items())
    lines += [
        "",
        "## Next Review",
        "",
    ]
    if handoff["launch_authorized"]:
        lines.append("- Review `FIRST_WAVE_DATABASE_REVIEW.sql` with customer IT before applying it.")
        lines.append("- After apply, rerun live schema verification and customer-access probes.")
    else:
        lines.append("- Resolve the blocking launch-gate items before asking customer IT to review executable SQL.")
        lines.append("- Use the CSV checklist to assign remaining evidence owners.")
    lines.append("")
    return "\n".join(lines)


def write_review_rows_csv(path: Path, rows: list[dict[str, str]]) -> None:
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
        "evidence",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_checklist_csv(path: Path, handoff: dict[str, Any]) -> None:
    rows = [
        {
            "key": "launch_authorized",
            "status": "pass" if handoff["launch_authorized"] else "blocked",
            "owner": "DAW executive sponsor + HomePilot operator",
            "evidence": "FIRST_WAVE_LAUNCH_GATE.md",
            "next_action": "Archive launch_authorized=true before executable database SQL is used.",
        },
        {
            "key": "customer_it_sql_review",
            "status": "ready" if handoff["launch_authorized"] else "not_started",
            "owner": "Customer IT + HomePilot operator",
            "evidence": "FIRST_WAVE_DATABASE_REVIEW.sql",
            "next_action": "Review SQL, tenant IDs, partner IDs, source provenance, and post-apply verification commands.",
        },
        {
            "key": "partner_auth_mapping",
            "status": "deferred",
            "owner": "Customer success + IT owner",
            "evidence": "PARTNER_ROSTER_TEMPLATE.csv",
            "next_action": "Map partner contacts to real Supabase Auth user IDs before membership rows are inserted.",
        },
        {
            "key": "post_apply_verification",
            "status": "blocked" if not handoff["launch_authorized"] else "required_after_apply",
            "owner": "HomePilot operator",
            "evidence": "schema_verification.json; customer_access_verification.json",
            "next_action": "Run live schema verification and customer-access probes after any approved apply.",
        },
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["key", "status", "owner", "evidence", "next_action"])
        writer.writeheader()
        writer.writerows(rows)


def build_first_wave_database_handoff(
    out_dir: Path,
    input_validation: dict[str, Any],
    import_plan: dict[str, Any],
    launch_gate: dict[str, Any],
    release_label: str = "local",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    scenario = _scenario(import_plan)
    authorized = bool(launch_gate.get("launch_authorized"))
    review_rows = build_review_rows(import_plan, launch_gate)
    created_at = utc_now()
    status = "ready_for_database_import_review" if authorized else "blocked_until_first_wave_launch_authorized"
    handoff = {
        "handoff_type": "homepilot_first_wave_database_handoff",
        "handoff_id": f"{scenario['tenant_slug']}:{scenario['module_key']}:first-wave-database-handoff",
        "created_at": created_at,
        "release_label": release_label,
        "status": status,
        "sql_mode": "review_sql_generated_not_applied" if authorized else "comment_only_blocked_gate",
        "launch_decision": launch_gate.get("launch_decision", "unknown"),
        "launch_authorized": authorized,
        "scenario": scenario,
        "summary": {
            "review_rows": len(review_rows),
            "campaign_records": len(import_plan.get("campaign_records", [])),
            "source_runs": len(import_plan.get("property_source_runs", [])),
            "partner_memberships_deferred": len(import_plan.get("partner_scope_records", [])),
            "executable_statement_count": 0,
            "tables_touched_when_authorized": [
                "homepilot_tenants",
                "homepilot_tenant_modules",
                "homepilot_campaigns",
                "homepilot_source_runs",
                "homepilot_audit_events",
            ],
        },
        "validation": {
            "status": input_validation.get("status"),
            "first_wave_decision": input_validation.get("first_wave_decision"),
        },
        "launch_gate": {
            "status": launch_gate.get("status"),
            "launch_decision": launch_gate.get("launch_decision"),
            "launch_authorized": authorized,
            "summary": launch_gate.get("summary", {}),
            "gates": launch_gate.get("gates", []),
        },
        "database_contract": {
            "review_tables": [
                {"table": "homepilot_tenants", "treatment": "tenant seed/upsert only after authorized gate"},
                {"table": "homepilot_tenant_modules", "treatment": "module entitlement upsert only after authorized gate"},
                {"table": "homepilot_campaigns", "treatment": "partner campaign seed rows only after authorized gate"},
                {"table": "homepilot_source_runs", "treatment": "source provenance rows only after authorized gate"},
                {"table": "homepilot_audit_events", "treatment": "handoff/gate audit rows only after authorized gate"},
                {"table": "homepilot_memberships", "treatment": "deferred until real Supabase Auth user IDs exist"},
                {"table": "homepilot_properties/homepilot_campaign_targets/homepilot_interactions", "treatment": "deferred until approved property file parse"},
            ],
            "join_keys": ["tenant_id", "module_key", "partner_id", "campaign_id", "property_id"],
        },
        "review_rows": review_rows,
        "guardrails": {
            "non_mutating_pack": True,
            "no_executable_sql_when_blocked": True,
            "launch_authorized_required_before_database_write": True,
            "customer_it_review_required_before_apply": True,
            "live_schema_verification_required_after_apply": True,
            "partner_memberships_deferred_without_auth_user_ids": True,
            "property_targets_deferred_until_approved_parse": True,
            "raw_contact_values_written": False,
            "secret_values_written": False,
        },
        "paths": {
            "database_handoff": str(out_dir / "first_wave_database_handoff.json"),
            "database_handoff_markdown": str(out_dir / "FIRST_WAVE_DATABASE_HANDOFF.md"),
            "database_handoff_checklist": str(out_dir / "FIRST_WAVE_DATABASE_HANDOFF_CHECKLIST.csv"),
            "database_review_rows": str(out_dir / "FIRST_WAVE_DATABASE_REVIEW_ROWS.csv"),
            "database_review_sql": str(out_dir / "FIRST_WAVE_DATABASE_REVIEW.sql"),
        },
    }
    sql = render_sql(handoff, import_plan)
    handoff["summary"]["executable_statement_count"] = _statement_count(sql) if authorized else 0
    write_json(out_dir / "first_wave_database_handoff.json", handoff)
    write_text(out_dir / "FIRST_WAVE_DATABASE_HANDOFF.md", render_markdown(handoff))
    write_review_rows_csv(out_dir / "FIRST_WAVE_DATABASE_REVIEW_ROWS.csv", review_rows)
    write_checklist_csv(out_dir / "FIRST_WAVE_DATABASE_HANDOFF_CHECKLIST.csv", handoff)
    write_text(out_dir / "FIRST_WAVE_DATABASE_REVIEW.sql", sql)
    return handoff


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a guarded HomePilot first-wave database handoff")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--input-validation", required=True, type=Path)
    parser.add_argument("--import-plan", required=True, type=Path)
    parser.add_argument("--launch-gate", required=True, type=Path)
    parser.add_argument("--release-label", default="local")
    args = parser.parse_args()

    handoff = build_first_wave_database_handoff(
        out_dir=args.out_dir,
        input_validation=load_json(args.input_validation) or {},
        import_plan=load_json(args.import_plan) or {},
        launch_gate=load_json(args.launch_gate) or {},
        release_label=args.release_label,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": handoff["status"],
        "sql_mode": handoff["sql_mode"],
        "launch_authorized": handoff["launch_authorized"],
        "database_handoff": handoff["paths"]["database_handoff"],
        "database_review_sql": handoff["paths"]["database_review_sql"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
