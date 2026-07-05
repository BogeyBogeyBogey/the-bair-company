#!/usr/bin/env python3
"""
HomePilot privacy, lifecycle, and export-audit helpers.

The live Supabase schema owns the real records. This module creates portable
evidence for enterprise workflows:

- export log records for homepilot_exports
- property delete plans with ordered SQL

It is intentionally local and deterministic enough for tests, customer package
builds, and dry-run reviews before touching production data.
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_platform import PILOT_MODULES, canonical_uuid
from homepilot_store import load_payload, validate_payload


ALLOWED_EXPORT_TYPES = {"csv", "xlsx", "pdf", "json", "api"}

DELETE_TABLES = (
    "homepilot_interactions",
    "homepilot_campaign_targets",
    "homepilot_assessments",
    "homepilot_property_media",
    "homepilot_properties",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_uuid(value: Any, label: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{label} must be a UUID: {value}") from exc


def _sql_literal(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _sql_list(values: list[str]) -> str:
    return "(" + ", ".join(_sql_literal(value) for value in values) + ")"


def _require_known_module(module_key: str | None) -> str | None:
    if module_key in (None, ""):
        return None
    if module_key not in PILOT_MODULES:
        raise ValueError(f"Unknown module_key: {module_key}")
    return module_key


def build_export_log_record(
    tenant_id: str,
    module_key: str | None,
    export_type: str,
    storage_path: str | None,
    row_count: int | None,
    filters: dict[str, Any] | None = None,
    created_by: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a row that can be imported into public.homepilot_exports."""
    tenant_uuid = _ensure_uuid(tenant_id, "tenant_id")
    module = _require_known_module(module_key)
    if export_type not in ALLOWED_EXPORT_TYPES:
        raise ValueError(f"Unknown export_type: {export_type}")
    if created_by:
        created_by = _ensure_uuid(created_by, "created_by")
    if row_count is not None and int(row_count) < 0:
        raise ValueError("row_count must be >= 0")

    created = created_at or utc_now()
    clean_filters = filters or {}
    if not isinstance(clean_filters, dict):
        raise ValueError("filters must be a JSON object")
    storage = str(storage_path or "")
    count = None if row_count is None else int(row_count)
    record_id = canonical_uuid(
        "homepilot_export",
        tenant_uuid,
        module or "all_modules",
        export_type,
        storage,
        count if count is not None else "",
        json.dumps(clean_filters, sort_keys=True, ensure_ascii=False),
        created,
    )

    return {
        "id": record_id,
        "tenant_id": tenant_uuid,
        "module_key": module,
        "export_type": export_type,
        "filters": clean_filters,
        "storage_path": storage or None,
        "row_count": count,
        "created_by": created_by,
        "created_at": created,
    }


