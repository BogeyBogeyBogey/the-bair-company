#!/usr/bin/env python3
"""
HomePilot tenant onboarding.

Creates the records that make customer access explicit:

- homepilot_tenants
- homepilot_tenant_modules
- optional homepilot_memberships

The generated tenant id is deterministic from the slug unless a real UUID is
provided, so pilot imports can use the same slug and still target the same
database tenant.
"""

from __future__ import annotations

import argparse
import json
import re
import uuid
from pathlib import Path
from typing import Any

from homepilot_platform import PILOT_MODULES, canonical_tenant_id
from homepilot_store import HomePilotStore


ROLES = {"viewer", "manager", "admin", "owner"}
PARTNER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def validate_uuid(value: str, label: str) -> None:
    try:
        uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{label} must be a UUID: {value}") from exc


def normalize_partner_id(value: str) -> str:
    partner_id = str(value or "").strip()
    if not partner_id:
        return ""
    if not PARTNER_ID_RE.match(partner_id):
        raise ValueError(f"Invalid partner_id: {value}")
    return partner_id


def parse_membership(value: str, tenant_id: str) -> dict[str, Any]:
    parts = [part.strip() for part in str(value).split(":")]
    if len(parts) == 1:
        user_id, role, partner_id = parts[0], "viewer", ""
    elif len(parts) in {2, 3}:
        user_id, role = parts[0], parts[1]
        partner_id = parts[2] if len(parts) == 3 else ""
    else:
        raise ValueError("Memberships must use user_id, user_id:role, or user_id:role:partner_id")
    validate_uuid(user_id, "membership.user_id")
    if role not in ROLES:
        raise ValueError(f"Unsupported membership role: {role}")
    row = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "role": role,
    }
    normalized_partner_id = normalize_partner_id(partner_id)
    if normalized_partner_id:
        row["partner_id"] = normalized_partner_id
    return row


