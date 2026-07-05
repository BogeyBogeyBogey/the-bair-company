#!/usr/bin/env python3
"""
Build CRM and webhook integration handoff packs for HomePilot customers.

The pack starts from a tenant-scoped customer package manifest and emits the
artifacts sales teams need: CRM import CSV, JSONL webhook payloads, provider
field mappings, idempotency/retry contract, and an operator runbook. It does not
call live CRMs and never writes API keys, webhook secrets, or service-role keys.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROVIDERS = ("hubspot", "pipedrive", "salesforce", "webhook")
SECRET_PATTERNS = {
    "service_role_key_literal": re.compile(r"service-role-key", re.IGNORECASE),
    "api_key_assignment": re.compile(r"api[_-]?key\s*[:=]\s*['\"][^'\"]+", re.IGNORECASE),
    "bearer_token": re.compile(r"bearer\s+[A-Za-z0-9._-]{20,}", re.IGNORECASE),
    "jwt_like_token": re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _path_from_manifest(manifest: dict[str, Any], key: str) -> Path | None:
    paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
    value = paths.get(key)
    return Path(value) if value else None


def _best_assessment(property_row: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    assessments = property_row.get("assessments") if isinstance(property_row.get("assessments"), dict) else {}
    if not assessments:
        return "", {}
    module_key = sorted(assessments, key=lambda key: assessments[key].get("score", 0), reverse=True)[0]
    return module_key, assessments[module_key]


def _stable_key(*parts: Any) -> str:
    raw = "|".join(str(part or "").strip().lower() for part in parts)
    clean = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return clean[:180] or "homepilot-record"


def _opportunity_stage(status: str) -> str:
    return {
        "generated": "prospect",
        "queued": "prospect",
        "sent": "contacted",
        "scanned": "engaged",
        "clicked": "engaged",
        "responded": "qualified",
        "appointment": "meeting_booked",
        "customer": "won",
        "rejected": "lost",
        "no_response": "nurture",
    }.get(status or "", "prospect")


def _crm_rows(snapshot: dict[str, Any], source_package_id: str) -> list[dict[str, Any]]:
    tenant = snapshot.get("tenant", {}) if isinstance(snapshot.get("tenant"), dict) else {}
    rows: list[dict[str, Any]] = []
    for property_row in snapshot.get("properties", []):
        best_module, best = _best_assessment(property_row)
        status = str(property_row.get("status") or "generated")
        row = {
            "integration_record_id": _stable_key(tenant.get("id"), property_row.get("id"), best_module),
            "tenant_id": tenant.get("id", ""),
            "tenant_name": tenant.get("name", ""),
            "property_id": property_row.get("id", ""),
            "address": property_row.get("address", ""),
            "city": property_row.get("city", ""),
            "lat": property_row.get("lat", ""),
            "lon": property_row.get("lon", ""),
            "status": status,
            "opportunity_stage": _opportunity_stage(status),
            "next_action": property_row.get("nextAction", ""),
            "estimated_value": property_row.get("estimatedValue", ""),
            "best_module": best_module,
            "best_score": best.get("score", ""),
            "best_grade": best.get("grade", ""),
            "best_label": best.get("label", ""),
            "confidence": best.get("confidence", ""),
            "tags": "; ".join(property_row.get("tags", [])),
            "interaction_count": len(property_row.get("interactions", [])),
            "source_package_id": source_package_id,
            "homepilot_source": "tenant_scoped_customer_package",
        }
        rows.append(row)
    return rows


def _webhook_payloads(snapshot: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tenant = snapshot.get("tenant", {}) if isinstance(snapshot.get("tenant"), dict) else {}
    payloads = []
    for row in rows:
        payloads.append({
            "event_type": "homepilot.opportunity.upsert",
            "schema_version": "2026-06-19",
            "idempotency_key": row["integration_record_id"],
            "tenant": {
                "id": tenant.get("id"),
                "name": tenant.get("name"),
                "modules": tenant.get("modules", []),
            },
            "property": {
                "id": row["property_id"],
                "address": row["address"],
                "city": row["city"],
                "lat": row["lat"],
                "lon": row["lon"],
                "tags": [tag.strip() for tag in row["tags"].split(";") if tag.strip()],
            },
            "opportunity": {
                "stage": row["opportunity_stage"],
                "status": row["status"],
                "module_key": row["best_module"],
                "score": row["best_score"],
                "grade": row["best_grade"],
                "label": row["best_label"],
                "confidence": row["confidence"],
                "estimated_value": row["estimated_value"],
                "next_action": row["next_action"],
            },
            "guardrails": {
                "opportunity_not_intent_without_response": row["status"] not in {"responded", "appointment", "customer"},
                "tenant_scoped": True,
                "module_scoped": True,
            },
        })
    return payloads


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def field_mapping(providers: list[str]) -> dict[str, Any]:
    common = {
        "external_id": "integration_record_id",
        "name": "address",
        "city": "city",
        "stage": "opportunity_stage",
        "value": "estimated_value",
        "source": "homepilot_source",
        "next_action": "next_action",
        "score": "best_score",
        "grade": "best_grade",
        "module": "best_module",
    }
    provider_fields = {
        "hubspot": {
            "object": "deal + company/property custom object",
            "fields": {**common, "dealname": "address", "dealstage": "opportunity_stage", "amount": "estimated_value"},
        },
        "pipedrive": {
            "object": "deal",
            "fields": {**common, "title": "address", "pipeline_stage": "opportunity_stage"},
        },
        "salesforce": {
            "object": "Lead or Opportunity custom object",
            "fields": {**common, "Company": "tenant_name", "Street": "address", "Status": "opportunity_stage"},
        },
        "webhook": {
            "object": "homepilot.opportunity.upsert event",
            "fields": {
                "idempotency_key": "integration_record_id",
                "tenant": "tenant_id, tenant_name",
                "property": "property_id, address, city, lat, lon, tags",
                "opportunity": "stage, module, score, grade, estimated_value, next_action",
            },
        },
    }
    return {provider: provider_fields[provider] for provider in providers if provider in provider_fields}


def integration_contract(providers: list[str]) -> dict[str, Any]:
    return {
        "contract_type": "homepilot_sales_integration_contract",
        "created_at": utc_now(),
        "providers": providers,
        "delivery_modes": ["manual_csv_import", "jsonl_webhook_batch", "future_live_api_sync"],
        "idempotency": {
            "key": "integration_record_id / webhook idempotency_key",
            "behavior": "Upsert by tenant + property + best module; never create duplicate opportunities for the same idempotency key.",
        },
        "retry_policy": {
            "max_attempts": 5,
            "backoff": "exponential: 1m, 5m, 15m, 1h, 6h",
            "dead_letter": "Store failed payload and operator note; do not drop records silently.",
        },
        "security": {
            "secrets_included": False,
            "webhook_url_env": "HOMEPILOT_CRM_WEBHOOK_URL",
            "api_key_env": "HOMEPILOT_CRM_API_KEY",
            "service_role_key_required": False,
        },
        "compliance": {
            "lead_language": "opportunity intelligence unless response status proves intent",
            "opt_outs": "CRM must preserve do-not-contact and suppression states before activation",
            "tenant_scope": "one tenant per integration pack",
        },
    }


def _scan_files(paths: list[Path]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        body = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(body):
                findings.append({"file": str(path), "pattern": label})
    return findings


def render_runbook(pack: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Sales Integration Runbook",
        "",
        f"Created: {pack['created_at']}",
        f"Status: {pack['status']}",
        f"Tenant: {pack['tenant'].get('name')} ({pack['tenant'].get('id')})",
        f"Providers: {', '.join(pack['providers'])}",
        "",
        "## Files",
        "",
        f"- CRM import CSV: {pack['paths']['crm_csv']}",
        f"- Webhook JSONL batch: {pack['paths']['webhook_jsonl']}",
        f"- Field mapping: {pack['paths']['field_mapping']}",
        f"- Integration contract: {pack['paths']['integration_contract']}",
        "",
        "## Operating Rules",
        "",
        "- Import or upsert by `integration_record_id` / webhook `idempotency_key`.",
        "- Keep CRM API keys and webhook URLs in environment or the target CRM, never in this pack.",
        "- Treat records as opportunity intelligence unless the status is responded, appointment, or customer.",
        "- Preserve opt-out and suppression states before any activation from CRM.",
        "- Review dead-letter failures manually before retrying.",
        "",
    ]
    if pack["failures"]:
        lines += ["## Failures", ""]
        lines.extend(f"- {failure}" for failure in pack["failures"])
    if pack["warnings"]:
        lines += ["## Warnings", ""]
        lines.extend(f"- {warning}" for warning in pack["warnings"])
    lines.append("")
    return "\n".join(lines)


def build_integration_pack(
    package_manifest_path: Path,
    out_dir: Path,
    providers: list[str] | None = None,
) -> dict[str, Any]:
    providers = list(providers or DEFAULT_PROVIDERS)
    unknown = sorted(set(providers) - set(DEFAULT_PROVIDERS))
    if unknown:
        raise ValueError(f"Unknown integration provider(s): {unknown}")
    manifest = load_json(package_manifest_path)
    snapshot_path = _path_from_manifest(manifest, "dashboard_snapshot")
    if not snapshot_path or not snapshot_path.exists():
        raise ValueError("Customer package manifest is missing an existing dashboard_snapshot path")
    snapshot = load_json(snapshot_path)
    source_scope = manifest.get("source_scope") if isinstance(manifest.get("source_scope"), dict) else {}
    tenant_ids = source_scope.get("tenant_ids") if isinstance(source_scope.get("tenant_ids"), list) else []
    enabled_modules = source_scope.get("enabled_modules") if isinstance(source_scope.get("enabled_modules"), list) else []
    access_audit = manifest.get("access_audit") if isinstance(manifest.get("access_audit"), dict) else {}
    audit_trail = manifest.get("audit_trail") if isinstance(manifest.get("audit_trail"), dict) else {}
    source_package_id = _stable_key(package_manifest_path, manifest.get("created_at"))
    rows = _crm_rows(snapshot, source_package_id=source_package_id)
    webhook_rows = _webhook_payloads(snapshot, rows)

    out_dir.mkdir(parents=True, exist_ok=True)
    crm_csv_path = out_dir / "crm_leads.csv"
    webhook_jsonl_path = out_dir / "webhook_payloads.jsonl"
    mapping_path = out_dir / "field_mapping.json"
    contract_path = out_dir / "integration_contract.json"
    manifest_path = out_dir / "integration_manifest.json"
    runbook_path = out_dir / "INTEGRATION_RUNBOOK.md"
    write_csv(crm_csv_path, rows)
    write_jsonl(webhook_jsonl_path, webhook_rows)
    write_json(mapping_path, field_mapping(providers))
    write_json(contract_path, integration_contract(providers))

    failures: list[str] = []
    warnings: list[str] = []
    if manifest.get("package_type") != "homepilot_customer_package":
        failures.append("Source manifest is not a homepilot_customer_package.")
    if access_audit.get("status") != "pass":
        failures.append(f"Package access audit is {access_audit.get('status')!r}, expected pass.")
    if audit_trail.get("status") != "pass":
        failures.append(f"Package audit trail is {audit_trail.get('status')!r}, expected pass.")
    if len(tenant_ids) != 1:
        failures.append(f"Integration source must be scoped to exactly one tenant, got {tenant_ids}.")
    if not enabled_modules:
        failures.append("Integration source has no enabled modules.")
    if not rows:
        warnings.append("No properties available for CRM/webhook integration.")
    idempotency_keys = [row["integration_record_id"] for row in rows]
    if len(idempotency_keys) != len(set(idempotency_keys)):
        failures.append("Duplicate integration_record_id values detected.")
    secret_findings = _scan_files([crm_csv_path, webhook_jsonl_path, mapping_path, contract_path])
    if secret_findings:
        failures.append(f"Secret-like values found in integration artifacts: {secret_findings}")

    pack = {
        "pack_type": "homepilot_sales_integration_pack",
        "created_at": utc_now(),
        "status": "pass" if not failures else "fail",
        "tenant": snapshot.get("tenant", {}),
        "providers": providers,
        "source_package": {
            "manifest": str(package_manifest_path),
            "access_audit_status": access_audit.get("status"),
            "audit_trail_status": audit_trail.get("status"),
            "tenant_ids": tenant_ids,
            "enabled_modules": enabled_modules,
        },
        "counts": {
            "crm_rows": len(rows),
            "webhook_payloads": len(webhook_rows),
            "providers": len(providers),
        },
        "checks": {
            "access_audit": {"status": access_audit.get("status")},
            "audit_trail": {"status": audit_trail.get("status")},
            "tenant_scope": {"status": "pass" if len(tenant_ids) == 1 else "fail", "tenant_ids": tenant_ids},
            "module_scope": {"status": "pass" if enabled_modules else "fail", "enabled_modules": enabled_modules},
            "idempotency": {"status": "pass" if len(idempotency_keys) == len(set(idempotency_keys)) else "fail"},
            "secret_scan": {"status": "pass" if not secret_findings else "fail", "findings": secret_findings},
        },
        "guardrails": {
            "secrets_included": False,
            "live_api_calls_made": False,
            "service_role_key_required": False,
            "tenant_scoped": len(tenant_ids) == 1,
            "module_scoped": bool(enabled_modules),
            "lead_language": "opportunity intelligence unless response proves intent",
        },
        "paths": {
            "integration_manifest": str(manifest_path),
            "runbook": str(runbook_path),
            "crm_csv": str(crm_csv_path),
            "webhook_jsonl": str(webhook_jsonl_path),
            "field_mapping": str(mapping_path),
            "integration_contract": str(contract_path),
        },
        "failures": failures,
        "warnings": warnings,
    }
    write_json(manifest_path, pack)
    write_text(runbook_path, render_runbook(pack))
    return pack


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HomePilot CRM/webhook integration handoff artifacts")
    parser.add_argument("--package-manifest", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--provider", dest="providers", action="append", default=None, choices=DEFAULT_PROVIDERS)
    args = parser.parse_args()

    pack = build_integration_pack(
        package_manifest_path=args.package_manifest,
        out_dir=args.out_dir,
        providers=args.providers,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": pack["status"],
        "tenant": pack["tenant"],
        "providers": pack["providers"],
        "counts": pack["counts"],
        "integration_manifest": pack["paths"]["integration_manifest"],
        "runbook": pack["paths"]["runbook"],
        "failures": pack["failures"],
        "warnings": pack["warnings"],
    }, indent=2, ensure_ascii=False))
    if pack["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
