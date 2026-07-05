#!/usr/bin/env python3
"""
HomePilot Supabase store.

This module imports HomePilot records into the shared Supabase schema using the
service-role key. It is deliberately separate from individual Pilot modules.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from homepilot_platform import PILOT_MODULES, metric_catalog, module_catalog


HERE = Path(__file__).parent.resolve()
HOME_ROOT = HERE.parent
ALLOWED_EXPORT_TYPES = {"csv", "xlsx", "pdf", "json", "api"}
ALLOWED_AUDIT_EVENT_TYPES = {
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
ALLOWED_AUDIT_SEVERITIES = {"info", "warn", "fail", "security"}


def load_dotenv_file(path: Path) -> None:
    """Small .env loader to keep the platform layer dependency-light."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


for env_path in (HOME_ROOT / ".env", HERE / ".env", HOME_ROOT.parent / "FacadePilot" / ".env"):
    load_dotenv_file(env_path)


class HomePilotStore:
    """PostgREST-based HomePilot store."""

    def __init__(
        self,
        url: str | None = None,
        service_key: str | None = None,
        dry_run: bool = False,
    ) -> None:
        self.url = (url or os.environ.get("HOMEPILOT_SUPABASE_URL") or os.environ.get("SUPABASE_URL") or "").rstrip("/")
        self.service_key = (
            service_key
            or os.environ.get("HOMEPILOT_SUPABASE_SERVICE_KEY")
            or os.environ.get("SUPABASE_SERVICE_KEY")
            or ""
        )
        self.dry_run = dry_run or not (self.url and self.service_key)

    @property
    def configured(self) -> bool:
        return bool(self.url and self.service_key)

    def _headers(self, prefer: str = "") -> dict[str, str]:
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _request(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        prefer: str = "",
    ) -> Any | None:
        if self.dry_run:
            count = len(payload) if isinstance(payload, list) else (1 if payload else 0)
            print(f"DRY RUN {method} {path} ({count} records)")
            return None

        url = f"{self.url}/rest/v1/{path.lstrip('/')}"
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, method=method, headers=self._headers(prefer))
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase {method} {path}: {exc.code} - {body[:500]}") from exc
        if not body:
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body

    def upsert(self, table: str, rows: list[dict[str, Any]], on_conflict: str | None = None) -> int:
        if not rows:
            return 0
        encoded_conflict = ""
        if on_conflict:
            encoded_conflict = "?on_conflict=" + urllib.parse.quote(on_conflict, safe=",")
        path = f"{table}{encoded_conflict}"
        for start in range(0, len(rows), 100):
            batch = rows[start:start + 100]
            self._request(
                "POST",
                path,
                payload=batch,
                prefer="resolution=merge-duplicates,return=minimal",
            )
        return len(rows)

    def seed_modules(self) -> int:
        modules = []
        metrics = metric_catalog()
        for key, definition in module_catalog().items():
            modules.append({
                "key": key,
                "label": definition["label"],
                "category": definition["category"],
                "metric_catalog": metrics[key],
            })
        return self.upsert("homepilot_modules", modules)

    def import_payload(self, payload: dict[str, Any]) -> dict[str, int]:
        validate_payload(payload)
        counts = {
            "campaigns": self.upsert("homepilot_campaigns", payload.get("campaigns", [])),
            "properties": self.upsert("homepilot_properties", payload.get("properties", [])),
            "assessments": self.upsert("homepilot_assessments", payload.get("assessments", [])),
            "campaign_targets": self.upsert(
                "homepilot_campaign_targets",
                payload.get("campaign_targets", []),
                on_conflict="campaign_id,property_id,module_key",
            ),
            "interactions": self.upsert("homepilot_interactions", payload.get("interactions", [])),
            "response_insights": self.upsert("homepilot_response_insights", payload.get("response_insights", [])),
            "exports": self.upsert("homepilot_exports", payload.get("exports", [])),
            "audit_events": self.upsert("homepilot_audit_events", payload.get("audit_events", [])),
        }
        return counts

    def check(self) -> bool:
        if self.dry_run:
            print("DRY RUN: no Supabase check performed")
            return False
        self._request("GET", "homepilot_modules?select=key&limit=1")
        return True


def _validate_uuid(value: Any, label: str) -> None:
    try:
        uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{label} must be a UUID: {value}") from exc


def _validate_list(payload: dict[str, Any], key: str, required: bool = False) -> None:
    if required and key not in payload:
        raise ValueError(f"Payload must contain list key: {key}")
    if key in payload and not isinstance(payload[key], list):
        raise ValueError(f"Payload key must be a list: {key}")


