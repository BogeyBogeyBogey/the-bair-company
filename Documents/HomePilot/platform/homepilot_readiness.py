#!/usr/bin/env python3
"""
HomePilot enterprise readiness evidence pack.

This is a local evidence bundle for buyer/security review. It gathers the
non-destructive gates that should be green before a live Supabase launch:

- local QA output, optionally
- deployment manifest smoke
- RLS launch dry-run evidence
- account access smoke
- customer access verification smoke
- live launch request smoke
- fixture cleanup plan
- customer portal smoke
- portal hosting smoke
- sales integration smoke
- sales integration sync dry-run smoke
- data vendor enrichment smoke
- data vendor enrichment refresh dry-run smoke
- enterprise demo room smoke
- boardroom report smoke
- partner cutdown smoke
- customer package smoke
- customer intelligence brief smoke
- campaign learning report smoke
- territory planning smoke
- ROI forecast smoke
- opportunity dossier smoke
- source ledger smoke
- audit trail smoke
- recovery smoke
- API contract smoke
- data processing register smoke
- data dictionary smoke
- data quality smoke
- compliance smoke
- retention lifecycle smoke
- privacy-safe benchmark smoke
- visual intelligence scale smoke
- monitoring and alerting smoke

It deliberately does not claim production verification. Only a live launch run
with a passing RLS probe can set production_verified to true.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_account_access import build_account_access_pack, parse_invitee
from homepilot_audit_trail import build_audit_trail_report, build_customer_package_audit_events, write_json as write_audit_json
from homepilot_api_contract import build_api_contract_pack
from homepilot_benchmarks import build_benchmark_rows, write_json as write_benchmark_json
from homepilot_boardroom_report import build_boardroom_report_pack
from homepilot_campaign_learning import build_campaign_learning_pack
from homepilot_compliance import build_compliance_report, write_json as write_compliance_json
from homepilot_customer_access_verification import build_customer_access_verification, load_account_access_plan
from homepilot_customer_brief import build_customer_brief_pack
from homepilot_customer_package import build_customer_package
from homepilot_data_dictionary import build_data_dictionary_pack
from homepilot_data_quality import build_data_quality_report, write_json as write_quality_json
from homepilot_deployment import build_deployment_pack
from homepilot_demo_room import build_daw_demo_payload, build_demo_room
from homepilot_enrichment import build_enrichment_pack
from homepilot_enrichment_refresh import build_enrichment_refresh_pack
from homepilot_hosting import build_hosting_pack
from homepilot_integration_sync import build_integration_sync_pack
from homepilot_integrations import build_integration_pack
from homepilot_intelligence_lab import build_intelligence_lab_pack
from homepilot_live_fixture import build_module_payload
from homepilot_live_launch_request import build_live_launch_request_pack
from homepilot_live_readiness import build_live_readiness_report
from homepilot_launch import run_live_rls_launch
from homepilot_monitoring import build_monitoring_pack
from homepilot_onboarding import build_onboarding_payload
from homepilot_partner_cutdown import build_partner_cutdown_pack
from homepilot_live_schema_verification import build_schema_verification_report
from homepilot_opportunity_dossier import build_opportunity_dossier_pack
from homepilot_portal import build_portal_bundle
from homepilot_processing_register import build_processing_register_pack
from homepilot_recovery import build_recovery_pack
from homepilot_retention import build_retention_report, write_json as write_retention_json
from homepilot_roi_forecast import build_roi_forecast_pack
from homepilot_snapshot import build_dashboard_snapshot
from homepilot_source_ledger import build_source_ledger_pack
from homepilot_territory_plan import build_territory_plan_pack
from homepilot_visual_intelligence import build_visual_intelligence_pack, build_visual_scale_fixture


HERE = Path(__file__).parent.resolve()
HOME_ROOT = HERE.parent


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    write_json(path, payload)


def _gate(name: str, status: str, **details: Any) -> dict[str, Any]:
    return {"name": name, "status": status, **details}


def _run_qa(out_dir: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(HERE)
    result = subprocess.run(
        [sys.executable, str(HERE / "homepilot_qa.py")],
        cwd=HOME_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    output_path = out_dir / "qa_output.txt"
    output_path.write_text((result.stdout or "") + (result.stderr or ""), encoding="utf-8")
    return _gate(
        "local_qa",
        "pass" if result.returncode == 0 else "fail",
        exit_code=result.returncode,
        output=str(output_path),
    )


def _build_deployment_smoke(out_dir: Path) -> dict[str, Any]:
    deployment_dir = out_dir / "deployment_smoke"
    pack = build_deployment_pack(
        out_dir=deployment_dir,
        release_label="readiness-local",
        environment="supabase",
    )
    manifest = pack["manifest"]
    return _gate(
        "deployment_manifest_smoke",
        "pass" if pack["status"] == "pass" else "fail",
        output=pack["paths"]["deployment_manifest"],
        runbook=pack["paths"]["deployment_runbook"],
        deployment_status=pack["status"],
        apply_order=manifest["apply_order"],
        issues=len(manifest["issues"]),
    )


def _build_schema_verification_smoke(out_dir: Path) -> dict[str, Any]:
    schema_dir = out_dir / "schema_verification_smoke"
    report = build_schema_verification_report(schema_dir, live=False, env={})
    return _gate(
        "schema_verification_smoke",
        "pass" if report["status"] == "dry_run" and report["contract_status"] == "pass" else "fail",
        output=report["paths"]["schema_verification"],
        runbook=report["paths"]["runbook"],
        verification_status=report["status"],
        contract_status=report["contract_status"],
        live_status=report["live_status"],
        production_verified=report["production_verified"],
        summary=report["summary"],
        failures=len(report["failures"]),
        warnings=len(report["warnings"]),
    )


def _build_launch_dry_run(out_dir: Path) -> dict[str, Any]:
    launch_dir = out_dir / "launch_dry_run"
    with contextlib.redirect_stdout(io.StringIO()):
        report = run_live_rls_launch(out_dir=launch_dir, dry_run=True)
    return _gate(
        "launch_dry_run",
        "pass" if report["status"] == "dry_run" and not report["production_verified"] else "fail",
        launch_report=report["paths"]["launch_report"],
        cleanup_plan=report["paths"]["cleanup_plan"],
        cleanup_sql=report["paths"]["cleanup_sql"],
        rls_probe=report["rls_probe"]["status"],
        production_verified=report["production_verified"],
    )



def _build_account_access_smoke(out_dir: Path) -> dict[str, Any]:
    access_dir = out_dir / "account_access_smoke"
    access_dir.mkdir(parents=True, exist_ok=True)
    owner_id = "11111111-1111-4111-8111-111111111111"
    manager_id = "22222222-2222-4222-8222-222222222222"
    partner_manager_id = "33333333-3333-4333-8333-333333333333"
    onboarding = build_onboarding_payload(
        name="Readiness Access Customer",
        slug="readiness-access-customer",
        modules=["windowpilot"],
        memberships=[f"{owner_id}:owner", f"{manager_id}:manager"],
    )
    onboarding_path = access_dir / "onboarding.json"
    _write_payload(onboarding_path, onboarding)
    pack = build_account_access_pack(
        access_dir,
        onboarding=onboarding,
        invitees=[
            parse_invitee(f"owner@example.com:owner:{owner_id}"),
            parse_invitee(f"manager@example.com:manager:{manager_id}"),
            parse_invitee(f"partner@example.com:manager:{partner_manager_id}:renotec-antwerp"),
        ],
    )
    plan = pack["plan"]
    owner_count = plan["role_counts"].get("owner", 0)
    ready_memberships = len(plan["membership_rows"])
    partner_scoped_memberships = len([row for row in plan["membership_rows"] if row.get("partner_id")])
    status = "pass" if (
        pack["status"] == "pass"
        and owner_count >= 1
        and ready_memberships == 3
        and partner_scoped_memberships == 1
    ) else "fail"
    return _gate(
        "account_access_smoke",
        status,
        output=pack["paths"]["account_access_plan"],
        markdown=pack["paths"]["markdown"],
        membership_upsert_sql=pack["paths"]["membership_upsert_sql"],
        membership_revocation_sql=pack["paths"]["membership_revocation_sql"],
        access_status=pack["status"],
        review_status=pack["review_status"],
        invitees=len(plan["invitees"]),
        ready_memberships=ready_memberships,
        partner_scoped_memberships=partner_scoped_memberships,
        role_counts=plan["role_counts"],
        scope_counts=plan.get("scope_counts", {}),
        warnings=len(plan["warnings"]),
        failures=len(plan["failures"]),
    )


def _build_customer_access_verification_smoke(out_dir: Path) -> dict[str, Any]:
    verification_dir = out_dir / "customer_access_verification_smoke"
    verification_dir.mkdir(parents=True, exist_ok=True)
    account_access_path = out_dir / "account_access_smoke" / "account_access_plan.json"
    report = build_customer_access_verification(
        verification_dir,
        account_access_plan=load_account_access_plan(account_access_path),
        dry_run=True,
        env={},
    )
    access_lens_proof = report.get("access_lens_proof") or {}
    status = "pass" if (
        report["status"] == "dry_run"
        and not report["production_verified"]
        and report["identities"]
        and access_lens_proof.get("status") == "review_ready"
        and Path(report["paths"]["access_lens_matrix"]).exists()
    ) else "fail"
    return _gate(
        "customer_access_verification_smoke",
        status,
        output=report["paths"]["customer_access_verification"],
        markdown=report["paths"]["markdown"],
        probe_contract=report["paths"]["probe_contract"],
        rls_probe_report=report["paths"]["rls_probe_report"],
        access_lens_matrix=report["paths"]["access_lens_matrix"],
        verification_status=report["status"],
        rls_probe=report["rls_probe"]["status"],
        access_lens_proof_status=access_lens_proof.get("status"),
        access_lens_summary=access_lens_proof.get("summary", {}),
        identities=len(report["identities"]),
        production_verified=report["production_verified"],
        warnings=len(report["warnings"]),
        failures=len(report["failures"]),
    )


def _build_live_readiness_smoke(out_dir: Path) -> dict[str, Any]:
    readiness_dir = out_dir / "live_readiness_smoke"
    account_access_path = out_dir / "account_access_smoke" / "account_access_plan.json"
    report = build_live_readiness_report(
        readiness_dir,
        account_access_plan_path=account_access_path,
        readiness_report_path=out_dir / "readiness_report.json",
        due_diligence_report_path=out_dir / "due_diligence_report.json",
        release_label="readiness-live-doctor",
        env={},
    )
    status = "pass" if (
        report["status"] == "action_required"
        and not report["ready_to_run_live_cutover"]
        and report["guardrails"]["secrets_written"] is False
        and report["missing_live_inputs"]
    ) else "fail"
    return _gate(
        "live_readiness_smoke",
        status,
        output=report["paths"]["live_readiness"],
        markdown=report["paths"]["markdown"],
        env_template=report["paths"]["env_template"],
        readiness_status=report["status"],
        ready_to_run_live_cutover=report["ready_to_run_live_cutover"],
        missing_live_inputs=len(report["missing_live_inputs"]),
        customer_access_status=report["customer_access"]["status"],
        secrets_written=report["guardrails"]["secrets_written"],
    )


def _build_live_launch_request_smoke(out_dir: Path) -> dict[str, Any]:
    request_dir = out_dir / "live_launch_request_smoke"
    live_readiness_path = out_dir / "live_readiness_smoke" / "live_readiness.json"
    account_access_path = out_dir / "account_access_smoke" / "account_access_plan.json"
    report = build_live_launch_request_pack(
        request_dir,
        live_readiness_report_path=live_readiness_path,
        account_access_plan_path=account_access_path,
        release_label="readiness-live-request",
    )
    status = "pass" if (
        report["status"] == "action_required"
        and report["summary"]["task_count"] > 0
        and report["guardrails"]["secrets_written"] is False
        and Path(report["paths"]["checklist_csv"]).exists()
        and Path(report["paths"]["env_template"]).exists()
    ) else "fail"
    return _gate(
        "live_launch_request_smoke",
        status,
        output=report["paths"]["live_launch_request"],
        markdown=report["paths"]["markdown"],
        checklist_csv=report["paths"]["checklist_csv"],
        env_template=report["paths"]["env_template"],
        request_email=report["paths"]["request_email"],
        request_status=report["status"],
        task_count=report["summary"]["task_count"],
        secret_task_count=report["summary"]["secret_task_count"],
        secrets_written=report["guardrails"]["secrets_written"],
    )


def _build_recovery_smoke(out_dir: Path) -> dict[str, Any]:
    recovery_dir = out_dir / "recovery_smoke"
    recovery_dir.mkdir(parents=True, exist_ok=True)
    payload = build_module_payload(
        tenant_slug="readiness-recovery-window",
        module_key="windowpilot",
        campaign_key="readiness-recovery-window",
        address="Readiness Herstellaan 1",
        city="Leuven",
        lat=50.884,
        lon=4.706,
        score=89,
    )
    payload_path = recovery_dir / "payload.json"
    _write_payload(payload_path, payload)
    pack = build_recovery_pack(
        payload_path=payload_path,
        out_dir=recovery_dir / "pack",
        include_properties=True,
        label="readiness_recovery_smoke",
    )
    return _gate(
        "recovery_smoke",
        "pass" if pack["status"] == "ready_for_review" else "fail",
        output=pack["paths"]["recovery_pack"],
        rollback_sql=pack["paths"]["rollback_sql"],
        backup_manifest=pack["paths"]["backup_manifest"],
        recovery_status=pack["status"],
        counts=pack["rollback_plan"]["counts"],
        warnings=len(pack["rollback_plan"]["warnings"]),
    )


def _build_api_contract_smoke(out_dir: Path) -> dict[str, Any]:
    api_dir = out_dir / "api_contract_smoke"
    pack = build_api_contract_pack(api_dir)
    contract = pack["contract"]
    return _gate(
        "api_contract_smoke",
        "pass" if pack["status"] == "pass" else "fail",
        output=pack["paths"]["api_contract"],
        markdown=pack["paths"]["markdown"],
        api_contract_status=pack["status"],
        counts=contract["counts"],
        issues=len(contract["issues"]),
    )


def _build_processing_register_smoke(out_dir: Path) -> dict[str, Any]:
    processing_dir = out_dir / "processing_register_smoke"
    pack = build_processing_register_pack(processing_dir)
    register = pack["register"]
    return _gate(
        "processing_register_smoke",
        "pass" if pack["status"] == "pass" else "fail",
        output=pack["paths"]["processing_register"],
        markdown=pack["paths"]["markdown"],
        processing_register_status=pack["status"],
        counts=register["counts"],
        issues=len(register["issues"]),
    )


def _build_data_dictionary_smoke(out_dir: Path) -> dict[str, Any]:
    dictionary_dir = out_dir / "data_dictionary_smoke"
    pack = build_data_dictionary_pack(dictionary_dir)
    dictionary = pack["dictionary"]
    return _gate(
        "data_dictionary_smoke",
        "pass" if pack["status"] == "pass" else "fail",
        output=pack["paths"]["data_dictionary"],
        markdown=pack["paths"]["markdown"],
        dictionary_status=pack["status"],
        counts=dictionary["counts"],
        issues=len(dictionary["issues"]),
    )


def _build_data_quality_smoke(out_dir: Path) -> dict[str, Any]:
    quality_dir = out_dir / "data_quality_smoke"
    quality_dir.mkdir(parents=True, exist_ok=True)
    payload = build_module_payload(
        tenant_slug="readiness-quality-window",
        module_key="windowpilot",
        campaign_key="readiness-quality-window",
        address="Readiness Qualitylaan 1",
        city="Leuven",
        lat=50.881,
        lon=4.703,
        score=93,
    )
    payload_path = quality_dir / "payload.json"
    _write_payload(payload_path, payload)
    report = build_data_quality_report(payload)
    report_path = quality_dir / "data_quality_report.json"
    write_quality_json(report_path, report)
    return _gate(
        "data_quality_smoke",
        "pass" if report["status"] == "pass" else "fail",
        output=str(report_path),
        quality_status=report["status"],
        metrics=report["metrics"],
        warnings=len(report["warnings"]),
        failures=len(report["failures"]),
    )


def _build_compliance_smoke(out_dir: Path) -> dict[str, Any]:
    compliance_dir = out_dir / "compliance_smoke"
    compliance_dir.mkdir(parents=True, exist_ok=True)
    payload = build_module_payload(
        tenant_slug="readiness-compliance-window",
        module_key="windowpilot",
        campaign_key="readiness-compliance-window",
        address="Readiness Compliancelaan 1",
        city="Leuven",
        lat=50.882,
        lon=4.704,
        score=91,
    )
    payload["campaigns"][0]["message_variant"] = "readiness_compliance"
    payload["campaign_targets"][0]["metadata"].update({
        "contact_basis": "legitimate_interest_reviewed",
        "source_provenance": "Synthetic readiness fixture; no live outreach",
        "contact_channel": "direct_mail",
        "opt_out_method": "Reply using customer suppression workflow",
        "retention_review_at": "2026-12-31",
        "lead_claim": "renovation opportunity based on visible property signals",
    })
    payload_path = compliance_dir / "payload.json"
    _write_payload(payload_path, payload)
    report = build_compliance_report(payload)
    report_path = compliance_dir / "compliance_report.json"
    write_compliance_json(report_path, report)
    return _gate(
        "compliance_smoke",
        "pass" if report["status"] == "pass" else "fail",
        output=str(report_path),
        compliance_status=report["status"],
        metrics=report["metrics"],
        warnings=len(report["warnings"]),
        failures=len(report["failures"]),
    )


def _build_customer_package_smoke(out_dir: Path) -> dict[str, Any]:
    smoke_dir = out_dir / "customer_package_smoke"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    tenant_slug = "readiness-window-customer"
    onboarding = build_onboarding_payload(
        name="Readiness Window Customer",
        slug=tenant_slug,
        modules=["windowpilot"],
    )
    payload = build_module_payload(
        tenant_slug=tenant_slug,
        module_key="windowpilot",
        campaign_key="readiness-window",
        address="Readiness Vensterlaan 1",
        city="Leuven",
        lat=50.879,
        lon=4.701,
        score=92,
    )
    payload["campaign_targets"][0]["metadata"].update({
        "contact_basis": "legitimate_interest_reviewed",
        "source_provenance": "Synthetic readiness fixture; no live outreach",
        "contact_channel": "direct_mail",
        "opt_out_method": "Reply using customer suppression workflow",
        "lead_claim": "renovation opportunity based on visible property signals",
    })
    onboarding_path = smoke_dir / "onboarding.json"
    payload_path = smoke_dir / "payload.json"
    _write_payload(onboarding_path, onboarding)
    _write_payload(payload_path, payload)

    package_dir = smoke_dir / "package"
    manifest = build_customer_package(
        onboarding_path=onboarding_path,
        payload_path=payload_path,
        output_dir=package_dir,
        tenant_name="Readiness Window Customer",
        tenant_slug=tenant_slug,
        modules=["windowpilot"],
        include_xlsx=True,
        include_zip=True,
        audit_payload=True,
    )
    expected_paths = [
        package_dir / "dashboard" / "index.html",
        package_dir / "dashboard" / "dashboard-data.js",
        package_dir / "exports" / "properties.csv",
        package_dir / "data" / "access_audit.json",
        package_dir / "data" / "export_log.json",
        package_dir / "data" / "customer_brief" / "customer_brief.json",
        package_dir / "data" / "customer_brief" / "CUSTOMER_BRIEF.md",
        package_dir / "data" / "campaign_learning" / "campaign_learning.json",
        package_dir / "data" / "campaign_learning" / "CAMPAIGN_LEARNING.md",
        package_dir / "data" / "territory_plan" / "territory_plan.json",
        package_dir / "data" / "territory_plan" / "TERRITORY_PLAN.md",
        package_dir / "data" / "roi_forecast" / "roi_forecast.json",
        package_dir / "data" / "roi_forecast" / "ROI_FORECAST.md",
        package_dir / "data" / "opportunity_dossier" / "opportunity_dossier.json",
        package_dir / "data" / "opportunity_dossier" / "OPPORTUNITY_DOSSIER.md",
        package_dir / "data" / "source_ledger" / "source_ledger.json",
        package_dir / "data" / "source_ledger" / "SOURCE_LEDGER.md",
        package_dir / "data" / "boardroom_report" / "boardroom_report.json",
        package_dir / "data" / "boardroom_report" / "BOARDROOM_REPORT.md",
        package_dir / "dashboard" / "boardroom-report.html",
        package_dir / "manifest.json",
        package_dir.with_suffix(".zip"),
    ]
    missing = [str(path) for path in expected_paths if not path.exists()]
    status = "pass" if manifest["access_audit"]["status"] == "pass" and not missing else "fail"
    return _gate(
        "customer_package_smoke",
        status,
        manifest=manifest["paths"]["manifest"],
        access_audit=manifest["access_audit"]["status"],
        export_log=manifest["paths"]["export_log"],
        customer_brief=manifest["paths"]["customer_brief"],
        customer_brief_status=manifest["customer_brief"]["status"],
        campaign_learning=manifest["paths"]["campaign_learning"],
        campaign_learning_status=manifest["campaign_learning"]["status"],
        territory_plan=manifest["paths"]["territory_plan"],
        territory_plan_status=manifest["territory_plan"]["status"],
        roi_forecast=manifest["paths"]["roi_forecast"],
        roi_forecast_status=manifest["roi_forecast"]["status"],
        opportunity_dossier=manifest["paths"]["opportunity_dossier"],
        opportunity_dossier_status=manifest["opportunity_dossier"]["status"],
        source_ledger=manifest["paths"]["source_ledger"],
        source_ledger_status=manifest["source_ledger"]["status"],
        source_ledger_review_status=manifest["source_ledger"]["review_status"],
        boardroom_report=manifest["paths"]["boardroom_report"],
        boardroom_report_html=manifest["paths"]["boardroom_report_html"],
        boardroom_report_status=manifest["boardroom_report"]["status"],
        boardroom_report_mode=manifest["boardroom_report"]["mode"],
        zip=manifest["paths"].get("zip"),
        missing=missing,
    )


def _build_customer_portal_smoke(out_dir: Path) -> dict[str, Any]:
    portal_dir = out_dir / "customer_portal_smoke"
    package_manifest = out_dir / "customer_package_smoke" / "package" / "manifest.json"
    portal = build_portal_bundle(package_manifest, portal_dir)
    checks = portal["checks"]
    status = "pass" if (
        portal["status"] == "pass"
        and checks["secret_scan"]["status"] == "pass"
        and checks["live_runtime"]["status"] == "pass"
    ) else "fail"
    return _gate(
        "customer_portal_smoke",
        status,
        output=portal["paths"]["portal_manifest"],
        readme=portal["paths"]["readme"],
        public_dir=portal["paths"]["public_dir"],
        headers=portal["paths"]["headers"],
        redirects=portal["paths"]["redirects"],
        routes=portal["paths"]["routes"],
        live_config=portal["paths"]["live_config"],
        live_loader=portal["paths"]["live_loader"],
        portal_status=portal["status"],
        required_public_files=checks["required_public_files"]["status"],
        expected_views=checks["expected_views"]["status"],
        access_audit=checks["access_audit"]["status"],
        tenant_scope=checks["tenant_scope"]["status"],
        module_scope=checks["module_scope"]["status"],
        secret_scan=checks["secret_scan"]["status"],
        live_runtime=checks["live_runtime"]["status"],
        live_runtime_status=portal["live_runtime"]["status"],
        exports=checks["exports"]["status"],
        failures=len(portal["failures"]),
        warnings=len(portal["warnings"]),
    )


def _build_portal_hosting_smoke(out_dir: Path) -> dict[str, Any]:
    hosting_dir = out_dir / "portal_hosting_smoke"
    portal_manifest = out_dir / "customer_portal_smoke" / "portal_manifest.json"
    pack = build_hosting_pack(
        portal_manifest_path=portal_manifest,
        out_dir=hosting_dir,
        release_label="readiness-local",
        env={},
    )
    manifest = pack["manifest"]
    status = "pass" if (
        pack["status"] == "pass"
        and manifest["stage_status"] == "buyer_review_hosting_ready"
        and manifest["checks"]["secret_scan"] == "pass"
    ) else "fail"
    return _gate(
        "portal_hosting_smoke",
        status,
        output=pack["paths"]["hosting_manifest"],
        runbook=pack["paths"]["runbook"],
        asset_manifest=pack["paths"]["asset_manifest"],
        cache_policy=pack["paths"]["cache_policy"],
        netlify_toml=pack["paths"]["netlify_toml"],
        vercel_json=pack["paths"]["vercel_json"],
        deployment_checklist=pack["paths"]["deployment_checklist"],
        rollback_manifest=pack["paths"]["rollback_manifest"],
        hosting_status=pack["status"],
        stage_status=manifest["stage_status"],
        production_gate=manifest["production_gate"],
        checks=manifest["checks"],
        summary=manifest["summary"],
        failures=len(manifest["failures"]),
        warnings=len(manifest["warnings"]),
    )


def _build_sales_integration_smoke(out_dir: Path) -> dict[str, Any]:
    integration_dir = out_dir / "sales_integration_smoke"
    package_manifest = out_dir / "customer_package_smoke" / "package" / "manifest.json"
    pack = build_integration_pack(package_manifest, integration_dir)
    checks = pack["checks"]
    status = "pass" if pack["status"] == "pass" and checks["secret_scan"]["status"] == "pass" else "fail"
    return _gate(
        "sales_integration_smoke",
        status,
        output=pack["paths"]["integration_manifest"],
        runbook=pack["paths"]["runbook"],
        crm_csv=pack["paths"]["crm_csv"],
        webhook_jsonl=pack["paths"]["webhook_jsonl"],
        field_mapping=pack["paths"]["field_mapping"],
        integration_contract=pack["paths"]["integration_contract"],
        integration_status=pack["status"],
        providers=pack["providers"],
        counts=pack["counts"],
        tenant_scope=checks["tenant_scope"]["status"],
        module_scope=checks["module_scope"]["status"],
        idempotency=checks["idempotency"]["status"],
        secret_scan=checks["secret_scan"]["status"],
        failures=len(pack["failures"]),
        warnings=len(pack["warnings"]),
    )


def _build_sales_integration_sync_smoke(out_dir: Path) -> dict[str, Any]:
    sync_dir = out_dir / "sales_integration_sync_smoke"
    integration_manifest = out_dir / "sales_integration_smoke" / "integration_manifest.json"
    report = build_integration_sync_pack(integration_manifest, sync_dir, live=False, env={})
    status = "pass" if report["status"] == "pass" and report["mode"] == "dry_run" else "fail"
    return _gate(
        "sales_integration_sync_smoke",
        status,
        output=report["paths"]["sync_report"],
        runbook=report["paths"]["runbook"],
        delivery_attempts=report["paths"]["delivery_attempts"],
        dead_letter=report["paths"]["dead_letter"],
        mode=report["mode"],
        summary=report["summary"],
        credentials=report["checks"]["credentials"],
        delivery=report["checks"]["delivery"],
        idempotency=report["checks"]["idempotency"],
        failures=len(report["failures"]),
        warnings=len(report["warnings"]),
    )


def _build_data_vendor_enrichment_smoke(out_dir: Path) -> dict[str, Any]:
    enrichment_dir = out_dir / "data_vendor_enrichment_smoke"
    package_manifest = out_dir / "customer_package_smoke" / "package" / "manifest.json"
    pack = build_enrichment_pack(package_manifest, enrichment_dir)
    plan = pack["plan"]
    status = "pass" if pack["status"] == "pass" else "fail"
    return _gate(
        "data_vendor_enrichment_smoke",
        status,
        output=pack["paths"]["data_vendor_plan"],
        markdown=pack["paths"]["markdown"],
        source_requirements=pack["paths"]["source_requirements"],
        enrichment_backlog=pack["paths"]["enrichment_backlog"],
        enrichment_status=pack["status"],
        review_status=pack["review_status"],
        summary=plan["summary"],
        categories=len(plan["coverage"]),
        backlog_items=plan["summary"]["backlog_items"],
        warnings=len(plan["warnings"]),
        failures=len(plan["failures"]),
    )


def _build_data_vendor_refresh_smoke(out_dir: Path) -> dict[str, Any]:
    refresh_dir = out_dir / "data_vendor_refresh_smoke"
    enrichment_plan = out_dir / "data_vendor_enrichment_smoke" / "data_vendor_plan.json"
    report = build_enrichment_refresh_pack(enrichment_plan, refresh_dir, live=False, env={}, max_jobs=25)
    status = "pass" if report["status"] == "pass" and report["mode"] == "dry_run" else "fail"
    return _gate(
        "data_vendor_refresh_smoke",
        status,
        output=report["paths"]["refresh_report"],
        runbook=report["paths"]["runbook"],
        refresh_jobs_jsonl=report["paths"]["refresh_jobs_jsonl"],
        refresh_jobs_csv=report["paths"]["refresh_jobs_csv"],
        delivery_attempts=report["paths"]["delivery_attempts"],
        dead_letter=report["paths"]["dead_letter"],
        mode=report["mode"],
        summary=report["summary"],
        credentials=report["checks"]["credentials"],
        delivery=report["checks"]["delivery"],
        idempotency=report["checks"]["idempotency"],
        tenant_scope=report["checks"]["tenant_scope"],
        failures=len(report["failures"]),
        warnings=len(report["warnings"]),
    )


def _build_enterprise_demo_room_smoke(out_dir: Path) -> dict[str, Any]:
    demo_dir = out_dir / "enterprise_demo_room_smoke"
    manifest = build_demo_room(demo_dir, include_xlsx=False, include_zip=False)
    summary = manifest["summary"]
    modules = set(manifest["modules"])
    status_checks = manifest.get("status_checks", {})
    status = "pass" if (
        manifest["status"] == "pass"
        and summary.get("properties", 0) >= 12
        and summary.get("interactions", 0) >= 16
        and modules >= {"facadepilot", "windowpilot", "roofpilot", "gardenpilot", "poolpilot", "porchpilot", "drivewaypilot"}
        and all(status == "pass" for status in status_checks.values())
    ) else "fail"
    return _gate(
        "enterprise_demo_room_smoke",
        status,
        output=manifest["paths"]["manifest"],
        readme=manifest["paths"]["readme"],
        dashboard=manifest["paths"]["dashboard_index"],
        portal_manifest=manifest["paths"]["portal_manifest"],
        integration_manifest=manifest["paths"]["integration_manifest"],
        data_vendor_plan=manifest["paths"]["data_vendor_plan"],
        data_vendor_plan_markdown=manifest["paths"]["data_vendor_plan_markdown"],
        properties=summary.get("properties", 0),
        assessments=summary.get("assessments", 0),
        interactions=summary.get("interactions", 0),
        modules=sorted(modules),
        status_checks=status_checks,
    )


def _build_boardroom_report_smoke(out_dir: Path) -> dict[str, Any]:
    boardroom_dir = out_dir / "boardroom_report_smoke"
    dashboard_dir = boardroom_dir / "dashboard"
    payload = build_daw_demo_payload(property_count=120)
    snapshot = build_dashboard_snapshot(
        payload,
        tenant_name="DAW Belgium Readiness Network",
        tenant_slug="daw-belgium-readiness-network",
        enabled_modules=["facadepilot"],
    )
    lab_pack = build_intelligence_lab_pack(
        boardroom_dir / "intelligence_lab",
        snapshot=snapshot,
        release_label="readiness-boardroom-smoke",
        run_count=6,
        lead_limit=30,
    )
    pack = build_boardroom_report_pack(
        snapshot=snapshot,
        output_dir=boardroom_dir,
        dashboard_dir=dashboard_dir,
    )
    report = pack["report"]
    paths = pack["paths"]
    partner_summary = paths.get("partner_summary")
    required_paths = [
        Path(paths["boardroom_report"]),
        Path(paths["markdown"]),
        Path(paths["html"]),
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    if not partner_summary or not Path(partner_summary).exists():
        missing.append("partner_summary")
    status = "pass" if (
        pack["status"] == "pass"
        and lab_pack["status"] == "pass"
        and pack["mode"] == "producer_network"
        and report["summary"]["properties"] == 120
        and report["summary"]["partners"] == 10
        and len(report["partner_rows"]) == 10
        and report["intelligence_lab"]["status"] == "ready"
        and report["intelligence_lab"]["family_count"] == 4
        and not missing
    ) else "fail"
    return _gate(
        "boardroom_report_smoke",
        status,
        output=paths["boardroom_report"],
        markdown=paths["markdown"],
        html=paths["html"],
        partner_summary=paths.get("partner_summary"),
        intelligence_lab=lab_pack["paths"]["pack"],
        intelligence_lab_markdown=lab_pack["paths"]["report"],
        intelligence_lab_status=lab_pack["status"],
        intelligence_lab_family_count=report.get("intelligence_lab", {}).get("family_count"),
        intelligence_lab_scope_leakage=report.get("intelligence_lab", {}).get("scope_leakage_count"),
        intelligence_lab_forbidden_claims=report.get("intelligence_lab", {}).get("forbidden_claim_count"),
        report_status=pack["status"],
        mode=pack["mode"],
        summary=report["summary"],
        partner_rows=len(report["partner_rows"]),
        missing=missing,
    )


def _build_partner_cutdown_smoke(out_dir: Path) -> dict[str, Any]:
    cutdown_dir = out_dir / "partner_cutdown_smoke"
    payload = build_daw_demo_payload(property_count=120)
    pack = build_partner_cutdown_pack(
        payload=payload,
        out_dir=cutdown_dir,
        tenant_name="DAW Belgium Readiness Network",
        tenant_slug="daw-belgium-readiness-network",
        modules=["facadepilot"],
        include_xlsx=False,
        include_zip=False,
    )
    summary = pack["summary"]
    failed = [row for row in pack["partners"] if row["status"] != "pass"]
    status = "pass" if (
        pack["status"] == "pass"
        and summary["partners"] == 10
        and summary["properties"] == 120
        and summary["failed_partners"] == 0
        and not failed
    ) else "fail"
    return _gate(
        "partner_cutdown_smoke",
        status,
        output=pack["paths"]["manifest"],
        cutdown_status=pack["status"],
        summary=summary,
        failed_partners=len(failed),
        sample_partner=pack["partners"][0] if pack["partners"] else None,
    )


def _build_customer_brief_smoke(out_dir: Path) -> dict[str, Any]:
    brief_dir = out_dir / "customer_brief_smoke"
    brief_dir.mkdir(parents=True, exist_ok=True)
    payload = build_module_payload(
        tenant_slug="readiness-brief-window",
        module_key="windowpilot",
        campaign_key="readiness-brief-window",
        address="Readiness Brieflaan 1",
        city="Leuven",
        lat=50.880,
        lon=4.702,
        score=94,
    )
    snapshot = build_dashboard_snapshot(
        payload,
        tenant_name="Readiness Brief Customer",
        tenant_slug="readiness-brief-window",
        enabled_modules=["windowpilot"],
    )
    pack = build_customer_brief_pack(brief_dir, snapshot=snapshot)
    brief = pack["brief"]
    return _gate(
        "customer_brief_smoke",
        "pass" if pack["status"] == "pass" and brief["scorecard"]["property_count"] == 1 else "fail",
        output=pack["paths"]["customer_brief"],
        markdown=pack["paths"]["markdown"],
        brief_status=pack["status"],
        scorecard=brief["scorecard"],
        issues=len(brief["issues"]),
    )


def _build_campaign_learning_smoke(out_dir: Path) -> dict[str, Any]:
    learning_dir = out_dir / "campaign_learning_smoke"
    learning_dir.mkdir(parents=True, exist_ok=True)
    payload = build_module_payload(
        tenant_slug="readiness-learning-window",
        module_key="windowpilot",
        campaign_key="readiness-learning-window",
        address="Readiness Learninglaan 1",
        city="Leuven",
        lat=50.886,
        lon=4.708,
        score=95,
    )
    snapshot = build_dashboard_snapshot(
        payload,
        tenant_name="Readiness Learning Customer",
        tenant_slug="readiness-learning-window",
        enabled_modules=["windowpilot"],
    )
    pack = build_campaign_learning_pack(learning_dir, snapshot=snapshot)
    report = pack["report"]
    return _gate(
        "campaign_learning_smoke",
        "pass" if pack["status"] == "pass" and report["funnel"]["properties"] == 1 else "fail",
        output=pack["paths"]["campaign_learning"],
        markdown=pack["paths"]["markdown"],
        learning_status=pack["status"],
        funnel=report["funnel"],
        experiments=len(report["experiment_backlog"]),
        issues=len(report["issues"]),
    )


def _build_territory_plan_smoke(out_dir: Path) -> dict[str, Any]:
    territory_dir = out_dir / "territory_plan_smoke"
    territory_dir.mkdir(parents=True, exist_ok=True)
    payload = build_module_payload(
        tenant_slug="readiness-territory-window",
        module_key="windowpilot",
        campaign_key="readiness-territory-window",
        address="Readiness Territoriumlaan 1",
        city="Leuven",
        lat=50.887,
        lon=4.709,
        score=96,
    )
    snapshot = build_dashboard_snapshot(
        payload,
        tenant_name="Readiness Territory Customer",
        tenant_slug="readiness-territory-window",
        enabled_modules=["windowpilot"],
    )
    pack = build_territory_plan_pack(territory_dir, snapshot=snapshot)
    plan = pack["plan"]
    return _gate(
        "territory_plan_smoke",
        "pass" if pack["status"] == "pass" and plan["market_overview"]["properties"] == 1 else "fail",
        output=pack["paths"]["territory_plan"],
        markdown=pack["paths"]["markdown"],
        territory_status=pack["status"],
        overview=plan["market_overview"],
        territories=len(plan["territory_cells"]),
        issues=len(plan["issues"]),
    )


def _build_roi_forecast_smoke(out_dir: Path) -> dict[str, Any]:
    roi_dir = out_dir / "roi_forecast_smoke"
    roi_dir.mkdir(parents=True, exist_ok=True)
    payload = build_module_payload(
        tenant_slug="readiness-roi-window",
        module_key="windowpilot",
        campaign_key="readiness-roi-window",
        address="Readiness Rendementlaan 1",
        city="Leuven",
        lat=50.888,
        lon=4.710,
        score=97,
    )
    snapshot = build_dashboard_snapshot(
        payload,
        tenant_name="Readiness ROI Customer",
        tenant_slug="readiness-roi-window",
        enabled_modules=["windowpilot"],
    )
    pack = build_roi_forecast_pack(roi_dir, snapshot=snapshot)
    report = pack["report"]
    return _gate(
        "roi_forecast_smoke",
        "pass" if pack["status"] == "pass" and report["business_case"]["properties"] == 1 else "fail",
        output=pack["paths"]["roi_forecast"],
        markdown=pack["paths"]["markdown"],
        roi_status=pack["status"],
        business_case=report["business_case"],
        scenarios=len(report["scenario_forecast"]),
        issues=len(report["issues"]),
    )


def _build_opportunity_dossier_smoke(out_dir: Path) -> dict[str, Any]:
    dossier_dir = out_dir / "opportunity_dossier_smoke"
    dossier_dir.mkdir(parents=True, exist_ok=True)
    payload = build_module_payload(
        tenant_slug="readiness-dossier-window",
        module_key="windowpilot",
        campaign_key="readiness-dossier-window",
        address="Readiness Dossierlaan 1",
        city="Leuven",
        lat=50.889,
        lon=4.711,
        score=98,
    )
    snapshot = build_dashboard_snapshot(
        payload,
        tenant_name="Readiness Dossier Customer",
        tenant_slug="readiness-dossier-window",
        enabled_modules=["windowpilot"],
    )
    pack = build_opportunity_dossier_pack(dossier_dir, snapshot=snapshot)
    report = pack["report"]
    return _gate(
        "opportunity_dossier_smoke",
        "pass" if pack["status"] == "pass" and report["summary"]["dossiers"] == 1 else "fail",
        output=pack["paths"]["opportunity_dossier"],
        markdown=pack["paths"]["markdown"],
        dossier_status=pack["status"],
        summary=report["summary"],
        issues=len(report["issues"]),
    )


def _build_source_ledger_smoke(out_dir: Path) -> dict[str, Any]:
    ledger_dir = out_dir / "source_ledger_smoke"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    payload = build_module_payload(
        tenant_slug="readiness-ledger-window",
        module_key="windowpilot",
        campaign_key="readiness-ledger-window",
        address="Readiness Bronlaan 1",
        city="Leuven",
        lat=50.890,
        lon=4.712,
        score=96,
    )
    payload["campaign_targets"][0]["metadata"].update({
        "contact_basis": "legitimate_interest_reviewed",
        "source_provenance": "Synthetic readiness fixture; no live outreach",
        "contact_channel": "direct_mail",
        "opt_out_method": "Reply using customer suppression workflow",
        "lead_claim": "renovation opportunity based on visible property signals",
    })
    pack = build_source_ledger_pack(ledger_dir, payload=payload)
    report = pack["report"]
    status = "pass" if pack["status"] == "pass" and report["summary"]["evidence_references"] >= 1 else "fail"
    return _gate(
        "source_ledger_smoke",
        status,
        output=pack["paths"]["source_ledger"],
        markdown=pack["paths"]["markdown"],
        source_ledger_status=pack["status"],
        review_status=report["review_status"],
        summary=report["summary"],
        gaps=len(report["review_gaps"]),
        failures=len(report["failures"]),
    )


def _build_retention_smoke(out_dir: Path) -> dict[str, Any]:
    retention_dir = out_dir / "retention_smoke"
    retention_dir.mkdir(parents=True, exist_ok=True)
    payload = build_module_payload(
        tenant_slug="readiness-retention-window",
        module_key="windowpilot",
        campaign_key="readiness-retention-window",
        address="Readiness Retentiedreef 1",
        city="Leuven",
        lat=50.883,
        lon=4.705,
        score=90,
    )
    payload["campaigns"][0]["message_variant"] = "readiness_retention"
    payload["campaign_targets"][0]["metadata"].update({
        "contact_basis": "legitimate_interest_reviewed",
        "source_provenance": "Synthetic readiness fixture; no live outreach",
        "contact_channel": "direct_mail",
        "opt_out_method": "Reply using customer suppression workflow",
        "retention_review_at": "2026-12-31",
        "delete_after": "2027-12-31",
        "lead_claim": "renovation opportunity based on visible property signals",
    })
    payload_path = retention_dir / "payload.json"
    _write_payload(payload_path, payload)
    report = build_retention_report(payload, as_of="2026-06-19")
    report_path = retention_dir / "retention_report.json"
    write_retention_json(report_path, report)
    return _gate(
        "retention_smoke",
        "pass" if report["status"] == "pass" else "fail",
        output=str(report_path),
        retention_status=report["status"],
        metrics=report["metrics"],
        actions=len(report["actions"]),
    )


def _build_audit_trail_smoke(out_dir: Path) -> dict[str, Any]:
    audit_dir = out_dir / "audit_trail_smoke"
    audit_dir.mkdir(parents=True, exist_ok=True)
    tenant_id = "11111111-1111-4111-8111-111111111111"
    manifest = {
        "package_type": "homepilot_customer_package",
        "onboarding_tenants": [{"id": tenant_id, "name": "Readiness Audit Customer"}],
        "modules": ["windowpilot"],
        "summary": {"properties": 1, "modules": {"windowpilot": 1}},
        "paths": {"manifest": "manifest.json", "exports": "exports"},
        "export_log": {
            "id": "22222222-2222-4222-8222-222222222222",
            "tenant_id": tenant_id,
            "module_key": "windowpilot",
            "export_type": "xlsx",
            "row_count": 1,
            "filters": {"modules": ["windowpilot"]},
        },
        "access_audit": {
            "status": "pass",
            "issues": [],
            "enabled_modules": ["windowpilot"],
        },
    }
    events = build_customer_package_audit_events(
        manifest,
        created_at="2026-06-19T00:00:00+00:00",
    )
    events_path = audit_dir / "audit_events.json"
    write_audit_json(events_path, events)
    report = build_audit_trail_report(
        events,
        expected_tenant_id=tenant_id,
        required_event_types=["customer_package_generated", "export_generated", "access_audit_passed"],
    )
    report_path = audit_dir / "audit_trail_report.json"
    write_audit_json(report_path, report)
    return _gate(
        "audit_trail_smoke",
        "pass" if report["status"] == "pass" else "fail",
        output=str(report_path),
        events=str(events_path),
        audit_trail_status=report["status"],
        metrics=report["metrics"],
        issues=len(report["issues"]),
    )


def _build_benchmark_smoke(out_dir: Path) -> dict[str, Any]:
    benchmark_dir = out_dir / "benchmark_privacy_smoke"
    benchmark_dir.mkdir(parents=True, exist_ok=True)
    payloads = []
    for index in range(10):
        payloads.append(build_module_payload(
            tenant_slug=f"readiness-benchmark-window-{index}",
            module_key="windowpilot",
            campaign_key=f"readiness-benchmark-window-{index}",
            address=f"Readiness Benchmarklaan {index}",
            city="Leuven",
            lat=50.80 + index / 1000,
            lon=4.70,
            score=80 + index,
        ))
    rows = build_benchmark_rows(payloads, min_sample_size=10, computed_at="2026-06-19T00:00:00+00:00")
    benchmark_path = benchmark_dir / "benchmarks.json"
    write_benchmark_json(benchmark_path, {"benchmarks": rows, "count": len(rows)})
    body = json.dumps(rows, ensure_ascii=False)
    leaks = {
        "tenant_id": "tenant_id" in body,
        "property_id": "property_id" in body,
        "address": "Readiness Benchmarklaan" in body,
    }
    status = "pass" if len(rows) == 1 and rows[0]["sample_size"] == 10 and not any(leaks.values()) else "fail"
    return _gate(
        "benchmark_privacy_smoke",
        status,
        output=str(benchmark_path),
        benchmark_count=len(rows),
        sample_size=rows[0]["sample_size"] if rows else 0,
        leaks=leaks,
    )


def _build_visual_intelligence_smoke(out_dir: Path) -> dict[str, Any]:
    visual_dir = out_dir / "visual_intelligence_smoke"
    pack = build_visual_intelligence_pack(
        visual_dir,
        snapshot=build_visual_scale_fixture(property_count=180),
        release_label="readiness-local",
    )
    visual = pack["visual"]
    status = "pass" if (
        pack["status"] == "pass"
        and visual["map"]["strategy"] == "clustered_map"
        and visual["graph"]["strategy"] == "budgeted_graph"
        and visual["secret_scan"]["status"] == "pass"
    ) else "fail"
    return _gate(
        "visual_intelligence_smoke",
        status,
        output=pack["paths"]["visual_intelligence"],
        runbook=pack["paths"]["runbook"],
        map_clusters=pack["paths"]["map_clusters"],
        visual_status=pack["status"],
        map_strategy=visual["map"]["strategy"],
        graph_strategy=visual["graph"]["strategy"],
        property_count=visual["map"]["property_count"],
        cluster_count=len(visual["map"]["clusters"]),
        graph_source_nodes=visual["graph"]["source_nodes"],
        graph_render_nodes=visual["graph"]["render_nodes"],
        secret_scan=visual["secret_scan"]["status"],
        warnings=len(visual["warnings"]),
    )


def _build_monitoring_smoke(out_dir: Path, gates: list[dict[str, Any]]) -> dict[str, Any]:
    monitoring_dir = out_dir / "monitoring_smoke"
    draft = {
        "report_type": "homepilot_enterprise_readiness_pack",
        "created_at": utc_now(),
        "status": "pass" if not any(gate["status"] == "fail" for gate in gates) else "fail",
        "production_verified": False,
        "gates": gates,
    }
    pack = build_monitoring_pack(monitoring_dir, readiness=draft, release_label="readiness-local")
    plan = pack["plan"]
    status = "pass" if (
        pack["status"] in {"buyer_review_monitoring_ready", "production_monitoring_ready"}
        and plan["secret_scan"]["status"] == "pass"
    ) else "fail"
    return _gate(
        "monitoring_smoke",
        status,
        output=pack["paths"]["monitoring_plan"],
        runbook=pack["paths"]["runbook"],
        alert_matrix=pack["paths"]["alert_matrix"],
        monitoring_status=pack["status"],
        production_gate=plan["production_gate"],
        summary=plan["summary"],
        watches=len(plan["watches"]),
        secret_scan=plan["secret_scan"]["status"],
    )


def build_readiness_pack(out_dir: Path, run_qa: bool = False) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    gates: list[dict[str, Any]] = []
    if run_qa:
        gates.append(_run_qa(out_dir))
    else:
        gates.append(_gate("local_qa", "skipped", reason="Run with --run-qa to include QA output."))
    gates.append(_build_deployment_smoke(out_dir))
    gates.append(_build_schema_verification_smoke(out_dir))
    gates.append(_build_launch_dry_run(out_dir))
    gates.append(_build_account_access_smoke(out_dir))
    gates.append(_build_customer_access_verification_smoke(out_dir))
    gates.append(_build_live_readiness_smoke(out_dir))
    gates.append(_build_live_launch_request_smoke(out_dir))
    gates.append(_build_customer_package_smoke(out_dir))
    gates.append(_build_customer_portal_smoke(out_dir))
    gates.append(_build_portal_hosting_smoke(out_dir))
    gates.append(_build_sales_integration_smoke(out_dir))
    gates.append(_build_sales_integration_sync_smoke(out_dir))
    gates.append(_build_data_vendor_enrichment_smoke(out_dir))
    gates.append(_build_data_vendor_refresh_smoke(out_dir))
    gates.append(_build_enterprise_demo_room_smoke(out_dir))
    gates.append(_build_boardroom_report_smoke(out_dir))
    gates.append(_build_partner_cutdown_smoke(out_dir))
    gates.append(_build_customer_brief_smoke(out_dir))
    gates.append(_build_campaign_learning_smoke(out_dir))
    gates.append(_build_territory_plan_smoke(out_dir))
    gates.append(_build_roi_forecast_smoke(out_dir))
    gates.append(_build_opportunity_dossier_smoke(out_dir))
    gates.append(_build_source_ledger_smoke(out_dir))
    gates.append(_build_audit_trail_smoke(out_dir))
    gates.append(_build_recovery_smoke(out_dir))
    gates.append(_build_api_contract_smoke(out_dir))
    gates.append(_build_processing_register_smoke(out_dir))
    gates.append(_build_data_dictionary_smoke(out_dir))
    gates.append(_build_data_quality_smoke(out_dir))
    gates.append(_build_compliance_smoke(out_dir))
    gates.append(_build_retention_smoke(out_dir))
    gates.append(_build_benchmark_smoke(out_dir))
    gates.append(_build_visual_intelligence_smoke(out_dir))
    gates.append(_build_monitoring_smoke(out_dir, gates))

    hard_failures = [gate for gate in gates if gate["status"] == "fail"]
    report = {
        "report_type": "homepilot_enterprise_readiness_pack",
        "created_at": utc_now(),
        "status": "pass" if not hard_failures else "fail",
        "production_verified": False,
        "production_verification_required": "Run platform/homepilot_live_readiness.py, platform/homepilot_live_schema_verification.py --live, platform/homepilot_launch.py rls-fixture live, and platform/homepilot_customer_access_verification.py live; require production_verified=true for schema, launch, and customer access.",
        "gates": gates,
        "paths": {
            "readiness_report": str(out_dir / "readiness_report.json"),
            "deployment_smoke": str(out_dir / "deployment_smoke"),
            "schema_verification_smoke": str(out_dir / "schema_verification_smoke"),
            "launch_dry_run": str(out_dir / "launch_dry_run"),
            "account_access_smoke": str(out_dir / "account_access_smoke"),
            "customer_access_verification_smoke": str(out_dir / "customer_access_verification_smoke"),
            "live_readiness_smoke": str(out_dir / "live_readiness_smoke"),
            "live_launch_request_smoke": str(out_dir / "live_launch_request_smoke"),
            "customer_package_smoke": str(out_dir / "customer_package_smoke"),
            "customer_portal_smoke": str(out_dir / "customer_portal_smoke"),
            "portal_hosting_smoke": str(out_dir / "portal_hosting_smoke"),
            "sales_integration_smoke": str(out_dir / "sales_integration_smoke"),
            "sales_integration_sync_smoke": str(out_dir / "sales_integration_sync_smoke"),
            "data_vendor_enrichment_smoke": str(out_dir / "data_vendor_enrichment_smoke"),
            "data_vendor_refresh_smoke": str(out_dir / "data_vendor_refresh_smoke"),
            "enterprise_demo_room_smoke": str(out_dir / "enterprise_demo_room_smoke"),
            "boardroom_report_smoke": str(out_dir / "boardroom_report_smoke"),
            "partner_cutdown_smoke": str(out_dir / "partner_cutdown_smoke"),
            "customer_brief_smoke": str(out_dir / "customer_brief_smoke"),
            "campaign_learning_smoke": str(out_dir / "campaign_learning_smoke"),
            "territory_plan_smoke": str(out_dir / "territory_plan_smoke"),
            "roi_forecast_smoke": str(out_dir / "roi_forecast_smoke"),
            "opportunity_dossier_smoke": str(out_dir / "opportunity_dossier_smoke"),
            "source_ledger_smoke": str(out_dir / "source_ledger_smoke"),
            "audit_trail_smoke": str(out_dir / "audit_trail_smoke"),
            "recovery_smoke": str(out_dir / "recovery_smoke"),
            "api_contract_smoke": str(out_dir / "api_contract_smoke"),
            "processing_register_smoke": str(out_dir / "processing_register_smoke"),
            "data_dictionary_smoke": str(out_dir / "data_dictionary_smoke"),
            "data_quality_smoke": str(out_dir / "data_quality_smoke"),
            "compliance_smoke": str(out_dir / "compliance_smoke"),
            "retention_smoke": str(out_dir / "retention_smoke"),
            "benchmark_privacy_smoke": str(out_dir / "benchmark_privacy_smoke"),
            "visual_intelligence_smoke": str(out_dir / "visual_intelligence_smoke"),
            "monitoring_smoke": str(out_dir / "monitoring_smoke"),
        },
    }
    write_json(out_dir / "readiness_report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot enterprise readiness evidence pack")
    sub = parser.add_subparsers(dest="cmd", required=True)

    build = sub.add_parser("build", help="Build local readiness evidence")
    build.add_argument("--out-dir", required=True, type=Path)
    build.add_argument("--run-qa", action="store_true")
    args = parser.parse_args()

    if args.cmd == "build":
        report = build_readiness_pack(args.out_dir, run_qa=args.run_qa)
        print(json.dumps({
            "output": str(args.out_dir),
            "status": report["status"],
            "production_verified": report["production_verified"],
            "report": report["paths"]["readiness_report"],
            "gates": {gate["name"]: gate["status"] for gate in report["gates"]},
        }, indent=2, ensure_ascii=False))
        if report["status"] == "fail":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
