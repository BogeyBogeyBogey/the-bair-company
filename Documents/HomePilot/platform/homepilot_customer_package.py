#!/usr/bin/env python3
"""
Build a customer-ready HomePilot package.

The package is the handoff artifact for demos, customer review, and static
deploys. It contains:

- dashboard/ static files with tenant-specific dashboard-data.js
- exports/ CSV files and optional XLSX workbook
- data/ dashboard snapshot and access audit report
- manifest.json with counts, paths, and package status
- optional zip archive
"""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_access_audit import build_access_audit
from homepilot_audit_trail import build_audit_trail_report, build_customer_package_audit_events, write_json as write_audit_json
from homepilot_boardroom_report import build_boardroom_report_pack
from homepilot_campaign_learning import build_campaign_learning_pack
from homepilot_customer_brief import build_customer_brief_pack
from homepilot_entitlements import enabled_modules_from_onboarding, filter_payload_for_entitlements, tenant_ids_from_onboarding
from homepilot_export import build_export_bundle
from homepilot_intelligence_lab import build_intelligence_lab_pack
from homepilot_onboarding import load_onboarding_payload
from homepilot_open_intelligence import build_open_intelligence_pack
from homepilot_opportunity_dossier import build_opportunity_dossier_pack
from homepilot_metric_access import filter_payload_metrics_for_surface
from homepilot_privacy import build_export_log_from_manifest, write_json as write_privacy_json
from homepilot_roi_forecast import build_roi_forecast_pack
from homepilot_snapshot import build_dashboard_snapshot, write_dashboard_js, write_dashboard_json
from homepilot_source_ledger import build_source_ledger_pack
from homepilot_store import load_payload, summarize_payload
from homepilot_territory_plan import build_territory_plan_pack


HERE = Path(__file__).parent.resolve()
HOME_ROOT = HERE.parent
CLIENT_ROOT = HOME_ROOT / "client"