def validate_payload(payload: dict[str, Any]) -> None:
    for key in ("properties", "assessments", "campaign_targets"):
        _validate_list(payload, key, required=True)
    for key in ("campaigns", "interactions", "response_insights", "exports", "audit_events"):
        _validate_list(payload, key, required=False)

    property_ids = {row.get("id") for row in payload["properties"]}
    campaign_ids = {row.get("id") for row in payload.get("campaigns", [])}
    known_modules = set(PILOT_MODULES)

    for campaign in payload.get("campaigns", []):
        for field in ("id", "tenant_id", "module_key", "name"):
            if not campaign.get(field):
                raise ValueError(f"Campaign missing {field}: {campaign}")
        _validate_uuid(campaign["id"], "campaign.id")
        _validate_uuid(campaign["tenant_id"], "campaign.tenant_id")
        if campaign["module_key"] not in known_modules:
            raise ValueError(f"Unknown module_key: {campaign['module_key']}")

    property_tenants: dict[str, str] = {}
    for prop in payload["properties"]:
        for field in ("id", "tenant_id", "address"):
            if not prop.get(field):
                raise ValueError(f"Property missing {field}: {prop}")
        _validate_uuid(prop["tenant_id"], "property.tenant_id")
        property_tenants[prop["id"]] = prop["tenant_id"]

    for assessment in payload["assessments"]:
        for field in ("id", "tenant_id", "property_id", "module_key"):
            if not assessment.get(field):
                raise ValueError(f"Assessment missing {field}: {assessment}")
        _validate_uuid(assessment["tenant_id"], "assessment.tenant_id")
        if assessment["property_id"] not in property_ids:
            raise ValueError(f"Assessment references unknown property_id: {assessment['property_id']}")
        if assessment["tenant_id"] != property_tenants[assessment["property_id"]]:
            raise ValueError(f"Assessment tenant mismatch for property_id: {assessment['property_id']}")
        if assessment["module_key"] not in known_modules:
            raise ValueError(f"Unknown module_key: {assessment['module_key']}")

    for target in payload["campaign_targets"]:
        for field in ("tenant_id", "campaign_id", "property_id", "module_key"):
            if not target.get(field):
                raise ValueError(f"Campaign target missing {field}: {target}")
        _validate_uuid(target["tenant_id"], "campaign_target.tenant_id")
        _validate_uuid(target["campaign_id"], "campaign_target.campaign_id")
        if campaign_ids and target["campaign_id"] not in campaign_ids:
            raise ValueError(f"Campaign target references unknown campaign_id: {target['campaign_id']}")
        if target["property_id"] not in property_ids:
            raise ValueError(f"Campaign target references unknown property_id: {target['property_id']}")
        if target["tenant_id"] != property_tenants[target["property_id"]]:
            raise ValueError(f"Campaign target tenant mismatch for property_id: {target['property_id']}")
        if target["module_key"] not in known_modules:
            raise ValueError(f"Unknown module_key: {target['module_key']}")

    for interaction in payload.get("interactions", []):
        for field in ("tenant_id", "property_id", "module_key", "interaction_type"):
            if not interaction.get(field):
                raise ValueError(f"Interaction missing {field}: {interaction}")
        _validate_uuid(interaction["tenant_id"], "interaction.tenant_id")
        if interaction["property_id"] not in property_ids:
            raise ValueError(f"Interaction references unknown property_id: {interaction['property_id']}")
        if interaction["tenant_id"] != property_tenants[interaction["property_id"]]:
            raise ValueError(f"Interaction tenant mismatch for property_id: {interaction['property_id']}")
        if interaction["module_key"] not in known_modules:
            raise ValueError(f"Unknown module_key: {interaction['module_key']}")
        if interaction.get("campaign_id"):
            _validate_uuid(interaction["campaign_id"], "interaction.campaign_id")
            if campaign_ids and interaction["campaign_id"] not in campaign_ids:
                raise ValueError(f"Interaction references unknown campaign_id: {interaction['campaign_id']}")

    for insight in payload.get("response_insights", []):
        for field in ("tenant_id", "module_key", "insight_type", "title", "body"):
            if not insight.get(field):
                raise ValueError(f"Response insight missing {field}: {insight}")
        _validate_uuid(insight["tenant_id"], "response_insight.tenant_id")
        if insight["module_key"] not in known_modules:
            raise ValueError(f"Unknown module_key: {insight['module_key']}")
        if insight.get("campaign_id"):
            _validate_uuid(insight["campaign_id"], "response_insight.campaign_id")
            if campaign_ids and insight["campaign_id"] not in campaign_ids:
                raise ValueError(f"Response insight references unknown campaign_id: {insight['campaign_id']}")

    for export in payload.get("exports", []):
        for field in ("tenant_id", "export_type"):
            if not export.get(field):
                raise ValueError(f"Export log missing {field}: {export}")
        if export.get("id"):
            _validate_uuid(export["id"], "export.id")
        _validate_uuid(export["tenant_id"], "export.tenant_id")
        if export.get("module_key") and export["module_key"] not in known_modules:
            raise ValueError(f"Unknown module_key: {export['module_key']}")
        if export["export_type"] not in ALLOWED_EXPORT_TYPES:
            raise ValueError(f"Unknown export_type: {export['export_type']}")
        if export.get("created_by"):
            _validate_uuid(export["created_by"], "export.created_by")
        if export.get("filters") is not None and not isinstance(export["filters"], dict):
            raise ValueError(f"Export filters must be an object: {export}")
        if export.get("row_count") is not None and int(export["row_count"]) < 0:
            raise ValueError(f"Export row_count must be >= 0: {export}")

    for event in payload.get("audit_events", []):
        for field in ("tenant_id", "event_type", "severity", "details", "created_at"):
            if field not in event:
                raise ValueError(f"Audit event missing {field}: {event}")
        if event.get("id"):
            _validate_uuid(event["id"], "audit_event.id")
        _validate_uuid(event["tenant_id"], "audit_event.tenant_id")
        if event.get("actor_user_id"):
            _validate_uuid(event["actor_user_id"], "audit_event.actor_user_id")
        if event.get("module_key") and event["module_key"] not in known_modules:
            raise ValueError(f"Unknown module_key: {event['module_key']}")
        if event["event_type"] not in ALLOWED_AUDIT_EVENT_TYPES:
            raise ValueError(f"Unknown audit event_type: {event['event_type']}")
        if event["severity"] not in ALLOWED_AUDIT_SEVERITIES:
            raise ValueError(f"Unknown audit severity: {event['severity']}")
        if not isinstance(event.get("details"), dict):
            raise ValueError(f"Audit event details must be an object: {event}")


