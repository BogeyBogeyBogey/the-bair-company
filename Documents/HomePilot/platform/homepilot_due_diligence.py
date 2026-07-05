#!/usr/bin/env python3
"""
Build a buyer/security due-diligence pack for HomePilot.

The readiness pack proves local gates. This module packages that proof into a
reviewable data room for enterprise buyers without copying raw customer data:
gate status, access matrices, source hashes, redaction scan, and a concise
executive summary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from homepilot_api_contract import build_api_contract_pack
from homepilot_data_dictionary import build_data_dictionary_pack
from homepilot_metric_access import build_product_access_matrix
from homepilot_platform import PILOT_MODULES
from homepilot_processing_register import build_processing_register_pack
from homepilot_readiness import build_readiness_pack


HERE = Path(__file__).parent.resolve()
HOME_ROOT = HERE.parent

CRITICAL_SOURCE_FILES = (
    "README.md",
    ".env.example",
    "platform/ARCHITECTURE.md",
    "platform/IMPORTING.md",
    "platform/DASHBOARD.md",
    "platform/PRODUCTION_READINESS.md",
    "platform/PRODUCTION_LAUNCH.md",
    "platform/MARKET_RESEARCH.md",
    "platform/homepilot_account_access.py",
    "platform/homepilot_customer_access_verification.py",
    "platform/homepilot_api_contract.py",
    "platform/homepilot_campaign_learning.py",
    "platform/homepilot_customer_brief.py",
    "platform/homepilot_territory_plan.py",
    "platform/homepilot_visual_intelligence.py",
    "platform/homepilot_processing_register.py",
    "platform/homepilot_platform.py",
    "platform/homepilot_preflight.py",
    "platform/homepilot_production_proof.py",
    "platform/homepilot_live_launch_request.py",
    "platform/homepilot_portal.py",
    "platform/homepilot_hosting.py",
    "platform/homepilot_release_pack.py",
    "platform/homepilot_recovery.py",
    "platform/homepilot_roi_forecast.py",
    "platform/homepilot_entitlements.py",
    "platform/homepilot_metric_access.py",
    "platform/homepilot_market_readiness.py",
    "platform/homepilot_access_audit.py",
    "platform/homepilot_audit_trail.py",
    "platform/homepilot_compliance.py",
    "platform/homepilot_data_quality.py",
    "platform/homepilot_deployment.py",
    "platform/homepilot_sql_apply_plan.py",
    "platform/homepilot_demo_room.py",
    "platform/homepilot_enrichment.py",
    "platform/homepilot_enrichment_refresh.py",
    "platform/homepilot_integrations.py",
    "platform/homepilot_integration_sync.py",
    "platform/homepilot_opportunity_dossier.py",
    "platform/homepilot_retention.py",
    "platform/homepilot_benchmarks.py",
    "platform/homepilot_customer_package.py",
    "platform/homepilot_data_dictionary.py",
    "platform/homepilot_source_ledger.py",
    "platform/homepilot_readiness.py",
    "platform/homepilot_launch.py",
    "platform/homepilot_monitoring.py",
    "platform/homepilot_ops_status.py",
    "platform/homepilot_rls_probe.py",
    "platform/supabase_schema.sql",
    "platform/dashboard_views.sql",
    "client/index.html",
    "client/app.js",
    "client/styles.css",
    "client/sample-data.js",
    "client/live-config.js",
    "client/live-data.js",
)

SENSITIVE_PATTERNS = {
    "supabase_service_key": re.compile(r"HOMEPILOT_SUPABASE_SERVICE_KEY\s*=\s*['\"][^'\"]+['\"]", re.IGNORECASE),
    "jwt_like_token": re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "secret_prompt": re.compile(r"secret prompt|private raw features", re.IGNORECASE),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_source_manifest() -> dict[str, Any]:
    files = []
    missing = []
    for rel_path in CRITICAL_SOURCE_FILES:
        path = HOME_ROOT / rel_path
        if not path.exists():
            missing.append(rel_path)
            continue
        files.append({
            "path": rel_path,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    return {
        "report_type": "homepilot_source_manifest",
        "created_at": utc_now(),
        "root": str(HOME_ROOT),
        "file_count": len(files),
        "missing": missing,
        "files": files,
    }


def summarize_readiness(readiness: dict[str, Any]) -> dict[str, Any]:
    gates = readiness.get("gates", [])
    return {
        "status": readiness.get("status", "unknown"),
        "production_verified": bool(readiness.get("production_verified")),
        "gate_count": len(gates),
        "gates": [
            {
                "name": gate.get("name"),
                "status": gate.get("status"),
                "output": gate.get("output") or gate.get("manifest") or gate.get("launch_report"),
            }
            for gate in gates
        ],
        "production_verification_required": readiness.get("production_verification_required", ""),
    }


def scan_generated_files(paths: list[Path]) -> dict[str, Any]:
    issues = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for label, pattern in SENSITIVE_PATTERNS.items():
                if pattern.search(line):
                    issues.append({
                        "file": str(path),
                        "line": line_number,
                        "pattern": label,
                    })
    return {
        "report_type": "homepilot_due_diligence_redaction_scan",
        "created_at": utc_now(),
        "status": "pass" if not issues else "fail",
        "files_scanned": [str(path) for path in paths if path.exists()],
        "issues": issues,
    }


def _status_from(readiness: dict[str, Any], redaction: dict[str, Any]) -> str:
    if redaction.get("status") != "pass":
        return "action_required"
    if readiness.get("status") != "pass":
        return "action_required"
    if readiness.get("production_verified"):
        return "production_ready"
    return "local_ready"


def render_markdown_report(report: dict[str, Any]) -> str:
    readiness = report["readiness"]
    lines = [
        "# HomePilot Enterprise Due-Diligence Pack",
        "",
        f"Created: {report['created_at']}",
        f"Status: {report['status']}",
        f"Production verified: {str(readiness['production_verified']).lower()}",
        "",
        "## Executive Summary",
        "",
        "HomePilot is the shared property intelligence platform for renovation opportunities across FacadePilot, WindowPilot, RoofPilot, GardenPilot, PoolPilot, PorchPilot, DrivewayPilot, and future pilots.",
        "",
        "The local evidence pack proves tenant/module scoping, account access planning, customer access verification setup, customer package and portal generation, enterprise demo-room readiness, CRM/webhook integration handoff and sync dry-run readiness, data vendor/enrichment backlog readiness, source/provenance ledger coverage, data dictionary, API contract and data processing register coverage, data quality, compliance metadata, retention lifecycle controls, audit trail evidence, deployment manifests, import recovery packs, metric visibility, and aggregate benchmark privacy. Production access still requires live Supabase RLS probes with real customer-authenticated JWTs.",
        "",
        "## Gate Summary",
        "",
    ]
    for gate in readiness["gates"]:
        lines.append(f"- {gate['name']}: {gate['status']}")
    lines += [
        "",
        "## Customer Access Model",
        "",
        "- Every customer belongs to one tenant.",
        "- Every paid product is represented as an enabled module.",
        "- Customer surfaces are filtered by tenant, module, and metric visibility.",
        "- Unknown metrics are hidden from customer dashboards and exports by default.",
        "- Cross-customer learnings are aggregate-only and thresholded.",
        "",
        "## Remaining Production Gate",
        "",
        readiness["production_verification_required"] or "Run the live launch/RLS probe before production rollout.",
        "",
        "## Files",
        "",
    ]
    for label, path in report["paths"].items():
        lines.append(f"- {label}: {path}")
    lines.append("")
    return "\n".join(lines)


def _normalize_modules(modules: list[str] | None) -> list[str]:
    if not modules:
        return list(PILOT_MODULES)
    unknown = sorted(set(modules) - set(PILOT_MODULES))
    if unknown:
        raise ValueError(f"Unknown module(s): {unknown}")
    return [module for module in PILOT_MODULES if module in set(modules)]


def build_due_diligence_pack(
    out_dir: Path,
    readiness_report_path: Path | None = None,
    modules: list[str] | None = None,
    role: str = "viewer",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = out_dir / "evidence"
    matrices_dir = out_dir / "access_matrices"
    dictionary_dir = evidence_dir / "data_dictionary"
    api_dir = evidence_dir / "api_contract"
    processing_dir = evidence_dir / "processing_register"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    matrices_dir.mkdir(parents=True, exist_ok=True)

    if readiness_report_path:
        readiness = load_json(readiness_report_path)
    else:
        readiness = build_readiness_pack(out_dir / "readiness", run_qa=False)
        readiness_report_path = Path(readiness["paths"]["readiness_report"])

    readiness_copy = evidence_dir / "readiness_report.json"
    shutil.copy2(readiness_report_path, readiness_copy)

    selected_modules = _normalize_modules(modules)
    access_matrix_paths: dict[str, str] = {}
    for surface in ("dashboard", "export", "benchmark"):
        matrix = build_product_access_matrix(selected_modules, role=role, surface=surface)
        matrix_path = matrices_dir / f"{surface}_access_matrix.json"
        write_json(matrix_path, matrix)
        access_matrix_paths[surface] = str(matrix_path)

    source_manifest = build_source_manifest()
    source_manifest_path = evidence_dir / "source_manifest.json"
    write_json(source_manifest_path, source_manifest)

    dictionary_pack = build_data_dictionary_pack(dictionary_dir, modules=selected_modules)
    api_contract_pack = build_api_contract_pack(api_dir, modules=selected_modules)
    processing_pack = build_processing_register_pack(processing_dir, modules=selected_modules)

    report = {
        "report_type": "homepilot_enterprise_due_diligence_pack",
        "created_at": utc_now(),
        "status": "building",
        "modules": selected_modules,
        "role": role,
        "readiness": summarize_readiness(readiness),
        "production_gate": {
            "verified": bool(readiness.get("production_verified")),
            "required": readiness.get("production_verification_required", "Run live RLS probe before production rollout."),
        },
        "customer_claims": [
            "One shared HomePilot database with tenant isolation.",
            "Pilot modules are entitlement-scoped per customer.",
            "Account access plans document invitees, roles, permissions, membership SQL, and revocation SQL before live customer access.",
            "Customer access verification converts planned invitees into redacted RLS probe identities and requires live proof before production access.",
            "Dashboard/export metrics are filtered by product visibility.",
            "The data dictionary documents every customer-facing module, metric, export sheet, table, and dashboard view used in enterprise handoffs.",
            "The API contract documents customer-safe Supabase read models, headers, filters, permissions, and RLS guarantees.",
            "Customer packages include a campaign learning report that converts responses and no-responses into a tenant-scoped experiment backlog.",
            "Customer packages include a boardroom-ready customer intelligence brief generated from the same tenant/module-scoped dashboard snapshot.",
            "Customer packages include a territory plan for the next campaign batch, prioritized by segment, module, score density, and visible pipeline value.",
            "Customer packages include a transparent ROI forecast with explicit assumptions, scenario outcomes, and capacity needs.",
            "Customer packages include opportunity dossiers explaining why top properties are prioritized, with evidence, metric drivers, review gaps, and next actions.",
            "Customer packages include a source ledger showing evidence coverage, source runs, confidence, timestamps, provenance gaps, and customer-safe guardrails.",
            "Customer portal bundles package the dashboard, tenant exports, live Auth/RLS runtime config, route map, security headers, and secret-scan evidence for online deployment review.",
            "Portal hosting packs document asset hashes, cache policy, provider configs, deployment checklist, rollback manifest, production blockers, and private-access guardrails for hosted customer portals.",
            "Enterprise demo rooms package the all-module synthetic showroom, customer package, portal bundle, CRM handoff, enrichment plan, data dictionary, exports, and audit evidence from one canonical payload.",
            "CRM/webhook integration packs provide sales import CSV, webhook JSONL payloads, provider field mappings, idempotency/retry rules, and secret-scan evidence.",
            "CRM/webhook sync packs dry-run or execute webhook delivery with env-only credentials, idempotency keys, retry accounting, dead-letter output, and secret-safe delivery reports.",
            "Data vendor/enrichment plans document parcel, geocode, imagery, energy, permit, pricing, and contact-provenance source coverage plus a per-property backlog.",
            "Data vendor refresh packs turn enrichment backlog into idempotent dry-run or live vendor/API jobs with env-only credentials, retry accounting, dead-letter output, and secret-safe reports.",
            "Visual intelligence packs prove clustered map readiness and second-brain graph render budgets for large territory reviews.",
            "Monitoring packs define customer-safe alert ownership, cadence, source gates, production blockers, and remediation for access, portal, CRM delivery, data quality, compliance, exports, and benchmark privacy.",
            "The data processing register documents processing purposes, data categories, privacy controls, retention workflows, and residual risks.",
            "Customer packages include an audit trail for package generation, exports, and access-audit outcomes.",
            "Recovery packs provide backup manifests, tenant-guarded rollback SQL, and operator runbooks for imports.",
            "Schema deployment manifests pin SQL apply order, checksums, and post-apply verification steps.",
            "Outreach records require provenance, contact basis, opt-out handling, safe opportunity language, and retention lifecycle metadata.",
            "Cross-customer benchmarks are aggregate-only and require minimum cohort thresholds.",
        ],
        "paths": {
            "readiness_report": str(readiness_copy),
            "source_manifest": str(source_manifest_path),
            "data_dictionary": dictionary_pack["paths"]["data_dictionary"],
            "data_dictionary_markdown": dictionary_pack["paths"]["markdown"],
            "api_contract": api_contract_pack["paths"]["api_contract"],
            "api_contract_markdown": api_contract_pack["paths"]["markdown"],
            "processing_register": processing_pack["paths"]["processing_register"],
            "processing_register_markdown": processing_pack["paths"]["markdown"],
            "dashboard_access_matrix": access_matrix_paths["dashboard"],
            "export_access_matrix": access_matrix_paths["export"],
            "benchmark_access_matrix": access_matrix_paths["benchmark"],
            "redaction_report": str(evidence_dir / "redaction_report.json"),
            "executive_summary": str(out_dir / "executive_summary.md"),
            "due_diligence_report": str(out_dir / "due_diligence_report.json"),
        },
        "source_manifest_summary": {
            "file_count": source_manifest["file_count"],
            "missing": source_manifest["missing"],
        },
    }

    report_path = out_dir / "due_diligence_report.json"
    summary_path = out_dir / "executive_summary.md"
    write_json(report_path, report)
    summary_path.write_text(render_markdown_report(report), encoding="utf-8")

    scan_paths = [
        report_path,
        summary_path,
        readiness_copy,
        source_manifest_path,
        Path(dictionary_pack["paths"]["data_dictionary"]),
        Path(dictionary_pack["paths"]["markdown"]),
        Path(api_contract_pack["paths"]["api_contract"]),
        Path(api_contract_pack["paths"]["markdown"]),
        Path(processing_pack["paths"]["processing_register"]),
        Path(processing_pack["paths"]["markdown"]),
        *(Path(path) for path in access_matrix_paths.values()),
    ]
    redaction = scan_generated_files(scan_paths)
    redaction_path = evidence_dir / "redaction_report.json"
    write_json(redaction_path, redaction)

    report["redaction"] = {
        "status": redaction["status"],
        "issue_count": len(redaction["issues"]),
    }
    report["status"] = _status_from(readiness, redaction)
    write_json(report_path, report)
    summary_path.write_text(render_markdown_report(report), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HomePilot enterprise due-diligence pack")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--readiness-report", type=Path)
    parser.add_argument("--module", dest="modules", action="append", default=None)
    parser.add_argument("--role", default="viewer")
    args = parser.parse_args()

    report = build_due_diligence_pack(
        out_dir=args.out_dir,
        readiness_report_path=args.readiness_report,
        modules=args.modules,
        role=args.role,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": report["status"],
        "production_verified": report["production_gate"]["verified"],
        "report": report["paths"]["due_diligence_report"],
        "summary": report["paths"]["executive_summary"],
        "redaction": report.get("redaction", {}),
    }, indent=2, ensure_ascii=False))
    if report["status"] == "action_required":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
