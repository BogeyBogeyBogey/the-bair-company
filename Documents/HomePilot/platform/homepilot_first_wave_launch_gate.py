#!/usr/bin/env python3
"""
Build the final non-mutating HomePilot first-wave launch gate.

The input validator and import plan explain whether a DAW-style campaign can be
staged. This module combines those artifacts with live proof and customer
go/no-go evidence so the operator, customer, IT, and legal teams can see one
clear launch decision before outreach or partner portal access.
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


def _norm_lower(value: Any) -> str:
    return _norm(value).lower()


def _gate_status(gates: list[dict[str, Any]], key: str) -> str | None:
    for gate in gates:
        if gate.get("key") == key or gate.get("gate") == key:
            return str(gate.get("status") or "")
    return None


def _is_pass(value: Any) -> bool:
    return _norm_lower(value) in {
        "pass",
        "passed",
        "ready",
        "ready_for_first_wave",
        "ready_for_live_import_review",
        "ready_for_first_wave_review",
        "production_verified",
        "verified",
        "go",
    }


def _production_verified(report: dict[str, Any] | None) -> bool:
    if not report:
        return False
    if bool(report.get("production_verified")):
        return True
    if bool(report.get("verified")):
        return True
    production_gate = report.get("production_gate")
    if isinstance(production_gate, dict) and bool(production_gate.get("verified")):
        return True
    return _norm_lower(report.get("status")) in {"production_verified", "verified"}


def _live_readiness_ready(report: dict[str, Any] | None) -> bool:
    if not report:
        return False
    return _norm_lower(report.get("status")) in {"ready", "pass", "production_ready"} or _production_verified(report)


def _public_data_required(import_plan: dict[str, Any] | None) -> bool:
    if not import_plan:
        return False
    none_values = {"", "none", "no", "false", "n/a", "not_used", "none_until_approved"}
    for source_run in import_plan.get("property_source_runs", []):
        value = _norm_lower(source_run.get("public_data_used"))
        if value not in none_values:
            return True
    return False


def _public_data_approved(public_data_intake: dict[str, Any] | None, public_data_required: bool) -> bool:
    if not public_data_required:
        return True
    if not public_data_intake:
        return False
    decision = _norm_lower(public_data_intake.get("production_import_decision"))
    status = _norm_lower(public_data_intake.get("status"))
    approved_decisions = {
        "approved_for_production_import",
        "ready_for_production_import",
        "ready_for_import",
        "pass",
    }
    return decision in approved_decisions or status in approved_decisions


def _evidence_path(report: dict[str, Any] | None, *keys: str) -> str:
    if not report:
        return ""
    paths = report.get("paths") if isinstance(report.get("paths"), dict) else {}
    for key in keys:
        value = paths.get(key)
        if value:
            return str(value)
    return ""


def _gate(
    key: str,
    label: str,
    status: str,
    evidence: str,
    next_action: str,
    owner: str,
    blocks_launch: bool = True,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "blocks_launch": blocks_launch and status != "pass",
        "evidence": evidence,
        "next_action": next_action,
        "owner": owner,
    }


def _decision_from_gates(gates: list[dict[str, Any]]) -> str:
    blockers = [gate["key"] for gate in gates if gate["blocks_launch"]]
    if not blockers:
        return "ready_for_first_wave_launch"
    if "customer_inputs" in blockers or "staging_plan" in blockers:
        return "blocked_until_customer_inputs_and_staging_review"
    if "live_proof" in blockers and "customer_go_no_go" in blockers:
        return "blocked_until_live_proof_and_customer_go_no_go"
    if "live_proof" in blockers:
        return "blocked_until_live_proof"
    if "customer_go_no_go" in blockers:
        return "blocked_until_customer_go_no_go"
    if "public_data_approval" in blockers:
        return "blocked_until_public_data_approval"
    return "blocked_until_first_wave_gate_review"


def render_launch_gate_markdown(gate: dict[str, Any]) -> str:
    scenario = gate["scenario"]
    lines = [
        "# HomePilot First Wave Launch Gate",
        "",
        f"Release: {gate['release_label']}",
        f"Created: {gate['created_at']}",
        f"Status: {gate['status']}",
        f"Launch decision: {gate['launch_decision']}",
        f"Launch authorized: {str(gate['launch_authorized']).lower()}",
        "",
        "This is the final non-mutating launch gate for a DAW-style producer-network campaign. It does not write to Supabase and it does not authorize outreach unless every blocking gate passes.",
        "",
        "## Scenario",
        "",
        f"- Tenant: {scenario['tenant_slug']}",
        f"- Module: {scenario['module_key']}",
        f"- Expected partners: {scenario['expected_partner_count']}",
        f"- Partner campaigns staged: {gate['summary']['campaign_records']}",
        f"- Staging rows: {gate['summary']['staging_rows']}",
        "",
        "## Gate Checklist",
        "",
        "| Gate | Status | Owner | Evidence | Next action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in gate["gates"]:
        lines.append(
            f"| {row['label']} | {row['status']} | {row['owner']} | {row['evidence']} | {row['next_action']} |"
        )
    lines += [
        "",
        "## Blockers",
        "",
    ]
    blockers = [row for row in gate["gates"] if row["blocks_launch"]]
    if blockers:
        lines.extend(f"- {row['label']}: {row['next_action']}" for row in blockers)
    else:
        lines.append("- No blocking gates remain. Operator still performs the final launch-room confirmation.")
    lines += [
        "",
        "## Guardrails",
        "",
        "- No outreach before customer go/no-go is archived.",
        "- No partner portal access before live RLS and customer-access proof pass.",
        "- No production public-data import before dataset-level approval and provenance are archived.",
        "- Synthetic examples and staging rows are training/review evidence, not customer production approval.",
        "",
    ]
    return "\n".join(lines)


def write_launch_gate_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["key", "label", "status", "blocks_launch", "owner", "evidence", "next_action"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def build_first_wave_launch_gate(
    out_dir: Path,
    input_validation: dict[str, Any],
    import_plan: dict[str, Any],
    public_data_intake: dict[str, Any] | None = None,
    live_readiness: dict[str, Any] | None = None,
    schema_verification: dict[str, Any] | None = None,
    launch_report: dict[str, Any] | None = None,
    customer_access_report: dict[str, Any] | None = None,
    release_label: str = "local",
    customer_go_no_go_ready: bool = False,
    customer_go_no_go_reference: str = "",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    validation_gates = input_validation.get("gates", [])
    validation_ready = input_validation.get("status") in {"customer_inputs_ready", "ready_for_first_wave"}
    validation_live_blocker_only = (
        validation_ready
        and input_validation.get("first_wave_decision") == "blocked_until_live_proof"
    )
    staging_ready = import_plan.get("status") in {"staging_plan_ready_import_blocked", "ready_for_live_import_review"}
    no_database_writes = bool(import_plan.get("guardrails", {}).get("no_database_writes"))
    source_approval_ready = all(
        _gate_status(validation_gates, key) == "pass"
        for key in ("contact_basis_and_suppression", "message_and_claim_approval", "partner_capacity_confirmed")
    )
    public_data_required = _public_data_required(import_plan)
    public_data_ready = _public_data_approved(public_data_intake, public_data_required)
    live_proof_ready = all([
        _live_readiness_ready(live_readiness),
        _production_verified(schema_verification),
        _production_verified(launch_report),
        _production_verified(customer_access_report),
    ])
    gates = [
        _gate(
            key="customer_inputs",
            label="Customer CSV inputs",
            status="pass" if validation_ready or validation_live_blocker_only else "blocked",
            evidence=_evidence_path(input_validation, "validation_markdown", "validation_report") or "FIRST_CAMPAIGN_INPUT_VALIDATION.md",
            next_action="Fix FIRST_CAMPAIGN_INPUT_ISSUES.csv blockers." if not validation_ready else "Keep validated customer files in the launch evidence archive.",
            owner="Customer success + DAW data owner",
        ),
        _gate(
            key="staging_plan",
            label="Non-mutating import/staging plan",
            status="pass" if staging_ready and no_database_writes else "blocked",
            evidence=_evidence_path(import_plan, "import_plan_markdown", "import_plan") or "FIRST_CAMPAIGN_IMPORT_PLAN.md",
            next_action="Review staged partner/campaign/source rows; do not write to Supabase yet." if staging_ready else "Rebuild the import plan after customer input fixes.",
            owner="HomePilot operator + IT owner",
        ),
        _gate(
            key="source_suppression_message",
            label="Source, suppression, message, and capacity approval",
            status="pass" if source_approval_ready else "blocked",
            evidence="PROPERTY_SOURCE_TEMPLATE.csv; SUPPRESSION_LIST_TEMPLATE.csv; MESSAGE_APPROVAL_TEMPLATE.csv; PARTNER_CAPACITY_TEMPLATE.csv",
            next_action="Archive approved source/contact basis, suppression, message, and partner-capacity evidence." if not source_approval_ready else "Keep approvals attached to the first-wave launch record.",
            owner="DAW legal + marketing + partner manager",
        ),
        _gate(
            key="public_data_approval",
            label="Public-data production approval",
            status="pass" if public_data_ready else "blocked",
            evidence="PUBLIC_DATA_PRODUCTION_INTAKE.md; PUBLIC_DATA_APPROVAL_CHECKLIST.csv",
            next_action="No public-data production import is required for this first wave." if not public_data_required else "Complete dataset-level licence, allowed-use, attribution, field allowlist, and transform approval.",
            owner="Legal + data owner",
            blocks_launch=public_data_required,
        ),
        _gate(
            key="live_proof",
            label="Live schema, RLS, and customer-access proof",
            status="pass" if live_proof_ready else "blocked",
            evidence="live_readiness.json; schema_verification.json; launch_report.json; customer_access_verification.json",
            next_action="Run live readiness, schema verification, RLS launch, and customer-access verification with production_verified=true." if not live_proof_ready else "Archive live proof with the launch record.",
            owner="IT owner + HomePilot operator",
        ),
        _gate(
            key="customer_go_no_go",
            label="Explicit customer go/no-go",
            status="pass" if customer_go_no_go_ready else "blocked",
            evidence=customer_go_no_go_reference or "Signed first-wave go/no-go decision",
            next_action="Get DAW/customer executive, legal, and campaign owner go/no-go after reviewing the staging plan." if not customer_go_no_go_ready else "Keep the signed go/no-go reference in the evidence room.",
            owner="DAW executive sponsor + campaign owner",
        ),
    ]
    decision = _decision_from_gates(gates)
    launch_authorized = decision == "ready_for_first_wave_launch"
    scenario = import_plan.get("scenario", {})
    gate = {
        "gate_type": "homepilot_first_wave_launch_gate",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": "ready" if launch_authorized else "blocked",
        "launch_decision": decision,
        "launch_authorized": launch_authorized,
        "scenario": {
            "tenant_slug": scenario.get("tenant_slug", "tenant"),
            "module_key": scenario.get("module_key", "facadepilot"),
            "expected_partner_count": scenario.get("expected_partner_count", 0),
            "network_shape": scenario.get("network_shape", "producer tenant with partner-scoped campaign records"),
        },
        "summary": {
            "gates": len(gates),
            "passed_gates": len([row for row in gates if row["status"] == "pass"]),
            "blocking_gates": len([row for row in gates if row["blocks_launch"]]),
            "partner_scope_records": import_plan.get("summary", {}).get("partner_scope_records", 0),
            "campaign_records": import_plan.get("summary", {}).get("campaign_records", 0),
            "staging_rows": import_plan.get("summary", {}).get("staging_rows", 0),
            "public_data_required": public_data_required,
            "live_proof_ready": live_proof_ready,
            "customer_go_no_go_ready": customer_go_no_go_ready,
        },
        "gates": gates,
        "inputs": {
            "validation_status": input_validation.get("status"),
            "validation_first_wave_decision": input_validation.get("first_wave_decision"),
            "import_plan_status": import_plan.get("status"),
            "import_decision": import_plan.get("import_decision"),
            "public_data_import_decision": public_data_intake.get("production_import_decision") if public_data_intake else None,
            "live_readiness_status": live_readiness.get("status") if live_readiness else None,
            "schema_production_verified": _production_verified(schema_verification),
            "launch_production_verified": _production_verified(launch_report),
            "customer_access_production_verified": _production_verified(customer_access_report),
        },
        "guardrails": {
            "non_mutating_gate": True,
            "no_database_writes": True,
            "no_outreach_without_launch_authorized": True,
            "customer_go_no_go_required": True,
            "live_rls_customer_access_required": True,
            "public_data_imports_require_dataset_approval": True,
            "synthetic_examples_are_not_customer_approval": True,
        },
        "paths": {
            "launch_gate": str(out_dir / "first_wave_launch_gate.json"),
            "launch_gate_markdown": str(out_dir / "FIRST_WAVE_LAUNCH_GATE.md"),
            "launch_gate_checklist": str(out_dir / "FIRST_WAVE_LAUNCH_GATE_CHECKLIST.csv"),
        },
    }
    write_json(out_dir / "first_wave_launch_gate.json", gate)
    write_text(out_dir / "FIRST_WAVE_LAUNCH_GATE.md", render_launch_gate_markdown(gate))
    write_launch_gate_csv(out_dir / "FIRST_WAVE_LAUNCH_GATE_CHECKLIST.csv", gates)
    return gate


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot first-wave launch gate")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--input-validation", required=True, type=Path)
    parser.add_argument("--import-plan", required=True, type=Path)
    parser.add_argument("--public-data-intake", type=Path)
    parser.add_argument("--live-readiness", type=Path)
    parser.add_argument("--schema-verification", type=Path)
    parser.add_argument("--launch-report", type=Path)
    parser.add_argument("--customer-access-report", type=Path)
    parser.add_argument("--release-label", default="local")
    parser.add_argument("--customer-go-no-go-ready", action="store_true")
    parser.add_argument("--customer-go-no-go-reference", default="")
    args = parser.parse_args()

    gate = build_first_wave_launch_gate(
        out_dir=args.out_dir,
        input_validation=load_json(args.input_validation) or {},
        import_plan=load_json(args.import_plan) or {},
        public_data_intake=load_json(args.public_data_intake),
        live_readiness=load_json(args.live_readiness),
        schema_verification=load_json(args.schema_verification),
        launch_report=load_json(args.launch_report),
        customer_access_report=load_json(args.customer_access_report),
        release_label=args.release_label,
        customer_go_no_go_ready=args.customer_go_no_go_ready,
        customer_go_no_go_reference=args.customer_go_no_go_reference,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": gate["status"],
        "launch_decision": gate["launch_decision"],
        "launch_authorized": gate["launch_authorized"],
        "launch_gate": gate["paths"]["launch_gate"],
        "launch_gate_markdown": gate["paths"]["launch_gate_markdown"],
        "launch_gate_checklist": gate["paths"]["launch_gate_checklist"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
