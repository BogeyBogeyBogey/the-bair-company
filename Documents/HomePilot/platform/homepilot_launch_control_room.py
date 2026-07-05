#!/usr/bin/env python3
"""
Build a non-mutating HomePilot live launch control room.

The control room does not prove new facts and does not write to Supabase. It
turns existing market-readiness, live-readiness, production-proof, and
first-wave gate evidence into one operator/customer-readable launch cockpit.
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
    re.compile(r"(?:service[_-]?role|anon[_-]?key|password|token|secret)\s*[:=]\s*['\"][^'\"\n]{12,}['\"]", re.IGNORECASE),
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


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _is_go(value: Any) -> bool:
    return _norm(value).lower() == "go"


def _production_verified(report: dict[str, Any] | None) -> bool:
    if not report:
        return False
    if bool(report.get("production_verified")):
        return True
    production_gate = report.get("production_gate")
    if isinstance(production_gate, dict) and bool(production_gate.get("verified")):
        return True
    return _norm(report.get("status")).lower() in {"production_ready", "production_verified", "verified"}


def _artifact_status(production_proof: dict[str, Any] | None, label: str) -> str:
    if not production_proof:
        return "missing"
    for artifact in production_proof.get("artifacts") or []:
        if artifact.get("label") == label:
            return str(artifact.get("status") or "unknown")
    return "missing"


def _stage_gate(
    key: str,
    label: str,
    status: str,
    owner: str,
    evidence: str,
    next_action: str,
    blocks_live_launch: bool,
    blocks_production: bool,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "owner": owner,
        "evidence": evidence,
        "next_action": next_action,
        "blocks_live_launch": bool(blocks_live_launch and status != "pass"),
        "blocks_production": bool(blocks_production and status != "pass"),
    }


def _safe_task_label(task: dict[str, Any]) -> str:
    category = str(task.get("category") or "")
    if category == "customer_access":
        role = str(task.get("role") or "planned user").replace("_", " ")
        access_scope = str(task.get("access_scope") or "tenant")
        return f"Prepare {role} {access_scope}-scope access probe credential"
    return str(task.get("input_name") or task.get("task_id") or "live launch input")


def _action_row(
    lane: str,
    status: str,
    owner: str,
    evidence: str,
    next_action: str,
    *,
    source: str,
    blocks_live_launch: bool = True,
    blocks_production: bool = True,
    env_var: str = "",
    secret_value_required: bool = False,
) -> dict[str, Any]:
    return {
        "lane": lane,
        "status": status,
        "owner": owner,
        "evidence": evidence,
        "next_action": next_action,
        "source": source,
        "blocks_live_launch": bool(blocks_live_launch and status != "pass"),
        "blocks_production": bool(blocks_production and status != "pass"),
        "env_var": env_var,
        "secret_value_required": bool(secret_value_required),
    }


def _actions_from_live_request(live_launch_request: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not live_launch_request:
        return [
            _action_row(
                "live_inputs",
                "blocked",
                "HomePilot operator",
                "LIVE_LAUNCH_REQUEST.md",
                "Generate the live launch request pack from the latest live readiness report.",
                source="missing_live_launch_request",
            )
        ]
    for task in live_launch_request.get("tasks") or []:
        task_label = _safe_task_label(task)
        purpose = str(task.get("purpose") or "").strip()
        next_action = f"Set {task_label} through the agreed secret manager or local launch session."
        if purpose:
            next_action += f" Purpose: {purpose}"
        rows.append(
            _action_row(
                "live_inputs",
                "blocked",
                str(task.get("owner_label") or task.get("owner") or "Owner required"),
                str(task.get("env_var") or "LIVE_LAUNCH_CHECKLIST.csv"),
                next_action,
                source="live_launch_request",
                env_var=str(task.get("env_var") or ""),
                secret_value_required=bool(task.get("secret_value_required")),
            )
        )
    if not rows:
        rows.append(
            _action_row(
                "live_inputs",
                "pass",
                "Platform admin / HomePilot operator",
                "LIVE_LAUNCH_REQUEST.md",
                "Keep live inputs in the secret manager and rerun live readiness before cutover.",
                source="live_launch_request",
                blocks_live_launch=False,
                blocks_production=False,
            )
        )
    return rows


def _actions_from_production_proof(production_proof: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    missing = []
    blockers = []
    if production_proof:
        missing = list(production_proof.get("production_gate", {}).get("missing_live_artifacts") or [])
        blockers = list(production_proof.get("production_gate", {}).get("blockers") or [])
    for label in missing:
        owner = "IT owner + HomePilot operator"
        if "customer_access" in str(label):
            owner = "Customer success + tenant admin"
        rows.append(
            _action_row(
                "production_proof",
                "blocked",
                owner,
                str(label),
                "Create or attach this live proof artifact with production_verified=true.",
                source="production_proof_missing_artifact",
                blocks_live_launch=False,
            )
        )
    for blocker in blockers[:12]:
        rows.append(
            _action_row(
                "production_proof",
                "blocked",
                "HomePilot operator + IT owner",
                "PRODUCTION_PROOF.md",
                str(blocker),
                source="production_proof_blocker",
                blocks_live_launch=False,
            )
        )
    if not rows:
        rows.append(
            _action_row(
                "production_proof",
                "pass" if _production_verified(production_proof) else "blocked",
                "HomePilot operator + IT owner",
                "PRODUCTION_PROOF.md",
                "Archive production proof and confirm all live reports show production_verified=true.",
                source="production_proof",
                blocks_live_launch=False,
            )
        )
    return rows


def _actions_from_first_wave_gate(first_wave_launch_gate: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not first_wave_launch_gate:
        return [
            _action_row(
                "first_wave",
                "blocked",
                "Customer success + campaign owner",
                "FIRST_WAVE_LAUNCH_GATE.md",
                "Build the first-wave launch gate after customer inputs and staging plan exist.",
                source="missing_first_wave_launch_gate",
                blocks_live_launch=False,
            )
        ]
    rows: list[dict[str, Any]] = []
    for gate in first_wave_launch_gate.get("gates") or []:
        if not gate.get("blocks_launch"):
            continue
        rows.append(
            _action_row(
                "first_wave",
                "blocked",
                str(gate.get("owner") or "Owner required"),
                str(gate.get("evidence") or "FIRST_WAVE_LAUNCH_GATE.md"),
                str(gate.get("next_action") or "Resolve the first-wave launch blocker."),
                source=f"first_wave_gate.{gate.get('key') or 'gate'}",
                blocks_live_launch=False,
            )
        )
    if not rows:
        rows.append(
            _action_row(
                "first_wave",
                "pass",
                "DAW campaign owner + HomePilot operator",
                "FIRST_WAVE_LAUNCH_GATE.md",
                "Keep the signed go/no-go and live proof in the evidence archive.",
                source="first_wave_launch_gate",
                blocks_live_launch=False,
                blocks_production=False,
            )
        )
    return rows


def _partner_auth_ready(partner_auth_mapping: dict[str, Any] | None) -> bool:
    if not partner_auth_mapping:
        return False
    if partner_auth_mapping.get("status") != "ready_for_membership_sql_review":
        return False
    summary = partner_auth_mapping.get("summary") or {}
    expected = int(summary.get("expected_partner_count") or 0)
    mapped = int(summary.get("mapped_partner_count") or 0)
    return (
        expected > 0
        and mapped >= expected
        and int(summary.get("blockers") or 0) == 0
        and int(summary.get("executable_statement_count") or 0) > 0
    )


def _partner_access_reconciled(partner_access_reconciliation: dict[str, Any] | None) -> bool:
    return bool(
        partner_access_reconciliation
        and partner_access_reconciliation.get("status") == "partner_access_reconciled"
        and partner_access_reconciliation.get("production_ready") is True
        and int((partner_access_reconciliation.get("summary") or {}).get("blockers") or 0) == 0
    )


def _public_data_reconciled(public_data_reconciliation: dict[str, Any] | None) -> bool:
    return bool(
        public_data_reconciliation
        and public_data_reconciliation.get("status") == "public_data_reconciled_for_production_import"
        and public_data_reconciliation.get("production_import_ready") is True
        and int((public_data_reconciliation.get("summary") or {}).get("blockers") or 0) == 0
    )


def _public_data_blocks_live_launch(public_data_reconciliation: dict[str, Any] | None) -> bool:
    if not public_data_reconciliation or _public_data_reconciled(public_data_reconciliation):
        return False
    summary = public_data_reconciliation.get("summary") or {}
    return bool(summary.get("first_wave_public_data_required") and int(summary.get("first_wave_blocks") or 0) > 0)


def _customer_signoff_reconciled(customer_signoff_reconciliation: dict[str, Any] | None) -> bool:
    return bool(
        customer_signoff_reconciliation
        and customer_signoff_reconciliation.get("status") == "customer_signoff_reconciled"
        and customer_signoff_reconciliation.get("production_signoff_ready") is True
        and int((customer_signoff_reconciliation.get("summary") or {}).get("blockers") or 0) == 0
    )


def _customer_signoff_blocks_live_launch(customer_signoff_reconciliation: dict[str, Any] | None) -> bool:
    if not customer_signoff_reconciliation or _customer_signoff_reconciled(customer_signoff_reconciliation):
        return False
    summary = customer_signoff_reconciliation.get("summary") or {}
    return int(summary.get("live_launch_blockers") or 0) > 0


def _actions_from_partner_auth_mapping(partner_auth_mapping: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not partner_auth_mapping:
        return [
            _action_row(
                "partner_access",
                "blocked",
                "Customer IT + customer success",
                "PARTNER_AUTH_MAPPING.md",
                "Build the partner Auth mapping pack before enabling partner portal access.",
                source="missing_partner_auth_mapping",
                blocks_live_launch=False,
            )
        ]
    if _partner_auth_ready(partner_auth_mapping):
        return [
            _action_row(
                "partner_access",
                "pass",
                "Customer IT + HomePilot operator",
                "PARTNER_AUTH_MAPPING.md; PARTNER_MEMBERSHIP_REVIEW.sql",
                "Keep the reviewed partner Auth mapping and membership SQL with live access evidence.",
                source="partner_auth_mapping",
                blocks_live_launch=False,
                blocks_production=False,
            )
        ]
    rows: list[dict[str, Any]] = []
    for issue in partner_auth_mapping.get("issues") or []:
        if issue.get("severity") != "blocker":
            continue
        rows.append(
            _action_row(
                "partner_access",
                "blocked",
                "Customer IT + customer success",
                str(issue.get("field") or "PARTNER_AUTH_MAPPING_ISSUES.csv"),
                str(issue.get("next_action") or "Resolve the partner Auth mapping blocker."),
                source=f"partner_auth_mapping.{issue.get('issue_key') or 'issue'}",
                blocks_live_launch=False,
            )
        )
    if not rows:
        rows.append(
            _action_row(
                "partner_access",
                "blocked",
                "Customer IT + customer success",
                "PARTNER_AUTH_MAPPING.md",
                "Complete partner Auth mapping and rerun the live launch control room.",
                source="partner_auth_mapping",
                blocks_live_launch=False,
            )
        )
    return rows[:12]


def _actions_from_partner_access_reconciliation(partner_access_reconciliation: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not partner_access_reconciliation:
        return [
            _action_row(
                "partner_access_reconciliation",
                "blocked",
                "Customer IT + customer success",
                "PARTNER_ACCESS_RECONCILIATION.md",
                "Build partner access reconciliation before production partner portal access.",
                source="missing_partner_access_reconciliation",
                blocks_live_launch=False,
            )
        ]
    if _partner_access_reconciled(partner_access_reconciliation):
        return [
            _action_row(
                "partner_access_reconciliation",
                "pass",
                "Customer IT + HomePilot operator",
                "PARTNER_ACCESS_RECONCILIATION.md",
                "Keep reconciliation evidence with partner Auth mapping and live customer-access proof.",
                source="partner_access_reconciliation",
                blocks_live_launch=False,
                blocks_production=False,
            )
        ]
    rows: list[dict[str, Any]] = []
    for issue in partner_access_reconciliation.get("issues") or []:
        if issue.get("severity") != "blocker":
            continue
        rows.append(
            _action_row(
                "partner_access_reconciliation",
                "blocked",
                "Customer IT + customer success",
                str(issue.get("evidence") or "PARTNER_ACCESS_RECONCILIATION_ISSUES.csv"),
                str(issue.get("next_action") or "Resolve the partner access reconciliation blocker."),
                source=f"partner_access_reconciliation.{issue.get('issue_key') or 'issue'}",
                blocks_live_launch=False,
            )
        )
    if not rows:
        rows.append(
            _action_row(
                "partner_access_reconciliation",
                "blocked",
                "Customer IT + customer success",
                "PARTNER_ACCESS_RECONCILIATION.md",
                "Resolve partner access reconciliation issues and rerun launch control.",
                source="partner_access_reconciliation",
                blocks_live_launch=False,
            )
        )
    return rows[:12]


def _actions_from_public_data_reconciliation(public_data_reconciliation: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not public_data_reconciliation:
        return [
            _action_row(
                "public_data_reconciliation",
                "blocked",
                "Legal/privacy owner + data engineering owner",
                "PUBLIC_DATA_RECONCILIATION.md",
                "Build public-data reconciliation before production public-data import.",
                source="missing_public_data_reconciliation",
                blocks_live_launch=False,
            )
        ]
    if _public_data_reconciled(public_data_reconciliation):
        return [
            _action_row(
                "public_data_reconciliation",
                "pass",
                "Legal/privacy owner + HomePilot operator",
                "PUBLIC_DATA_RECONCILIATION.md",
                "Keep dataset approval, field allowlist, source-run metadata, and live proof with production evidence.",
                source="public_data_reconciliation",
                blocks_live_launch=False,
                blocks_production=False,
            )
        ]
    rows: list[dict[str, Any]] = []
    for issue in public_data_reconciliation.get("issues") or []:
        if issue.get("severity") != "blocker":
            continue
        rows.append(
            _action_row(
                "public_data_reconciliation",
                "blocked",
                "Legal/privacy owner + data engineering owner",
                str(issue.get("evidence") or "PUBLIC_DATA_RECONCILIATION_ISSUES.csv"),
                str(issue.get("next_action") or "Resolve the public-data reconciliation blocker."),
                source=f"public_data_reconciliation.{issue.get('issue_key') or 'issue'}",
                blocks_live_launch=bool(issue.get("blocks_first_wave")),
            )
        )
    if not rows:
        rows.append(
            _action_row(
                "public_data_reconciliation",
                "blocked",
                "Legal/privacy owner + data engineering owner",
                "PUBLIC_DATA_RECONCILIATION.md",
                "Resolve public-data reconciliation issues and rerun launch control.",
                source="public_data_reconciliation",
                blocks_live_launch=False,
            )
        )
    return rows[:12]


def _actions_from_customer_signoff_reconciliation(customer_signoff_reconciliation: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not customer_signoff_reconciliation:
        return [
            _action_row(
                "customer_signoff_reconciliation",
                "blocked",
                "Executive sponsor + customer success",
                "CUSTOMER_SIGNOFF_RECONCILIATION.md",
                "Build customer signoff reconciliation before treating buyer-review evidence as customer approval.",
                source="missing_customer_signoff_reconciliation",
                blocks_live_launch=True,
                blocks_production=True,
            )
        ]
    if _customer_signoff_reconciled(customer_signoff_reconciliation):
        return [
            _action_row(
                "customer_signoff_reconciliation",
                "pass",
                "Executive sponsor + customer success",
                "CUSTOMER_SIGNOFF_RECONCILIATION.md",
                "Keep signed customer decision evidence with the launch and production proof pack.",
                source="customer_signoff_reconciliation",
                blocks_live_launch=False,
                blocks_production=False,
            )
        ]
    rows: list[dict[str, Any]] = []
    for issue in customer_signoff_reconciliation.get("issues") or []:
        if issue.get("severity") != "blocker":
            continue
        rows.append(
            _action_row(
                "customer_signoff_reconciliation",
                "blocked",
                "Executive sponsor + customer success",
                str(issue.get("evidence") or "CUSTOMER_SIGNOFF_RECONCILIATION_ISSUES.csv"),
                str(issue.get("next_action") or "Resolve the customer decision blocker."),
                source=f"customer_signoff_reconciliation.{issue.get('issue_key') or 'issue'}",
                blocks_live_launch=bool(issue.get("blocks_live_launch")),
                blocks_production=bool(issue.get("blocks_production")),
            )
        )
    if not rows:
        rows.append(
            _action_row(
                "customer_signoff_reconciliation",
                "blocked",
                "Executive sponsor + customer success",
                "CUSTOMER_SIGNOFF_RECONCILIATION.md",
                "Resolve customer signoff reconciliation issues and rerun launch control.",
                source="customer_signoff_reconciliation",
                blocks_live_launch=_customer_signoff_blocks_live_launch(customer_signoff_reconciliation),
                blocks_production=True,
            )
        )
    return rows[:12]


def _stage_gates(
    market_readiness: dict[str, Any],
    live_readiness: dict[str, Any] | None,
    live_launch_request: dict[str, Any] | None,
    production_proof: dict[str, Any] | None,
    first_wave_launch_gate: dict[str, Any] | None,
    partner_auth_mapping: dict[str, Any] | None,
    partner_access_reconciliation: dict[str, Any] | None,
    public_data_reconciliation: dict[str, Any] | None,
    customer_signoff_reconciliation: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    decisions = market_readiness.get("decisions") or {}
    live_tasks = len((live_launch_request or {}).get("tasks") or [])
    first_wave_authorized = bool((first_wave_launch_gate or {}).get("launch_authorized"))
    production_ready = _production_verified(production_proof)
    partner_auth_ready = _partner_auth_ready(partner_auth_mapping)
    partner_access_ready = _partner_access_reconciled(partner_access_reconciliation)
    public_data_ready = _public_data_reconciled(public_data_reconciliation)
    public_data_blocks_live_launch = _public_data_blocks_live_launch(public_data_reconciliation)
    customer_signoff_ready = _customer_signoff_reconciled(customer_signoff_reconciliation)
    customer_signoff_blocks_live_launch = _customer_signoff_blocks_live_launch(customer_signoff_reconciliation)
    return [
        _stage_gate(
            "buyer_review",
            "Buyer review evidence",
            "pass" if _is_go(decisions.get("buyer_review")) else "blocked",
            "Executive sponsor + sales lead",
            "MARKET_READINESS_SCORECARD.md",
            "Use the data room for buyer review; do not claim production proof yet.",
            False,
            False,
        ),
        _stage_gate(
            "live_inputs",
            "Live Supabase, RLS fixture, and customer-access inputs",
            "pass" if live_readiness and live_readiness.get("ready_to_run_live_cutover") is True and live_tasks == 0 else "blocked",
            "Platform admin + HomePilot operator + customer success",
            "LIVE_READINESS.md; LIVE_LAUNCH_REQUEST.md",
            "Complete the live launch checklist through the agreed secret channel, then rerun live readiness.",
            True,
            True,
        ),
        _stage_gate(
            "live_schema",
            "Live schema metadata verification",
            "pass" if _artifact_status(production_proof, "schema_verification_report") == "present" and production_ready else "blocked",
            "IT owner + database admin",
            "schema_verification.json",
            "Apply reviewed SQL and run live schema verification with production_verified=true.",
            True,
            True,
        ),
        _stage_gate(
            "live_rls",
            "Live RLS launch probe",
            "pass" if _artifact_status(production_proof, "launch_report") == "present" and production_ready else "blocked",
            "HomePilot operator + IT owner",
            "launch_report.json",
            "Run the live RLS launch fixture and archive launch_report.json with production_verified=true.",
            True,
            True,
        ),
        _stage_gate(
            "customer_access",
            "Customer and partner access verification",
            "pass" if _artifact_status(production_proof, "customer_access_report") == "present" and production_ready else "blocked",
            "Customer success + tenant admin",
            "customer_access_verification.json",
            "Run planned owner, manager, and partner-scoped customer access probes with production_verified=true.",
            True,
            True,
        ),
        _stage_gate(
            "partner_auth_mapping",
            "Partner Auth mapping and membership review",
            "pass" if partner_auth_ready else "blocked",
            "Customer IT + customer success",
            "PARTNER_AUTH_MAPPING.md; PARTNER_MEMBERSHIP_REVIEW.sql",
            "Map every approved partner to a real Supabase Auth user UUID before partner portal access.",
            False,
            True,
        ),
        _stage_gate(
            "partner_access_reconciliation",
            "Partner Auth, membership, and customer-access reconciliation",
            "pass" if partner_access_ready else "blocked",
            "Customer IT + customer success",
            "PARTNER_ACCESS_RECONCILIATION.md",
            "Prove every mapped partner Auth UUID is present in account-access memberships and live customer-access verification.",
            False,
            True,
        ),
        _stage_gate(
            "public_data_reconciliation",
            "Public-data source, approval, and live-proof reconciliation",
            "pass" if public_data_ready else "blocked",
            "Legal/privacy owner + data engineering owner",
            "PUBLIC_DATA_RECONCILIATION.md",
            "Approve exact public datasets, field allowlists, attribution, source-run metadata, and live proof before production public-data import.",
            public_data_blocks_live_launch,
            True,
        ),
        _stage_gate(
            "first_wave",
            "First-wave customer go/no-go",
            "pass" if first_wave_authorized else "blocked",
            "DAW executive sponsor + campaign owner",
            "FIRST_WAVE_LAUNCH_GATE.md",
            "Resolve live proof, customer input, public-data, and explicit customer go/no-go blockers before outreach.",
            False,
            True,
        ),
        _stage_gate(
            "customer_signoff_reconciliation",
            "Customer decisions and signoff reconciliation",
            "pass" if customer_signoff_ready else "blocked",
            "Executive sponsor + customer success",
            "CUSTOMER_SIGNOFF_RECONCILIATION.md",
            "Archive signed buyer-review acceptance, customer inputs, first-wave go/no-go, commercial terms, support acknowledgement, and live proof before treating the launch as approved.",
            customer_signoff_blocks_live_launch,
            True,
        ),
        _stage_gate(
            "production_rollout",
            "Production rollout proof",
            "pass" if production_ready else "blocked",
            "HomePilot operator + IT owner",
            "PRODUCTION_PROOF.md",
            "Production is go only after live readiness, schema, launch/RLS, and customer access proof all pass.",
            True,
            True,
        ),
    ]


def _status(stage_gates: list[dict[str, Any]]) -> str:
    if not any(gate["blocks_production"] for gate in stage_gates):
        return "production_ready"
    if not any(gate["blocks_live_launch"] for gate in stage_gates):
        return "ready_for_live_launch_review"
    if any(gate["key"] == "live_inputs" and gate["blocks_live_launch"] for gate in stage_gates):
        return "blocked_until_live_inputs"
    return "blocked_until_live_proof"


def _summary(
    stage_gates: list[dict[str, Any]],
    action_board: list[dict[str, Any]],
    market_readiness: dict[str, Any],
    live_launch_request: dict[str, Any] | None,
    first_wave_launch_gate: dict[str, Any] | None,
    production_proof: dict[str, Any] | None,
    partner_auth_mapping: dict[str, Any] | None,
    partner_access_reconciliation: dict[str, Any] | None,
    public_data_reconciliation: dict[str, Any] | None,
    customer_signoff_reconciliation: dict[str, Any] | None,
) -> dict[str, Any]:
    partner_summary = (partner_auth_mapping or {}).get("summary") or {}
    partner_access_summary = (partner_access_reconciliation or {}).get("summary") or {}
    public_data_summary = (public_data_reconciliation or {}).get("summary") or {}
    customer_signoff_summary = (customer_signoff_reconciliation or {}).get("summary") or {}
    return {
        "stage_gates": len(stage_gates),
        "passed_stage_gates": len([gate for gate in stage_gates if gate["status"] == "pass"]),
        "blocking_live_launch_gates": len([gate for gate in stage_gates if gate["blocks_live_launch"]]),
        "blocking_production_gates": len([gate for gate in stage_gates if gate["blocks_production"]]),
        "action_items": len([row for row in action_board if row["status"] != "pass"]),
        "live_launch_task_count": len((live_launch_request or {}).get("tasks") or []),
        "first_wave_launch_authorized": bool((first_wave_launch_gate or {}).get("launch_authorized")),
        "partner_auth_mapping_status": (partner_auth_mapping or {}).get("status"),
        "partner_auth_expected_count": int(partner_summary.get("expected_partner_count") or 0),
        "partner_auth_mapped_count": int(partner_summary.get("mapped_partner_count") or 0),
        "partner_access_reconciliation_status": (partner_access_reconciliation or {}).get("status"),
        "partner_access_reconciled_count": int(partner_access_summary.get("fully_reconciled_partner_count") or 0),
        "partner_access_reconciliation_blockers": int(partner_access_summary.get("blockers") or 0),
        "public_data_reconciliation_status": (public_data_reconciliation or {}).get("status"),
        "public_data_approved_source_count": int(public_data_summary.get("approved_source_count") or 0),
        "public_data_registered_source_count": int(public_data_summary.get("registered_source_count") or 0),
        "public_data_reconciliation_blockers": int(public_data_summary.get("blockers") or 0),
        "public_data_first_wave_required": bool(public_data_summary.get("first_wave_public_data_required")),
        "customer_signoff_reconciliation_status": (customer_signoff_reconciliation or {}).get("status"),
        "customer_signoff_signed_decision_count": int(customer_signoff_summary.get("signed_decision_count") or 0),
        "customer_signoff_decision_count": int(customer_signoff_summary.get("decision_count") or 0),
        "customer_signoff_live_launch_blockers": int(customer_signoff_summary.get("live_launch_blockers") or 0),
        "customer_signoff_production_blockers": int(customer_signoff_summary.get("production_blockers") or 0),
        "production_verified": _production_verified(production_proof),
        "buyer_review_decision": (market_readiness.get("decisions") or {}).get("buyer_review"),
        "live_launch_decision": (market_readiness.get("decisions") or {}).get("live_launch"),
        "production_decision": (market_readiness.get("decisions") or {}).get("production"),
    }


def _secret_scan(control_room: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(control_room, ensure_ascii=False)
    findings = []
    for pattern in SECRET_PATTERNS:
        if pattern.search(body):
            findings.append(pattern.pattern)
    return {
        "status": "pass" if not findings else "fail",
        "issue_count": len(findings),
        "patterns": findings,
    }


def render_markdown(control_room: dict[str, Any]) -> str:
    summary = control_room["summary"]
    lines = [
        "# HomePilot Live Launch Control Room",
        "",
        f"Release: {control_room['release_label']}",
        f"Created: {control_room['created_at']}",
        f"Status: {control_room['status']}",
        "",
        "This is a non-mutating launch cockpit. It combines existing evidence into one review surface; it does not write to Supabase, authorize outreach, or create production proof by itself.",
        "",
        "## Decisions",
        "",
        f"- Buyer review: {summary['buyer_review_decision']}",
        f"- Live launch: {summary['live_launch_decision']}",
        f"- Production: {summary['production_decision']}",
        f"- First-wave launch authorized: {str(summary['first_wave_launch_authorized']).lower()}",
        f"- Partner Auth mapping: {summary['partner_auth_mapping_status']} ({summary['partner_auth_mapped_count']}/{summary['partner_auth_expected_count']} mapped)",
        f"- Partner access reconciliation: {summary['partner_access_reconciliation_status']} ({summary['partner_access_reconciled_count']} reconciled, {summary['partner_access_reconciliation_blockers']} blockers)",
        f"- Public-data reconciliation: {summary['public_data_reconciliation_status']} ({summary['public_data_approved_source_count']}/{summary['public_data_registered_source_count']} sources approved, {summary['public_data_reconciliation_blockers']} blockers)",
        f"- Customer signoff reconciliation: {summary['customer_signoff_reconciliation_status']} ({summary['customer_signoff_signed_decision_count']}/{summary['customer_signoff_decision_count']} signed, {summary['customer_signoff_live_launch_blockers']} live blockers, {summary['customer_signoff_production_blockers']} production blockers)",
        f"- Production verified: {str(summary['production_verified']).lower()}",
        "",
        "## Stage Gates",
        "",
        "| Gate | Status | Owner | Evidence | Next action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for gate in control_room["stage_gates"]:
        lines.append(
            f"| {gate['label']} | {gate['status']} | {gate['owner']} | {gate['evidence']} | {gate['next_action']} |"
        )
    lines += [
        "",
        "## Action Board",
        "",
        "| Lane | Status | Owner | Evidence | Next action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in control_room["action_board"]:
        lines.append(
            f"| {row['lane']} | {row['status']} | {row['owner']} | {row['evidence']} | {row['next_action']} |"
        )
    lines += [
        "",
        "## Command Sequence",
        "",
    ]
    for command in control_room["command_sequence"]:
        lines.append(f"- `{command}`")
    lines += [
        "",
        "## Guardrails",
        "",
        "- No live writes from this control room.",
        "- No outreach or partner portal access before launch_authorized=true.",
        "- No production claim until live schema, RLS launch, and customer access reports show production_verified=true.",
        "- Secret values stay in the secret manager or local launch session; this artifact stores env var names only.",
        "- Synthetic examples are training material, not customer production approval.",
        "",
    ]
    return "\n".join(lines)


def write_action_board_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "lane",
        "status",
        "owner",
        "evidence",
        "next_action",
        "source",
        "blocks_live_launch",
        "blocks_production",
        "env_var",
        "secret_value_required",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def build_launch_control_room_pack(
    out_dir: Path,
    *,
    market_readiness: dict[str, Any],
    live_readiness: dict[str, Any] | None = None,
    live_launch_request: dict[str, Any] | None = None,
    production_proof: dict[str, Any] | None = None,
    first_wave_launch_gate: dict[str, Any] | None = None,
    partner_auth_mapping: dict[str, Any] | None = None,
    partner_access_reconciliation: dict[str, Any] | None = None,
    public_data_reconciliation: dict[str, Any] | None = None,
    customer_signoff_reconciliation: dict[str, Any] | None = None,
    release_label: str = "local",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stage_gates = _stage_gates(
        market_readiness,
        live_readiness,
        live_launch_request,
        production_proof,
        first_wave_launch_gate,
        partner_auth_mapping,
        partner_access_reconciliation,
        public_data_reconciliation,
        customer_signoff_reconciliation,
    )
    action_board = (
        _actions_from_live_request(live_launch_request)
        + _actions_from_production_proof(production_proof)
        + _actions_from_first_wave_gate(first_wave_launch_gate)
        + _actions_from_partner_auth_mapping(partner_auth_mapping)
        + _actions_from_partner_access_reconciliation(partner_access_reconciliation)
        + _actions_from_public_data_reconciliation(public_data_reconciliation)
        + _actions_from_customer_signoff_reconciliation(customer_signoff_reconciliation)
    )
    control_room = {
        "control_room_type": "homepilot_live_launch_control_room",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": _status(stage_gates),
        "stage_gates": stage_gates,
        "action_board": action_board,
        "summary": _summary(
            stage_gates,
            action_board,
            market_readiness,
            live_launch_request,
            first_wave_launch_gate,
            production_proof,
            partner_auth_mapping,
            partner_access_reconciliation,
            public_data_reconciliation,
            customer_signoff_reconciliation,
        ),
        "command_sequence": [
            "source /path/to/live_launch.env",
            "python3 platform/homepilot_live_readiness.py --out-dir /tmp/homepilot_live_readiness --readiness-report /path/to/readiness_report.json --due-diligence-report /path/to/due_diligence_report.json --account-access-plan /path/to/account_access_plan.json",
            "python3 platform/homepilot_production_cutover.py --live --out-dir /tmp/homepilot_cutover_live --readiness-report /path/to/readiness_report.json --due-diligence-report /path/to/due_diligence_report.json --account-access-plan /path/to/account_access_plan.json",
            "python3 platform/homepilot_first_wave_launch_gate.py --out-dir /tmp/homepilot_first_wave_launch_gate --input-validation /path/to/first_campaign_input_validation.json --import-plan /path/to/first_campaign_import_plan.json",
            "python3 platform/homepilot_partner_auth_mapping.py --out-dir /tmp/homepilot_partner_auth_mapping --import-plan /path/to/first_campaign_import_plan.json --launch-gate /path/to/first_wave_launch_gate.json --mapping-csv /path/to/PARTNER_AUTH_MAPPING_COMPLETED.csv",
            "python3 platform/homepilot_partner_access_reconciliation.py --out-dir /tmp/homepilot_partner_access_reconciliation --partner-auth-mapping /path/to/partner_auth_mapping.json --account-access-plan /path/to/account_access_plan.json --customer-access-verification /path/to/customer_access_verification.json",
            "python3 platform/homepilot_public_data_reconciliation.py --out-dir /tmp/homepilot_public_data_reconciliation --public-register /path/to/customer_public_data_source_register.json --public-data-intake /path/to/public_data_production_intake.json --first-campaign-import-plan /path/to/first_campaign_import_plan.json --first-wave-launch-gate /path/to/first_wave_launch_gate.json",
            "python3 platform/homepilot_customer_signoff_reconciliation.py --out-dir /tmp/homepilot_customer_signoff_reconciliation --customer-acceptance-plan /path/to/customer_acceptance_plan.json --first-campaign-input-validation /path/to/first_campaign_input_validation.json --first-campaign-import-plan /path/to/first_campaign_import_plan.json --first-wave-launch-gate /path/to/first_wave_launch_gate.json --customer-pilot-proposal /path/to/customer_pilot_proposal.json --support-sla-plan /path/to/support_sla_plan.json --customer-signoff-evidence /path/to/CUSTOMER_SIGNOFF_EVIDENCE_COMPLETED.csv",
        ],
        "guardrails": {
            "non_mutating": True,
            "no_live_writes": True,
            "no_supabase_writes": True,
            "no_outreach_authorized": not bool((first_wave_launch_gate or {}).get("launch_authorized")),
            "production_requires_verified_live_reports": True,
            "secret_values_written": False,
            "stores_env_var_names_only": True,
            "synthetic_examples_are_not_customer_approval": True,
        },
        "inputs": {
            "market_readiness_status": market_readiness.get("status"),
            "live_readiness_status": live_readiness.get("status") if live_readiness else None,
            "live_launch_request_status": live_launch_request.get("status") if live_launch_request else None,
            "production_proof_status": production_proof.get("status") if production_proof else None,
            "first_wave_launch_gate_status": first_wave_launch_gate.get("status") if first_wave_launch_gate else None,
            "partner_auth_mapping_status": partner_auth_mapping.get("status") if partner_auth_mapping else None,
            "partner_access_reconciliation_status": partner_access_reconciliation.get("status") if partner_access_reconciliation else None,
            "public_data_reconciliation_status": public_data_reconciliation.get("status") if public_data_reconciliation else None,
            "customer_signoff_reconciliation_status": customer_signoff_reconciliation.get("status") if customer_signoff_reconciliation else None,
        },
        "paths": {
            "launch_control_room": str(out_dir / "live_launch_control_room.json"),
            "launch_control_room_markdown": str(out_dir / "LIVE_LAUNCH_CONTROL_ROOM.md"),
            "launch_action_board": str(out_dir / "LIVE_LAUNCH_ACTION_BOARD.csv"),
        },
    }
    control_room["secret_scan"] = _secret_scan(control_room)
    control_room["guardrails"]["secret_values_written"] = control_room["secret_scan"]["status"] != "pass"
    write_json(out_dir / "live_launch_control_room.json", control_room)
    write_text(out_dir / "LIVE_LAUNCH_CONTROL_ROOM.md", render_markdown(control_room))
    write_action_board_csv(out_dir / "LIVE_LAUNCH_ACTION_BOARD.csv", action_board)
    return control_room


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot live launch control room")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--market-readiness", required=True, type=Path)
    parser.add_argument("--live-readiness", type=Path)
    parser.add_argument("--live-launch-request", type=Path)
    parser.add_argument("--production-proof", type=Path)
    parser.add_argument("--first-wave-launch-gate", type=Path)
    parser.add_argument("--partner-auth-mapping", type=Path)
    parser.add_argument("--partner-access-reconciliation", type=Path)
    parser.add_argument("--public-data-reconciliation", type=Path)
    parser.add_argument("--customer-signoff-reconciliation", type=Path)
    parser.add_argument("--release-label", default="local")
    args = parser.parse_args()

    control_room = build_launch_control_room_pack(
        args.out_dir,
        market_readiness=load_json(args.market_readiness) or {},
        live_readiness=load_json(args.live_readiness),
        live_launch_request=load_json(args.live_launch_request),
        production_proof=load_json(args.production_proof),
        first_wave_launch_gate=load_json(args.first_wave_launch_gate),
        partner_auth_mapping=load_json(args.partner_auth_mapping),
        partner_access_reconciliation=load_json(args.partner_access_reconciliation),
        public_data_reconciliation=load_json(args.public_data_reconciliation),
        customer_signoff_reconciliation=load_json(args.customer_signoff_reconciliation),
        release_label=args.release_label,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": control_room["status"],
        "action_items": control_room["summary"]["action_items"],
        "launch_control_room": control_room["paths"]["launch_control_room"],
        "markdown": control_room["paths"]["launch_control_room_markdown"],
        "action_board": control_room["paths"]["launch_action_board"],
    }, indent=2, ensure_ascii=False))
    if control_room["secret_scan"]["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
