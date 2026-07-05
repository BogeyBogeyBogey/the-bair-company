#!/usr/bin/env python3
"""
Build a live Supabase verification fixture for HomePilot.

The fixture is intentionally small but complete: two tenants, two modules, real
membership placeholders, campaign data, interactions, export logs, and a probe
config. It turns the final RLS launch check into a repeatable sequence instead
of manual setup work.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_onboarding import build_onboarding_payload, validate_onboarding_payload
from homepilot_platform import (
    PILOT_MODULES,
    canonical_campaign_id,
    canonical_property_id,
    canonical_tenant_id,
    canonical_uuid,
    stable_hash,
)
from homepilot_audit_trail import build_audit_event
from homepilot_privacy import build_export_log_record
from homepilot_rls_probe import load_probe_config
from homepilot_store import validate_payload


DEFAULT_CREATED_AT = "2026-06-19T00:00:00+00:00"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _metrics_for_module(module_key: str, score: int) -> dict[str, Any]:
    if module_key == "windowpilot":
        return {
            "window_opportunity_score": score,
            "replacement_urgency": "Old glazing, high energy story fit",
            "visible_window_count": 14,
            "glazing_age_signal": "pre-2000",
            "energy_savings_story_fit": 88,
        }
    if module_key == "facadepilot":
        return {
            "facade_opportunity_score": score,
            "facade_preset": "Crepi insulation",
            "visible_facade_area_m2": 132,
            "property_type": "halfopen",
            "pre_1990_neighborhood_pct": 61,
            "median_income": 42800,
        }
    raise ValueError(f"Unsupported live fixture module: {module_key}")


def _grade(score: int) -> str:
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    return "B"


def build_module_payload(
    tenant_slug: str,
    module_key: str,
    campaign_key: str,
    address: str,
    city: str,
    lat: float,
    lon: float,
    score: int,
    partner_id: str = "",
    partner_name: str = "",
) -> dict[str, list[dict[str, Any]]]:
    if module_key not in PILOT_MODULES:
        raise ValueError(f"Unknown module_key: {module_key}")

    tenant_id = canonical_tenant_id(tenant_slug)
    campaign_id = canonical_campaign_id(tenant_id, module_key, campaign_key)
    property_id = canonical_property_id(tenant_id, address, lat, lon)
    assessment_id = "asmt_" + stable_hash(tenant_id, property_id, module_key, "live-fixture")
    interaction_id = canonical_uuid("interaction", tenant_id, property_id, module_key, "live-fixture")
    insight_id = canonical_uuid("insight", tenant_id, campaign_id, module_key, "live-fixture")
    grade = _grade(score)
    metrics = _metrics_for_module(module_key, score)
    partner_metadata = {}
    if partner_id:
        partner_metadata = {
            "partner_id": partner_id,
            "partner_name": partner_name or partner_id,
            "network_role": "renovation_partner",
        }

    payload = {
        "campaigns": [{
            "id": campaign_id,
            "tenant_id": tenant_id,
            "module_key": module_key,
            "name": f"{PILOT_MODULES[module_key].label} RLS Verification",
            "channel": "direct_mail",
            "status": "running",
            "territory": {"fixture": "homepilot_live_fixture", "city": city},
            "message_variant": "rls_fixture",
            **({"partner_id": partner_id, "partner_name": partner_name or partner_id, "metadata": partner_metadata} if partner_id else {}),
        }],
        "properties": [{
            "id": property_id,
            "tenant_id": tenant_id,
            "source_external_id": f"rls-{module_key}",
            "address": address,
            "city": city,
            "country_code": "BE",
            "lat": lat,
            "lon": lon,
            "property_type": "halfopen",
            "tags": ["rls-fixture", module_key] + ([partner_id] if partner_id else []),
            "core": {
                "fixture": True,
                "module_key": module_key,
                **({"network": {"scope": "producer_partner_network", **partner_metadata}} if partner_id else {}),
            },
        }],
        "assessments": [{
            "id": assessment_id,
            "tenant_id": tenant_id,
            "property_id": property_id,
            "module_key": module_key,
            "score": score,
            "grade": grade,
            "confidence": 0.92,
            "metrics": metrics,
            "evidence": [{"type": "note", "value": "Synthetic live RLS verification fixture"}],
            "source_run_id": "homepilot-live-fixture",
        }],
        "campaign_targets": [{
            "tenant_id": tenant_id,
            "campaign_id": campaign_id,
            "property_id": property_id,
            "module_key": module_key,
            "status": "responded",
            "priority_score": score,
            "priority_grade": grade,
            "metadata": {"next_action": "Verify RLS isolation, then archive fixture", **partner_metadata},
        }],
        "interactions": [{
            "id": interaction_id,
            "tenant_id": tenant_id,
            "property_id": property_id,
            "campaign_id": campaign_id,
            "module_key": module_key,
            "interaction_type": "note",
            "response_status": "interested",
            "detail": "Synthetic interaction for live RLS verification",
            "metadata": {"fixture": "homepilot_live_fixture", **partner_metadata},
            "occurred_at": DEFAULT_CREATED_AT,
        }],
        "response_insights": [{
            "id": insight_id,
            "tenant_id": tenant_id,
            "campaign_id": campaign_id,
            "module_key": module_key,
            "insight_type": "recommendation",
            "title": f"{PILOT_MODULES[module_key].label} fixture insight",
            "body": "This synthetic insight exists only to verify tenant, module, and partner isolation.",
            "supporting_metrics": {"fixture": True, "response_rate_pct": 100, **({"partner_id": partner_id} if partner_id else {})},
        }],
        "exports": [
            build_export_log_record(
                tenant_id=tenant_id,
                module_key=module_key,
                export_type="xlsx",
                storage_path=f"rls-fixture/{tenant_slug}/{module_key}/homepilot_export.xlsx",
                row_count=1,
                filters={"fixture": "homepilot_live_fixture", "modules": [module_key], **({"partner_id": partner_id} if partner_id else {})},
                created_at=DEFAULT_CREATED_AT,
            )
        ],
        "audit_events": [
            build_audit_event(
                tenant_id=tenant_id,
                module_key=module_key,
                event_type="rls_probe_run",
                subject_type="live_fixture",
                subject_id=tenant_slug,
                details={"fixture": "homepilot_live_fixture", "module": module_key, **({"partner_id": partner_id} if partner_id else {})},
                created_at=DEFAULT_CREATED_AT,
            )
        ],
    }
    validate_payload(payload)
    return payload


def combine_payloads(payloads: list[dict[str, list[dict[str, Any]]]]) -> dict[str, list[dict[str, Any]]]:
    combined = {
        "campaigns": [],
        "properties": [],
        "assessments": [],
        "campaign_targets": [],
        "interactions": [],
        "response_insights": [],
        "exports": [],
        "audit_events": [],
    }
    for payload in payloads:
        for key in combined:
            combined[key].extend(payload.get(key, []))
    validate_payload(combined)
    return combined


def _identity(
    label: str,
    email: str,
    password: str,
    tenant_id: str,
    module_key: str,
    user_id: str | None = None,
    access_token: str | None = None,
    partner_id: str = "",
) -> dict[str, Any]:
    identity = {
        "label": label,
        "email": email,
        "password": password,
        "tenant_id": tenant_id,
        "modules": [module_key],
    }
    if user_id:
        identity["user_id"] = user_id
    if access_token:
        identity["access_token"] = access_token
    if partner_id:
        identity["partner_id"] = partner_id
    return identity


def _readme(
    out_dir: Path,
    onboarding_path: Path,
    payload_path: Path,
    probe_path: Path,
    missing_user_ids: list[str],
) -> str:
    missing = ", ".join(missing_user_ids) if missing_user_ids else "none"
    return f"""# HomePilot Live RLS Fixture