def build_export_log_from_manifest(
    export_manifest: dict[str, Any],
    tenant_id: str,
    module_key: str | None = None,
    storage_path: str | None = None,
    created_by: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    modules = export_manifest.get("tenant", {}).get("modules", [])
    selected_module = module_key
    if selected_module is None and isinstance(modules, list) and len(modules) == 1:
        selected_module = modules[0]
    export_type = "xlsx" if export_manifest.get("xlsx_written") else "csv"
    summary = export_manifest.get("summary") if isinstance(export_manifest.get("summary"), dict) else {}
    files = export_manifest.get("files") if isinstance(export_manifest.get("files"), dict) else {}
    filters = {
        "modules": modules if isinstance(modules, list) else [],
        "source": "homepilot_customer_export",
        "files": sorted(files),
    }
    row_count = int(summary.get("properties") or 0)
    return build_export_log_record(
        tenant_id=tenant_id,
        module_key=selected_module,
        export_type=export_type,
        storage_path=storage_path,
        row_count=row_count,
        filters=filters,
        created_by=created_by,
        created_at=created_at,
    )


def _rows_for_properties(rows: list[dict[str, Any]], property_ids: set[str]) -> list[dict[str, Any]]:
    return [row for row in rows if str(row.get("property_id") or "") in property_ids]


def _build_delete_sql(tenant_id: str, property_ids: list[str]) -> list[str]:
    tenant = _sql_literal(tenant_id)
    ids = _sql_list(property_ids)
    return [
        "begin;",
        f"delete from public.homepilot_interactions where tenant_id = {tenant} and property_id in {ids};",
        f"delete from public.homepilot_campaign_targets where tenant_id = {tenant} and property_id in {ids};",
        f"delete from public.homepilot_assessments where tenant_id = {tenant} and property_id in {ids};",
        f"delete from public.homepilot_property_media where tenant_id = {tenant} and property_id in {ids};",
        f"delete from public.homepilot_properties where tenant_id = {tenant} and id in {ids};",
        "-- Campaign-level response insights and campaigns are retained by default.",
        "-- Review affected_campaign_ids before pruning aggregate campaign records.",
        "commit;",
    ]


def build_property_delete_plan(payload: dict[str, Any], property_ids: list[str]) -> dict[str, Any]:
    """Create an auditable per-property deletion plan from a canonical payload."""
    validate_payload(payload)
    requested = [str(value) for value in property_ids if str(value).strip()]
    if not requested:
        raise ValueError("At least one property_id is required")

    properties_by_id = {str(row.get("id")): row for row in payload.get("properties", [])}
    missing = [property_id for property_id in requested if property_id not in properties_by_id]
    if missing:
        raise ValueError(f"Unknown property_id in payload: {missing}")

    tenants = {str(properties_by_id[property_id].get("tenant_id")) for property_id in requested}
    if len(tenants) != 1:
        raise ValueError(f"Delete plans must target exactly one tenant, got: {sorted(tenants)}")
    tenant_id = _ensure_uuid(next(iter(tenants)), "tenant_id")

    property_set = set(requested)
    target_rows = _rows_for_properties(payload.get("campaign_targets", []), property_set)
    assessment_rows = _rows_for_properties(payload.get("assessments", []), property_set)
    interaction_rows = _rows_for_properties(payload.get("interactions", []), property_set)
    media_rows = _rows_for_properties(payload.get("property_media", []), property_set)

    affected_campaign_ids = sorted({
        str(row.get("campaign_id"))
        for row in [*target_rows, *interaction_rows]
        if row.get("campaign_id")
    })
    affected_modules = sorted({
        str(row.get("module_key"))
        for row in [*target_rows, *assessment_rows, *interaction_rows]
        if row.get("module_key")
    })

    counts = {
        "homepilot_interactions": len(interaction_rows),
        "homepilot_campaign_targets": len(target_rows),
        "homepilot_assessments": len(assessment_rows),
        "homepilot_property_media": len(media_rows),
        "homepilot_properties": len(requested),
    }

    warnings = [
        "homepilot_response_insights are campaign-level records and are not deleted by a property plan.",
        "homepilot_campaigns are retained unless a separate review proves the campaign has no remaining targets.",
    ]
    if not media_rows:
        warnings.append("No property_media rows were present in the payload; SQL still deletes matching live media rows.")

    return {
        "plan_type": "homepilot_property_delete_plan",
        "created_at": utc_now(),
        "tenant_id": tenant_id,
        "property_ids": requested,
        "affected_modules": affected_modules,
        "affected_campaign_ids": affected_campaign_ids,
        "counts": counts,
        "delete_order": list(DELETE_TABLES),
        "sql": _build_delete_sql(tenant_id, requested),
        "warnings": warnings,
        "status": "ready_for_review",
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_sql(path: Path, sql_lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sql_lines) + "\n", encoding="utf-8")


def _json_arg(value: str) -> dict[str, Any]:
    data = json.loads(value)
    if not isinstance(data, dict):
        raise ValueError("--filters-json must decode to a JSON object")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="HomePilot privacy and export-audit tools")
    sub = parser.add_subparsers(dest="cmd", required=True)

    export_log = sub.add_parser("export-log", help="Build a homepilot_exports row")
    export_log.add_argument("--tenant-id", required=True)
    export_log.add_argument("--module-key", default="")
    export_log.add_argument("--export-type", required=True, choices=sorted(ALLOWED_EXPORT_TYPES))
    export_log.add_argument("--storage-path", default="")
    export_log.add_argument("--row-count", type=int, default=0)
    export_log.add_argument("--filters-json", default="{}")
    export_log.add_argument("--created-by", default="")
    export_log.add_argument("--out", required=True, type=Path)

    delete_plan = sub.add_parser("delete-plan", help="Build a per-property delete plan")
    delete_plan.add_argument("--payload", required=True, type=Path)
    delete_plan.add_argument("--property-id", action="append", required=True)
    delete_plan.add_argument("--out", required=True, type=Path)
    delete_plan.add_argument("--sql-out", type=Path)

    args = parser.parse_args()
    if args.cmd == "export-log":
        record = build_export_log_record(
            tenant_id=args.tenant_id,
            module_key=args.module_key or None,
            export_type=args.export_type,
            storage_path=args.storage_path or None,
            row_count=args.row_count,
            filters=_json_arg(args.filters_json),
            created_by=args.created_by or None,
        )
        write_json(args.out, record)
        print(json.dumps({"output": str(args.out), "id": record["id"]}, indent=2))
    elif args.cmd == "delete-plan":
        payload = load_payload(args.payload)
        plan = build_property_delete_plan(payload, args.property_id)
        write_json(args.out, plan)
        if args.sql_out:
            write_sql(args.sql_out, plan["sql"])
        print(json.dumps({
            "output": str(args.out),
            "sql": str(args.sql_out) if args.sql_out else None,
            "properties": len(plan["property_ids"]),
            "status": plan["status"],
        }, indent=2))


if __name__ == "__main__":
    main()
