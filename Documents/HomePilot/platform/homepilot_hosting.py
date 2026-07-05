#!/usr/bin/env python3
"""
Build HomePilot portal hosting evidence.

Portal bundles contain tenant-scoped customer data and live Auth/RLS runtime
scaffolding. This module turns a portal bundle into a hosting review pack:
asset hashes, cache policy, provider configs, rollback manifest, deployment
checklist, and production blockers. It does not deploy or write secrets.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PORTAL_URL_ENV = "HOMEPILOT_PORTAL_URL"
SECRET_PATTERNS = {
    "service_role_key": re.compile(r"service[-_ ]?role[-_ ]?key", re.IGNORECASE),
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _asset_role(relative_path: str) -> str:
    if relative_path == "index.html":
        return "entrypoint"
    if relative_path in {"dashboard-data.js", "live-config.js", "live-data.js"}:
        return "runtime_data"
    if relative_path.startswith("exports/"):
        return "customer_export"
    if relative_path.endswith((".js", ".css")):
        return "static_asset"
    return "asset"


def _cache_header(relative_path: str) -> str:
    role = _asset_role(relative_path)
    if role in {"entrypoint", "runtime_data", "customer_export"}:
        return "no-store"
    return "public, max-age=31536000, immutable"


def build_asset_manifest(public_dir: Path) -> dict[str, Any]:
    assets = []
    for path in sorted(public_dir.rglob("*")):
        if not path.is_file():
            continue
        relative_path = str(path.relative_to(public_dir))
        assets.append({
            "path": relative_path,
            "role": _asset_role(relative_path),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "cache_control": _cache_header(relative_path),
        })
    return {
        "manifest_type": "homepilot_portal_asset_manifest",
        "created_at": utc_now(),
        "public_dir": str(public_dir),
        "asset_count": len(assets),
        "total_bytes": sum(asset["bytes"] for asset in assets),
        "assets": assets,
    }


def build_cache_policy(asset_manifest: dict[str, Any]) -> dict[str, Any]:
    rules = []
    for asset in asset_manifest["assets"]:
        rules.append({
            "path": f"/{asset['path']}",
            "role": asset["role"],
            "cache_control": asset["cache_control"],
        })
    return {
        "policy_type": "homepilot_portal_cache_policy",
        "rules": rules,
        "guardrails": {
            "customer_data_no_store": True,
            "runtime_config_no_store": True,
            "exports_no_store": True,
            "immutable_only_for_static_assets": True,
        },
    }


def render_netlify_toml(cache_policy: dict[str, Any]) -> str:
    lines = [
        "[build]",
        '  publish = "public"',
        "",
    ]
    for rule in cache_policy["rules"]:
        lines += [
            "[[headers]]",
            f'  for = "{rule["path"]}"',
            "  [headers.values]",
            f'    Cache-Control = "{rule["cache_control"]}"',
            "",
        ]
    lines += [
        "[[redirects]]",
        '  from = "/*"',
        '  to = "/index.html"',
        "  status = 200",
        "",
    ]
    return "\n".join(lines)


def render_vercel_json(cache_policy: dict[str, Any]) -> str:
    return json.dumps({
        "cleanUrls": True,
        "trailingSlash": False,
        "headers": [{
            "source": rule["path"],
            "headers": [{"key": "Cache-Control", "value": rule["cache_control"]}],
        } for rule in cache_policy["rules"]],
        "rewrites": [{"source": "/(.*)", "destination": "/index.html"}],
    }, indent=2, ensure_ascii=False) + "\n"


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def deployment_checklist(portal: dict[str, Any], production_url: str) -> list[dict[str, Any]]:
    live_runtime = portal.get("live_runtime", {}) if isinstance(portal.get("live_runtime"), dict) else {}
    return [
        {
            "step": "source_portal_review",
            "status": "pass" if portal.get("status") == "pass" else "fail",
            "owner": "Platform Ops",
            "evidence": portal.get("paths", {}).get("portal_manifest"),
            "detail": "Portal bundle must pass tenant/module scope and secret scan before hosting.",
        },
        {
            "step": "private_access_control",
            "status": "blocked",
            "owner": "Customer Ops",
            "evidence": "",
            "detail": "Tenant-scoped static snapshots require authenticated/private hosting or replacement by live RLS reads before production exposure.",
        },
        {
            "step": "live_runtime_config",
            "status": "ready" if live_runtime.get("status") == "ready_for_customer_auth_config" else "blocked",
            "owner": "Platform Ops",
            "evidence": live_runtime.get("config"),
            "detail": "Configure public Supabase anon key and customer JWT handling only after live RLS proof.",
        },
        {
            "step": "production_url",
            "status": "ready" if production_url else "blocked",
            "owner": "Platform Ops",
            "evidence": production_url,
            "detail": "Record the customer-approved portal URL after hosting provider deployment.",
        },
        {
            "step": "post_deploy_probe",
            "status": "blocked",
            "owner": "Platform Ops",
            "evidence": "",
            "detail": "Run browser smoke, live healthcheck, and customer access verification against the hosted URL.",
        },
    ]


def render_runbook(manifest: dict[str, Any]) -> str:
    lines = [
        "# HomePilot Portal Hosting Runbook",
        "",
        f"Release: {manifest['release_label']}",
        f"Created: {manifest['created_at']}",
        f"Status: {manifest['status']}",
        f"Production verified: {str(manifest['production_gate']['verified']).lower()}",
        "",
        "## Hosting Guardrails",
        "",
        "- Tenant-scoped static snapshots are customer data and must not be exposed on a public unauthenticated URL.",
        "- Browser assets may contain only the public Supabase anon key after live RLS proof; never a privileged Supabase key.",
        "- `dashboard-data.js`, `live-config.js`, `live-data.js`, and exports use `Cache-Control: no-store`.",
        "- Keep `netlify.toml`, `vercel.json`, `_headers`, and `_redirects` with the release evidence.",
        "- Roll back by redeploying the prior asset manifest and portal bundle.",
        "",
        "## Production Blockers",
        "",
    ]
    blockers = manifest["production_gate"]["blockers"]
    lines.extend(f"- {blocker}" for blocker in blockers) if blockers else lines.append("- None.")
    lines += ["", "## Checklist", ""]
    for item in manifest["checklist"]:
        lines.append(f"- {item['step']}: {item['status']} - {item['detail']}")
    lines.append("")
    return "\n".join(lines)


def build_hosting_pack(
    portal_manifest_path: Path,
    out_dir: Path,
    release_label: str = "local",
    production_url: str = "",
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = env if env is not None else os.environ
    portal = load_json(portal_manifest_path)
    public_dir = Path(portal.get("paths", {}).get("public_dir", ""))
    headers_path = Path(portal.get("paths", {}).get("headers", ""))
    redirects_path = Path(portal.get("paths", {}).get("redirects", ""))
    production_url = production_url or env.get(PORTAL_URL_ENV, "")
    out_dir.mkdir(parents=True, exist_ok=True)

    asset_manifest = build_asset_manifest(public_dir) if public_dir.exists() else {
        "manifest_type": "homepilot_portal_asset_manifest",
        "created_at": utc_now(),
        "public_dir": str(public_dir),
        "asset_count": 0,
        "total_bytes": 0,
        "assets": [],
    }
    cache_policy = build_cache_policy(asset_manifest)
    checklist = deployment_checklist(portal, production_url)

    asset_manifest_path = out_dir / "asset_manifest.json"
    cache_policy_path = out_dir / "cache_policy.json"
    netlify_path = out_dir / "netlify.toml"
    vercel_path = out_dir / "vercel.json"
    checklist_path = out_dir / "deployment_checklist.csv"
    rollback_path = out_dir / "rollback_manifest.json"
    hosting_manifest_path = out_dir / "hosting_manifest.json"
    runbook_path = out_dir / "HOSTING_RUNBOOK.md"

    failures: list[str] = []
    warnings: list[str] = []
    if portal.get("status") != "pass":
        failures.append(f"Portal bundle status is {portal.get('status')!r}, expected pass.")
    if not public_dir.exists():
        failures.append(f"Portal public_dir is missing: {public_dir}")
    if not headers_path.exists():
        failures.append(f"Portal headers file is missing: {headers_path}")
    if not redirects_path.exists():
        failures.append(f"Portal redirects file is missing: {redirects_path}")
    if not any(asset["path"] == "dashboard-data.js" for asset in asset_manifest["assets"]):
        warnings.append("No static dashboard-data.js snapshot found; live runtime must provide data.")

    static_snapshot_present = any(asset["path"] == "dashboard-data.js" for asset in asset_manifest["assets"])
    production_blockers = []
    if static_snapshot_present:
        production_blockers.append("Static tenant snapshot present; require private hosting/access control or live RLS-only runtime before public production.")
    if not production_url:
        production_blockers.append(f"Missing customer-approved portal URL in {PORTAL_URL_ENV}.")
    production_blockers.append("Missing hosted browser smoke and customer access verification against production URL.")

    secret_findings = _scan_files([*public_dir.rglob("*")] if public_dir.exists() else [])
    if secret_findings:
        failures.append(f"Secret-like values found in hosted public assets: {secret_findings}")

    status = "pass" if not failures else "fail"
    manifest = {
        "manifest_type": "homepilot_portal_hosting_pack",
        "created_at": utc_now(),
        "release_label": release_label,
        "status": status,
        "stage_status": "buyer_review_hosting_ready" if status == "pass" else "action_required",
        "production_gate": {
            "verified": False,
            "production_url": production_url or None,
            "blockers": production_blockers,
            "required": "Private hosting/access control, live Auth/RLS proof, hosted browser smoke, and customer access verification before production.",
        },
        "source_portal": {
            "portal_manifest": str(portal_manifest_path),
            "public_dir": str(public_dir),
            "headers": str(headers_path),
            "redirects": str(redirects_path),
            "tenant": portal.get("tenant", {}),
            "modules": portal.get("modules", []),
            "live_runtime_status": portal.get("live_runtime", {}).get("status") if isinstance(portal.get("live_runtime"), dict) else None,
        },
        "publish_policy": {
            "requires_access_control_for_static_snapshot": static_snapshot_present,
            "browser_service_role_allowed": False,
            "runtime_config_no_store": True,
            "exports_no_store": True,
            "provider_configs": ["netlify.toml", "vercel.json"],
        },
        "checks": {
            "portal_status": "pass" if portal.get("status") == "pass" else "fail",
            "public_dir": "pass" if public_dir.exists() else "fail",
            "headers": "pass" if headers_path.exists() else "fail",
            "redirects": "pass" if redirects_path.exists() else "fail",
            "asset_manifest": "pass" if asset_manifest["asset_count"] else "fail",
            "cache_policy": "pass" if cache_policy["rules"] else "fail",
            "secret_scan": "pass" if not secret_findings else "fail",
        },
        "summary": {
            "assets": asset_manifest["asset_count"],
            "total_bytes": asset_manifest["total_bytes"],
            "static_snapshot_present": static_snapshot_present,
            "exports": sum(1 for asset in asset_manifest["assets"] if asset["role"] == "customer_export"),
            "no_store_assets": sum(1 for asset in asset_manifest["assets"] if asset["cache_control"] == "no-store"),
        },
        "paths": {
            "hosting_manifest": str(hosting_manifest_path),
            "runbook": str(runbook_path),
            "asset_manifest": str(asset_manifest_path),
            "cache_policy": str(cache_policy_path),
            "netlify_toml": str(netlify_path),
            "vercel_json": str(vercel_path),
            "deployment_checklist": str(checklist_path),
            "rollback_manifest": str(rollback_path),
        },
        "checklist": checklist,
        "failures": failures,
        "warnings": warnings,
    }

    rollback = {
        "rollback_type": "homepilot_portal_hosting_rollback",
        "release_label": release_label,
        "source_portal_manifest": str(portal_manifest_path),
        "asset_manifest": str(asset_manifest_path),
        "rollback_steps": [
            "Disable public portal route or hosting alias.",
            "Redeploy the previous reviewed portal bundle and asset manifest.",
            "Run browser smoke, access audit, and customer access verification before re-enabling access.",
        ],
    }

    write_json(asset_manifest_path, asset_manifest)
    write_json(cache_policy_path, cache_policy)
    write_text(netlify_path, render_netlify_toml(cache_policy))
    write_text(vercel_path, render_vercel_json(cache_policy))
    write_csv(checklist_path, checklist)
    write_json(rollback_path, rollback)
    write_json(hosting_manifest_path, manifest)
    write_text(runbook_path, render_runbook(manifest))

    output_secret_findings = _scan_files([
        hosting_manifest_path,
        runbook_path,
        asset_manifest_path,
        cache_policy_path,
        netlify_path,
        vercel_path,
        checklist_path,
        rollback_path,
    ])
    if output_secret_findings:
        manifest["status"] = "fail"
        manifest["stage_status"] = "action_required"
        manifest["failures"] = [*manifest["failures"], f"Secret-like values found in hosting artifacts: {output_secret_findings}"]
        manifest["checks"]["secret_scan"] = "fail"
        write_json(hosting_manifest_path, manifest)
        write_text(runbook_path, render_runbook(manifest))

    return {
        "status": manifest["status"],
        "stage_status": manifest["stage_status"],
        "manifest": manifest,
        "paths": manifest["paths"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HomePilot portal hosting evidence")
    parser.add_argument("--portal-manifest", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--release-label", default="local")
    parser.add_argument("--production-url", default="")
    args = parser.parse_args()
    pack = build_hosting_pack(
        portal_manifest_path=args.portal_manifest,
        out_dir=args.out_dir,
        release_label=args.release_label,
        production_url=args.production_url,
    )
    print(json.dumps({
        "output": str(args.out_dir),
        "status": pack["status"],
        "stage_status": pack["stage_status"],
        "hosting_manifest": pack["paths"]["hosting_manifest"],
        "runbook": pack["paths"]["runbook"],
        "production_gate": pack["manifest"]["production_gate"],
        "failures": pack["manifest"]["failures"],
        "warnings": pack["manifest"]["warnings"],
    }, indent=2, ensure_ascii=False))
    if pack["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
