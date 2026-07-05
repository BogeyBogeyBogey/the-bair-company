#!/usr/bin/env python3
"""
HomePilot release go/no-go audit.

Readiness and due-diligence packs prove local buyer-review readiness. Production
readiness is a separate claim and must be backed by live readiness evidence, a
live schema verification report, a live launch report, and a customer access
verification report with production_verified=true and passing RLS probes.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _gate_statuses(readiness: dict[str, Any] | None) -> dict[str, str]:
    if not readiness:
        return {}
    return {
        str(gate.get("name")): str(gate.get("status"))
        for gate in readiness.get("gates", [])
    }


def _readiness_blockers(readiness: dict[str, Any] | None) -> list[str]:
    blockers = []
    if not readiness:
        return ["Missing readiness report."]
    if readiness.get("status") != "pass":
        blockers.append(f"Readiness report status is {readiness.get('status')!r}, expected 'pass'.")
    for name, status in _gate_statuses(readiness).items():
        if status != "pass":
            blockers.append(f"Readiness gate {name} is {status}, expected pass.")
    return blockers


def _due_diligence_blockers(due_diligence: dict[str, Any] | None) -> list[str]:
    blockers = []
    if not due_diligence:
        return ["Missing due-diligence report."]
    if due_diligence.get("status") not in {"local_ready", "production_ready"}:
        blockers.append(f"Due-diligence report status is {due_diligence.get('status')!r}.")
    redaction = due_diligence.get("redaction") if isinstance(due_diligence.get("redaction"), dict) else {}
    if redaction.get("status") != "pass":
        blockers.append("Due-diligence redaction scan is not pass.")
    missing_sources = due_diligence.get("source_manifest_summary", {}).get("missing", [])
    if missing_sources:
        blockers.append(f"Source manifest is missing files: {missing_sources}.")
    return blockers


def _production_blockers(
    readiness: dict[str, Any] | None,
    due_diligence: dict[str, Any] | None,
    live_readiness: dict[str, Any] | None,
    launch: dict[str, Any] | None,
    customer_access: dict[str, Any] | None,
    schema_verification: dict[str, Any] | None,
) -> list[str]:
    blockers = []
    if not live_readiness:
        blockers.append("Missing live readiness report with status ready.")
    else:
        if live_readiness.get("status") != "ready":
            blockers.append(f"Live readiness status is {live_readiness.get('status')!r}, expected 'ready'.")
        if live_readiness.get("ready_to_run_live_cutover") is not True:
            blockers.append("Live readiness ready_to_run_live_cutover is not true.")
        if live_readiness.get("guardrails", {}).get("secrets_written") is not False:
            blockers.append("Live readiness guardrail secrets_written is not false.")
    if not schema_verification:
        blockers.append("Missing live schema verification report with production_verified=true.")
    else:
        if schema_verification.get("status") != "pass":
            blockers.append(f"Schema verification status is {schema_verification.get('status')!r}, expected 'pass'.")
        if schema_verification.get("production_verified") is not True:
            blockers.append("Schema verification production_verified is not true.")
        if schema_verification.get("contract_status") != "pass":
            blockers.append(f"Schema verification contract_status is {schema_verification.get('contract_status')!r}, expected 'pass'.")
        if schema_verification.get("live_status") != "pass":
            blockers.append(f"Schema verification live_status is {schema_verification.get('live_status')!r}, expected 'pass'.")
    if not launch:
        blockers.append("Missing live launch report with production_verified=true.")
    else:
        if launch.get("status") != "pass":
            blockers.append(f"Launch report status is {launch.get('status')!r}, expected 'pass'.")
        if launch.get("production_verified") is not True:
            blockers.append("Launch report production_verified is not true.")
        rls_status = launch.get("rls_probe", {}).get("status")
        if rls_status != "pass":
            blockers.append(f"Launch RLS probe status is {rls_status!r}, expected 'pass'.")
        cleanup_status = launch.get("cleanup", {}).get("status")
        if cleanup_status not in {"ready_for_review", "reviewed", "applied"}:
            blockers.append(f"Launch cleanup status is {cleanup_status!r}; cleanup plan must be reviewable.")
    if not customer_access:
        blockers.append("Missing customer access verification report with production_verified=true.")
    else:
        if customer_access.get("status") != "pass":
            blockers.append(f"Customer access verification status is {customer_access.get('status')!r}, expected 'pass'.")
        if customer_access.get("production_verified") is not True:
            blockers.append("Customer access verification production_verified is not true.")
        access_rls_status = customer_access.get("rls_probe", {}).get("status")
        if access_rls_status != "pass":
            blockers.append(f"Customer access RLS probe status is {access_rls_status!r}, expected 'pass'.")
    return blockers


def build_release_audit(
    readiness: dict[str, Any] | None,
    due_diligence: dict[str, Any] | None,
    live_readiness: dict[str, Any] | None = None,
    launch: dict[str, Any] | None = None,
    customer_access: dict[str, Any] | None = None,
    schema_verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    buyer_blockers = _readiness_blockers(readiness) + _due_diligence_blockers(due_diligence)
    production_blockers = buyer_blockers + _production_blockers(
        readiness,
        due_diligence,
        live_readiness,
        launch,
        customer_access,
        schema_verification,
    )
    buyer_review = "go" if not buyer_blockers else "no_go"
    production = "go" if not production_blockers else "no_go"
    status = "production_ready" if production == "go" else ("buyer_review_ready" if buyer_review == "go" else "action_required")

    return {
        "report_type": "homepilot_release_audit",
        "created_at": utc_now(),
        "status": status,
        "decisions": {
            "buyer_review": buyer_review,
            "production": production,
        },
        "blockers": {
            "buyer_review": buyer_blockers,
            "production": production_blockers,
        },
        "evidence": {
            "readiness_status": readiness.get("status") if readiness else None,
            "readiness_gates": _gate_statuses(readiness),
            "readiness_production_verified": readiness.get("production_verified") if readiness else None,
            "production_proof_source": "live readiness + live schema verification + live launch report + customer access verification report",
            "due_diligence_status": due_diligence.get("status") if due_diligence else None,
            "due_diligence_redaction": due_diligence.get("redaction", {}) if due_diligence else {},
            "live_readiness_status": live_readiness.get("status") if live_readiness else None,
            "live_readiness_ready_to_run_live_cutover": live_readiness.get("ready_to_run_live_cutover") if live_readiness else None,
            "live_readiness_guardrails": live_readiness.get("guardrails", {}) if live_readiness else {},
            "schema_verification_status": schema_verification.get("status") if schema_verification else None,
            "schema_verification_production_verified": schema_verification.get("production_verified") if schema_verification else None,
            "schema_verification_contract_status": schema_verification.get("contract_status") if schema_verification else None,
            "schema_verification_live_status": schema_verification.get("live_status") if schema_verification else None,
            "launch_status": launch.get("status") if launch else None,
            "launch_production_verified": launch.get("production_verified") if launch else None,
            "launch_rls_probe": launch.get("rls_probe", {}) if launch else {},
            "customer_access_status": customer_access.get("status") if customer_access else None,
            "customer_access_production_verified": customer_access.get("production_verified") if customer_access else None,
            "customer_access_rls_probe": customer_access.get("rls_probe", {}) if customer_access else {},
        },
        "required_for_production": [
            "readiness report status pass",
            "due-diligence report status production_ready or local_ready with clean redaction",
            "live readiness report status ready",
            "live readiness ready_to_run_live_cutover true",
            "live readiness secrets_written false",
            "live schema verification report status pass",
            "schema verification production_verified true",
            "schema verification contract_status and live_status pass",
            "live launch report status pass",
            "launch report production_verified true",
            "launch RLS probe pass with real customer JWTs",
            "customer access verification report status pass",
            "customer access verification production_verified true",
            "customer access RLS probe pass for planned invitees",
            "fixture cleanup plan ready for review",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot release go/no-go audit")
    parser.add_argument("--readiness-report", required=True, type=Path)
    parser.add_argument("--due-diligence-report", required=True, type=Path)
    parser.add_argument("--launch-report", type=Path)
    parser.add_argument("--customer-access-report", type=Path)
    parser.add_argument("--schema-verification-report", type=Path)
    parser.add_argument("--live-readiness-report", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--require-production", action="store_true")
    args = parser.parse_args()

    report = build_release_audit(
        readiness=load_json(args.readiness_report),
        due_diligence=load_json(args.due_diligence_report),
        live_readiness=load_json(args.live_readiness_report),
        launch=load_json(args.launch_report),
        customer_access=load_json(args.customer_access_report),
        schema_verification=load_json(args.schema_verification_report),
    )
    write_json(args.out, report)
    print(json.dumps({
        "output": str(args.out),
        "status": report["status"],
        "buyer_review": report["decisions"]["buyer_review"],
        "production": report["decisions"]["production"],
        "production_blockers": report["blockers"]["production"],
    }, indent=2, ensure_ascii=False))
    if report["decisions"]["buyer_review"] != "go":
        raise SystemExit(1)
    if args.require_production and report["decisions"]["production"] != "go":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
