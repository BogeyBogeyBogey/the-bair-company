#!/usr/bin/env python3
"""
HomePilot retention and lifecycle audit.

This module turns privacy retention from a note into a repeatable operating
control. It audits contacted campaign targets for retention review dates,
delete-after dates, opt-out lifecycle handling, and produces reviewable actions
without mutating production data.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_store import load_payload, validate_payload


CONTACTED_STATUSES = {"sent", "scanned", "clicked", "responded", "appointment", "customer", "no_response"}
OPT_OUT_RESPONSES = {"do_not_contact", "wrong_address"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("metadata")
    return value if isinstance(value, dict) else {}


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _days_until(target: date | None, as_of: date) -> int | None:
    if target is None:
        return None
    return (target - as_of).days


def _is_opted_out(target: dict[str, Any], payload: dict[str, Any]) -> bool:
    metadata = _metadata(target)
    if metadata.get("do_not_contact") or metadata.get("opted_out") or metadata.get("suppressed"):
        return True
    pair = (target.get("property_id"), target.get("module_key"), target.get("campaign_id"))
    for interaction in payload.get("interactions", []):
        if interaction.get("property_id") != pair[0]:
            continue
        if interaction.get("module_key") != pair[1]:
            continue
        if pair[2] and interaction.get("campaign_id") not in (pair[2], None):
            continue
        if interaction.get("response_status") in OPT_OUT_RESPONSES:
            return True
    return False


def _action(
    target: dict[str, Any],
    action_type: str,
    severity: str,
    reason: str,
    **details: Any,
) -> dict[str, Any]:
    return {
        "property_id": target.get("property_id"),
        "module_key": target.get("module_key"),
        "campaign_id": target.get("campaign_id"),
        "status": target.get("status"),
        "action": action_type,
        "severity": severity,
        "reason": reason,
        **{key: value for key, value in details.items() if value not in (None, "", [])},
    }


def build_retention_report(
    payload: dict[str, Any],
    as_of: date | str | None = None,
    warning_days: int = 30,
) -> dict[str, Any]:
    validate_payload(payload)
    if isinstance(as_of, str):
        as_of_date = date.fromisoformat(as_of[:10])
    else:
        as_of_date = as_of or today_utc()
    warning_days = int(warning_days)

    actions: list[dict[str, Any]] = []
    contacted_count = 0
    scheduled_count = 0
    opt_out_count = 0

    for target in payload.get("campaign_targets", []):
        status = str(target.get("status") or "")
        if status not in CONTACTED_STATUSES:
            continue
        contacted_count += 1
        metadata = _metadata(target)
        review_at = _parse_date(metadata.get("retention_review_at"))
        delete_after = _parse_date(metadata.get("delete_after"))
        has_schedule = bool(review_at or delete_after)
        if has_schedule:
            scheduled_count += 1
        opted_out = _is_opted_out(target, payload)
        if opted_out:
            opt_out_count += 1

        if not has_schedule:
            actions.append(_action(
                target,
                "add_retention_schedule",
                "fail",
                "Contacted target has no retention_review_at or delete_after metadata.",
            ))
            continue

        delete_days = _days_until(delete_after, as_of_date)
        review_days = _days_until(review_at, as_of_date)
        if delete_after and delete_days is not None and delete_days <= 0:
            actions.append(_action(
                target,
                "build_delete_plan",
                "fail",
                "delete_after is due or overdue.",
                delete_after=delete_after.isoformat(),
                days_overdue=abs(delete_days),
            ))
        elif delete_after and delete_days is not None and delete_days <= warning_days:
            actions.append(_action(
                target,
                "prepare_delete_review",
                "warn",
                "delete_after is approaching.",
                delete_after=delete_after.isoformat(),
                days_until=delete_days,
            ))

        if review_at and review_days is not None and review_days <= 0:
            actions.append(_action(
                target,
                "review_retention",
                "warn",
                "retention_review_at is due or overdue.",
                retention_review_at=review_at.isoformat(),
                days_overdue=abs(review_days),
            ))
        elif review_at and review_days is not None and review_days <= warning_days:
            actions.append(_action(
                target,
                "prepare_retention_review",
                "warn",
                "retention_review_at is approaching.",
                retention_review_at=review_at.isoformat(),
                days_until=review_days,
            ))

        if opted_out and not delete_after:
            actions.append(_action(
                target,
                "set_delete_after_for_opt_out",
                "warn",
                "Opt-out/suppression record has no delete_after date.",
            ))

    failure_count = sum(1 for action in actions if action["severity"] == "fail")
    warning_count = sum(1 for action in actions if action["severity"] == "warn")
    delete_plan_property_ids = sorted({
        str(action["property_id"])
        for action in actions
        if action["action"] == "build_delete_plan" and action.get("property_id")
    })
    status = "fail" if failure_count else ("warn" if warning_count else "pass")
    return {
        "report_type": "homepilot_retention_lifecycle_audit",
        "created_at": utc_now(),
        "as_of": as_of_date.isoformat(),
        "status": status,
        "metrics": {
            "campaign_target_count": len(payload.get("campaign_targets", [])),
            "contacted_count": contacted_count,
            "scheduled_count": scheduled_count,
            "unscheduled_count": max(contacted_count - scheduled_count, 0),
            "opt_out_count": opt_out_count,
            "action_count": len(actions),
            "failure_count": failure_count,
            "warning_count": warning_count,
            "delete_plan_property_count": len(delete_plan_property_ids),
        },
        "actions": sorted(actions, key=lambda row: (row["severity"], row["action"], str(row.get("property_id")))),
        "delete_plan_property_ids": delete_plan_property_ids,
        "required_metadata": {
            "contacted_targets": ["retention_review_at or delete_after"],
            "opt_out_targets": ["delete_after", "suppression metadata where legally required"],
        },
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit HomePilot retention lifecycle metadata")
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--as-of", default="")
    parser.add_argument("--warning-days", type=int, default=30)
    parser.add_argument("--fail-on-warn", action="store_true")
    args = parser.parse_args()

    report = build_retention_report(
        load_payload(args.json),
        as_of=args.as_of or None,
        warning_days=args.warning_days,
    )
    write_json(args.out, report)
    print(json.dumps({
        "output": str(args.out),
        "status": report["status"],
        "actions": report["metrics"]["action_count"],
        "failures": report["metrics"]["failure_count"],
        "warnings": report["metrics"]["warning_count"],
    }, indent=2, ensure_ascii=False))
    if report["status"] == "fail" or (args.fail_on_warn and report["status"] == "warn"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
