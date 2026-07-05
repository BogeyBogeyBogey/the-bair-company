#!/usr/bin/env python3
"""
Verify planned customer access against live tenant/module/partner RLS.

Account access plans are review evidence. This module is the production bridge:
it turns those planned invitees into tenant/module/partner RLS probe identities, reads credentials only
from environment variables, and writes a redacted verification pack. It never
writes passwords, tokens, service-role keys, or anon keys to disk.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from homepilot_rls_probe import run_probe, write_json
from homepilot_store import HOME_ROOT, load_dotenv_file


for env_path in (HOME_ROOT / ".env", HOME_ROOT / "platform" / ".env"):
    load_dotenv_file(env_path)


ProbeRunner = Callable[[dict[str, Any], str, str, bool], dict[str, Any]]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def load_account_access_plan(path: Path) -> dict[str, Any]:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("report_type") != "homepilot_account_access_plan":
        raise ValueError("Expected a homepilot_account_access_plan JSON file")
    return plan


def _env_value(env: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = env.get(key, "").strip()
        if value:
            return value
    return ""


def _safe_env_label(email: str, role: str) -> str:
    raw = f"{role}_{email}".upper()
    return re.sub(r"[^A-Z0-9]+", "_", raw).strip("_")[:80]


def _identity_contract(plan: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []
    tenant = plan.get("tenant") if isinstance(plan.get("tenant"), dict) else {}
    tenant_id = str(tenant.get("id") or "")
    modules = list(plan.get("enabled_modules") or [])
    identities: list[dict[str, Any]] = []

    if plan.get("status") != "pass":
        failures.append(f"Account access plan status is {plan.get('status')!r}, expected 'pass'.")
    if plan.get("review_status") != "ready":
        failures.append(f"Account access plan review_status is {plan.get('review_status')!r}, expected 'ready'.")
    if not tenant_id:
        failures.append("Account access plan tenant id is missing.")
    if not modules:
        failures.append("Account access plan has no enabled modules.")

    for index, invitee in enumerate(plan.get("invitees") or [], start=1):
        email = str(invitee.get("email") or "").strip().lower()
        role = str(invitee.get("role") or "")
        user_id = str(invitee.get("user_id") or "").strip()
        partner_id = str(invitee.get("partner_id") or "").strip()
        access_scope = str(invitee.get("access_scope") or ("partner" if partner_id else "tenant"))
        label = _safe_env_label(email or f"invitee_{index}", role or "user")
        password_env = f"HOMEPILOT_ACCESS_{label}_PASSWORD"
        token_env = f"HOMEPILOT_ACCESS_{label}_TOKEN"
        identity = {
            "label": label.lower(),
            "email": email,
            "role": role,
            "user_id": user_id or None,
            "tenant_id": tenant_id,
            "modules": modules,
            "access_scope": access_scope,
            "partner_id": partner_id or None,
            "password_env": password_env,
            "token_env": token_env,
            "credential_modes": ["access_token_env", "password_env"],
        }
        identities.append(identity)
        if not email:
            failures.append(f"Invitee {index} is missing email.")
        if not role:
            failures.append(f"Invitee {email or index} is missing role.")
        if access_scope == "partner" and not partner_id:
            failures.append(f"Invitee {email or index} is partner-scoped but missing partner_id.")
        if not user_id:
            failures.append(f"Invitee {email or index} is missing Supabase Auth user_id.")

    if not identities:
        failures.append("Account access plan has no invitees to verify.")
    if not any(identity["role"] == "owner" for identity in identities):
        warnings.append("No owner identity is included in the customer access verification contract.")
    return identities, failures, warnings


def _credentialed_probe_config(
    contract_identities: list[dict[str, Any]],
    env: dict[str, str],
) -> tuple[dict[str, Any], list[str], list[str]]:
    identities = []
    failures: list[str] = []
    warnings: list[str] = []
    for identity in contract_identities:
        access_token = _env_value(env, identity["token_env"])
        password = _env_value(env, identity["password_env"])
        probe_identity = {
            "label": identity["label"],
            "tenant_id": identity["tenant_id"],
            "modules": identity["modules"],
            "user_id": identity.get("user_id"),
            "partner_id": identity.get("partner_id"),
        }
        if access_token:
            probe_identity["access_token"] = access_token
            credential_mode = "access_token_env"
        elif password:
            probe_identity["email"] = identity["email"]
            probe_identity["password"] = password
            credential_mode = "password_env"
        else:
            credential_mode = "missing"
            failures.append(
                f"Missing credentials for {identity['email']}; set {identity['token_env']} or {identity['password_env']}."
            )
        identity["credential_status"] = "ready" if credential_mode != "missing" else "missing"
        identity["credential_mode_used"] = credential_mode
        if credential_mode == "password_env":
            warnings.append(f"{identity['email']} will use password auth for verification; prefer short-lived access token env when available.")
        identities.append(probe_identity)
    return {"identities": identities}, failures, warnings


def _redacted_contract(plan: dict[str, Any], identities: list[dict[str, Any]]) -> dict[str, Any]:
    tenant = plan.get("tenant", {})
    return {
        "contract_type": "homepilot_customer_access_probe_contract",
        "created_at": utc_now(),
        "tenant": {
            "id": tenant.get("id"),
            "name": tenant.get("name"),
            "slug": tenant.get("slug"),
        },
        "enabled_modules": plan.get("enabled_modules", []),
        "identities": [
            {
                "label": identity["label"],
                "email": identity["email"],
                "role": identity["role"],
                "user_id": identity.get("user_id"),
                "tenant_id": identity["tenant_id"],
                "modules": identity["modules"],
                "access_scope": identity.get("access_scope", "tenant"),
                "partner_id": identity.get("partner_id"),
                "token_env": identity["token_env"],
                "password_env": identity["password_env"],
                "credential_status": identity.get("credential_status", "not_checked"),
                "credential_mode_used": identity.get("credential_mode_used", "not_checked"),
            }
            for identity in identities
        ],
        "guardrails": {
            "secrets_written": False,
            "service_role_key_required": False,
            "anon_key_written": False,
            "tenant_scoped": True,
            "module_scoped": True,
            "partner_scoped": True,
            "rls_probe_required_for_production": True,
        },
    }


def _default_access_lenses(plan: dict[str, Any]) -> list[dict[str, Any]]:
    modules = list(plan.get("enabled_modules") or [])
    lenses = [
        {
            "key": "producer_network",
            "label": "Tenant executive",
            "scope": "tenant-wide producer or customer workspace",
            "partner_mode": "all",
            "module_mode": "all",
            "module_keys": modules,
            "live_gate": "blocked_until_live_rls_customer_access_proof",
        },
        {
            "key": "module_only_customer",
            "label": "Module-only customer",
            "scope": "tenant plus entitled module rows only",
            "partner_mode": "all",
            "module_mode": "first_module",
            "module_keys": modules[:1],
            "live_gate": "blocked_until_live_schema_rls_customer_access_proof",
        },
    ]
    if any(invitee.get("partner_id") for invitee in plan.get("invitees") or []):
        lenses.append({
            "key": "partner_renovator",
            "label": "Partner renovator",
            "scope": "assigned records only",
            "partner_mode": "first_partner",
            "module_mode": "all",
            "module_keys": modules,
            "live_gate": "blocked_until_live_rls_customer_access_and_partner_reconciliation",
        })
    return lenses


def _lenses_from_snapshot(plan: dict[str, Any], dashboard_snapshot: dict[str, Any] | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    snapshot = dashboard_snapshot if isinstance(dashboard_snapshot, dict) else {}
    lenses = snapshot.get("accessLenses") if isinstance(snapshot.get("accessLenses"), list) else []
    network = snapshot.get("network") if isinstance(snapshot.get("network"), dict) else {}
    partners = network.get("partners") if isinstance(network.get("partners"), list) else []
    metadata = {
        "source": "dashboard_snapshot" if lenses else "account_access_plan_default",
        "network_partner_count": len(partners),
        "network_partner_ids": [str(row.get("id")) for row in partners if isinstance(row, dict) and row.get("id")],
    }
    clean_lenses = [dict(lens) for lens in lenses if isinstance(lens, dict) and lens.get("key")]
    return (clean_lenses or _default_access_lenses(plan), metadata)


def _identity_module_match(identity: dict[str, Any], required_modules: list[str]) -> bool:
    identity_modules = set(identity.get("modules") or [])
    return set(required_modules).issubset(identity_modules)


def _identity_scope_match(identity: dict[str, Any], lens: dict[str, Any]) -> bool:
    partner_mode = str(lens.get("partner_mode") or "all")
    partner_id = str(identity.get("partner_id") or "")
    if partner_mode == "all":
        return not partner_id
    if partner_mode in {"first_partner", "selected_partner", "partner"}:
        expected = str(lens.get("partner_id") or "")
        return bool(partner_id) and (not expected or expected == partner_id or partner_mode == "first_partner")
    return not partner_id


def _lens_required_modules(lens: dict[str, Any], plan_modules: list[str]) -> list[str]:
    lens_modules = [str(key) for key in lens.get("module_keys") or [] if str(key).strip()]
    if str(lens.get("module_mode") or "") == "first_module":
        return (lens_modules or plan_modules)[:1]
    return lens_modules or plan_modules


def _build_access_lens_proof(
    plan: dict[str, Any],
    identities: list[dict[str, Any]],
    dashboard_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    plan_modules = list(plan.get("enabled_modules") or [])
    lenses, metadata = _lenses_from_snapshot(plan, dashboard_snapshot)
    partner_identity_count = sum(1 for identity in identities if identity.get("partner_id"))
    tenant_identity_count = sum(1 for identity in identities if not identity.get("partner_id"))
    rows: list[dict[str, Any]] = []
    missing = 0
    sample_only = 0

    for lens in lenses:
        required_modules = _lens_required_modules(lens, plan_modules)
        matches = [
            identity
            for identity in identities
            if _identity_module_match(identity, required_modules) and _identity_scope_match(identity, lens)
        ]
        partner_mode = str(lens.get("partner_mode") or "all")
        if matches:
            coverage_status = "covered"
            if partner_mode in {"first_partner", "selected_partner", "partner"}:
                network_partner_count = int(metadata.get("network_partner_count") or 0)
                if network_partner_count and partner_identity_count < network_partner_count:
                    coverage_status = "sample_covered_pending_partner_reconciliation"
                    sample_only += 1
        else:
            coverage_status = "missing_identity"
            missing += 1
        rows.append({
            "lens_key": str(lens.get("key")),
            "label": str(lens.get("label") or lens.get("key")),
            "expected_scope": str(lens.get("scope") or ""),
            "partner_mode": partner_mode,
            "required_modules": required_modules,
            "matched_identity_labels": [identity["label"] for identity in matches],
            "matched_roles": sorted({str(identity.get("role") or "") for identity in matches if identity.get("role")}),
            "coverage_status": coverage_status,
            "live_gate": str(lens.get("live_gate") or "blocked_until_live_customer_access_probe"),
            "production_gate": "requires_live_rls_probe_and_customer_access_verification",
        })

    status = "action_required" if missing else "review_ready"
    return {
        "proof_type": "homepilot_access_lens_proof",
        "status": status,
        "source": metadata["source"],
        "summary": {
            "lens_count": len(rows),
            "covered_lenses": sum(1 for row in rows if row["coverage_status"] == "covered"),
            "sample_covered_lenses": sample_only,
            "missing_lenses": missing,
            "tenant_identities": tenant_identity_count,
            "partner_identities": partner_identity_count,
            "network_partner_count": metadata["network_partner_count"],
        },
        "lenses": rows,
        "guardrails": {
            "proof_is_not_runtime_authorization": True,
            "runtime_authorization_remains_supabase_rls": True,
            "tenant_scope_required": True,
            "module_scope_required": True,
            "partner_scope_required_for_partner_lenses": True,
            "production_requires_live_customer_jwts": True,
            "no_secrets_written": True,
        },
    }


def _write_access_lens_matrix(path: Path, proof: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "lens_key",
        "label",
        "expected_scope",
        "partner_mode",
        "required_modules",
        "matched_identity_labels",
        "matched_roles",
        "coverage_status",
        "live_gate",
        "production_gate",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in proof.get("lenses") or []:
            writer.writerow({
                **row,
                "required_modules": "; ".join(row.get("required_modules") or []),
                "matched_identity_labels": "; ".join(row.get("matched_identity_labels") or []),
                "matched_roles": "; ".join(row.get("matched_roles") or []),
            })


def _skipped_probe_report(dry_run: bool, failures: list[str]) -> dict[str, Any]:
    if dry_run:
        status = "skipped_dry_run"
        reason = "Dry-run validates the customer access contract without reading live credentials or calling Supabase."
    else:
        status = "skipped_missing_credentials"
        reason = "Live customer access verification needs credentials for every planned identity."
    return {
        "report_type": "homepilot_customer_access_rls_probe",
        "created_at": utc_now(),
        "status": status,
        "reason": reason,
        "failures": failures,
    }


def render_markdown(report: dict[str, Any]) -> str:
    account = report["account_access"]
    lines = [
        "# HomePilot Customer Access Verification",
        "",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        f"Production verified: {str(report['production_verified']).lower()}",
        f"Tenant: {account['tenant'].get('name')} ({account['tenant'].get('slug')})",
        f"Modules: {', '.join(account['enabled_modules']) or 'none'}",
        f"RLS probe: {report['rls_probe']['status']}",
        "",
        "## Identities",
        "",
    ]
    for identity in report["identities"]:
        scope = f"partner `{identity['partner_id']}`" if identity.get("partner_id") else "tenant"
        lines.append(
            f"- {identity['email']}: `{identity['role']}`; {identity['credential_status']}; scope: {scope}; modules: {', '.join(identity['modules'])}"
        )
    lines += [
        "",
        "## Guardrails",
        "",
    ]
    for key, value in report["guardrails"].items():
        if isinstance(value, bool):
            value = "yes" if value else "no"
        lines.append(f"- {key}: {value}")
    proof = report.get("access_lens_proof") or {}
    if proof:
        lines += [
            "",
            "## Access Lens Proof",
            "",
            f"Status: {proof.get('status')}",
            f"Source: {proof.get('source')}",
            "",
            "| Lens | Expected Scope | Coverage | Matched Identities |",
            "| --- | --- | --- | --- |",
        ]
        for row in proof.get("lenses") or []:
            lines.append(
                f"| {row['lens_key']} | {row['expected_scope']} | {row['coverage_status']} | "
                f"{', '.join(row.get('matched_identity_labels') or []) or 'none'} |"
            )
    if report["warnings"]:
        lines += ["", "## Warnings", ""]
        lines.extend(f"- {warning}" for warning in report["warnings"])
    if report["failures"]:
        lines += ["", "## Failures", ""]
        lines.extend(f"- {failure}" for failure in report["failures"])
    lines.append("")
    return "\n".join(lines)


def build_customer_access_verification(
    out_dir: Path,
    account_access_plan: dict[str, Any],
    url: str = "",
    anon_key: str = "",
    dry_run: bool = False,
    allow_empty: bool = False,
    env: dict[str, str] | None = None,
    probe_runner: ProbeRunner = run_probe,
    dashboard_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ if env is None else env)
    identities, contract_failures, contract_warnings = _identity_contract(account_access_plan)
    probe_config, credential_failures, credential_warnings = _credentialed_probe_config(identities, env)
    if dry_run:
        for identity in identities:
            identity["credential_status"] = "not_required_for_dry_run"
            identity["credential_mode_used"] = "not_written"
    failures = contract_failures + ([] if dry_run else credential_failures)
    warnings = contract_warnings + ([] if dry_run else credential_warnings)

    contract_path = out_dir / "customer_access_probe_contract.json"
    probe_path = out_dir / "customer_access_rls_probe_report.json"
    report_path = out_dir / "customer_access_verification.json"
    markdown_path = out_dir / "CUSTOMER_ACCESS_VERIFICATION.md"
    access_lens_matrix_path = out_dir / "ACCESS_LENS_PROOF_MATRIX.csv"
    access_lens_proof = _build_access_lens_proof(account_access_plan, identities, dashboard_snapshot)

    write_json(contract_path, _redacted_contract(account_access_plan, identities))
    _write_access_lens_matrix(access_lens_matrix_path, access_lens_proof)

    if dry_run or failures:
        probe_report = _skipped_probe_report(dry_run=dry_run, failures=failures)
    else:
        if not url or not anon_key:
            failures.append("Live customer access verification requires Supabase URL and anon key.")
            probe_report = _skipped_probe_report(dry_run=False, failures=failures)
        else:
            probe_report = probe_runner(probe_config, url, anon_key, allow_empty)
    write_json(probe_path, probe_report)

    if dry_run:
        status = "dry_run" if not contract_failures else "fail"
    else:
        status = "pass" if not failures and probe_report.get("status") == "pass" else "fail"
    production_verified = (
        status == "pass"
        and probe_report.get("status") == "pass"
        and access_lens_proof["summary"]["missing_lenses"] == 0
    )
    report = {
        "report_type": "homepilot_customer_access_verification",
        "created_at": utc_now(),
        "status": status,
        "production_verified": production_verified,
        "dry_run": dry_run,
        "account_access": {
            "status": account_access_plan.get("status"),
            "review_status": account_access_plan.get("review_status"),
            "tenant": account_access_plan.get("tenant", {}),
            "enabled_modules": account_access_plan.get("enabled_modules", []),
            "invitees": len(account_access_plan.get("invitees", [])),
            "ready_memberships": len(account_access_plan.get("membership_rows", [])),
        },
        "identities": [
            {
                "label": identity["label"],
                "email": identity["email"],
                "role": identity["role"],
                "user_id": identity.get("user_id"),
                "tenant_id": identity["tenant_id"],
                "modules": identity["modules"],
                "access_scope": identity.get("access_scope", "tenant"),
                "partner_id": identity.get("partner_id"),
                "credential_status": "not_required_for_dry_run" if dry_run else identity.get("credential_status", "missing"),
                "credential_mode_used": "not_written" if dry_run else identity.get("credential_mode_used", "missing"),
                "token_env": identity["token_env"],
                "password_env": identity["password_env"],
            }
            for identity in identities
        ],
        "rls_probe": {
            "status": probe_report.get("status"),
            "path": str(probe_path),
        },
        "access_lens_proof": access_lens_proof,
        "guardrails": {
            "secrets_written": False,
            "service_role_key_required": False,
            "tenant_scoped": True,
            "module_scoped": True,
            "partner_scoped": True,
            "production_requires_live_probe_pass": True,
        },
        "failures": failures,
        "warnings": warnings,
        "paths": {
            "customer_access_verification": str(report_path),
            "markdown": str(markdown_path),
            "probe_contract": str(contract_path),
            "rls_probe_report": str(probe_path),
            "access_lens_matrix": str(access_lens_matrix_path),
        },
    }
    write_json(report_path, report)
    write_text(markdown_path, render_markdown(report))
    return report


def build_customer_access_verification_from_file(
    out_dir: Path,
    account_access_plan_path: Path,
    url: str = "",
    anon_key: str = "",
    dry_run: bool = False,
    allow_empty: bool = False,
    env: dict[str, str] | None = None,
    dashboard_snapshot_path: Path | None = None,
) -> dict[str, Any]:
    dashboard_snapshot = json.loads(dashboard_snapshot_path.read_text(encoding="utf-8")) if dashboard_snapshot_path else None
    return build_customer_access_verification(
        out_dir=out_dir,
        account_access_plan=load_account_access_plan(account_access_plan_path),
        url=url,
        anon_key=anon_key,
        dry_run=dry_run,
        allow_empty=allow_empty,
        env=env,
        dashboard_snapshot=dashboard_snapshot,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify HomePilot planned customer access with live RLS")
    parser.add_argument("--account-access-plan", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--url", default=os.environ.get("HOMEPILOT_SUPABASE_URL") or os.environ.get("SUPABASE_URL") or "")
    parser.add_argument("--anon-key", default=os.environ.get("HOMEPILOT_SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_ANON_KEY") or "")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-empty", action="store_true")
    parser.add_argument("--dashboard-snapshot", type=Path, help="Optional dashboard snapshot with accessLenses to prove planned customer visibility.")
    args = parser.parse_args()

    report = build_customer_access_verification_from_file(
        out_dir=args.out_dir,
        account_access_plan_path=args.account_access_plan,
        url=args.url,
        anon_key=args.anon_key,
        dry_run=args.dry_run,
        allow_empty=args.allow_empty,
        dashboard_snapshot_path=args.dashboard_snapshot,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": report["status"],
        "production_verified": report["production_verified"],
        "customer_access_verification": report["paths"]["customer_access_verification"],
        "rls_probe": report["rls_probe"]["status"],
        "access_lens_proof": report["access_lens_proof"]["status"],
        "failures": report["failures"],
    }, indent=2, ensure_ascii=False))
    if report["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
