#!/usr/bin/env python3
"""
HomePilot recovery and rollback planning.

This module creates non-destructive recovery evidence for imports and customer
handoffs. It never executes SQL. It writes a backup manifest, a tenant-guarded
rollback plan, SQL for review, and a small runbook that operators can archive
with the import evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_platform import PILOT_MODULES
from homepilot_store import load_payload, validate_payload


DELETE_ORDER = (
    "homepilot_audit_events",
    "homepilot_exports",
    "homepilot_interactions",
    "homepilot_campaign_targets",
    "homepilot_response_insights",
    "homepilot_assessments",
    "homepilot_property_media",
    "homepilot_campaigns",
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _row_module(row: dict[str, Any]) -> str | None:
    module = row.get("module_key")
    return str(module) if module else None


def _matches_module(row: dict[str, Any], module_keys: set[str] | None) -> bool:
    if module_keys is None:
        return True
    module = _row_module(row)
    return module in module_keys


def _rows(payload: dict[str, Any], key: str, tenant_id: str, module_keys: set[str] | None) -> list[dict[str, Any]]:
    result = []
    for row in payload.get(key, []):
        if str(row.get("tenant_id") or "") != tenant_id:
            continue
        if not _matches_module(row, module_keys):
            continue
        result.append(row)
    return result


def _property_rows(payload: dict[str, Any], tenant_id: str, property_ids: set[str]) -> list[dict[str, Any]]:
    return [
        row for row in payload.get("properties", [])
        if str(row.get("tenant_id") or "") == tenant_id and str(row.get("id") or "") in property_ids
    ]


def _id_values(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({str(row["id"]) for row in rows if row.get("id")})


def _target_condition(rows: list[dict[str, Any]]) -> str:
    clauses = []
    for row in rows:
        if not (row.get("campaign_id") and row.get("property_id") and row.get("module_key")):
            continue
        clauses.append(
            "(campaign_id = "
            + _sql_literal(row["campaign_id"])
            + " and property_id = "
            + _sql_literal(row["property_id"])
            + " and module_key = "
            + _sql_literal(row["module_key"])
            + ")"
        )
    return " or ".join(clauses)


def _insight_condition(rows: list[dict[str, Any]]) -> str:
    clauses = []
    for row in rows:
        if row.get("id"):
            continue
        parts = []
        if row.get("campaign_id"):
            parts.append("campaign_id = " + _sql_literal(row["campaign_id"]))
        if row.get("module_key"):
            parts.append("module_key = " + _sql_literal(row["module_key"]))
        if row.get("title"):
            parts.append("title = " + _sql_literal(row["title"]))
        if parts:
            clauses.append("(" + " and ".join(parts) + ")")
    return " or ".join(clauses)


def _delete_by_ids_sql(table: str, tenant_id: str, ids: list[str]) -> list[str]:
    if not ids:
        return []
    return [
        f"delete from public.{table}",
        f"where tenant_id = {_sql_literal(tenant_id)}",
        f"  and id in {_sql_list(ids)};",
    ]


def _delete_by_property_ids_sql(table: str, tenant_id: str, property_ids: list[str]) -> list[str]:
    if not property_ids:
        return []
    return [
        f"delete from public.{table}",
        f"where tenant_id = {_sql_literal(tenant_id)}",
        f"  and property_id in {_sql_list(property_ids)};",
    ]


def _module_keys(module_keys: list[str] | None) -> set[str] | None:
    if not module_keys:
        return None
    unknown = sorted(set(module_keys) - set(PILOT_MODULES))
    if unknown:
        raise ValueError(f"Unknown module_key(s): {unknown}")
    return set(module_keys)


def _tenant_id_from_payload(payload: dict[str, Any], tenant_id: str | None) -> str:
    if tenant_id:
        return _ensure_uuid(tenant_id, "tenant_id")
    tenant_ids = {
        str(row.get("tenant_id"))
        for key in ("properties", "campaigns", "assessments", "campaign_targets", "interactions", "response_insights", "exports", "audit_events")
        for row in payload.get(key, [])
        if row.get("tenant_id")
    }
    if len(tenant_ids) != 1:
        raise ValueError(f"Recovery plans require exactly one tenant, got: {sorted(tenant_ids)}")
    return _ensure_uuid(next(iter(tenant_ids)), "tenant_id")


def build_backup_manifest(paths: list[Path], label: str = "homepilot_recovery_backup") -> dict[str, Any]:
    files = []
    missing = []
    for path in paths:
        if not path.exists():
            missing.append(str(path))
            continue
        files.append({
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        })
    return {
        "manifest_type": "homepilot_backup_manifest",
        "created_at": utc_now(),
        "label": label,
        "status": "pass" if files and not missing else "fail",
        "file_count": len(files),
        "missing": missing,
        "files": files,
    }


def build_import_rollback_plan(
    payload: dict[str, Any],
    tenant_id: str | None = None,
    module_keys: list[str] | None = None,
    include_properties: bool = False,
) -> dict[str, Any]:
    validate_payload(payload)
    target_tenant = _tenant_id_from_payload(payload, tenant_id)
    module_filter = _module_keys(module_keys)

    audit_rows = _rows(payload, "audit_events", target_tenant, module_filter)
    export_rows = _rows(payload, "exports", target_tenant, module_filter)
    interaction_rows = _rows(payload, "interactions", target_tenant, module_filter)
    target_rows = _rows(payload, "campaign_targets", target_tenant, module_filter)
    insight_rows = _rows(payload, "response_insights", target_tenant, module_filter)
    assessment_rows = _rows(payload, "assessments", target_tenant, module_filter)
    media_rows = _rows(payload, "property_media", target_tenant, module_filter)
    campaign_rows = _rows(payload, "campaigns", target_tenant, module_filter)

    property_ids = {
        str(row.get("property_id"))
        for row in [*interaction_rows, *target_rows, *assessment_rows, *media_rows]
        if row.get("property_id")
    }
    property_rows = _property_rows(payload, target_tenant, property_ids) if include_properties else []

    counts = {
        "homepilot_audit_events": len(audit_rows),
        "homepilot_exports": len(export_rows),
        "homepilot_interactions": len(interaction_rows),
        "homepilot_campaign_targets": len(target_rows),
        "homepilot_response_insights": len(insight_rows),
        "homepilot_assessments": len(assessment_rows),
        "homepilot_property_media": len(media_rows),
        "homepilot_campaigns": len(campaign_rows),
        "homepilot_properties": len(property_rows),
    }

    sql = ["begin;", "-- Review this rollback plan before executing in production."]
    warnings = [
        "This plan is non-destructive evidence until an operator reviews and executes the SQL.",
        "Run only with service-role access after archiving the backup manifest and import payload.",
    ]

    for table, rows in (
        ("homepilot_audit_events", audit_rows),
        ("homepilot_exports", export_rows),
        ("homepilot_interactions", interaction_rows),
    ):
        ids = _id_values(rows)
        if ids:
            sql.extend(_delete_by_ids_sql(table, target_tenant, ids))
        elif rows:
            warnings.append(f"{table} rows without ids cannot be precisely deleted by id.")

    target_condition = _target_condition(target_rows)
    if target_condition:
        sql.extend([
            "delete from public.homepilot_campaign_targets",
            f"where tenant_id = {_sql_literal(target_tenant)}",
            f"  and ({target_condition});",
        ])
    elif target_rows:
        warnings.append("campaign target rows are missing campaign_id/property_id/module_key rollback keys.")

    insight_ids = _id_values(insight_rows)
    if insight_ids:
        sql.extend(_delete_by_ids_sql("homepilot_response_insights", target_tenant, insight_ids))
    fallback_insights = _insight_condition(insight_rows)
    if fallback_insights:
        sql.extend([
            "delete from public.homepilot_response_insights",
            f"where tenant_id = {_sql_literal(target_tenant)}",
            f"  and ({fallback_insights});",
        ])

    assessment_ids = _id_values(assessment_rows)
    if assessment_ids:
        sql.extend(_delete_by_ids_sql("homepilot_assessments", target_tenant, assessment_ids))
    elif assessment_rows:
        warnings.append("assessment rows without ids cannot be precisely deleted by id.")

    media_ids = _id_values(media_rows)
    if media_ids:
        sql.extend(_delete_by_ids_sql("homepilot_property_media", target_tenant, media_ids))
    elif media_rows:
        sql.extend(_delete_by_property_ids_sql("homepilot_property_media", target_tenant, sorted(property_ids)))
        warnings.append("property_media rows without ids will be deleted by tenant/property guard.")

    campaign_ids = _id_values(campaign_rows)
    if campaign_ids:
        sql.extend(_delete_by_ids_sql("homepilot_campaigns", target_tenant, campaign_ids))
    elif campaign_rows:
        warnings.append("campaign rows without ids cannot be precisely deleted by id.")

    if include_properties:
        property_row_ids = sorted({str(row["id"]) for row in property_rows if row.get("id")})
        if property_row_ids:
            sql.extend([
                "delete from public.homepilot_properties",
                f"where tenant_id = {_sql_literal(target_tenant)}",
                f"  and id in {_sql_list(property_row_ids)};",
            ])
        warnings.append("Property deletion is enabled; confirm these properties were created by the import and are not shared with other workflows.")
    else:
        warnings.append("Properties are retained by default; rerun with --include-properties only for imports that created new property rows.")
    sql.append("commit;")

    affected_modules = sorted({
        str(row.get("module_key"))
        for row in [*campaign_rows, *target_rows, *assessment_rows, *interaction_rows, *insight_rows, *audit_rows, *export_rows]
        if row.get("module_key")
    })
    affected_campaign_ids = sorted({
        str(row.get("campaign_id"))
        for row in [*target_rows, *interaction_rows, *insight_rows]
        if row.get("campaign_id")
    })

    return {
        "plan_type": "homepilot_import_rollback_plan",
        "created_at": utc_now(),
        "status": "ready_for_review",
        "tenant_id": target_tenant,
        "module_keys": sorted(module_filter) if module_filter else "all",
        "include_properties": include_properties,
        "affected_modules": affected_modules,
        "affected_property_ids": sorted(property_ids),
        "affected_campaign_ids": affected_campaign_ids,
        "counts": counts,
        "delete_order": list(DELETE_ORDER),
        "sql": sql,
        "warnings": warnings,
    }


def render_recovery_runbook(pack: dict[str, Any]) -> str:
    rollback = pack["rollback_plan"]
    backup = pack["backup_manifest"]
    lines = [
        "# HomePilot Recovery Pack",
        "",
        f"Created: {pack['created_at']}",
        f"Tenant: {rollback['tenant_id']}",
        f"Status: {pack['status']}",
        "",
        "## Evidence",
        "",
        f"- Backup manifest: {pack['paths']['backup_manifest']}",
        f"- Rollback plan: {pack['paths']['rollback_plan']}",
        f"- Rollback SQL: {pack['paths']['rollback_sql']}",
        "",
        "## Backup Files",
        "",
    ]
    for file_info in backup["files"]:
        lines.append(f"- {file_info['path']} ({file_info['bytes']} bytes, sha256 {file_info['sha256']})")
    lines += [
        "",
        "## Rollback Review",
        "",
        f"- Modules: {rollback['module_keys']}",
        f"- Affected properties: {len(rollback['affected_property_ids'])}",
        f"- Affected campaigns: {len(rollback['affected_campaign_ids'])}",
        f"- Include properties: {str(rollback['include_properties']).lower()}",
        "",
        "## Operator Steps",
        "",
        "1. Archive this folder with the import payload and launch/readiness evidence.",
        "2. Review tenant id, module keys, affected records, and warnings.",
        "3. Execute rollback SQL only with service-role access and a fresh production backup.",
        "4. Run data quality, access audit, and RLS probe after rollback.",
        "",
        "## Warnings",
        "",
    ]
    for warning in rollback["warnings"]:
        lines.append(f"- {warning}")
    lines.append("")
    return "\n".join(lines)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def build_recovery_pack(
    payload_path: Path,
    out_dir: Path,
    tenant_id: str | None = None,
    module_keys: list[str] | None = None,
    include_properties: bool = False,
    label: str = "homepilot_import_recovery",
) -> dict[str, Any]:
    payload = load_payload(payload_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    backup_manifest = build_backup_manifest([payload_path], label=label)
    rollback_plan = build_import_rollback_plan(
        payload,
        tenant_id=tenant_id,
        module_keys=module_keys,
        include_properties=include_properties,
    )
    pack = {
        "pack_type": "homepilot_recovery_pack",
        "created_at": utc_now(),
        "status": "ready_for_review" if backup_manifest["status"] == "pass" and rollback_plan["status"] == "ready_for_review" else "fail",
        "backup_manifest": backup_manifest,
        "rollback_plan": rollback_plan,
        "paths": {
            "backup_manifest": str(out_dir / "backup_manifest.json"),
            "rollback_plan": str(out_dir / "rollback_plan.json"),
            "rollback_sql": str(out_dir / "rollback_plan.sql"),
            "runbook": str(out_dir / "RECOVERY_RUNBOOK.md"),
            "recovery_pack": str(out_dir / "recovery_pack.json"),
        },
    }
    write_json(out_dir / "backup_manifest.json", backup_manifest)
    write_json(out_dir / "rollback_plan.json", rollback_plan)
    write_text(out_dir / "rollback_plan.sql", "\n".join(rollback_plan["sql"]) + "\n")
    write_text(out_dir / "RECOVERY_RUNBOOK.md", render_recovery_runbook(pack))
    write_json(out_dir / "recovery_pack.json", pack)
    return pack


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HomePilot recovery evidence and rollback plans")
    sub = parser.add_subparsers(dest="cmd", required=True)

    build = sub.add_parser("recovery-pack", help="Build a backup manifest, rollback plan, SQL, and runbook")
    build.add_argument("--payload", required=True, type=Path)
    build.add_argument("--out-dir", required=True, type=Path)
    build.add_argument("--tenant-id", default="")
    build.add_argument("--module", dest="modules", action="append", default=None)
    build.add_argument("--include-properties", action="store_true")
    build.add_argument("--label", default="homepilot_import_recovery")

    args = parser.parse_args()
    if args.cmd == "recovery-pack":
        pack = build_recovery_pack(
            payload_path=args.payload,
            out_dir=args.out_dir,
            tenant_id=args.tenant_id or None,
            module_keys=args.modules,
            include_properties=args.include_properties,
            label=args.label,
        )
        print(json.dumps({
            "output": str(args.out_dir),
            "status": pack["status"],
            "tenant_id": pack["rollback_plan"]["tenant_id"],
            "backup_files": pack["backup_manifest"]["file_count"],
            "rollback_sql": pack["paths"]["rollback_sql"],
            "warnings": len(pack["rollback_plan"]["warnings"]),
        }, indent=2))
        if pack["status"] == "fail":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
