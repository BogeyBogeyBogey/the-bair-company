#!/usr/bin/env python3
"""
Build reviewable account-access packs for HomePilot tenants.

This sits between onboarding JSON and a live Supabase rollout. It shows who will
be invited, which role they get, which modules that role can see, which
permissions follow from the role, and which SQL rows must be reviewed for
membership upsert or revocation. It never stores passwords or privileged keys.
"""

from __future__ import annotations

import argparse
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_metric_access import ROLE_PERMISSIONS, build_product_access_matrix
from homepilot_onboarding import ROLES, load_onboarding_payload, validate_onboarding_payload
from homepilot_platform import PILOT_MODULES


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PARTNER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SECRET_FIELD_NAMES = {"password", "token", "secret", "service_key", "api_key"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _uuid(value: str, label: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{label} must be a UUID: {value}") from exc


def _normalize_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise ValueError(f"Invalid invitee email: {value}")
    return email


def _normalize_partner_id(value: str) -> str:
    partner_id = str(value or "").strip()
    if not partner_id:
        return ""
    if not PARTNER_ID_RE.match(partner_id):
        raise ValueError(f"Invalid partner_id: {value}")
    return partner_id


def parse_invitee(value: str) -> dict[str, Any]:
    parts = [part.strip() for part in str(value).split(":")]
    if len(parts) not in {2, 3, 4}:
        raise ValueError("Invitees must use email:role, email:role:user_id, or email:role:user_id:partner_id")
    email, role = parts[0], parts[1]
    if role not in ROLES:
        raise ValueError(f"Unsupported invitee role: {role}")
    invitee = {
        "email": _normalize_email(email),
        "role": role,
    }
    if len(parts) >= 3 and parts[2]:
        invitee["user_id"] = _uuid(parts[2], "invitee.user_id")
    if len(parts) == 4 and parts[3]:
        invitee["partner_id"] = _normalize_partner_id(parts[3])
    return invitee


def _tenant(onboarding: dict[str, Any]) -> dict[str, Any]:
    validate_onboarding_payload(onboarding)
    tenants = onboarding.get("tenants", [])
    if len(tenants) != 1:
        raise ValueError("Account access packs require exactly one tenant")
    return tenants[0]


def _enabled_modules(onboarding: dict[str, Any]) -> list[str]:
    modules = []
    for row in onboarding.get("tenant_modules", []):
        if row.get("enabled", True):
            module_key = str(row.get("module_key") or "")
            if module_key in PILOT_MODULES:
                modules.append(module_key)
    return [module for module in PILOT_MODULES if module in set(modules)]


def _secret_scan(invitees: list[dict[str, Any]]) -> list[str]:
    findings = []
    for invitee in invitees:
        for key in invitee:
            lower = str(key).lower()
            if lower in SECRET_FIELD_NAMES or any(fragment in lower for fragment in SECRET_FIELD_NAMES):
                findings.append(f"Invitee contains secret-like field: {key}")
    return findings


def _issues(onboarding: dict[str, Any], invitees: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []
    tenant = _tenant(onboarding)
    modules = _enabled_modules(onboarding)
    if not modules:
        failures.append("Tenant has no enabled modules.")
    if not invitees:
        failures.append("At least one invitee is required for production customer access.")
    if invitees and not any(invitee["role"] == "owner" for invitee in invitees):
        warnings.append("No owner invitee configured; production accounts should have at least one owner.")
    seen_emails = set()
    seen_user_ids = set()
    for invitee in invitees:
        email = invitee["email"]
        user_id = invitee.get("user_id")
        if email in seen_emails:
            failures.append(f"Duplicate invitee email: {email}")
        seen_emails.add(email)
        if user_id:
            if user_id in seen_user_ids:
                failures.append(f"Duplicate invitee user_id: {user_id}")
            seen_user_ids.add(user_id)
        else:
            warnings.append(f"Invitee {email} is missing Supabase Auth user_id; membership SQL will stay pending.")
    failures.extend(_secret_scan(invitees))
    if not tenant.get("id"):
        failures.append("Tenant id is missing.")
    return failures, warnings


def _membership_rows(tenant_id: str, invitees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for invitee in invitees:
        user_id = invitee.get("user_id")
        if not user_id:
            continue
        rows.append({
            "tenant_id": tenant_id,
            "user_id": user_id,
            "role": invitee["role"],
            "partner_id": invitee.get("partner_id"),
        })
    return rows


def _invitee_rows(invitees: list[dict[str, Any]], modules: list[str]) -> list[dict[str, Any]]:
    rows = []
    for invitee in invitees:
        role = invitee["role"]
        partner_id = invitee.get("partner_id")
        rows.append({
            "email": invitee["email"],
            "role": role,
            "user_id": invitee.get("user_id"),
            "auth_status": "ready" if invitee.get("user_id") else "pending_auth_user",
            "permissions": list(ROLE_PERMISSIONS[role]),
            "modules": modules,
            "access_scope": "partner" if partner_id else "tenant",
            "partner_id": partner_id,
            "invite_action": "add_membership" if invitee.get("user_id") else "create_or_invite_supabase_auth_user",
        })
    return rows


def _sql_literal_or_null(value: str | None) -> str:
    if value is None or value == "":
        return "null"
    return _quote(value)


def _membership_sql(rows: list[dict[str, Any]]) -> str:
    lines = [
        "-- HomePilot membership upsert SQL.",
        "-- Review user_id values against Supabase Auth before executing.",
    ]
    if not rows:
        lines.append("-- No membership rows ready; create/invite Supabase Auth users first.")
        return "\n".join(lines) + "\n"
    values = ",\n".join(
        f"  ({_quote(row['tenant_id'])}::uuid, {_quote(row['user_id'])}::uuid, {_quote(row['role'])}, {_sql_literal_or_null(row.get('partner_id'))})"
        for row in rows
    )
    lines += [
        "insert into public.homepilot_memberships (tenant_id, user_id, role, partner_id)",
        "values",
        values,
        "on conflict (tenant_id, user_id) do update set role = excluded.role, partner_id = excluded.partner_id;",
    ]
    return "\n".join(lines) + "\n"


def _revocation_sql(rows: list[dict[str, Any]], tenant_id: str) -> str:
    lines = [
        "-- HomePilot membership revocation SQL.",
        "-- This removes tenant access only; delete Supabase Auth users separately if required.",
    ]
    if not rows:
        lines.append(f"-- No ready user IDs. Tenant id: {tenant_id}")
        return "\n".join(lines) + "\n"
    user_ids = ", ".join(f"{_quote(row['user_id'])}::uuid" for row in rows)
    lines += [
        "delete from public.homepilot_memberships",
        f"where tenant_id = {_quote(tenant_id)}::uuid",
        f"  and user_id in ({user_ids});",
    ]
    return "\n".join(lines) + "\n"


def build_account_access_plan(onboarding: dict[str, Any], invitees: list[dict[str, Any]]) -> dict[str, Any]:
    tenant = _tenant(onboarding)
    modules = _enabled_modules(onboarding)
    failures, warnings = _issues(onboarding, invitees)
    membership_rows = _membership_rows(tenant["id"], invitees)
    role_counts: dict[str, int] = {}
    scope_counts: dict[str, int] = {"tenant": 0, "partner": 0}
    for invitee in invitees:
        role_counts[invitee["role"]] = role_counts.get(invitee["role"], 0) + 1
        scope_counts["partner" if invitee.get("partner_id") else "tenant"] += 1
    return {
        "report_type": "homepilot_account_access_plan",
        "created_at": utc_now(),
        "status": "fail" if failures else "pass",
        "review_status": "ready" if not failures and not warnings else "review_required",
        "tenant": {
            "id": tenant["id"],
            "name": tenant["name"],
            "slug": tenant["slug"],
            "data_region": tenant.get("data_region"),
            "subscription_tier": tenant.get("subscription_tier"),
        },
        "enabled_modules": modules,
        "invitees": _invitee_rows(invitees, modules),
        "membership_rows": membership_rows,
        "role_counts": dict(sorted(role_counts.items())),
        "scope_counts": {key: count for key, count in scope_counts.items() if count},
        "access_matrices": {
            role: build_product_access_matrix(modules, role=role, surface="dashboard")
            for role in sorted(role_counts)
        },
        "operational_steps": [
            "Confirm signed tenant/module/partner scope before sending invitations.",
            "Create or invite Supabase Auth users for invitees without user_id.",
            "Apply reviewed membership upsert SQL only after Auth user IDs are known.",
            "Run live healthcheck and RLS probe with real customer JWTs before production access.",
            "Archive revocation SQL so access can be removed quickly during offboarding.",
        ],
        "guardrails": {
            "passwords_included": False,
            "service_role_keys_included": False,
            "tenant_scoped": True,
            "partner_scope_supported": True,
            "unscoped_membership_means_full_tenant": True,
            "module_entitlements_source": "homepilot_tenant_modules",
            "rls_required_before_production": True,
        },
        "failures": failures,
        "warnings": warnings,
    }


def render_markdown(plan: dict[str, Any]) -> str:
    tenant = plan["tenant"]
    lines = [
        "# HomePilot Account Access Plan",
        "",
        f"Created: {plan['created_at']}",
        f"Status: {plan['status']}",
        f"Review status: {plan['review_status']}",
        f"Tenant: {tenant['name']} ({tenant['slug']})",
        f"Modules: {', '.join(plan['enabled_modules']) or 'none'}",
        "",
        "## Invitees",
        "",
    ]
    for invitee in plan["invitees"]:
        scope = f"partner `{invitee['partner_id']}`" if invitee.get("partner_id") else "tenant"
        lines.append(
            f"- {invitee['email']}: `{invitee['role']}`; {invitee['auth_status']}; scope: {scope}; permissions: {', '.join(invitee['permissions'])}"
        )
    lines += ["", "## Membership Rows", ""]
    if plan["membership_rows"]:
        for row in plan["membership_rows"]:
            scope = f" partner `{row['partner_id']}`" if row.get("partner_id") else " full tenant"
            lines.append(f"- `{row['user_id']}` -> `{row['tenant_id']}` as `{row['role']}`;{scope}")
    else:
        lines.append("- No membership rows ready yet; create/invite Supabase Auth users first.")
    lines += ["", "## Operational Steps", ""]
    for index, step in enumerate(plan["operational_steps"], start=1):
        lines.append(f"{index}. {step}")
    lines += ["", "## Guardrails", ""]
    for key, value in plan["guardrails"].items():
        if isinstance(value, bool):
            value = "yes" if value else "no"
        lines.append(f"- {key}: {value}")
    if plan["warnings"]:
        lines += ["", "## Warnings", ""]
        for warning in plan["warnings"]:
            lines.append(f"- {warning}")
    if plan["failures"]:
        lines += ["", "## Failures", ""]
        for failure in plan["failures"]:
            lines.append(f"- {failure}")
    lines.append("")
    return "\n".join(lines)


def build_account_access_pack(out_dir: Path, onboarding: dict[str, Any], invitees: list[dict[str, Any]]) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = build_account_access_plan(onboarding, invitees)
    json_path = out_dir / "account_access_plan.json"
    markdown_path = out_dir / "ACCOUNT_ACCESS_PLAN.md"
    membership_sql_path = out_dir / "membership_upsert.sql"
    revocation_sql_path = out_dir / "membership_revocation.sql"
    write_json(json_path, plan)
    markdown_path.write_text(render_markdown(plan), encoding="utf-8")
    membership_sql_path.write_text(_membership_sql(plan["membership_rows"]), encoding="utf-8")
    revocation_sql_path.write_text(_revocation_sql(plan["membership_rows"], plan["tenant"]["id"]), encoding="utf-8")
    return {
        "status": plan["status"],
        "review_status": plan["review_status"],
        "paths": {
            "account_access_plan": str(json_path),
            "markdown": str(markdown_path),
            "membership_upsert_sql": str(membership_sql_path),
            "membership_revocation_sql": str(revocation_sql_path),
        },
        "plan": plan,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot account access plan")
    parser.add_argument("--onboarding", required=True, type=Path)
    parser.add_argument("--invite", dest="invitees", action="append", required=True, help="email:role, email:role:user_id, or email:role:user_id:partner_id")
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    pack = build_account_access_pack(
        args.out_dir,
        onboarding=load_onboarding_payload(args.onboarding),
        invitees=[parse_invitee(value) for value in args.invitees],
    )
    print(json.dumps({
        "status": pack["status"],
        "review_status": pack["review_status"],
        "tenant": pack["plan"]["tenant"],
        "invitees": len(pack["plan"]["invitees"]),
        "paths": pack["paths"],
        "warnings": pack["plan"]["warnings"],
        "failures": pack["plan"]["failures"],
    }, indent=2, ensure_ascii=False))
    if pack["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