Generated at {utc_now()}.

This fixture proves the production access model with three real Supabase Auth users:

- Window customer: can see only the WindowPilot tenant/module.
- Facade customer: can see only the FacadePilot tenant/module.
- Facade partner: can see only assigned FacadePilot partner records inside the facade tenant.

Missing membership user IDs: {missing}

If user IDs are missing, create the Supabase Auth users first, copy their UUIDs,
and rebuild this fixture with `--window-user-id` and `--facade-user-id`.

## Import

```bash
python3 platform/homepilot_onboarding.py import-json --json {onboarding_path}
python3 platform/homepilot_store.py import-json --json {payload_path}
```

## Probe

```bash
python3 platform/homepilot_rls_probe.py probe \\
  --config {probe_path} \\
  --out {out_dir / "rls_probe_report.json"}
```

The probe report must be `pass` before a customer gets production access.
"""


def build_live_fixture(
    out_dir: Path,
    window_email: str = "window.rls@example.com",
    window_password: str = "replace-window-password",
    facade_email: str = "facade.rls@example.com",
    facade_password: str = "replace-facade-password",
    window_user_id: str | None = None,
    facade_user_id: str | None = None,
    facade_partner_email: str = "facade.partner.rls@example.com",
    facade_partner_password: str = "replace-facade-partner-password",
    facade_partner_user_id: str | None = None,
    window_access_token: str | None = None,
    facade_access_token: str | None = None,
    facade_partner_access_token: str | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    window_slug = "homepilot-rls-window"
    facade_slug = "homepilot-rls-facade"
    window_tenant_id = canonical_tenant_id(window_slug)
    facade_tenant_id = canonical_tenant_id(facade_slug)

    window_payload = build_module_payload(
        tenant_slug=window_slug,
        module_key="windowpilot",
        campaign_key="window-rls-fixture",
        address="RLS Vensterlaan 10",
        city="Leuven",
        lat=50.8791,
        lon=4.7012,
        score=91,
    )
    facade_payload = combine_payloads([
        build_module_payload(
            tenant_slug=facade_slug,
            module_key="facadepilot",
            campaign_key="facade-renotec-rls-fixture",
            address="RLS Gevelstraat 20",
            city="Gent",
            lat=51.0504,
            lon=3.7303,
            score=86,
            partner_id="renotec-antwerp",
            partner_name="Renotec Gevelwerken",
        ),
        build_module_payload(
            tenant_slug=facade_slug,
            module_key="facadepilot",
            campaign_key="facade-other-partner-rls-fixture",
            address="RLS Partnerstraat 30",
            city="Gent",
            lat=51.0551,
            lon=3.7356,
            score=84,
            partner_id="other-facade-partner",
            partner_name="Other Facade Partner",
        ),
    ])
    combined_payload = combine_payloads([window_payload, facade_payload])

    window_memberships = [f"{window_user_id}:owner"] if window_user_id else []
    facade_memberships = [f"{facade_user_id}:owner"] if facade_user_id else []
    if facade_partner_user_id:
        facade_memberships.append(f"{facade_partner_user_id}:manager:renotec-antwerp")
    window_onboarding = build_onboarding_payload(
        name="HomePilot RLS Window Customer",
        slug=window_slug,
        modules=["windowpilot"],
        memberships=window_memberships,
        settings={"fixture": "homepilot_live_fixture"},
    )
    facade_onboarding = build_onboarding_payload(
        name="HomePilot RLS Facade Customer",
        slug=facade_slug,
        modules=["facadepilot"],
        memberships=facade_memberships,
        settings={"fixture": "homepilot_live_fixture"},
    )
    onboarding = {
        "tenants": window_onboarding["tenants"] + facade_onboarding["tenants"],
        "tenant_modules": window_onboarding["tenant_modules"] + facade_onboarding["tenant_modules"],
        "memberships": window_onboarding["memberships"] + facade_onboarding["memberships"],
    }
    validate_onboarding_payload(onboarding)

    probe_config = {
        "identities": [
            _identity(
                "window_customer",
                window_email,
                window_password,
                window_tenant_id,
                "windowpilot",
                user_id=window_user_id,
                access_token=window_access_token,
            ),
            _identity(
                "facade_customer",
                facade_email,
                facade_password,
                facade_tenant_id,
                "facadepilot",
                user_id=facade_user_id,
                access_token=facade_access_token,
            ),
            _identity(
                "facade_partner",
                facade_partner_email,
                facade_partner_password,
                facade_tenant_id,
                "facadepilot",
                user_id=facade_partner_user_id,
                access_token=facade_partner_access_token,
                partner_id="renotec-antwerp",
            ),
        ]
    }

    onboarding_path = out_dir / "onboarding.json"
    payload_path = out_dir / "payload.json"
    probe_path = out_dir / "rls_probe_config.json"
    window_payload_path = out_dir / "window_payload.json"
    facade_payload_path = out_dir / "facade_payload.json"
    manifest_path = out_dir / "manifest.json"
    readme_path = out_dir / "README.md"

    _write_json(onboarding_path, onboarding)
    _write_json(payload_path, combined_payload)
    _write_json(probe_path, probe_config)
    _write_json(window_payload_path, window_payload)
    _write_json(facade_payload_path, facade_payload)
    load_probe_config(probe_path)

    missing_user_ids = []
    if not window_user_id:
        missing_user_ids.append("window_customer")
    if not facade_user_id:
        missing_user_ids.append("facade_customer")
    if not facade_partner_user_id:
        missing_user_ids.append("facade_partner")

    manifest = {
        "fixture_type": "homepilot_live_rls_fixture",
        "created_at": utc_now(),
        "status": "ready" if not missing_user_ids else "needs_user_ids",
        "tenants": [
            {"label": "window_customer", "tenant_id": window_tenant_id, "modules": ["windowpilot"]},
            {"label": "facade_customer", "tenant_id": facade_tenant_id, "modules": ["facadepilot"]},
        ],
        "probe_identities": [
            {"label": "window_customer", "tenant_id": window_tenant_id, "modules": ["windowpilot"]},
            {"label": "facade_customer", "tenant_id": facade_tenant_id, "modules": ["facadepilot"]},
            {"label": "facade_partner", "tenant_id": facade_tenant_id, "modules": ["facadepilot"], "partner_id": "renotec-antwerp"},
        ],
        "missing_user_ids": missing_user_ids,
        "paths": {
            "onboarding": str(onboarding_path),
            "payload": str(payload_path),
            "probe_config": str(probe_path),
            "window_payload": str(window_payload_path),
            "facade_payload": str(facade_payload_path),
            "readme": str(readme_path),
            "manifest": str(manifest_path),
        },
        "record_counts": {
            "tenants": len(onboarding["tenants"]),
            "memberships": len(onboarding["memberships"]),
            "properties": len(combined_payload["properties"]),
            "assessments": len(combined_payload["assessments"]),
            "campaign_targets": len(combined_payload["campaign_targets"]),
            "interactions": len(combined_payload["interactions"]),
            "response_insights": len(combined_payload["response_insights"]),
            "exports": len(combined_payload["exports"]),
        },
    }
    _write_json(manifest_path, manifest)
    _write_text(readme_path, _readme(out_dir, onboarding_path, payload_path, probe_path, missing_user_ids))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot live RLS verification fixture")
    sub = parser.add_subparsers(dest="cmd", required=True)

    build = sub.add_parser("build", help="Write onboarding, payload, and RLS probe config")
    build.add_argument("--out-dir", required=True, type=Path)
    build.add_argument("--window-email", default="window.rls@example.com")
    build.add_argument("--window-password", default="replace-window-password")
    build.add_argument("--window-user-id", default="")
    build.add_argument("--window-access-token", default="")
    build.add_argument("--facade-email", default="facade.rls@example.com")
    build.add_argument("--facade-password", default="replace-facade-password")
    build.add_argument("--facade-user-id", default="")
    build.add_argument("--facade-access-token", default="")
    build.add_argument("--facade-partner-email", default="facade.partner.rls@example.com")
    build.add_argument("--facade-partner-password", default="replace-facade-partner-password")
    build.add_argument("--facade-partner-user-id", default="")
    build.add_argument("--facade-partner-access-token", default="")
    args = parser.parse_args()

    if args.cmd == "build":
        manifest = build_live_fixture(
            out_dir=args.out_dir,
            window_email=args.window_email,
            window_password=args.window_password,
            window_user_id=args.window_user_id or None,
            window_access_token=args.window_access_token or None,
            facade_email=args.facade_email,
            facade_password=args.facade_password,
            facade_user_id=args.facade_user_id or None,
            facade_access_token=args.facade_access_token or None,
            facade_partner_email=args.facade_partner_email,
            facade_partner_password=args.facade_partner_password,
            facade_partner_user_id=args.facade_partner_user_id or None,
            facade_partner_access_token=args.facade_partner_access_token or None,
        )
        print(json.dumps({
            "output": str(args.out_dir),
            "status": manifest["status"],
            "tenants": len(manifest["tenants"]),
            "manifest": manifest["paths"]["manifest"],
        }, indent=2))


if __name__ == "__main__":
    main()
