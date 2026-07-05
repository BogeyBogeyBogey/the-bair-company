#!/usr/bin/env python3
"""
Reconcile partner Auth mapping, account access, and customer-access evidence.

This pack is intentionally non-mutating. It does not create users, write
memberships, call Supabase, or expose raw contact data. It answers one narrow
production-readiness question: do the approved partner Auth mappings appear in
the planned membership rows and in the customer-access verification contract?
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


SECRET_PATTERNS = (
    re.compile(r"service[-_ ]?role", re.IGNORECASE),
    re.compile(r"authorization:\s*bearer", re.IGNORECASE),
    re.compile(r"secret-token", re.IGNORECASE),
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


def _text(value: Any) -> str:
    return str(value or "").strip()


def _valid_uuid(value: Any) -> bool:
    try:
        uuid.UUID(_text(value))
    except (TypeError, ValueError):
        return False
    return True


def _is_partner_id(value: Any) -> bool:
    partner_id = _text(value)
    return bool(partner_id) and not partner_id.startswith("customer_to_confirm")


def _mapping_ready(partner_auth_mapping: dict[str, Any] | None) -> bool:
    if not partner_auth_mapping:
        return False
    summary = partner_auth_mapping.get("summary") or {}
    expected = int(summary.get("expected_partner_count") or 0)
    mapped = int(summary.get("mapped_partner_count") or 0)
    return (
        partner_auth_mapping.get("status") == "ready_for_membership_sql_review"
        and expected > 0
        and mapped >= expected
        and int(summary.get("blockers") or 0) == 0
        and int(summary.get("executable_statement_count") or 0) > 0
    )


def _expected_partners(partner_auth_mapping: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not partner_auth_mapping:
        return []
    expected = partner_auth_mapping.get("expected_partners")
    if isinstance(expected, list) and expected:
        return [
            {
                "partner_id": _text(row.get("partner_id")).lower(),
                "partner_name": _text(row.get("partner_name")),
                "source": _text(row.get("source")),
            }
            for row in expected
            if isinstance(row, dict) and _text(row.get("partner_id"))
        ]
    rows = partner_auth_mapping.get("mapping_rows") if isinstance(partner_auth_mapping.get("mapping_rows"), list) else []
    seen: set[str] = set()
    partners: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        partner_id = _text(row.get("partner_id")).lower()
        if not partner_id or partner_id in seen:
            continue
        seen.add(partner_id)
        partners.append({
            "partner_id": partner_id,
            "partner_name": _text(row.get("partner_name")),
            "source": _text(row.get("source")),
        })
    return partners


def _mapping_by_partner(partner_auth_mapping: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    rows = (partner_auth_mapping or {}).get("mapping_rows")
    if not isinstance(rows, list):
        return {}
    mapped: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        partner_id = _text(row.get("partner_id")).lower()
        if partner_id:
            mapped[partner_id] = row
    return mapped


def _account_memberships(account_access_plan: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    rows = (account_access_plan or {}).get("membership_rows")
    if not isinstance(rows, list):
        return {}
    by_partner: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        partner_id = _text(row.get("partner_id")).lower()
        if partner_id:
            by_partner.setdefault(partner_id, []).append(row)
    return by_partner


def _customer_identities(customer_access_verification: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    rows = (customer_access_verification or {}).get("identities")
    if not isinstance(rows, list):
        return {}
    by_partner: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        partner_id = _text(row.get("partner_id")).lower()
        if partner_id:
            by_partner.setdefault(partner_id, []).append(row)
    return by_partner


def _add_issue(
    issues: list[dict[str, Any]],
    severity: str,
    issue_key: str,
    partner_id: str,
    evidence: str,
    detail: str,
    next_action: str,
    blocks_production: bool = True,
) -> None:
    issues.append({
        "severity": severity,
        "issue_key": issue_key,
        "partner_id": partner_id,
        "evidence": evidence,
        "detail": detail,
        "next_action": next_action,
        "blocks_production": blocks_production,
    })


def _matching_user(rows: list[dict[str, Any]], user_id: str) -> dict[str, Any] | None:
    for row in rows:
        if _text(row.get("user_id")).lower() == user_id.lower():
            return row
    return None


def _coverage_status(rows: list[dict[str, Any]], user_id: str) -> str:
    if not user_id:
        return "waiting_for_partner_auth_mapping"
    if _matching_user(rows, user_id):
        return "matched"
    if rows:
        return "user_id_mismatch"
    return "missing"


def _matrix_and_issues(
    expected_partners: list[dict[str, Any]],
    partner_auth_mapping: dict[str, Any] | None,
    account_access_plan: dict[str, Any] | None,
    customer_access_verification: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    mapping_rows = _mapping_by_partner(partner_auth_mapping)
    memberships = _account_memberships(account_access_plan)
    identities = _customer_identities(customer_access_verification)
    customer_production_verified = bool((customer_access_verification or {}).get("production_verified"))

    if not partner_auth_mapping:
        _add_issue(
            issues,
            "blocker",
            "partner_auth_mapping_missing",
            "",
            "PARTNER_AUTH_MAPPING.md",
            "Partner Auth mapping evidence is missing.",
            "Build the partner Auth mapping pack before partner access reconciliation.",
        )
    elif not _mapping_ready(partner_auth_mapping):
        _add_issue(
            issues,
            "blocker",
            "partner_auth_mapping_not_ready",
            "",
            "PARTNER_AUTH_MAPPING.md",
            "Partner Auth mapping is not ready for membership SQL review.",
            "Map every approved partner to a real Supabase Auth UUID and rerun reconciliation.",
        )
    if not account_access_plan:
        _add_issue(
            issues,
            "blocker",
            "account_access_plan_missing",
            "",
            "account_access_plan.json",
            "Account access plan is missing.",
            "Build account-access evidence with partner-scoped membership rows.",
        )
    elif account_access_plan.get("status") != "pass" or account_access_plan.get("review_status") != "ready":
        _add_issue(
            issues,
            "blocker",
            "account_access_plan_not_ready",
            "",
            "account_access_plan.json",
            "Account access plan is not pass/ready.",
            "Resolve account-access failures before partner access reconciliation.",
        )
    if not customer_access_verification:
        _add_issue(
            issues,
            "blocker",
            "customer_access_verification_missing",
            "",
            "customer_access_verification.json",
            "Customer access verification is missing.",
            "Run customer-access verification from the account access plan.",
        )
    elif not customer_production_verified:
        _add_issue(
            issues,
            "blocker",
            "customer_access_not_production_verified",
            "",
            "customer_access_verification.json",
            "Customer access verification has not passed with production_verified=true.",
            "Run live owner, manager, and partner-scoped access probes with real customer credentials.",
        )

    matrix: list[dict[str, Any]] = []
    for partner in expected_partners:
        partner_id = _text(partner.get("partner_id")).lower()
        row = mapping_rows.get(partner_id, {})
        user_id = _text(row.get("supabase_user_id"))
        uuid_status = _text(row.get("uuid_status")) or ("valid" if _valid_uuid(user_id) else "missing")
        account_rows = memberships.get(partner_id, [])
        customer_rows = identities.get(partner_id, [])
        account_status = _coverage_status(account_rows, user_id)
        customer_status = _coverage_status(customer_rows, user_id)
        mapped_status = "mapped" if user_id and uuid_status == "valid" else "missing_or_invalid"

        if _is_partner_id(partner_id) and user_id and uuid_status == "valid":
            if account_status == "missing":
                _add_issue(
                    issues,
                    "blocker",
                    "membership_row_missing",
                    partner_id,
                    "account_access_plan.json",
                    "Mapped partner Auth user is not present in partner-scoped membership rows.",
                    "Add the mapped Supabase Auth UUID to account access or rerun membership planning.",
                )
            elif account_status == "user_id_mismatch":
                _add_issue(
                    issues,
                    "blocker",
                    "membership_user_id_mismatch",
                    partner_id,
                    "account_access_plan.json",
                    "Account access has this partner_id but with a different user_id.",
                    "Align account-access membership rows with the partner Auth mapping.",
                )
            if customer_status == "missing":
                _add_issue(
                    issues,
                    "blocker",
                    "customer_access_identity_missing",
                    partner_id,
                    "customer_access_verification.json",
                    "Mapped partner Auth user is not present in customer-access verification identities.",
                    "Rerun customer-access verification after partner Auth users are in the account plan.",
                )
            elif customer_status == "user_id_mismatch":
                _add_issue(
                    issues,
                    "blocker",
                    "customer_access_user_id_mismatch",
                    partner_id,
                    "customer_access_verification.json",
                    "Customer-access verification has this partner_id but with a different user_id.",
                    "Align customer-access probe identities with the partner Auth mapping.",
                )

        matrix.append({
            "partner_id": partner_id,
            "partner_name": _text(partner.get("partner_name")),
            "mapped_user_status": mapped_status,
            "uuid_status": uuid_status,
            "account_access_status": account_status,
            "customer_access_status": customer_status,
            "customer_access_production_verified": customer_production_verified,
            "overall_status": "pass" if (
                mapped_status == "mapped"
                and account_status == "matched"
                and customer_status == "matched"
                and customer_production_verified
            ) else "blocked",
        })
    return matrix, issues


def _summary(
    expected_partners: list[dict[str, Any]],
    matrix: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    partner_auth_mapping: dict[str, Any] | None,
    account_access_plan: dict[str, Any] | None,
    customer_access_verification: dict[str, Any] | None,
) -> dict[str, Any]:
    blockers = [issue for issue in issues if issue.get("severity") == "blocker"]
    return {
        "expected_partner_count": len(expected_partners),
        "mapped_partner_count": len([row for row in matrix if row["mapped_user_status"] == "mapped"]),
        "account_access_covered_count": len([row for row in matrix if row["account_access_status"] == "matched"]),
        "customer_access_covered_count": len([row for row in matrix if row["customer_access_status"] == "matched"]),
        "fully_reconciled_partner_count": len([row for row in matrix if row["overall_status"] == "pass"]),
        "blockers": len(blockers),
        "warnings": len([issue for issue in issues if issue.get("severity") == "warning"]),
        "partner_auth_mapping_status": (partner_auth_mapping or {}).get("status"),
        "account_access_status": (account_access_plan or {}).get("status"),
        "customer_access_status": (customer_access_verification or {}).get("status"),
        "customer_access_production_verified": bool((customer_access_verification or {}).get("production_verified")),
    }


def _status(summary: dict[str, Any], issues: list[dict[str, Any]]) -> str:
    keys = {issue.get("issue_key") for issue in issues if issue.get("severity") == "blocker"}
    if not issues and summary["expected_partner_count"] and summary["fully_reconciled_partner_count"] >= summary["expected_partner_count"]:
        return "partner_access_reconciled"
    if "partner_auth_mapping_missing" in keys or "partner_auth_mapping_not_ready" in keys:
        return "blocked_until_partner_auth_mapping"
    if "account_access_plan_missing" in keys or "account_access_plan_not_ready" in keys:
        return "blocked_until_account_access_plan"
    if "customer_access_verification_missing" in keys or "customer_access_not_production_verified" in keys:
        return "blocked_until_customer_access_verification"
    return "blocked_until_partner_access_alignment"


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# HomePilot Partner Access Reconciliation",
        "",
        f"Release: {report['release_label']}",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        f"Production ready: {str(report['production_ready']).lower()}",
        "",
        "This pack reconciles partner Auth mapping, account membership planning, and customer-access verification. It is non-mutating and does not grant access.",
        "",
        "## Summary",
        "",
        f"- Expected partners: {summary['expected_partner_count']}",
        f"- Mapped partners: {summary['mapped_partner_count']}",
        f"- Account-access covered: {summary['account_access_covered_count']}",
        f"- Customer-access covered: {summary['customer_access_covered_count']}",
        f"- Fully reconciled: {summary['fully_reconciled_partner_count']}",
        f"- Customer access production verified: {str(summary['customer_access_production_verified']).lower()}",
        f"- Blockers: {summary['blockers']}",
        "",
        "## Partner Matrix",
        "",
        "| Partner | Mapping | Account access | Customer access | Overall |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report["partner_matrix"]:
        lines.append(
            f"| {row['partner_id']} | {row['mapped_user_status']} | {row['account_access_status']} | {row['customer_access_status']} | {row['overall_status']} |"
        )
    lines += ["", "## Issues", ""]
    if report["issues"]:
        for issue in report["issues"]:
            partner = f" `{issue['partner_id']}`" if issue.get("partner_id") else ""
            lines.append(f"- {issue['severity']}: {issue['issue_key']}{partner} - {issue['next_action']}")
    else:
        lines.append("- No reconciliation issues detected.")
    lines += ["", "## Guardrails", ""]
    for key, value in report["guardrails"].items():
        value = "yes" if value is True else "no" if value is False else value
        lines.append(f"- {key}: {value}")
    lines.append("")
    return "\n".join(lines)


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _secret_scan(report: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(report, ensure_ascii=False)
    findings = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(body)]
    return {
        "status": "pass" if not findings else "fail",
        "issue_count": len(findings),
        "patterns": findings,
    }


def build_partner_access_reconciliation_pack(
    out_dir: Path,
    *,
    partner_auth_mapping: dict[str, Any] | None,
    account_access_plan: dict[str, Any] | None,
    customer_access_verification: dict[str, Any] | None,
    release_label: str = "local",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    expected_partners = _expected_partners(partner_auth_mapping)
    matrix, issues = _matrix_and_issues(
        expected_partners,
        partner_auth_mapping,
        account_access_plan,
        customer_access_verification,
    )
    summary = _summary(
        expected_partners,
        matrix,
        issues,
        partner_auth_mapping,
        account_access_plan,
        customer_access_verification,
    )
    status = _status(summary, issues)
    report = {
        "reconciliation_type": "homepilot_partner_access_reconciliation",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": status,
        "production_ready": status == "partner_access_reconciled",
        "summary": summary,
        "partner_matrix": matrix,
        "issues": issues,
        "source_contract": {
            "partner_auth_mapping": "partner_id + supabase_user_id",
            "account_access_plan": "membership_rows partner_id + user_id",
            "customer_access_verification": "identities partner_id + user_id + production_verified",
        },
        "guardrails": {
            "non_mutating_pack": True,
            "no_database_writes": True,
            "no_supabase_writes": True,
            "no_secret_values_written": True,
            "no_raw_contact_values_written": True,
            "tenant_scoped": True,
            "module_scoped": True,
            "partner_scoped": True,
            "production_requires_customer_access_probe": True,
            "synthetic_demo_results_must_be_labelled": True,
        },
        "paths": {
            "partner_access_reconciliation": str(out_dir / "partner_access_reconciliation.json"),
            "partner_access_reconciliation_markdown": str(out_dir / "PARTNER_ACCESS_RECONCILIATION.md"),
            "partner_access_reconciliation_matrix": str(out_dir / "PARTNER_ACCESS_RECONCILIATION_MATRIX.csv"),
            "partner_access_reconciliation_issues": str(out_dir / "PARTNER_ACCESS_RECONCILIATION_ISSUES.csv"),
        },
    }
    report["secret_scan"] = _secret_scan(report)
    if report["secret_scan"]["status"] != "pass":
        report["status"] = "fail_secret_scan"
        report["production_ready"] = False
    write_json(out_dir / "partner_access_reconciliation.json", report)
    write_text(out_dir / "PARTNER_ACCESS_RECONCILIATION.md", render_markdown(report))
    write_csv(out_dir / "PARTNER_ACCESS_RECONCILIATION_MATRIX.csv", matrix, [
        "partner_id",
        "partner_name",
        "mapped_user_status",
        "uuid_status",
        "account_access_status",
        "customer_access_status",
        "customer_access_production_verified",
        "overall_status",
    ])
    write_csv(out_dir / "PARTNER_ACCESS_RECONCILIATION_ISSUES.csv", issues, [
        "severity",
        "issue_key",
        "partner_id",
        "evidence",
        "detail",
        "next_action",
        "blocks_production",
    ])
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HomePilot partner access reconciliation evidence")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--partner-auth-mapping", type=Path)
    parser.add_argument("--account-access-plan", type=Path)
    parser.add_argument("--customer-access-verification", type=Path)
    parser.add_argument("--release-label", default="local")
    args = parser.parse_args()
    report = build_partner_access_reconciliation_pack(
        args.out_dir,
        partner_auth_mapping=load_json(args.partner_auth_mapping),
        account_access_plan=load_json(args.account_access_plan),
        customer_access_verification=load_json(args.customer_access_verification),
        release_label=args.release_label,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": report["status"],
        "production_ready": report["production_ready"],
        "expected_partner_count": report["summary"]["expected_partner_count"],
        "fully_reconciled_partner_count": report["summary"]["fully_reconciled_partner_count"],
        "paths": report["paths"],
    }, indent=2, ensure_ascii=False))
    if report["secret_scan"]["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