def build_onboarding_payload(
    name: str,
    slug: str,
    modules: list[str],
    subscription_tier: str = "pro",
    data_region: str = "eu-west",
    memberships: list[str] | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if not name.strip():
        raise ValueError("Tenant name is required")
    if not slug.strip():
        raise ValueError("Tenant slug is required")
    if not modules:
        raise ValueError("At least one module is required")
    unknown = [module for module in modules if module not in PILOT_MODULES]
    if unknown:
        raise ValueError(f"Unknown module(s): {unknown}")

    tenant_id = canonical_tenant_id(slug)
    tenant = {
        "id": tenant_id,
        "name": name.strip(),
        "slug": slug.strip(),
        "subscription_tier": subscription_tier,
        "data_region": data_region,
        "settings": settings or {},
    }
    tenant_modules = [{
        "tenant_id": tenant_id,
        "module_key": module,
        "enabled": True,
        "settings": {},
    } for module in modules]
    membership_rows = [
        parse_membership(value, tenant_id)
        for value in (memberships or [])
    ]
    return {
        "tenants": [tenant],
        "tenant_modules": tenant_modules,
        "memberships": membership_rows,
    }


def validate_onboarding_payload(payload: dict[str, Any]) -> None:
    for key in ("tenants", "tenant_modules", "memberships"):
        if key not in payload or not isinstance(payload[key], list):
            raise ValueError(f"Onboarding payload must contain list key: {key}")
    tenant_ids = {row.get("id") for row in payload["tenants"]}
    if len(tenant_ids) != len(payload["tenants"]):
        raise ValueError("Duplicate or missing tenant ids in onboarding payload")
    for tenant in payload["tenants"]:
        for field in ("id", "name", "slug"):
            if not tenant.get(field):
                raise ValueError(f"Tenant missing {field}: {tenant}")
        validate_uuid(tenant["id"], "tenant.id")
    for tenant_module in payload["tenant_modules"]:
        for field in ("tenant_id", "module_key"):
            if not tenant_module.get(field):
                raise ValueError(f"Tenant module missing {field}: {tenant_module}")
        validate_uuid(tenant_module["tenant_id"], "tenant_module.tenant_id")
        if tenant_module["tenant_id"] not in tenant_ids:
            raise ValueError(f"Tenant module references unknown tenant: {tenant_module}")
        if tenant_module["module_key"] not in PILOT_MODULES:
            raise ValueError(f"Unknown module_key: {tenant_module['module_key']}")
    for membership in payload["memberships"]:
        for field in ("tenant_id", "user_id", "role"):
            if not membership.get(field):
                raise ValueError(f"Membership missing {field}: {membership}")
        validate_uuid(membership["tenant_id"], "membership.tenant_id")
        validate_uuid(membership["user_id"], "membership.user_id")
        if membership["tenant_id"] not in tenant_ids:
            raise ValueError(f"Membership references unknown tenant: {membership}")
        if membership["role"] not in ROLES:
            raise ValueError(f"Unsupported membership role: {membership['role']}")
        if membership.get("partner_id"):
            normalize_partner_id(str(membership["partner_id"]))


def load_onboarding_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_onboarding_payload(payload)
    return payload


def summarize_onboarding_payload(payload: dict[str, Any]) -> dict[str, Any]:
    validate_onboarding_payload(payload)
    return {
        "tenants": len(payload["tenants"]),
        "tenant_modules": len(payload["tenant_modules"]),
        "memberships": len(payload["memberships"]),
        "partner_scoped_memberships": len([row for row in payload["memberships"] if row.get("partner_id")]),
        "modules": sorted({row["module_key"] for row in payload["tenant_modules"]}),
        "tenant_ids": [row["id"] for row in payload["tenants"]],
    }


def import_onboarding_payload(store: HomePilotStore, payload: dict[str, Any]) -> dict[str, int]:
    validate_onboarding_payload(payload)
    store.seed_modules()
    return {
        "tenants": store.upsert("homepilot_tenants", payload["tenants"]),
        "tenant_modules": store.upsert(
            "homepilot_tenant_modules",
            payload["tenant_modules"],
            on_conflict="tenant_id,module_key",
        ),
        "memberships": store.upsert(
            "homepilot_memberships",
            payload["memberships"],
            on_conflict="tenant_id,user_id",
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="HomePilot tenant onboarding")
    parser.add_argument("--dry-run", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    build = sub.add_parser("build", help="Build onboarding JSON")
    build.add_argument("--name", required=True)
    build.add_argument("--slug", required=True)
    build.add_argument("--module", dest="modules", action="append", required=True)
    build.add_argument("--subscription-tier", default="pro")
    build.add_argument("--data-region", default="eu-west")
    build.add_argument("--member", dest="memberships", action="append", default=[])
    build.add_argument("--out", required=True, type=Path)

    summary = sub.add_parser("summary-json", help="Validate and summarize onboarding JSON")
    summary.add_argument("--json", required=True, type=Path)

    import_json = sub.add_parser("import-json", help="Import onboarding JSON")
    import_json.add_argument("--json", required=True, type=Path)

    args = parser.parse_args()

    if args.cmd == "build":
        payload = build_onboarding_payload(
            name=args.name,
            slug=args.slug,
            modules=args.modules,
            subscription_tier=args.subscription_tier,
            data_region=args.data_region,
            memberships=args.memberships,
        )
        validate_onboarding_payload(payload)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"output": str(args.out), **summarize_onboarding_payload(payload)}, indent=2))
    elif args.cmd == "summary-json":
        payload = load_onboarding_payload(args.json)
        print(json.dumps(summarize_onboarding_payload(payload), indent=2))
    elif args.cmd == "import-json":
        payload = load_onboarding_payload(args.json)
        store = HomePilotStore(dry_run=args.dry_run)
        counts = import_onboarding_payload(store, payload)
        print(json.dumps({"imported": counts, "dry_run": store.dry_run}, indent=2))


if __name__ == "__main__":
    main()
