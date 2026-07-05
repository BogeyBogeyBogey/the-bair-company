#!/usr/bin/env python3
"""
HomePilot audit trail helpers.

Access audits and export logs prove individual artifacts. This module creates a
portable event trail around operator/customer handoffs so enterprise buyers can
review who generated what evidence, for which tenant/module, and whether the
handoff was clean.
"""

from __future__ import annotations

import argparse
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_platform import PILOT_MODULES, canonical_uuid


AUDIT_EVENT_TYPES = {
    "access_audit_failed",
    "access_audit_passed",
    "customer_package_generated",
    "dashboard_snapshot_generated",
    "data_imported",
    "delete_plan_generated",
    "export_generated",
    "preflight_run",
    "readiness_pack_generated",
    "retention_reviewed",
    "rls_probe_run",
}

AUDIT_SEVERITIES = {"info", "warn", "fail", "security"}

SENSITIVE_PATTERNS = {
    "jwt_like_token": re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
    "service_key": re.compile(r"service[_-]?role|supabase[_-]?service|api[_-]?key", re.IGNORECASE),
    "password": re.compile(r"password|passwd|pwd", re.IGNORECASE),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_uuid(value: Any, label: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{label} must be a UUID: {value}") from exc


def _clean_module(module_key: str | None) -> str | None:
    if module_key in (None, ""):
        return None
    if module_key not in PILOT_MODULES:
        raise ValueError(f"Unknown module_key: {module_key}")
    return module_key


def _clean_details(details: dict[str, Any] | None) -> dict[str, Any]:
    clean = details or {}
    if not isinstance(clean, dict):
        raise ValueError("details must be a JSON object")
    return clean


def validate_audit_event(event: dict[str, Any]) -> None:
    if event.get("id"):
        _ensure_uuid(event["id"], "audit_event.id")
    for field in ("tenant_id", "event_type", "severity", "details", "created_at"):
        if field not in event:
            raise ValueError(f"Audit event missing {field}: {event}")
    _ensure_uuid(event["tenant_id"], "audit_event.tenant_id")
    if event.get("actor_user_id"):
        _ensure_uuid(event["actor_user_id"], "audit_event.actor_user_id")
    _clean_module(event.get("module_key"))
    if event["event_type"] not in AUDIT_EVENT_TYPES:
        raise ValueError(f"Unknown audit event_type: {event['event_type']}")
    if event["severity"] not in AUDIT_SEVERITIES:
        raise ValueError(f"Unknown audit severity: {event['severity']}")
    if not isinstance(event.get("details"), dict):
        raise ValueError(f"Audit event details must be an object: {event}")


def build_audit_event(
    tenant_id: str,
    event_type: str,
    module_key: str | None = None,
    actor_user_id: str | None = None,
    subject_type: str | None = None,
    subject_id: str | None = None,
    severity: str = "info",
    details: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    tenant_uuid = _ensure_uuid(tenant_id, "tenant_id")
    module = _clean_module(module_key)
    actor = _ensure_uuid(actor_user_id, "actor_user_id") if actor_user_id else None
    created = created_at or utc_now()
    clean_details = _clean_details(details)
    event = {
        "id": canonical_uuid(
            "homepilot_audit_event",
            tenant_uuid,
            module or "all_modules",
            event_type,
            actor or "",
            subject_type or "",
            subject_id or "",
            severity,
            json.dumps(clean_details, sort_keys=True, ensure_ascii=False),
            created,
        ),
        "tenant_id": tenant_uuid,
        "actor_user_id": actor,
        "module_key": module,
        "event_type": event_type,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "severity": severity,
        "details": clean_details,
        "created_at": created,
    }
    validate_audit_event(event)
    return event


def _manifest_tenant_id(manifest: dict[str, Any]) -> str:
    tenants = manifest.get("onboarding_tenants") if isinstance(manifest.get("onboarding_tenants"), list) else []
    if tenants and tenants[0].get("id"):
        return str(tenants[0]["id"])
    tenant_ids = manifest.get("source_scope", {}).get("tenant_ids", [])
    if tenant_ids:
        return str(tenant_ids[0])
    raise ValueError("Customer package manifest does not contain a tenant id")


def _single_module(modules: list[Any]) -> str | None:
    module_keys = [str(module) for module in modules if str(module) in PILOT_MODULES]
    return module_keys[0] if len(module_keys) == 1 else None


def build_customer_package_audit_events(
    manifest: dict[str, Any],
    actor_user_id: str | None = None,
    created_at: str | None = None,
) -> list[dict[str, Any]]:
    tenant_id = _manifest_tenant_id(manifest)
    modules = manifest.get("modules") if isinstance(manifest.get("modules"), list) else []
    module_key = _single_module(modules)
    summary = manifest.get("summary") if isinstance(manifest.get("summary"), dict) else {}
    export_log = manifest.get("export_log") if isinstance(manifest.get("export_log"), dict) else {}
    access_audit = manifest.get("access_audit") if isinstance(manifest.get("access_audit"), dict) else {}
    access_status = str(access_audit.get("status") or "unknown")
    access_event_type = "access_audit_passed" if access_status == "pass" else "access_audit_failed"
    access_severity = "info" if access_status == "pass" else "security"

    return [
        build_audit_event(
            tenant_id=tenant_id,
            module_key=module_key,
            actor_user_id=actor_user_id,
            event_type="customer_package_generated",
            subject_type="customer_package",
            subject_id=str(manifest.get("package_type", "homepilot_customer_package")),
            details={
                "module_count": len(modules),
                "modules": modules,
                "summary": summary,
                "artifact_keys": sorted((manifest.get("paths") or {}).keys()),
            },
            created_at=created_at,
        ),
        build_audit_event(
            tenant_id=tenant_id,
            module_key=export_log.get("module_key") or module_key,
            actor_user_id=actor_user_id,
            event_type="export_generated",
            subject_type="export",
            subject_id=export_log.get("id"),
            details={
                "export_type": export_log.get("export_type"),
                "row_count": export_log.get("row_count"),
                "filter_modules": export_log.get("filters", {}).get("modules", []),
            },
            created_at=created_at,
        ),
        build_audit_event(
            tenant_id=tenant_id,
            module_key=module_key,
            actor_user_id=actor_user_id,
            event_type=access_event_type,
            subject_type="access_audit",
            subject_id="customer_package_access_audit",
            severity=access_severity,
            details={
                "status": access_status,
                "issue_count": len(access_audit.get("issues") or []),
                "enabled_modules": access_audit.get("enabled_modules", []),
            },
            created_at=created_at,
        ),
    ]


def _sensitive_issues(event: dict[str, Any]) -> list[str]:
    body = json.dumps(event.get("details", {}), sort_keys=True, ensure_ascii=False)
    issues = []
    for label, pattern in SENSITIVE_PATTERNS.items():
        if pattern.search(body):
            issues.append(f"{event.get('event_type')}: details contain sensitive marker {label}")
    return issues


def build_audit_trail_report(
    events: list[dict[str, Any]],
    expected_tenant_id: str | None = None,
    required_event_types: list[str] | None = None,
) -> dict[str, Any]:
    issues: list[str] = []
    seen_ids: set[str] = set()
    event_types: dict[str, int] = {}
    severity_counts: dict[str, int] = {}
    tenant_ids: set[str] = set()
    module_keys: set[str] = set()
    expected = _ensure_uuid(expected_tenant_id, "expected_tenant_id") if expected_tenant_id else None

    for event in events:
        try:
            validate_audit_event(event)
        except ValueError as exc:
            issues.append(str(exc))
            continue
        event_id = str(event["id"])
        if event_id in seen_ids:
            issues.append(f"Duplicate audit event id: {event_id}")
        seen_ids.add(event_id)
        tenant_id = str(event["tenant_id"])
        tenant_ids.add(tenant_id)
        if expected and tenant_id != expected:
            issues.append(f"Audit event tenant {tenant_id} does not match expected tenant {expected}")
        if event.get("module_key"):
            module_keys.add(str(event["module_key"]))
        event_types[event["event_type"]] = event_types.get(event["event_type"], 0) + 1
        severity_counts[event["severity"]] = severity_counts.get(event["severity"], 0) + 1
        issues.extend(_sensitive_issues(event))

    for required in required_event_types or []:
        if required not in AUDIT_EVENT_TYPES:
            issues.append(f"Required audit event type is unknown: {required}")
        elif event_types.get(required, 0) == 0:
            issues.append(f"Missing required audit event type: {required}")

    return {
        "report_type": "homepilot_audit_trail_report",
        "created_at": utc_now(),
        "status": "pass" if not issues else "fail",
        "metrics": {
            "event_count": len(events),
            "tenant_count": len(tenant_ids),
            "module_count": len(module_keys),
            "event_types": dict(sorted(event_types.items())),
            "severity_counts": dict(sorted(severity_counts.items())),
        },
        "tenant_ids": sorted(tenant_ids),
        "module_keys": sorted(module_keys),
        "required_event_types": required_event_types or [],
        "issues": issues,
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or audit HomePilot audit trail events")
    sub = parser.add_subparsers(dest="cmd", required=True)

    package_events = sub.add_parser("package-events", help="Build audit events from a customer package manifest")
    package_events.add_argument("--manifest", required=True, type=Path)
    package_events.add_argument("--actor-user-id", default="")
    package_events.add_argument("--out", required=True, type=Path)

    report = sub.add_parser("report", help="Audit an audit_events JSON file")
    report.add_argument("--json", required=True, type=Path)
    report.add_argument("--tenant-id", default="")
    report.add_argument("--required-event", dest="required_events", action="append", default=[])
    report.add_argument("--out", required=True, type=Path)

    args = parser.parse_args()
    if args.cmd == "package-events":
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        events = build_customer_package_audit_events(
            manifest,
            actor_user_id=args.actor_user_id or None,
        )
        write_json(args.out, events)
        print(json.dumps({"output": str(args.out), "events": len(events)}, indent=2))
    elif args.cmd == "report":
        events = json.loads(args.json.read_text(encoding="utf-8"))
        if not isinstance(events, list):
            raise ValueError("--json must contain a list of audit events")
        audit_report = build_audit_trail_report(
            events,
            expected_tenant_id=args.tenant_id or None,
            required_event_types=args.required_events,
        )
        write_json(args.out, audit_report)
        print(json.dumps({
            "output": str(args.out),
            "status": audit_report["status"],
            "events": audit_report["metrics"]["event_count"],
            "issues": len(audit_report["issues"]),
        }, indent=2))
        if audit_report["status"] != "pass":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