CLIENT_FILES = (
    "index.html",
    "app.js",
    "styles.css",
    "sample-data.js",
    "live-config.js",
    "live-data.js",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def copy_dashboard_files(output_dir: Path, snapshot: dict[str, Any]) -> dict[str, str]:
    dashboard_dir = output_dir / "dashboard"
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    for filename in CLIENT_FILES:
        source = CLIENT_ROOT / filename
        target = dashboard_dir / filename
        shutil.copy2(source, target)
        files[filename] = str(target)
    data_path = dashboard_dir / "dashboard-data.js"
    write_dashboard_js(snapshot, data_path)
    files["dashboard-data.js"] = str(data_path)
    return files


def zip_directory(source_dir: Path, zip_path: Path) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path == zip_path:
                continue
            if path.is_file():
                archive.write(path, path.relative_to(source_dir))
    return zip_path


def build_customer_package(
    onboarding_path: Path,
    payload_path: Path,
    output_dir: Path,
    tenant_name: str | None = None,
    tenant_slug: str | None = None,
    modules: list[str] | None = None,
    include_xlsx: bool = True,
    include_zip: bool = False,
    audit_payload: bool = False,
    include_intelligence_lab: bool = False,
    intelligence_lab_run_count: int = 12,
) -> dict[str, Any]:
    onboarding = load_onboarding_payload(onboarding_path)
    payload = load_payload(payload_path)
    onboarding_tenants = onboarding.get("tenants", [])
    if len(onboarding_tenants) != 1:
        raise ValueError("Customer packages require exactly one onboarding tenant")

    tenant_ids = tenant_ids_from_onboarding(onboarding)
    package_modules = modules if modules is not None else enabled_modules_from_onboarding(onboarding)
    scoped_payload = filter_payload_for_entitlements(
        payload,
        tenant_ids=tenant_ids,
        enabled_modules=package_modules,
    )
    scoped_payload = filter_payload_metrics_for_surface(scoped_payload, surface="customer_package")
    snapshot = build_dashboard_snapshot(
        scoped_payload,
        tenant_name=tenant_name,
        tenant_slug=tenant_slug,
        enabled_modules=package_modules,
        tenant_ids=tenant_ids,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    scoped_payload_path = data_dir / "scoped_payload.json"
    scoped_payload_path.write_text(json.dumps(scoped_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    brief_pack = build_customer_brief_pack(data_dir / "customer_brief", snapshot=snapshot)
    learning_pack = build_campaign_learning_pack(data_dir / "campaign_learning", snapshot=snapshot)
    territory_pack = build_territory_plan_pack(data_dir / "territory_plan", snapshot=snapshot)
    roi_pack = build_roi_forecast_pack(data_dir / "roi_forecast", snapshot=snapshot)
    dossier_pack = build_opportunity_dossier_pack(data_dir / "opportunity_dossier", snapshot=snapshot)
    source_ledger_pack = build_source_ledger_pack(data_dir / "source_ledger", payload=scoped_payload)
    intelligence_lab_pack = None
    if include_intelligence_lab:
        intelligence_lab_pack = build_intelligence_lab_pack(
            data_dir / "intelligence_lab",
            snapshot=snapshot,
            release_label=tenant_slug or tenant_name or onboarding_tenants[0]["id"],
            run_count=intelligence_lab_run_count,
            lead_limit=50,
        )
    open_intelligence_pack = build_open_intelligence_pack(data_dir / "open_intelligence", snapshot=snapshot)
    snapshot["openIntelligence"] = open_intelligence_pack["report"]
    snapshot_path = data_dir / "dashboard_snapshot.json"
    write_dashboard_json(snapshot, snapshot_path)
    dashboard_files = copy_dashboard_files(output_dir, snapshot)
    boardroom_pack = build_boardroom_report_pack(
        snapshot=snapshot,
        output_dir=data_dir / "boardroom_report",
        dashboard_dir=output_dir / "dashboard",
    )
    dashboard_files["boardroom-report.html"] = boardroom_pack["paths"]["html"]

    export_manifest = build_export_bundle(
        snapshot=snapshot,
        output_dir=output_dir / "exports",
        include_xlsx=include_xlsx,
    )

    export_log_record = build_export_log_from_manifest(
        export_manifest=export_manifest,
        tenant_id=onboarding_tenants[0]["id"],
        storage_path=str(output_dir / "exports"),
    )
    export_log_path = data_dir / "export_log.json"
    write_privacy_json(export_log_path, export_log_record)

    audit_report = build_access_audit(
        onboarding_path=onboarding_path,
        payload_path=scoped_payload_path if audit_payload else None,
        snapshot_path=snapshot_path,
        export_dir=output_dir / "exports",
    )
    audit_path = data_dir / "access_audit.json"
    audit_path.write_text(json.dumps(audit_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if audit_report["status"] != "pass":
        raise ValueError(f"Access audit failed: {audit_report['issues']}")

    manifest = {
        "package_type": "homepilot_customer_package",
        "created_at": utc_now(),
        "tenant": snapshot.get("tenant", {}),
        "onboarding_tenants": onboarding.get("tenants", []),
        "modules": snapshot.get("tenant", {}).get("modules", []),
        "summary": snapshot.get("summary", {}),
        "paths": {
            "dashboard_index": str(output_dir / "dashboard" / "index.html"),
            "dashboard_snapshot": str(snapshot_path),
            "scoped_payload": str(scoped_payload_path),
            "access_audit": str(audit_path),
            "export_log": str(export_log_path),
            "customer_brief": brief_pack["paths"]["customer_brief"],
            "customer_brief_markdown": brief_pack["paths"]["markdown"],
            "campaign_learning": learning_pack["paths"]["campaign_learning"],
            "campaign_learning_markdown": learning_pack["paths"]["markdown"],
            "territory_plan": territory_pack["paths"]["territory_plan"],
            "territory_plan_markdown": territory_pack["paths"]["markdown"],
            "roi_forecast": roi_pack["paths"]["roi_forecast"],
            "roi_forecast_markdown": roi_pack["paths"]["markdown"],
            "opportunity_dossier": dossier_pack["paths"]["opportunity_dossier"],
            "opportunity_dossier_markdown": dossier_pack["paths"]["markdown"],
            "source_ledger": source_ledger_pack["paths"]["source_ledger"],
            "source_ledger_markdown": source_ledger_pack["paths"]["markdown"],
            "intelligence_lab": intelligence_lab_pack["paths"]["pack"] if intelligence_lab_pack else None,
            "intelligence_lab_markdown": intelligence_lab_pack["paths"]["report"] if intelligence_lab_pack else None,
            "open_intelligence": open_intelligence_pack["paths"]["open_intelligence"],
            "open_intelligence_markdown": open_intelligence_pack["paths"]["markdown"],
            "open_intelligence_boardroom_brief": open_intelligence_pack["paths"]["boardroom_brief"],
            "open_intelligence_decision_matrix": open_intelligence_pack["paths"]["decision_matrix"],
            "open_intelligence_marketing_impact_planner": open_intelligence_pack["paths"]["marketing_impact_planner"],
            "open_intelligence_measurement_loop": open_intelligence_pack["paths"]["measurement_loop"],
            "open_intelligence_production_gate": open_intelligence_pack["paths"]["production_gate"],
            "open_intelligence_production_gates": open_intelligence_pack["paths"]["production_gates"],
            "open_intelligence_production_runbook": open_intelligence_pack["paths"]["production_runbook"],
            "boardroom_report": boardroom_pack["paths"]["boardroom_report"],
            "boardroom_report_markdown": boardroom_pack["paths"]["markdown"],
            "boardroom_report_html": boardroom_pack["paths"]["html"],
            "boardroom_partner_summary": boardroom_pack["paths"].get("partner_summary"),
            "audit_events": str(data_dir / "audit_events.json"),
            "audit_trail_report": str(data_dir / "audit_trail_report.json"),
            "exports": str(output_dir / "exports"),
        },
        "source_scope": {
            "tenant_ids": sorted(tenant_ids),
            "enabled_modules": package_modules,
            "scoped_summary": summarize_payload(scoped_payload),
        },
        "dashboard_files": dashboard_files,
        "export_manifest": export_manifest,
        "export_log": export_log_record,
        "customer_brief": {
            "status": brief_pack["status"],
            "scorecard": brief_pack["brief"]["scorecard"],
            "data_confidence": brief_pack["brief"]["data_confidence"],
        },
        "campaign_learning": {
            "status": learning_pack["status"],
            "funnel": learning_pack["report"]["funnel"],
            "experiments": len(learning_pack["report"]["experiment_backlog"]),
        },
        "territory_plan": {
            "status": territory_pack["status"],
            "market_overview": territory_pack["plan"]["market_overview"],
            "territories": len(territory_pack["plan"]["territory_cells"]),
        },
        "roi_forecast": {
            "status": roi_pack["status"],
            "business_case": roi_pack["report"]["business_case"],
            "scenarios": len(roi_pack["report"]["scenario_forecast"]),
        },
        "opportunity_dossier": {
            "status": dossier_pack["status"],
            "summary": dossier_pack["report"]["summary"],
        },
        "source_ledger": {
            "status": source_ledger_pack["status"],
            "review_status": source_ledger_pack["report"]["review_status"],
            "summary": source_ledger_pack["report"]["summary"],
        },
        "intelligence_lab": {
            "status": intelligence_lab_pack["status"] if intelligence_lab_pack else "not_run",
            "families": intelligence_lab_pack["report"]["families"] if intelligence_lab_pack else {},
            "snapshot_keys_attached": intelligence_lab_pack["report"]["snapshot_keys_attached"] if intelligence_lab_pack else [],
        },
        "open_intelligence": {
            "status": open_intelligence_pack["status"],
            "model": open_intelligence_pack["report"]["model_card"]["name"],
            "model_lab": open_intelligence_pack["report"]["model_lab"]["status"],
            "data_collaboration_room": open_intelligence_pack["report"]["data_collaboration_room"]["status"],
            "marketing_impact_planner": open_intelligence_pack["report"]["marketing_impact_planner"]["status"],
            "boardroom_brief": open_intelligence_pack["report"]["boardroom_brief"]["status"],
            "boardroom_decisions": len(open_intelligence_pack["report"]["boardroom_brief"]["decision_questions"]),
            "activation_lanes": len(open_intelligence_pack["report"]["marketing_impact_planner"]["activation_lanes"]),
            "measurement_stages": len(open_intelligence_pack["report"]["marketing_impact_planner"]["measurement_loop"]),
            "production_gate": open_intelligence_pack["report"]["production_gate"]["status"],
            "production_ready": open_intelligence_pack["report"]["production_gate"]["production_ready"],
            "production_blockers": open_intelligence_pack["report"]["production_gate"]["production_blocker_count"],
            "experiment_families": [
                row.get("family")
                for row in open_intelligence_pack["report"]["model_lab"]["experiment_families"]
            ],
        },
        "boardroom_report": {
            "status": boardroom_pack["status"],
            "mode": boardroom_pack["mode"],
            "headline": boardroom_pack["report"]["headline"],
            "summary": boardroom_pack["report"]["summary"],
            "intelligence_lab": boardroom_pack["report"].get("intelligence_lab", {}),
        },
        "access_audit": audit_report,
    }

    audit_events = build_customer_package_audit_events(manifest)
    audit_trail_report = build_audit_trail_report(
        audit_events,
        expected_tenant_id=onboarding_tenants[0]["id"],
        required_event_types=["customer_package_generated", "export_generated", "access_audit_passed"],
    )
    audit_events_path = data_dir / "audit_events.json"
    audit_trail_path = data_dir / "audit_trail_report.json"
    write_audit_json(audit_events_path, audit_events)
    write_audit_json(audit_trail_path, audit_trail_report)
    if audit_trail_report["status"] != "pass":
        raise ValueError(f"Audit trail failed: {audit_trail_report['issues']}")
    manifest["audit_trail"] = {
        "status": audit_trail_report["status"],
        "event_count": len(audit_events),
        "event_types": audit_trail_report["metrics"]["event_types"],
    }

    manifest_path = output_dir / "manifest.json"
    manifest["paths"]["manifest"] = str(manifest_path)
    if include_zip:
        manifest["paths"]["zip"] = str(output_dir.with_suffix(".zip"))
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if include_zip:
        zip_path = zip_directory(output_dir, output_dir.with_suffix(".zip"))
        manifest["paths"]["zip"] = str(zip_path)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot customer package")
    parser.add_argument("--onboarding", required=True, type=Path)
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--tenant-name", default="")
    parser.add_argument("--tenant-slug", default="")
    parser.add_argument("--module", dest="modules", action="append", default=None)
    parser.add_argument("--no-xlsx", action="store_true")
    parser.add_argument("--zip", dest="include_zip", action="store_true")
    parser.add_argument("--audit-payload", action="store_true", help="Also audit the raw canonical payload")
    parser.add_argument("--include-intelligence-lab", action="store_true")
    parser.add_argument("--intelligence-lab-run-count", type=int, default=12)
    args = parser.parse_args()

    manifest = build_customer_package(
        onboarding_path=args.onboarding,
        payload_path=args.payload,
        output_dir=args.out_dir,
        tenant_name=args.tenant_name or None,
        tenant_slug=args.tenant_slug or None,
        modules=args.modules,
        include_xlsx=not args.no_xlsx,
        include_zip=args.include_zip,
        audit_payload=args.audit_payload,
        include_intelligence_lab=args.include_intelligence_lab,
        intelligence_lab_run_count=args.intelligence_lab_run_count,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "tenant": manifest["tenant"],
        "summary": manifest["summary"],
        "customer_brief": manifest["customer_brief"]["status"],
        "campaign_learning": manifest["campaign_learning"]["status"],
        "territory_plan": manifest["territory_plan"]["status"],
        "roi_forecast": manifest["roi_forecast"]["status"],
        "opportunity_dossier": manifest["opportunity_dossier"]["status"],
        "source_ledger": manifest["source_ledger"]["status"],
        "intelligence_lab": manifest["intelligence_lab"]["status"],
        "open_intelligence": manifest["open_intelligence"]["status"],
        "boardroom_report": manifest["boardroom_report"]["status"],
        "access_audit": manifest["access_audit"]["status"],
        "audit_trail": manifest["audit_trail"]["status"],
        "manifest": manifest["paths"]["manifest"],
        "zip": manifest["paths"].get("zip"),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
