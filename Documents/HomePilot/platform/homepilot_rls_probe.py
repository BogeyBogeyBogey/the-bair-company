#!/usr/bin/env python3
"""
Supabase RLS probe for HomePilot.

This script verifies the production promise that customers only see their own
tenant data, only the modules they bought, and only assigned partner records when partner-scoped. It logs in as real Supabase Auth
users or uses supplied access tokens, queries customer-facing tables/views with
the user's JWT, and writes a pass/fail evidence report.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from homepilot_platform import PILOT_MODULES
from homepilot_store import HOME_ROOT, load_dotenv_file


for env_path in (HOME_ROOT / ".env", HOME_ROOT / "platform" / ".env"):
    load_dotenv_file(env_path)


@dataclass(frozen=True)
class ProbeEndpoint:
    name: str
    path: str
    tenant_field: str | None = "tenant_id"
    module_field: str | None = "module_key"
    partner_fields: tuple[str, ...] = ()
    require_rows: bool = False


PROBE_ENDPOINTS: tuple[ProbeEndpoint, ...] = (
    ProbeEndpoint(
        name="homepilot_tenants",
        path="homepilot_tenants?select=id,slug,name&limit=50",
        tenant_field="id",
        module_field=None,
        require_rows=True,
    ),
    ProbeEndpoint(
        name="homepilot_tenant_modules",
        path="homepilot_tenant_modules?select=tenant_id,module_key,enabled&enabled=eq.true&limit=100",
        require_rows=True,
    ),
    ProbeEndpoint(
        name="homepilot_properties",
        path="homepilot_properties?select=id,tenant_id,address,core&limit=100",
        module_field=None,
        partner_fields=("core.network.partner_id", "core.partner_id"),
        require_rows=True,
    ),
    ProbeEndpoint(
        name="homepilot_assessments",
        path="homepilot_assessments?select=id,tenant_id,property_id,module_key&limit=100",
        require_rows=True,
    ),
    ProbeEndpoint(
        name="homepilot_campaigns",
        path="homepilot_campaigns?select=id,tenant_id,module_key,name,partner_id,metadata,territory&limit=100",
        partner_fields=("partner_id", "metadata.partner_id", "territory.partner_id"),
    ),
    ProbeEndpoint(
        name="homepilot_campaign_targets",
        path="homepilot_campaign_targets?select=id,tenant_id,campaign_id,property_id,module_key,metadata&limit=100",
        partner_fields=("metadata.partner_id",),
    ),
    ProbeEndpoint(
        name="homepilot_interactions",
        path="homepilot_interactions?select=id,tenant_id,property_id,module_key,metadata&limit=100",
        partner_fields=("metadata.partner_id",),
    ),
    ProbeEndpoint(
        name="homepilot_response_insights",
        path="homepilot_response_insights?select=id,tenant_id,campaign_id,module_key,supporting_metrics&limit=100",
    ),
    ProbeEndpoint(
        name="homepilot_exports",
        path="homepilot_exports?select=id,tenant_id,module_key,export_type,filters&limit=100",
        partner_fields=("filters.partner_id",),
    ),
    ProbeEndpoint(
        name="homepilot_audit_events",
        path="homepilot_audit_events?select=id,tenant_id,module_key,event_type&limit=100",
        require_rows=True,
    ),
    ProbeEndpoint(
        name="homepilot_property_intelligence",
        path="homepilot_property_intelligence?select=tenant_id,property_id,module_key,partner_id&limit=100",
        partner_fields=("partner_id",),
        require_rows=True,
    ),
    ProbeEndpoint(
        name="homepilot_campaign_metrics",
        path="homepilot_campaign_metrics?select=tenant_id,campaign_id,module_key,partner_id&limit=100",
        partner_fields=("partner_id",),
    ),
    ProbeEndpoint(
        name="homepilot_module_metrics",
        path="homepilot_module_metrics?select=tenant_id,module_key&limit=100",
        require_rows=True,
    ),
    ProbeEndpoint(
        name="homepilot_second_brain_edges",
        path="homepilot_second_brain_edges?select=tenant_id,module_key,source_type,target_type&limit=100",
    ),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _validate_uuid(value: Any, label: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{label} must be a UUID: {value}") from exc


def _validate_partner_id(value: Any, label: str) -> str:
    partner_id = str(value or "").strip()
    if not partner_id:
        return ""
    if len(partner_id) > 128 or not partner_id.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise ValueError(f"{label} must be a safe partner id: {value}")
    return partner_id


def _headers(api_key: str, bearer: str) -> dict[str, str]:
    return {
        "apikey": api_key,
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "application/json",
    }


def _request_json(
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url}: {exc.code} - {body[:500]}") from exc
    if not body:
        return None
    return json.loads(body)


def login_with_password(url: str, anon_key: str, email: str, password: str) -> dict[str, Any]:
    auth_url = f"{url.rstrip('/')}/auth/v1/token?grant_type=password"
    payload = {"email": email, "password": password}
    response = _request_json("POST", auth_url, _headers(anon_key, anon_key), payload)
    if not isinstance(response, dict) or not response.get("access_token"):
        raise RuntimeError(f"Supabase auth did not return an access token for {email}")
    return response


class SupabaseUserClient:
    def __init__(self, url: str, anon_key: str, access_token: str) -> None:
        self.url = url.rstrip("/")
        self.anon_key = anon_key
        self.access_token = access_token

    def get(self, path: str) -> list[dict[str, Any]]:
        request_url = f"{self.url}/rest/v1/{path.lstrip('/')}"
        response = _request_json("GET", request_url, _headers(self.anon_key, self.access_token))
        if not isinstance(response, list):
            raise RuntimeError(f"Expected list response for {path}, got {type(response).__name__}")
        return response


def load_probe_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    identities = config.get("identities")
    if not isinstance(identities, list) or not identities:
        raise ValueError("Probe config must contain a non-empty identities list")
    for identity in identities:
        for field in ("label", "tenant_id", "modules"):
            if not identity.get(field):
                raise ValueError(f"Probe identity missing {field}: {identity}")
        _validate_uuid(identity["tenant_id"], f"{identity['label']}.tenant_id")
        if not isinstance(identity["modules"], list) or not identity["modules"]:
            raise ValueError(f"Probe identity must contain modules: {identity}")
        if identity.get("partner_id"):
            identity["partner_id"] = _validate_partner_id(identity["partner_id"], f"{identity['label']}.partner_id")
        unknown = [module for module in identity["modules"] if module not in PILOT_MODULES]
        if unknown:
            raise ValueError(f"Unknown module(s) for {identity['label']}: {unknown}")
        if not identity.get("access_token") and not (identity.get("email") and identity.get("password")):
            raise ValueError(f"Probe identity needs access_token or email/password: {identity['label']}")
    return config


def _row_path(row: dict[str, Any], path: str) -> Any:
    value: Any = row
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _row_partner_id(row: dict[str, Any], fields: tuple[str, ...]) -> str:
    for field in fields:
        value = _row_path(row, field)
        if value not in (None, ""):
            return str(value)
    return ""


def evaluate_rows(
    endpoint: ProbeEndpoint,
    rows: list[dict[str, Any]],
    identity: dict[str, Any],
    allow_empty: bool = False,
) -> dict[str, Any]:
    tenant_id = str(identity["tenant_id"])
    modules = set(identity.get("modules", []))
    partner_id = str(identity.get("partner_id") or "")
    issues: list[str] = []

    if endpoint.require_rows and not allow_empty and not rows:
        issues.append(f"{endpoint.name} returned no rows; seed probe data before calling this verified")

    for index, row in enumerate(rows):
        if endpoint.tenant_field:
            row_tenant = str(row.get(endpoint.tenant_field) or "")
            if row_tenant != tenant_id:
                issues.append(
                    f"{endpoint.name}[{index}] exposes tenant {row_tenant or '<missing>'}, expected {tenant_id}"
                )
        if endpoint.module_field:
            module = row.get(endpoint.module_field)
            if module not in (None, "") and module not in modules:
                issues.append(
                    f"{endpoint.name}[{index}] exposes module {module}, allowed modules are {sorted(modules)}"
                )
        if partner_id and endpoint.partner_fields:
            row_partner_id = _row_partner_id(row, endpoint.partner_fields)
            if row_partner_id != partner_id:
                issues.append(
                    f"{endpoint.name}[{index}] exposes partner {row_partner_id or '<missing>'}, expected {partner_id}"
                )

    return {
        "endpoint": endpoint.name,
        "row_count": len(rows),
        "status": "pass" if not issues else "fail",
        "issues": issues,
    }


def probe_identity(
    identity: dict[str, Any],
    client_get: Callable[[str], list[dict[str, Any]]],
    allow_empty: bool = False,
) -> dict[str, Any]:
    checks = []
    for endpoint in PROBE_ENDPOINTS:
        try:
            rows = client_get(endpoint.path)
            checks.append(evaluate_rows(endpoint, rows, identity, allow_empty=allow_empty))
        except Exception as exc:  # noqa: BLE001 - report every probe failure as evidence.
            checks.append({
                "endpoint": endpoint.name,
                "row_count": 0,
                "status": "fail",
                "issues": [str(exc)],
            })
    return {
        "label": identity["label"],
        "tenant_id": identity["tenant_id"],
        "modules": identity["modules"],
        "partner_id": identity.get("partner_id"),
        "checks": checks,
        "status": "pass" if all(check["status"] == "pass" for check in checks) else "fail",
    }


def run_probe(config: dict[str, Any], url: str, anon_key: str, allow_empty: bool = False) -> dict[str, Any]:
    identities = []
    for identity in config["identities"]:
        access_token = identity.get("access_token")
        user_id = identity.get("user_id")
        if not access_token:
            login = login_with_password(url, anon_key, identity["email"], identity["password"])
            access_token = login["access_token"]
            user = login.get("user") if isinstance(login.get("user"), dict) else {}
            user_id = user.get("id") or user_id
        client = SupabaseUserClient(url=url, anon_key=anon_key, access_token=access_token)
        result = probe_identity(identity, client.get, allow_empty=allow_empty)
        if user_id:
            result["user_id"] = user_id
        identities.append(result)

    return {
        "report_type": "homepilot_rls_probe",
        "created_at": utc_now(),
        "supabase_url": url.rstrip("/"),
        "status": "pass" if all(identity["status"] == "pass" for identity in identities) else "fail",
        "identities": identities,
    }


def write_template(path: Path) -> None:
    template = {
        "identities": [
            {
                "label": "window_customer",
                "email": "window@example.com",
                "password": "replace-me",
                "tenant_id": "00000000-0000-4000-8000-000000000001",
                "modules": ["windowpilot"],
            },
            {
                "label": "facade_customer",
                "email": "facade@example.com",
                "password": "replace-me",
                "tenant_id": "00000000-0000-4000-8000-000000000002",
                "modules": ["facadepilot"],
                "partner_id": "renotec-antwerp",
            },
        ]
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(template, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe HomePilot Supabase RLS with real user JWTs")
    parser.add_argument("--url", default=os.environ.get("HOMEPILOT_SUPABASE_URL") or os.environ.get("SUPABASE_URL") or "")
    parser.add_argument("--anon-key", default=os.environ.get("HOMEPILOT_SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_ANON_KEY") or "")
    parser.add_argument("--allow-empty", action="store_true", help="Do not fail required endpoints when the seed dataset is empty")
    sub = parser.add_subparsers(dest="cmd", required=True)

    template = sub.add_parser("template", help="Write a probe identity config template")
    template.add_argument("--out", required=True, type=Path)

    probe = sub.add_parser("probe", help="Run the RLS probe")
    probe.add_argument("--config", required=True, type=Path)
    probe.add_argument("--out", required=True, type=Path)

    args = parser.parse_args()
    if args.cmd == "template":
        write_template(args.out)
        print(json.dumps({"output": str(args.out)}, indent=2))
        return

    if not args.url or not args.anon_key:
        raise SystemExit("Set HOMEPILOT_SUPABASE_URL and HOMEPILOT_SUPABASE_ANON_KEY, or pass --url and --anon-key")
    config = load_probe_config(args.config)
    report = run_probe(config, url=args.url, anon_key=args.anon_key, allow_empty=args.allow_empty)
    write_json(args.out, report)
    print(json.dumps({
        "output": str(args.out),
        "status": report["status"],
        "identities": len(report["identities"]),
    }, indent=2))
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
