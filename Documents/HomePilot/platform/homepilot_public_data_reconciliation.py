#!/usr/bin/env python3
"""
Reconcile public-data source, approval, and launch-gate evidence.

This pack is intentionally non-mutating. It does not fetch public datasets,
write Supabase rows, approve licences, or start imports. It answers one narrow
production-readiness question: do the public-data source register, production
intake, first-wave import plan, and launch gate agree on what can be imported,
what is only buyer-review evidence, and what remains blocked?
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
    re.compile(r"service[-_ ]?role", re.IGNORECASE),
    re.compile(r"authorization:\s*bearer", re.IGNORECASE),
    re.compile(r"secret-token", re.IGNORECASE),
)

APPROVED_APPROVAL_STATUSES = {
    "approved",
    "approved_for_production_import",
    "ready_for_production_import",
    "ready_for_import",
    "pass",
}
APPROVED_IMPORT_DECISIONS = {
    "approved_for_production_import",
    "ready_for_production_import",
    "ready_for_import",
    "pass",
}
NOT_USED_PUBLIC_DATA_VALUES = {
    "",
    "none",
    "no",
    "false",
    "n/a",
    "not_used",
    "none_until_approved",
}


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


def _norm(value: Any) -> str:
    return _text(value).lower().replace("-", "_").replace(" ", "_")


def _sources(public_register: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = (public_register or {}).get("sources")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _approvals(public_data_intake: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = (public_data_intake or {}).get("dataset_approvals")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _first_wave_public_data_required(import_plan: dict[str, Any] | None) -> bool:
    if not import_plan:
        return False
    rows = import_plan.get("property_source_runs")
    if not isinstance(rows, list):
        return False
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _norm(row.get("public_data_used")) not in NOT_USED_PUBLIC_DATA_VALUES:
            return True
    return False


def _first_wave_public_data_gate_status(first_wave_launch_gate: dict[str, Any] | None) -> str:
    gates = (first_wave_launch_gate or {}).get("gates")
    if not isinstance(gates, list):
        return "missing"
    for gate in gates:
        if isinstance(gate, dict) and gate.get("key") == "public_data_approval":
            return _norm(gate.get("status")) or "missing"
    return "missing"


def _live_proof_ready(first_wave_launch_gate: dict[str, Any] | None) -> bool:
    summary = (first_wave_launch_gate or {}).get("summary")
    if isinstance(summary, dict):
        return bool(summary.get("live_proof_ready"))
    return False


def _add_issue(
    issues: list[dict[str, Any]],
    severity: str,
    issue_key: str,
    source: str,
    evidence: str,
    detail: str,
    next_action: str,
    blocks_production: bool = True,
    blocks_first_wave: bool = False,
) -> None:
    issues.append({
        "severity": severity,
        "issue_key": issue_key,
        "source": source,
        "evidence": evidence,
        "detail": detail,
        "next_action": next_action,
        "blocks_production": blocks_production,
        "blocks_first_wave": blocks_first_wave,
    })


def _matrix_and_issues(
    public_register: dict[str, Any] | None,
    public_data_intake: dict[str, Any] | None,
    first_campaign_import_plan: dict[str, Any] | None,
    first_wave_launch_gate: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    sources = _sources(public_register)
    approvals = _approvals(public_data_intake)
    approvals_by_source = {_text(row.get("source")): row for row in approvals}
    required_for_first_wave = _first_wave_public_data_required(first_campaign_import_plan)
    public_gate_status = _first_wave_public_data_gate_status(first_wave_launch_gate)
    live_proof_ready = _live_proof_ready(first_wave_launch_gate)

    if not public_register:
        _add_issue(
            issues,
            "blocker",
            "public_data_source_register_missing",
            "",
            "PUBLIC_DATA_SOURCE_REGISTER.md",
            "Public-data source register is missing.",
            "Build the public-data source register before any production public-data import.",
        )
    elif public_register.get("status") != "buyer_review_public_data_ready":
        _add_issue(
            issues,
            "blocker",
            "public_data_source_register_not_ready",
            "",
            "PUBLIC_DATA_SOURCE_REGISTER.md",
            "Public-data source register is not buyer-review ready.",
            "Resolve public-data source register issues before production import review.",
        )

    if not public_data_intake:
        _add_issue(
            issues,
            "blocker",
            "public_data_production_intake_missing",
            "",
            "PUBLIC_DATA_PRODUCTION_INTAKE.md",
            "Public-data production intake is missing.",
            "Build the public-data production intake and approval checklist.",
        )
    elif _norm(public_data_intake.get("production_import_decision")) not in APPROVED_IMPORT_DECISIONS:
        _add_issue(
            issues,
            "blocker",
            "public_data_import_not_approved",
            "",
            "PUBLIC_DATA_PRODUCTION_INTAKE.md",
            "Public-data production import is not approved.",
            "Complete dataset-level approvals and live proof before importing public-data enrichments.",
        )

    if required_for_first_wave and public_gate_status != "pass":
        _add_issue(
            issues,
            "blocker",
            "first_wave_public_data_gate_blocked",
            "",
            "FIRST_WAVE_LAUNCH_GATE.md",
            "First-wave import plan uses public data but the launch gate has not passed public-data approval.",
            "Complete public-data approval before first-wave launch.",
            blocks_first_wave=True,
        )

    if not live_proof_ready:
        _add_issue(
            issues,
            "blocker",
            "live_proof_missing",
            "",
            "live_readiness.json; schema_verification.json; launch_report.json; customer_access_verification.json",
            "Live schema, RLS, and customer-access proof is not ready.",
            "Run live verification with production_verified=true before production public-data import.",
        )

    register_source_names = {_text(row.get("source")) for row in sources}
    approval_source_names = set(approvals_by_source)
    for missing in sorted(register_source_names - approval_source_names):
        _add_issue(
            issues,
            "blocker",
            "dataset_approval_missing",
            missing,
            "PUBLIC_DATA_APPROVAL_CHECKLIST.csv",
            "Source is listed in the register but missing from the production approval checklist.",
            "Add a dataset approval row with licence, allowed-use, attribution, field allowlist, and owner.",
        )
    for extra in sorted(approval_source_names - register_source_names):
        _add_issue(
            issues,
            "warning",
            "approval_without_register_source",
            extra,
            "PUBLIC_DATA_SOURCE_REGISTER.md",
            "Production intake includes a source that is not in the public-data source register.",
            "Add the source to the register or remove it from production intake.",
            blocks_production=False,
        )

    matrix: list[dict[str, Any]] = []
    for source in sources:
        source_name = _text(source.get("source"))
        approval = approvals_by_source.get(source_name, {})
        approval_status = _norm(approval.get("approval_status"))
        import_decision = _norm(approval.get("production_import_decision"))
        register_status = _norm(source.get("recommended_status"))
        source_is_approved = approval_status in APPROVED_APPROVAL_STATUSES
        import_is_approved = import_decision in APPROVED_IMPORT_DECISIONS
        row_status = "approved_for_production_import" if source_is_approved and import_is_approved and live_proof_ready else "blocked"

        if approval and not source_is_approved:
            _add_issue(
                issues,
                "blocker",
                "dataset_approval_not_ready",
                source_name,
                "PUBLIC_DATA_APPROVAL_CHECKLIST.csv",
                f"Dataset approval status is {approval.get('approval_status') or 'missing'}.",
                "Approve the exact dataset, allowed use, attribution, field allowlist, transform version, and owner before import.",
            )
        if approval and not import_is_approved:
            _add_issue(
                issues,
                "blocker",
                "dataset_import_decision_not_ready",
                source_name,
                "PUBLIC_DATA_APPROVAL_CHECKLIST.csv",
                f"Production import decision is {approval.get('production_import_decision') or 'missing'}.",
                "Move the dataset import decision to approved_for_production_import only after all evidence is archived.",
            )
        if register_status in {"legal_review_required", "review_required"} and not source_is_approved:
            _add_issue(
                issues,
                "blocker",
                "legal_review_required",
                source_name,
                "PUBLIC_DATA_SOURCE_REGISTER.md",
                f"Register status is {source.get('recommended_status')}.",
                "Complete legal/privacy review before production use.",
            )

        matrix.append({
            "source": source_name,
            "publisher": _text(source.get("publisher")),
            "register_status": source.get("recommended_status") or "",
            "licence_or_terms": source.get("licence_or_terms") or "",
            "approval_status": approval.get("approval_status") or "missing",
            "production_import_decision": approval.get("production_import_decision") or "missing",
            "data_category": approval.get("data_category") or "",
            "storage_target": approval.get("storage_target") or "",
            "first_wave_public_data_required": required_for_first_wave,
            "first_wave_public_data_gate_status": public_gate_status,
            "live_proof_ready": live_proof_ready,
            "overall_status": row_status,
        })
    return matrix, issues


def _summary(
    matrix: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    first_campaign_import_plan: dict[str, Any] | None,
    first_wave_launch_gate: dict[str, Any] | None,
) -> dict[str, Any]:
    blockers = [issue for issue in issues if issue.get("severity") == "blocker"]
    return {
        "registered_source_count": len(matrix),
        "approved_source_count": len([row for row in matrix if row["overall_status"] == "approved_for_production_import"]),
        "blocked_source_count": len([row for row in matrix if row["overall_status"] != "approved_for_production_import"]),
        "blockers": len(blockers),
        "warnings": len([issue for issue in issues if issue.get("severity") == "warning"]),
        "first_wave_public_data_required": _first_wave_public_data_required(first_campaign_import_plan),
        "first_wave_public_data_gate_status": _first_wave_public_data_gate_status(first_wave_launch_gate),
        "first_wave_blocks": len([issue for issue in blockers if issue.get("blocks_first_wave")]),
        "live_proof_ready": _live_proof_ready(first_wave_launch_gate),
    }


def _status(summary: dict[str, Any]) -> str:
    if summary["registered_source_count"] and summary["approved_source_count"] >= summary["registered_source_count"] and summary["blockers"] == 0:
        return "public_data_reconciled_for_production_import"
    if summary["first_wave_public_data_required"] and summary["first_wave_blocks"]:
        return "blocked_until_public_data_approval"
    if summary["blocked_source_count"] and not summary["live_proof_ready"]:
        return "blocked_until_dataset_approvals_and_live_proof"
    if summary["blocked_source_count"]:
        return "blocked_until_dataset_approvals"
    return "blocked_until_public_data_reconciliation"


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# HomePilot Public Data Reconciliation",
        "",
        f"Release: {report['release_label']}",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        f"Production import ready: {str(report['production_import_ready']).lower()}",
        "",
        "This pack reconciles the public-data source register, production intake, first-wave import plan, and launch-gate status. It is non-mutating and does not approve, fetch, or import public data.",
        "",
        "## Summary",
        "",
        f"- Registered sources: {summary['registered_source_count']}",
        f"- Approved sources: {summary['approved_source_count']}",
        f"- Blocked sources: {summary['blocked_source_count']}",
        f"- First-wave public data required: {str(summary['first_wave_public_data_required']).lower()}",
        f"- First-wave public-data gate: {summary['first_wave_public_data_gate_status']}",
        f"- Live proof ready: {str(summary['live_proof_ready']).lower()}",
        f"- Blockers: {summary['blockers']}",
        "",
        "## Source Matrix",
        "",
        "| Source | Register | Approval | Import decision | Overall |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report["source_matrix"]:
        lines.append(
            f"| {row['source']} | {row['register_status']} | {row['approval_status']} | {row['production_import_decision']} | {row['overall_status']} |"
        )
    lines += ["", "## Issues", ""]
    if report["issues"]:
        for issue in report["issues"]:
            source = f" `{issue['source']}`" if issue.get("source") else ""
            lines.append(f"- {issue['severity']}: {issue['issue_key']}{source} - {issue['next_action']}")
    else:
        lines.append("- No public-data reconciliation issues detected.")
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


def build_public_data_reconciliation_pack(
    out_dir: Path,
    *,
    public_register: dict[str, Any] | None,
    public_data_intake: dict[str, Any] | None,
    first_campaign_import_plan: dict[str, Any] | None,
    first_wave_launch_gate: dict[str, Any] | None,
    release_label: str = "local",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    matrix, issues = _matrix_and_issues(
        public_register,
        public_data_intake,
        first_campaign_import_plan,
        first_wave_launch_gate,
    )
    summary = _summary(matrix, issues, first_campaign_import_plan, first_wave_launch_gate)
    status = _status(summary)
    report = {
        "reconciliation_type": "homepilot_public_data_reconciliation",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": status,
        "production_import_ready": status == "public_data_reconciled_for_production_import",
        "summary": summary,
        "source_matrix": matrix,
        "issues": issues,
        "source_contract": {
            "public_register": "sources source + licence_or_terms + recommended_status",
            "public_data_intake": "dataset_approvals source + approval_status + production_import_decision",
            "first_campaign_import_plan": "property_source_runs public_data_used",
            "first_wave_launch_gate": "public_data_approval gate + live_proof_ready summary",
        },
        "guardrails": {
            "non_mutating_pack": True,
            "no_dataset_fetches": True,
            "no_database_writes": True,
            "no_supabase_writes": True,
            "no_secret_values_written": True,
            "no_raw_contact_values_written": True,
            "dataset_level_licence_required": True,
            "field_allowlist_required": True,
            "public_data_separate_from_contact_basis": True,
            "owner_data_blocked_by_default": True,
            "individual_epc_blocked_without_legal_basis": True,
            "scraped_contact_data_blocked": True,
            "production_requires_live_proof": True,
        },
        "paths": {
            "public_data_reconciliation": str(out_dir / "public_data_reconciliation.json"),
            "public_data_reconciliation_markdown": str(out_dir / "PUBLIC_DATA_RECONCILIATION.md"),
            "public_data_reconciliation_matrix": str(out_dir / "PUBLIC_DATA_RECONCILIATION_MATRIX.csv"),
            "public_data_reconciliation_issues": str(out_dir / "PUBLIC_DATA_RECONCILIATION_ISSUES.csv"),
        },
    }
    report["secret_scan"] = _secret_scan(report)
    if report["secret_scan"]["status"] != "pass":
        report["status"] = "fail_secret_scan"
        report["production_import_ready"] = False
    write_json(out_dir / "public_data_reconciliation.json", report)
    write_text(out_dir / "PUBLIC_DATA_RECONCILIATION.md", render_markdown(report))
    write_csv(out_dir / "PUBLIC_DATA_RECONCILIATION_MATRIX.csv", matrix, [
        "source",
        "publisher",
        "register_status",
        "licence_or_terms",
        "approval_status",
        "production_import_decision",
        "data_category",
        "storage_target",
        "first_wave_public_data_required",
        "first_wave_public_data_gate_status",
        "live_proof_ready",
        "overall_status",
    ])
    write_csv(out_dir / "PUBLIC_DATA_RECONCILIATION_ISSUES.csv", issues, [
        "severity",
        "issue_key",
        "source",
        "evidence",
        "detail",
        "next_action",
        "blocks_production",
        "blocks_first_wave",
    ])
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HomePilot public-data reconciliation evidence")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--public-register", type=Path)
    parser.add_argument("--public-data-intake", type=Path)
    parser.add_argument("--first-campaign-import-plan", type=Path)
    parser.add_argument("--first-wave-launch-gate", type=Path)
    parser.add_argument("--release-label", default="local")
    args = parser.parse_args()
    report = build_public_data_reconciliation_pack(
        args.out_dir,
        public_register=load_json(args.public_register),
        public_data_intake=load_json(args.public_data_intake),
        first_campaign_import_plan=load_json(args.first_campaign_import_plan),
        first_wave_launch_gate=load_json(args.first_wave_launch_gate),
        release_label=args.release_label,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": report["status"],
        "production_import_ready": report["production_import_ready"],
        "registered_source_count": report["summary"]["registered_source_count"],
        "approved_source_count": report["summary"]["approved_source_count"],
        "blockers": report["summary"]["blockers"],
        "paths": report["paths"],
    }, indent=2, ensure_ascii=False))
    if report["secret_scan"]["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