def load_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_payload(data)
    return data


def summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    modules: dict[str, int] = {}
    tenants: set[str] = set()
    for prop in payload.get("properties", []):
        tenants.add(prop.get("tenant_id", ""))
    for assessment in payload.get("assessments", []):
        key = assessment.get("module_key", "")
        modules[key] = modules.get(key, 0) + 1
        tenants.add(assessment.get("tenant_id", ""))
    return {
        "tenants": len([item for item in tenants if item]),
        "campaigns": len(payload.get("campaigns", [])),
        "properties": len(payload.get("properties", [])),
        "assessments": len(payload.get("assessments", [])),
        "campaign_targets": len(payload.get("campaign_targets", [])),
        "interactions": len(payload.get("interactions", [])),
        "response_insights": len(payload.get("response_insights", [])),
        "exports": len(payload.get("exports", [])),
        "audit_events": len(payload.get("audit_events", [])),
        "modules": modules,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="HomePilot Supabase store")
    parser.add_argument("--dry-run", action="store_true", help="Print writes without calling Supabase")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="Check Supabase connectivity")
    sub.add_parser("seed-modules", help="Upsert HomePilot module catalog")

    summary = sub.add_parser("summary-json", help="Validate and summarize a HomePilot JSON payload")
    summary.add_argument("--json", required=True, type=Path)

    import_json = sub.add_parser("import-json", help="Import a HomePilot JSON payload")
    import_json.add_argument("--json", required=True, type=Path)

    args = parser.parse_args()
    store = HomePilotStore(dry_run=args.dry_run)

    if args.cmd == "check":
        if not store.configured:
            print("Not configured: set HOMEPILOT_SUPABASE_URL and HOMEPILOT_SUPABASE_SERVICE_KEY")
            sys.exit(1)
        store.check()
        print("HomePilot Supabase connection OK")
    elif args.cmd == "seed-modules":
        count = store.seed_modules()
        suffix = " (dry run)" if store.dry_run else ""
        print(f"Seeded {count} modules{suffix}")
    elif args.cmd == "summary-json":
        payload = load_payload(args.json)
        print(json.dumps(summarize_payload(payload), indent=2, ensure_ascii=False))
    elif args.cmd == "import-json":
        payload = load_payload(args.json)
        store.seed_modules()
        counts = store.import_payload(payload)
        suffix = " (dry run)" if store.dry_run else ""
        print(json.dumps({"imported": counts, "dry_run": store.dry_run}, indent=2))
        if suffix:
            print(suffix.strip())


if __name__ == "__main__":
    main()
