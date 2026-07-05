#!/usr/bin/env python3
"""
HomePilot production preflight.

This module ties the market-readiness evidence together for operators:
local health, readiness gates, buyer due-diligence, optional live launch
evidence, and optional customer access verification evidence. It does not mutate
production data.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_healthcheck import build_healthcheck_report
from homepilot_release_audit import build_release_audit


STAGES = {"buyer_review", "live_launch", "production_rollout"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _health_blockers(healthcheck: dict[str, Any]) -> list[str]:
    blockers = []
    for check in healthcheck.get("checks", []):
        if check.get("status") == "fail":
            blockers.append(f"Healthcheck {check.get('name')} is fail.")
    return blockers


def _action(label: str, status: str, detail: str) -> dict[str, str]:
    return {"label": label, "status": status, "detail": detail}


def _next_actions(
    decisions: dict[str, str],
    local_health: dict[str, Any],
    live_health: dict[str, Any],
    schema_verification: dict[str, Any] | None,
    launch: dict[str, Any] | None,
    customer_access: dict[str, Any] | None,
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    local_fails = _health_blockers(local_health)
    live_fails = _health_blockers(live_health)
    if local_fails:
        actions.append(_action("fix_local_contracts", "required", "Resolve failing local health checks before buyer review."))
    if decisions["buyer_review"] == "go" and decisions["live_launch"] != "go":
        actions.append(_action("configure_live_environment", "required", "Set Supabase URL, service-role key, anon key, and verify REST reachability before live launch."))
    if decisions["live_launch"] == "go" and not schema_verification:
        actions.append(_action("run_live_schema_verification", "required", "Run homepilot_live_schema_verification.py --live and archive schema_verification.json."))
    if schema_verification and schema_verification.get("production_verified") is not True:
        actions.append(_action("fix_live_schema_verification", "required", "Resolve live schema verification failures before importing launch fixtures."))
    if decisions["live_launch"] == "go" and schema_verification and schema_verification.get("production_verified") is True and not launch:
        actions.append(_action("run_live_rls_launch", "required", "Run homepilot_launch.py rls-fixture with real Supabase users and archive launch/RLS reports."))
    if launch and launch.get("production_verified") is True and not customer_access:
        actions.append(_action("run_customer_access_verification", "required", "Run homepilot_customer_access_verification.py with planned customer identities and archive its RLS report."))
    if launch and customer_access and launch.get("production_verified") is True and customer_access.get("production_verified") is True and decisions["production"] == "go":
        actions.append(_action("review_cleanup_plan", "required", "Archive evidence first, then review and apply fixture cleanup SQL."))
    if live_fails and not local_fails:
        actions.append(_action("resolve_live_preflight", "required", "Live launch is blocked until all live health checks pass."))
    if not actions:
        actions.append(_action("continue", "ready", "Requested preflight stage has no blockers."))
    return actions


def build_preflight_report(
    readiness: dict[str, Any] | None,
    due_diligence: dict[str, Any] | None,
    launch: dict[str, Any] | None = None,
    customer_access: dict[str, Any] | None = None,
    schema_verification: dict[str, Any] | None = None,
    live_readiness: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
    stage: str = "buyer_review",
    live: bool = False,
) -> dict[str, Any]:
    if stage not in STAGES:
        raise ValueError(f"Unsupported stage: {stage}")
    env = dict(os.environ if env is None else env)

    local_health = build_healthcheck_report(env=env, live=False, require_live=False)
    live_health = build_healthcheck_report(env=env, live=live, require_live=True)
    release = build_release_audit(
        readiness=readiness,
        due_diligence=due_diligence,
        live_readiness=live_readiness,
        launch=launch,
        customer_access=customer_access,
        schema_verification=schema_verification,
    )

    buyer_blockers = _dedupe(_health_blockers(local_health) + release["blockers"]["buyer_review"])
    live_launch_blockers = _dedupe(buyer_blockers + _health_blockers(live_health))
    production_blockers = _dedupe(live_launch_blockers + release["blockers"]["production"])

    decisions = {
        "buyer_review": "go" if not buyer_blockers else "no_go",
        "live_launch": "go" if not live_launch_blockers else "no_go",
        "production": "go" if not production_blockers else "no_go",
    }
    blockers = {
        "buyer_review": buyer_blockers,
        "live_launch": live_launch_blockers,
        "production": production_blockers,
    }
    highest = (
        "production_ready" if decisions["production"] == "go"
        else "live_launch_ready" if decisions["live_launch"] == "go"
        else "buyer_review_ready" if decisions["buyer_review"] == "go"
        else "action_required"
    )
    stage_key = {
        "buyer_review": "buyer_review",
        "live_launch": "live_launch",
        "production_rollout": "production",
    }[stage]

    return {
        "report_type": "homepilot_production_preflight",
        "created_at": utc_now(),
        "requested_stage": stage,
        "stage_status": "pass" if decisions[stage_key] == "go" else "fail",
        "status": highest,
        "decisions": decisions,
        "blockers": blockers,
        "healthchecks": {
            "local": {
                "status": local_health["status"],
                "summary": local_health["summary"],
                "checks": {check["name"]: check["status"] for check in local_health["checks"]},
            },
            "live": {
                "status": live_health["status"],
                "summary": live_health["summary"],
                "checks": {check["name"]: check["status"] for check in live_health["checks"]},
            },
        },
        "release_audit": {
            "status": release["status"],
            "decisions": release["decisions"],
            "required_for_production": release["required_for_production"],
        },
        "evidence": {
            "readiness_status": readiness.get("status") if readiness else None,
            "due_diligence_status": due_diligence.get("status") if due_diligence else None,
            "schema_verification_status": schema_verification.get("status") if schema_verification else None,
            "schema_verification_production_verified": schema_verification.get("production_verified") if schema_verification else None,
            "schema_verification_contract_status": schema_verification.get("contract_status") if schema_verification else None,
            "schema_verification_live_status": schema_verification.get("live_status") if schema_verification else None,
            "launch_status": launch.get("status") if launch else None,
            "launch_production_verified": launch.get("production_verified") if launch else None,
            "launch_rls_probe": launch.get("rls_probe", {}).get("status") if launch else None,
            "customer_access_status": customer_access.get("status") if customer_access else None,
            "customer_access_production_verified": customer_access.get("production_verified") if customer_access else None,
            "customer_access_rls_probe": customer_access.get("rls_probe", {}).get("status") if customer_access else None,
        },
        "next_actions": _next_actions(decisions, local_health, live_health, schema_verification, launch, customer_access),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot production preflight report")
    parser.add_argument("--readiness-report", required=True, type=Path)
    parser.add_argument("--due-diligence-report", required=True, type=Path)
    parser.add_argument("--launch-report", type=Path)
    parser.add_argument("--customer-access-report", type=Path)
    parser.add_argument("--schema-verification-report", type=Path)
    parser.add_argument("--live-readiness-report", type=Path)
    parser.add_argument("--stage", choices=sorted(STAGES), default="buyer_review")
    parser.add_argument("--live", action="store_true", help="Also verify live Supabase REST reachability")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    report = build_preflight_report(
        readiness=load_json(args.readiness_report),
        due_diligence=load_json(args.due_diligence_report),
        launch=load_json(args.launch_report),
        customer_access=load_json(args.customer_access_report),
        schema_verification=load_json(args.schema_verification_report),
        live_readiness=load_json(args.live_readiness_report),
        stage=args.stage,
        live=args.live,
    )
    write_json(args.out, report)
    print(json.dumps({
        "output": str(args.out),
        "requested_stage": report["requested_stage"],
        "stage_status": report["stage_status"],
        "status": report["status"],
        "decisions": report["decisions"],
        "blockers": report["blockers"][{
            "buyer_review": "buyer_review",
            "live_launch": "live_launch",
            "production_rollout": "production",
        }[args.stage]],
    }, indent=2, ensure_ascii=False))
    if report["stage_status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
